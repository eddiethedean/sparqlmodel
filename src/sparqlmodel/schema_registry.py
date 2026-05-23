"""Lite ontology hints for polymorphic queries and inverse metadata (TripleModel 0.12+)."""

from __future__ import annotations

from triplemodel import OntologyRegistry, apply_hints_to_model

from sparqlmodel.model import SPARQLModel

SchemaRegistry = OntologyRegistry


def registry_for_model(model_cls: type[SPARQLModel]) -> OntologyRegistry | None:
    """Return ``Rdf.ontology_registry`` when set on a :class:`~sparqlmodel.model.SPARQLModel`."""
    rdf = getattr(model_cls, "Rdf", None)
    reg = getattr(rdf, "ontology_registry", None) if rdf is not None else None
    if isinstance(reg, OntologyRegistry):
        return reg
    return None


def apply_schema_hints(model_cls: type[SPARQLModel], registry: OntologyRegistry) -> None:
    """Apply inverse hints from a registry onto ``model_cls`` (TripleModel helper)."""
    apply_hints_to_model(model_cls, registry)


__all__ = [
    "SchemaRegistry",
    "apply_schema_hints",
    "registry_for_model",
]
