"""Store protocol for SPARQL backends."""

from __future__ import annotations

from typing import Any, Protocol

from triplemodel import Store


class StoreProtocol(Protocol):
    """Protocol for RDF persistence backends."""

    @property
    def graph(self) -> Store:
        """Underlying RDF graph (pyoxigraph via :class:`~triplemodel.Store`)."""

    def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute a SPARQL SELECT query and return bindings."""

    def update_graph(self, add: Store | None = None, remove: Store | None = None) -> None:
        """Add or remove triples from the store."""
