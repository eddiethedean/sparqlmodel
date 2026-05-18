"""ORM eager-load: hydrate query results and ``get`` by relationship depth."""

from __future__ import annotations

from typing import Any

from sparqlmodel.exceptions import ConfigurationError, HydrationError
from sparqlmodel.graph import graph_to_model, subject_has_rdf_type
from sparqlmodel.model import SPARQLModel
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI


def _model_var_name(model_cls: type[SPARQLModel]) -> str:
    return model_cls.__name__.lower()


def validate_depth(depth: int) -> None:
    """Raise if hydration depth is outside the supported range (0–2)."""
    if depth < 0 or depth > 2:
        raise ConfigurationError("depth must be 0, 1, or 2")


def hydrate_from_bindings(
    model_cls: type[SPARQLModel],
    bindings: list[dict[str, Any]],
    store: MemoryStore,
    *,
    depth: int = 0,
) -> list[SPARQLModel]:
    """Hydrate models from SPARQL SELECT bindings."""
    validate_depth(depth)
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
            model = hydrate_one(model_cls, IRI(iri_str), store, depth=depth)
            if model is not None:
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
    validate_depth(depth)
    if not subject_has_rdf_type(model_cls, iri, store.graph):
        return None

    return graph_to_model(model_cls, IRI(str(iri)), store.graph, depth=depth)
