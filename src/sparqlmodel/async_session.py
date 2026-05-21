"""Async ORM unit of work over a graph store (:class:`AsyncSPARQLSession`)."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from triplemodel import Store
from typing_extensions import Self

from sparqlmodel import session_core
from sparqlmodel.async_query import AsyncQuery
from sparqlmodel.graph import (
    cascade_subjects_for_removal,
    owned_triples_for_subjects,
    triples_to_graph,
)
from sparqlmodel.model import SPARQLModel
from sparqlmodel.rdf_bridge import model_to_graph
from sparqlmodel.session_state import SessionState, identity_key_for_iri
from sparqlmodel.stores.async_base import AsyncStoreProtocol
from sparqlmodel.stores.async_memory import AsyncMemoryStore
from sparqlmodel.types import IRI, NamespaceRegistry


class AsyncSPARQLSession:
    """Async ORM session: CRUD, queries, and graph sync with the backing store.

    Use as an async context manager::

        async with AsyncSPARQLSession(store=AsyncHttpStore(endpoint)) as session:
            await session.put(model)

    Same identity map, hydration, and cascade semantics as
    :class:`~sparqlmodel.session.SPARQLSession`.
    Not safe to share across concurrent asyncio tasks; use one session per task.
    """

    def __init__(
        self,
        store: AsyncStoreProtocol | None = None,
        *,
        prefixes: dict[str, str] | None = None,
        autoflush: bool = True,
        close_on_exit: bool = True,
        rollback_on_error: bool = True,
    ) -> None:
        self._store: AsyncStoreProtocol = store or AsyncMemoryStore(prefixes=prefixes)
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
    def store(self) -> AsyncStoreProtocol:
        return self._store

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._namespaces

    @property
    def graph(self) -> Store:
        return self._store.graph

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError(session_core.CLOSED_ASYNC_SESSION_MSG)

    async def flush(self) -> None:
        """Write all pending models queued with ``put(..., flush=False)``."""
        self._check_open()
        pending = list(self._state.pending)
        index = 0
        try:
            while index < len(pending):
                await session_core.put_impl_async(self._store, self._state, pending[index])
                index += 1
        except Exception:
            self._state.clear_pending()
            for model in pending[index:]:
                self._state.add_pending(model)
            raise
        self._state.clear_pending()

    async def rollback_pending(self) -> None:
        """Discard pending models without writing to the store."""
        self._check_open()
        self._state.clear_pending()

    async def close(self) -> None:
        """Close the backing store when it implements ``aclose()``."""
        if self._closed:
            return
        if self._state.pending:
            n = len(self._state.pending)
            raise RuntimeError(
                f"Cannot close AsyncSPARQLSession with {n} pending put(s); "
                "call flush() or rollback_pending() first"
            )
        aclose = getattr(self._store, "aclose", None)
        if callable(aclose):
            await aclose()
        self._closed = True

    async def __aenter__(self) -> Self:
        self._check_open()
        return self

    async def __aexit__(
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
                        await self.flush()
                    except Exception as exc:
                        flush_err = exc
            elif self.rollback_on_error:
                await self.rollback_pending()
        finally:
            if self.close_on_exit:
                try:
                    await self.close()
                except RuntimeError as close_err:
                    if flush_err is not None:
                        raise flush_err from close_err
                    if exc_type is None or self.rollback_on_error:
                        raise
        if flush_err is not None:
            raise flush_err

    async def expire(self, model_cls: type[SPARQLModel], iri: str | IRI) -> None:
        """Remove a resource from the identity map and hydration cache."""
        self._check_open()
        session_core.expire_impl(self._state, model_cls, iri)

    async def expunge(self, model: SPARQLModel) -> None:
        """Detach ``model`` from the identity map and hydration cache (store unchanged)."""
        self._check_open()
        session_core.expunge_impl(self._state, model)

    async def expunge_all(self) -> None:
        """Clear the identity map and hydration cache; pending ``put`` queue is kept."""
        self._check_open()
        session_core.expunge_all_impl(self._state)

    async def refresh(self, model: SPARQLModel, *, depth: int = 0) -> SPARQLModel:
        """Reload ``model`` from the store at ``depth`` (updates cached instance when present)."""
        self._check_open()
        await self._maybe_autoflush()
        return session_core.refresh_impl(self._state, self._store, model, depth=depth)

    async def merge(self, model: SPARQLModel) -> SPARQLModel:
        """Return the session instance for ``model``'s identity key (no store write)."""
        self._check_open()
        await self._maybe_autoflush()
        return session_core.merge_impl(self._state, model)

    async def _maybe_autoflush(self) -> None:
        if self.autoflush and self._state.pending:
            await self.flush()

    async def add(self, model: SPARQLModel) -> SPARQLModel:
        """Insert model triples into the store (no delete)."""
        self._check_open()
        await self._maybe_autoflush()
        model.ensure_id()
        session_core.check_stale_add(self._store.graph, model)
        g = model_to_graph(model)
        await self._store.update_graph(add=g)
        self._state.set_identity(model)
        session_core.invalidate_cascade_keys(self._state, self._store.graph, model, for_put=False)
        return model

    async def put(self, model: SPARQLModel, *, flush: bool = True) -> SPARQLModel:
        """Upsert model and cascaded embedded resources."""
        self._check_open()
        if flush:
            await self._maybe_autoflush()
            return await session_core.put_impl_async(self._store, self._state, model)
        model.ensure_id()
        assert model.id is not None
        session_core.invalidate_cascade_keys(self._state, self._store.graph, model, for_put=True)
        key = identity_key_for_iri(type(model), model.id)
        self._state.evict_identity_prefix(key[0], key[1])
        self._state.add_pending(model)
        self._state.invalidate_hydration_for_iri(key[1])
        return model

    async def delete(self, model: SPARQLModel) -> None:
        """Remove owned triples for the model and cascaded embedded resources."""
        self._check_open()
        await self._maybe_autoflush()
        model.ensure_id()
        subjects = cascade_subjects_for_removal(model, self._store.graph, for_put=False)
        session_core.remove_pending_for_subjects(self._state, subjects)
        session_core.invalidate_cascade_keys(self._state, self._store.graph, model, for_put=False)
        remove_g = triples_to_graph(owned_triples_for_subjects(subjects, self._store.graph))
        if len(remove_g):
            await self._store.update_graph(remove=remove_g)
        self._state.expire_model(model)

    async def get(
        self,
        model_cls: type[SPARQLModel],
        iri: str | IRI,
        *,
        depth: int = 0,
    ) -> SPARQLModel | None:
        """Load a model by IRI with optional relationship depth."""
        self._check_open()
        await self._maybe_autoflush()
        return await session_core.get_impl_async(
            self._state, self._store, model_cls, iri, depth=depth
        )

    async def hydrate_bindings(
        self,
        model_cls: type[SPARQLModel],
        bindings: list[dict[str, Any]],
        *,
        depth: int = 0,
    ) -> list[SPARQLModel]:
        """Hydrate query results with identity map and session cache."""
        self._check_open()
        await self._maybe_autoflush()
        return await session_core.hydrate_bindings_impl_async(
            self._state,
            self._store,
            model_cls,
            bindings,
            depth=depth,
            get_fn=self.get,
        )

    def query(self, model_cls: type[SPARQLModel]) -> AsyncQuery:
        """Start a fluent async query for the given model class."""
        self._check_open()
        return AsyncQuery(self, model_cls)

    async def execute(self, sparql: str) -> list[dict[str, Any]]:
        """Execute raw SPARQL SELECT."""
        self._check_open()
        await self._maybe_autoflush()
        if not session_core.sparql_has_prefix_declarations(sparql):
            prefix_block = self._namespaces.sparql_prefixes()
            if prefix_block:
                sparql = f"{prefix_block}\n\n{sparql}"
        return await self._store.query(sparql)
