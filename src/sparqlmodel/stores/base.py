"""Store protocol for SPARQL backends."""

from __future__ import annotations

from typing import Any, Protocol

from rdflib import Graph


class Store(Protocol):
    """Protocol for RDF persistence backends."""

    @property
    def graph(self) -> Graph:
        """Underlying RDF graph."""

    def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute a SPARQL SELECT query and return bindings."""

    def update_graph(self, add: Graph | None = None, remove: Graph | None = None) -> None:
        """Add or remove triples from the store."""
