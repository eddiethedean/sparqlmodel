"""In-memory async RDF store (sync graph, async API surface)."""

from __future__ import annotations

from typing import Any

from triplemodel import Store

from sparqlmodel.stores.memory import MemoryStore


class AsyncMemoryStore:
    """In-memory RDF store with async methods delegating to :class:`~MemoryStore`."""

    def __init__(
        self,
        graph: Store | None = None,
        *,
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self._inner = MemoryStore(graph=graph, prefixes=prefixes)

    @property
    def graph(self) -> Store:
        return self._inner.graph

    @property
    def namespaces(self):
        return self._inner.namespaces

    async def query(self, sparql: str) -> list[dict[str, Any]]:
        return self._inner.query(sparql)

    async def update_graph(self, add: Store | None = None, remove: Store | None = None) -> None:
        self._inner.update_graph(add=add, remove=remove)

    async def aclose(self) -> None:
        return None
