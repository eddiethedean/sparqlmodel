"""ORM unit of work over a graph store (:class:`SPARQLSession`)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Any

from triplemodel import Store, load_graph
from typing_extensions import Self

from sparqlmodel import session_core
from sparqlmodel.graph import (
    cascade_subjects_for_removal,
    owned_triples_for_subjects,
    triples_to_graph,
)
from sparqlmodel.model import SPARQLModel
from sparqlmodel.query import Query
from sparqlmodel.rdf_bridge import model_to_graph
from sparqlmodel.serializers import _resolve_rdf_format
from sparqlmodel.session_state import SessionState, identity_key_for_iri
from sparqlmodel.stores.base import StoreProtocol
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI, NamespaceRegistry


class SPARQLSession:
    """ORM session: CRUD, queries, and graph sync with the backing store.

    Use as a context manager to flush pending writes on success, discard the
    pending queue on error, and close the backing store when it supports
    ``HttpStore.close()`` when using :class:`~sparqlmodel.stores.http.HttpStore`::

        with SPARQLSession(store=HttpStore(endpoint)) as session:
            session.put(model)

    Already-flushed writes are not rolled back on error; only the pending queue
    from ``put(..., flush=False)`` is affected. Full transactional rollback may
    be added in a future release.

    Not thread-safe; use one session per thread or asyncio task.
    """

    _relationships_materialized = staticmethod(session_core.relationships_materialized)
    _depth_satisfied = staticmethod(session_core.depth_satisfied)

    def _put_impl(self, model: SPARQLModel) -> SPARQLModel:
        """Backward-compatible hook for tests; delegates to :mod:`session_core`."""
        return session_core.put_impl(self._store, self._state, model)

    def __init__(
        self,
        store: StoreProtocol | None = None,
        *,
        prefixes: dict[str, str] | None = None,
        autoflush: bool = True,
        close_on_exit: bool = True,
        rollback_on_error: bool = True,
    ) -> None:
        self._store: StoreProtocol = store or MemoryStore(prefixes=prefixes)
        store_prefixes = getattr(self._store, "namespaces", None)
        store_pfx = store_prefixes.prefixes if store_prefixes else {}
        merged_prefixes = {**store_pfx, **(prefixes or {})}
        self._namespaces = NamespaceRegistry(merged_prefixes)
        self._namespaces.bind(self._store.graph)
        self._state = SessionState()
        self.autoflush = autoflush
        self.close_on_exit = close_on_exit
        self.rollback_on_error = rollback_on_error
        self._closed = False

    @classmethod
    def from_rdf_file(
        cls,
        path: str | Path,
        *,
        format: str = "turtle",
        prefixes: Mapping[str, str] | None = None,
        autoflush: bool = True,
        close_on_exit: bool = True,
        rollback_on_error: bool = True,
    ) -> Self:
        """Open a session over an on-disk RDF file.

        Uses an in-memory :class:`~sparqlmodel.stores.memory.MemoryStore`. Parses ``path`` with
        TripleModel ``load_graph`` (pass a :class:`~pathlib.Path`, not file
        contents as a string). Use for tutorials, fixtures, and ETL that starts from Turtle,
        TriG, or other supported formats before ``put`` / ``query``.

        Args:
            path: File path to parse.
            format: RDF format hint (e.g. ``\"turtle\"``, ``\"trig\"``); inferred from extension
                when omitted on ``load_graph``.
            prefixes: Namespace prefixes merged into the session registry and graph.
            autoflush: Passed to :meth:`__init__`.
            close_on_exit: Passed to :meth:`__init__`.
            rollback_on_error: Passed to :meth:`__init__`.
        """
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"RDF file not found: {source}")
        fmt = _resolve_rdf_format(format)
        prefix_map = dict(prefixes) if prefixes is not None else None
        graph = load_graph(
            source=source,
            format=fmt,
            bind_prefixes=prefix_map,
        )
        store = MemoryStore(graph=graph, prefixes=prefix_map)
        return cls(
            store=store,
            prefixes=prefix_map,
            autoflush=autoflush,
            close_on_exit=close_on_exit,
            rollback_on_error=rollback_on_error,
        )

    @property
    def store(self) -> StoreProtocol:
        return self._store

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._namespaces

    @property
    def graph(self) -> Store:
        return self._store.graph

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError(session_core.CLOSED_SESSION_MSG)

    def flush(self) -> None:
        """Write all pending models queued with ``put(..., flush=False)``."""
        self._check_open()
        pending = list(self._state.pending)
        index = 0
        try:
            while index < len(pending):
                self._put_impl(pending[index])
                index += 1
        except Exception:
            self._state.clear_pending()
            for model in pending[index:]:
                self._state.add_pending(model)
            raise
        self._state.clear_pending()

    def rollback_pending(self) -> None:
        """Discard pending models without writing to the store."""
        self._check_open()
        self._state.clear_pending()

    def close(self) -> None:
        """Close the backing store when it implements ``close()``."""
        if self._closed:
            return
        if self._state.pending:
            n = len(self._state.pending)
            raise RuntimeError(
                f"Cannot close SPARQLSession with {n} pending put(s); "
                "call flush() or rollback_pending() first"
            )
        close = getattr(self._store, "close", None)
        if callable(close):
            close()
        self._closed = True

    def __enter__(self) -> Self:
        self._check_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        flush_err: BaseException | None = None
        try:
            if exc_type is None:
                if self._state.pending:
                    try:
                        self.flush()
                    except Exception as exc:
                        flush_err = exc
            elif self.rollback_on_error:
                self.rollback_pending()
        finally:
            if self.close_on_exit:
                try:
                    self.close()
                except RuntimeError as close_err:
                    if flush_err is not None:
                        raise flush_err from close_err
                    if exc_type is None or self.rollback_on_error:
                        raise
        if flush_err is not None:
            raise flush_err

    def expire(self, model_cls: type[SPARQLModel], iri: str | IRI) -> None:
        """Remove a resource from the identity map and hydration cache."""
        self._check_open()
        session_core.expire_impl(self._state, model_cls, iri)

    def _maybe_autoflush(self) -> None:
        if self.autoflush and self._state.pending:
            self.flush()

    def add(self, model: SPARQLModel) -> SPARQLModel:
        """Insert model triples into the store (no delete)."""
        self._check_open()
        self._maybe_autoflush()
        model.ensure_id()
        session_core.check_stale_add(self._store.graph, model)
        g = model_to_graph(model)
        self._store.update_graph(add=g)
        self._state.set_identity(model)
        session_core.invalidate_cascade_keys(self._state, self._store.graph, model, for_put=False)
        return model

    def put(self, model: SPARQLModel, *, flush: bool = True) -> SPARQLModel:
        """Upsert model and cascaded embedded resources."""
        self._check_open()
        if flush:
            self._maybe_autoflush()
            return session_core.put_impl(self._store, self._state, model)
        model.ensure_id()
        assert model.id is not None
        session_core.invalidate_cascade_keys(self._state, self._store.graph, model, for_put=True)
        key = identity_key_for_iri(type(model), model.id)
        self._state.evict_identity_prefix(key[0], key[1])
        self._state.add_pending(model)
        self._state.invalidate_hydration_for_iri(key[1])
        return model

    def delete(self, model: SPARQLModel) -> None:
        """Remove owned triples for the model and cascaded embedded resources."""
        self._check_open()
        self._maybe_autoflush()
        model.ensure_id()
        subjects = cascade_subjects_for_removal(model, self._store.graph, for_put=False)
        session_core.remove_pending_for_subjects(self._state, subjects)
        session_core.invalidate_cascade_keys(self._state, self._store.graph, model, for_put=False)
        remove_g = triples_to_graph(owned_triples_for_subjects(subjects, self._store.graph))
        if len(remove_g):
            self._store.update_graph(remove=remove_g)
        self._state.expire_model(model)

    def get(
        self,
        model_cls: type[SPARQLModel],
        iri: str | IRI,
        *,
        depth: int = 0,
    ) -> SPARQLModel | None:
        """Load a model by IRI with optional relationship depth."""
        self._check_open()
        self._maybe_autoflush()
        return session_core.get_impl(self._state, self._store, model_cls, iri, depth=depth)

    def hydrate_bindings(
        self,
        model_cls: type[SPARQLModel],
        bindings: list[dict[str, Any]],
        *,
        depth: int = 0,
    ) -> list[SPARQLModel]:
        """Hydrate query results with identity map and session cache."""
        self._check_open()
        self._maybe_autoflush()
        return session_core.hydrate_bindings_impl(
            self._state,
            self._store,
            model_cls,
            bindings,
            depth=depth,
            get_fn=self.get,
        )

    def query(self, model_cls: type[SPARQLModel]) -> Query:
        """Start a fluent query for the given model class."""
        self._check_open()
        return Query(self, model_cls)

    def execute(self, sparql: str) -> list[dict[str, Any]]:
        """Execute raw SPARQL SELECT."""
        self._check_open()
        self._maybe_autoflush()
        if not session_core.sparql_has_prefix_declarations(sparql):
            prefix_block = self._namespaces.sparql_prefixes()
            if prefix_block:
                sparql = f"{prefix_block}\n\n{sparql}"
        return self._store.query(sparql)
