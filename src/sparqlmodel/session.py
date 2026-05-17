"""SPARQLSession persistence layer."""

from __future__ import annotations

from typing import Any

from rdflib import Graph

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.graph import (
    model_to_graph,
    owned_triples_for_subject,
    triples_to_graph,
)
from sparqlmodel.hydration import hydrate_one
from sparqlmodel.model import SPARQLModel
from sparqlmodel.query import Query
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI, NamespaceRegistry


class SPARQLSession:
    """Primary persistence and query interface."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self._store = store or MemoryStore(prefixes=prefixes)
        self._namespaces = NamespaceRegistry(
            {**self._store.namespaces.prefixes, **(prefixes or {})}
        )
        self._namespaces.bind(self._store.graph)

    @property
    def store(self) -> MemoryStore:
        return self._store

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._namespaces

    @property
    def graph(self) -> Graph:
        return self._store.graph

    def add(self, model: SPARQLModel) -> SPARQLModel:
        """Insert model triples into the store (no delete)."""
        model.ensure_id()
        g = model_to_graph(model)
        self._store.update_graph(add=g)
        return model

    def put(self, model: SPARQLModel) -> SPARQLModel:
        """Upsert model: remove owned triples then insert."""
        subject = model.ensure_id()
        remove_g = triples_to_graph(
            owned_triples_for_subject(type(model), subject, self._store.graph)
        )
        add_g = model_to_graph(model)
        self._store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
        return model

    def delete(self, model: SPARQLModel) -> None:
        """Remove owned triples for the model."""
        subject = model.ensure_id()
        remove_g = triples_to_graph(
            owned_triples_for_subject(type(model), subject, self._store.graph)
        )
        if len(remove_g):
            self._store.update_graph(remove=remove_g)

    def get(
        self,
        model_cls: type[SPARQLModel],
        iri: str | IRI,
        *,
        depth: int = 0,
    ) -> SPARQLModel | None:
        """Load a model by IRI with optional relationship depth."""
        if depth < 0 or depth > 2:
            raise ConfigurationError("depth must be 0, 1, or 2")
        return hydrate_one(model_cls, iri, self._store, depth=depth)

    def query(self, model_cls: type[SPARQLModel]) -> Query:
        """Start a fluent query for the given model class."""
        return Query(self, model_cls)

    def execute(self, sparql: str) -> list[dict[str, Any]]:
        """Execute raw SPARQL SELECT."""
        if "PREFIX" not in sparql.upper():
            prefix_block = self._namespaces.sparql_prefixes()
            if prefix_block:
                sparql = f"{prefix_block}\n\n{sparql}"
        return self._store.query(sparql)
