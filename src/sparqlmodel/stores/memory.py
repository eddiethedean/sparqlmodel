"""In-memory RDF store backed by pyoxigraph (``triplemodel.Store``)."""

from __future__ import annotations

from typing import Any

from pyoxigraph import BlankNode, Literal, NamedNode
from triplemodel import Store
from triplemodel.store.sparql_result import SparqlResult

from sparqlmodel.exceptions import QueryError
from sparqlmodel.types import NamespaceRegistry


class MemoryStore:
    """In-memory RDF store using :class:`~triplemodel.Store`."""

    def __init__(
        self,
        graph: Store | None = None,
        *,
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self._graph = graph or Store()
        self._registry = NamespaceRegistry(prefixes)
        self._registry.bind(self._graph)

    @property
    def graph(self) -> Store:
        return self._graph

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._registry

    @property
    def mirror_generation(self) -> int:
        """Monotonic counter; ``0`` for in-memory stores (no wholesale mirror sync)."""
        return 0

    def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute SPARQL SELECT and return variable bindings."""
        try:
            result = self._graph.query(sparql)
        except Exception as exc:
            raise QueryError(f"SPARQL query failed: {exc}") from exc

        if not isinstance(result, SparqlResult):
            raise QueryError(f"Unexpected SPARQL result type: {type(result).__name__}")
        if result.type not in ("SELECT", "bindings"):
            raise QueryError(f"Expected SELECT query, got {result.type}")

        bindings: list[dict[str, Any]] = []
        for row in result:
            if not hasattr(row, "keys"):
                continue
            bindings.append({str(var): _term_value(row[var]) for var in row})
        return bindings

    def update_graph(self, add: Store | None = None, remove: Store | None = None) -> None:
        """Add or remove triples."""
        if remove is not None:
            for triple in remove:
                self._graph.remove(triple)
        if add is not None:
            for triple in add:
                self._graph.add(triple)


def _term_value(term: object) -> Any:
    if term is None:
        return None
    if isinstance(term, NamedNode):
        return term.value
    if isinstance(term, BlankNode):
        raw = str(term)
        return raw if raw.startswith("_:") else f"_:{raw}"
    if isinstance(term, Literal):
        return str(term.value)
    return str(term)
