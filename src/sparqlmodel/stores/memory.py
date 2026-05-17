"""In-memory RDF store backed by rdflib."""

from __future__ import annotations

from typing import Any

from rdflib import Graph
from rdflib.query import ResultRow

from sparqlmodel.exceptions import QueryError
from sparqlmodel.types import NamespaceRegistry


class MemoryStore:
    """In-memory RDF store using an rdflib Graph."""

    def __init__(
        self,
        graph: Graph | None = None,
        *,
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self._graph = graph or Graph()
        self._registry = NamespaceRegistry(prefixes)
        self._registry.bind(self._graph)

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._registry

    def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute SPARQL SELECT and return variable bindings."""
        try:
            result = self._graph.query(sparql)
        except Exception as exc:
            raise QueryError(f"SPARQL query failed: {exc}") from exc

        if result.type != "SELECT":
            raise QueryError(f"Expected SELECT query, got {result.type}")

        bindings: list[dict[str, Any]] = []
        for row in result:
            if isinstance(row, ResultRow):
                bindings.append({str(k): _term_value(row[k]) for k in row.labels})
        return bindings

    def update_graph(self, add: Graph | None = None, remove: Graph | None = None) -> None:
        """Add or remove triples."""
        if remove is not None:
            for triple in remove:
                self._graph.remove(triple)
        if add is not None:
            for triple in add:
                self._graph.add(triple)


def _term_value(term: Any) -> Any:
    if term is None:
        return None
    return str(term)
