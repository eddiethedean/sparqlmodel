"""Async store protocol for SPARQL backends."""

from __future__ import annotations

from typing import Any, Protocol

from triplemodel import Store

from sparqlmodel.types import NamespaceRegistry


class AsyncStoreProtocol(Protocol):
    """Protocol for async RDF persistence backends."""

    @property
    def graph(self) -> Store:
        """Underlying RDF graph (pyoxigraph via :class:`~triplemodel.Store`)."""

    @property
    def namespaces(self) -> NamespaceRegistry:
        """Prefix registry bound to the store graph."""

    async def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute a SPARQL SELECT query and return bindings."""

    async def update_graph(self, add: Store | None = None, remove: Store | None = None) -> None:
        """Add or remove triples from the store."""

    async def aclose(self) -> None:
        """Release resources (HTTP client, etc.)."""
