"""ORM unit of work over a graph store (:class:`SPARQLSession`)."""

from __future__ import annotations

import re
from types import TracebackType
from typing import Any, cast

from triplemodel import Store
from typing_extensions import Self

from sparqlmodel.fields import relationship_allows_iri
from sparqlmodel.graph import (
    cascade_subjects_for_removal,
    owned_triples_for_subjects,
    triples_to_graph,
)
from sparqlmodel.hydration import hydrate_one, validate_depth
from sparqlmodel.model import SPARQLModel
from sparqlmodel.query import Query
from sparqlmodel.rdf_bridge import model_to_graph
from sparqlmodel.session_state import (
    _HYDRATION_MISS,
    SessionState,
    identity_key_for_iri,
)
from sparqlmodel.stores.base import StoreProtocol
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI, NamespaceRegistry

_CLOSED_SESSION_MSG = "Cannot use a closed SPARQLSession"
_PREFIX_DECL_RE = re.compile(r"^\s*PREFIX\b", re.IGNORECASE | re.MULTILINE)


def _sparql_has_prefix_declarations(sparql: str) -> bool:
    """Return True if ``sparql`` already declares at least one PREFIX."""
    return _PREFIX_DECL_RE.search(sparql) is not None


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
    """

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
            raise RuntimeError(_CLOSED_SESSION_MSG)

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
        self._closed = True
        close = getattr(self._store, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> Self:
        self._check_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                if self._state.pending:
                    self.flush()
            elif self.rollback_on_error:
                self.rollback_pending()
        finally:
            if self.close_on_exit:
                try:
                    self.close()
                except RuntimeError:
                    if exc_type is not None and not self.rollback_on_error:
                        return
                    raise

    def expire(self, model_cls: type[SPARQLModel], iri: str | IRI) -> None:
        """Remove a resource from the identity map and hydration cache."""
        self._check_open()
        key = identity_key_for_iri(model_cls, iri)
        self._state.evict_identity_prefix(key[0], key[1])
        self._state.invalidate_hydration_for(key[0], key[1])
        self._state.remove_pending_for(key[0], key[1])

    @staticmethod
    def _relationships_materialized(model: SPARQLModel) -> bool:
        for name, _field_info, _related in model.get_relationship_fields():
            if isinstance(getattr(model, name, None), SPARQLModel):
                return True
        return False

    @staticmethod
    def _depth_satisfied(model: SPARQLModel, depth: int) -> bool:
        """Return whether ``model`` has relationships loaded through ``depth``."""
        if depth <= 0:
            return True
        rel_fields = list(model.get_relationship_fields())
        if depth == 1:
            if not rel_fields:
                return True
            return SPARQLSession._relationships_materialized(model)
        for name, field_info, _related_cls in rel_fields:
            value = getattr(model, name, None)
            if value is None:
                continue
            if isinstance(value, IRI):
                if relationship_allows_iri(field_info.annotation):
                    continue
                return False
            if not isinstance(value, SPARQLModel):
                return False
            if not SPARQLSession._depth_satisfied(value, depth - 1):
                return False
        return True

    def _maybe_autoflush(self) -> None:
        if self.autoflush and self._state.pending:
            self.flush()

    def _invalidate_cascade_keys(self, model: SPARQLModel, *, for_put: bool) -> None:
        subjects = cascade_subjects_for_removal(model, self._store.graph, for_put=for_put)
        keys = [identity_key_for_iri(cls, iri) for cls, iri in subjects]
        self._state.expire_keys(keys)

    def _put_impl(self, model: SPARQLModel) -> SPARQLModel:
        model.ensure_id()
        subjects = cascade_subjects_for_removal(model, self._store.graph, for_put=True)
        remove_g = triples_to_graph(owned_triples_for_subjects(subjects, self._store.graph))
        add_g = model_to_graph(model)
        self._store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
        self._invalidate_cascade_keys(model, for_put=True)
        self._state.set_identity(model)
        return model

    def add(self, model: SPARQLModel) -> SPARQLModel:
        """Insert model triples into the store (no delete)."""
        self._check_open()
        self._maybe_autoflush()
        model.ensure_id()
        self._check_stale_add(model)
        g = model_to_graph(model)
        self._store.update_graph(add=g)
        self._state.set_identity(model)
        self._invalidate_cascade_keys(model, for_put=False)
        return model

    def put(self, model: SPARQLModel, *, flush: bool = True) -> SPARQLModel:
        """Upsert model and cascaded embedded resources."""
        self._check_open()
        if flush:
            self._maybe_autoflush()
            return self._put_impl(model)
        model.ensure_id()
        assert model.id is not None
        self._invalidate_cascade_keys(model, for_put=True)
        key = identity_key_for_iri(type(model), model.id)
        self._state.evict_identity_prefix(key[0], key[1])
        self._state.add_pending(model)
        self._state.invalidate_hydration_for(key[0], key[1])
        return model

    def delete(self, model: SPARQLModel) -> None:
        """Remove owned triples for the model and cascaded embedded resources."""
        self._check_open()
        self._maybe_autoflush()
        model.ensure_id()
        self._invalidate_cascade_keys(model, for_put=False)
        subjects = cascade_subjects_for_removal(model, self._store.graph, for_put=False)
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
        validate_depth(depth)
        id_key = identity_key_for_iri(model_cls, iri)
        hkey = (model_cls, id_key[1], depth)
        hydrated = self._state.get_hydration(hkey)
        if hydrated is not _HYDRATION_MISS:
            return cast("SPARQLModel | None", hydrated)

        identity = self._state.get_identity(id_key)
        if identity is not None and self._depth_satisfied(identity, depth):
            if depth == 0 and self._relationships_materialized(identity):
                pass  # re-hydrate shallow even when identity is eager-loaded
            else:
                self._state.set_hydration(hkey, identity)
                return identity

        model = hydrate_one(model_cls, iri, self._store, depth=depth)
        if model is not None:
            existing = self._state.get_identity(id_key)
            if existing is None or depth > 0 or not self._relationships_materialized(existing):
                self._state.set_identity(model)
            self._state.set_hydration(hkey, model)
        else:
            self._state.set_hydration(hkey, model)
        return model

    def hydrate_bindings(
        self,
        model_cls: type[SPARQLModel],
        bindings: list[dict[str, Any]],
        *,
        depth: int = 0,
    ) -> list[SPARQLModel]:
        """Hydrate query results with identity map and session cache."""
        self._check_open()
        validate_depth(depth)
        results: list[SPARQLModel] = []
        seen: set[str] = set()
        var_name = model_cls.__name__.lower()

        for binding in bindings:
            iri_value = binding.get(var_name) or binding.get(f"?{var_name}")
            if iri_value is None:
                for key, val in binding.items():
                    if key.lstrip("?") == var_name:
                        iri_value = val
                        break
            if iri_value is None:
                continue
            iri_str = str(iri_value)
            if iri_str in seen:
                continue
            seen.add(iri_str)
            model = self.get(model_cls, IRI(iri_str), depth=depth)
            if model is not None:
                results.append(model)
        return results

    def query(self, model_cls: type[SPARQLModel]) -> Query:
        """Start a fluent query for the given model class."""
        self._check_open()
        return Query(self, model_cls)

    def execute(self, sparql: str) -> list[dict[str, Any]]:
        """Execute raw SPARQL SELECT."""
        self._check_open()
        self._maybe_autoflush()
        if not _sparql_has_prefix_declarations(sparql):
            prefix_block = self._namespaces.sparql_prefixes()
            if prefix_block:
                sparql = f"{prefix_block}\n\n{sparql}"
        return self._store.query(sparql)

    def _check_stale_add(self, model: SPARQLModel) -> None:
        """Warn when ``add`` may duplicate triples for an existing subject."""
        import warnings

        from sparqlmodel.exceptions import StaleTripleWarning

        model.ensure_id()
        subject = model.id
        assert subject is not None
        from sparqlmodel.graph import _predicate_pattern, _subject_pattern

        prefixes = model.get_prefixes()
        subj_ref = _subject_pattern(subject, prefixes)
        if not any(self._store.graph.triples((subj_ref, None, None))):
            return
        for _name, field_info in model.get_scalar_fields():
            from sparqlmodel.fields import get_field_metadata

            meta = get_field_metadata(field_info)
            if meta is None:
                continue
            pred = _predicate_pattern(meta.predicate, prefixes)
            if any(self._store.graph.triples((subj_ref, pred, None))):
                warnings.warn(
                    f"add() on {type(model).__name__} subject {subject!s} may leave stale "
                    f"triples for predicate {meta.predicate!r}; use put() for upsert.",
                    StaleTripleWarning,
                    stacklevel=2,
                )
                return
