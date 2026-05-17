"""Hydrate SPARQL query results into typed models."""

from __future__ import annotations

from typing import Any

from rdflib import RDF

from sparqlmodel.exceptions import HydrationError
from sparqlmodel.graph import _subject_ref, graph_to_model
from sparqlmodel.model import SPARQLModel
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI


def _model_var_name(model_cls: type[SPARQLModel]) -> str:
    return model_cls.__name__.lower()


def hydrate_from_bindings(
    model_cls: type[SPARQLModel],
    bindings: list[dict[str, Any]],
    store: MemoryStore,
    *,
    depth: int = 0,
) -> list[SPARQLModel]:
    """Hydrate models from SPARQL SELECT bindings."""
    results: list[SPARQLModel] = []
    seen: set[str] = set()
    var_name = _model_var_name(model_cls).lstrip("?")

    for binding in bindings:
        iri_value = binding.get(var_name)
        if iri_value is None:
            iri_value = binding.get(f"?{var_name}")
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
        try:
            model = graph_to_model(
                model_cls,
                IRI(iri_str),
                store.graph,
                depth=depth,
            )
            results.append(model)
        except Exception as exc:
            raise HydrationError(f"Failed to hydrate {iri_str}: {exc}") from exc

    return results


def hydrate_one(
    model_cls: type[SPARQLModel],
    iri: str | IRI,
    store: MemoryStore,
    *,
    depth: int = 0,
) -> SPARQLModel | None:
    """Load a single model by IRI from the store."""
    prefixes = model_cls.get_prefixes()
    subject = _subject_ref(iri, prefixes)
    types = list(store.graph.objects(subject, RDF.type))
    if not types:
        return None
    expected = model_cls.namespace_registry().expand(model_cls.rdf_type)
    if str(types[0]) != expected:
        return None

    return graph_to_model(model_cls, IRI(str(iri)), store.graph, depth=depth)
