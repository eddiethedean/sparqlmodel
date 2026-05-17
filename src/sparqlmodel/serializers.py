"""RDF and JSON-LD serialization."""

from __future__ import annotations

from typing import Any, TypeVar

from rdflib import Graph

from sparqlmodel.fields import get_field_metadata
from sparqlmodel.graph import model_to_graph
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import IRI, expand_iri

T = TypeVar("T", bound=SPARQLModel)

SUPPORTED_FORMATS = frozenset({"turtle", "ttl", "nt", "ntriples", "xml", "json-ld", "jsonld"})


def export_graph(graph: Graph, format: str = "turtle") -> str:
    """Serialize an rdflib Graph to a string."""
    fmt = _normalize_format(format)
    return graph.serialize(format=fmt)


def import_graph(data: str, format: str = "turtle") -> Graph:
    """Parse RDF data into an rdflib Graph."""
    g = Graph()
    fmt = _normalize_format(format)
    g.parse(data=data, format=fmt)
    return g


def export_model(model: SPARQLModel, format: str = "turtle") -> str:
    """Serialize a model instance to RDF."""
    return export_graph(model_to_graph(model), format)


def model_to_jsonld(model: SPARQLModel) -> dict[str, Any]:
    """Convert a model to a JSON-LD document."""
    prefixes = model.get_prefixes()
    ctx: dict[str, Any] = {"@context": dict(prefixes)}
    node: dict[str, Any] = {
        "@id": expand_iri(str(model.id), prefixes),
        "@type": expand_iri(model.rdf_type, prefixes),
    }

    for name, field_info in model.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        value = getattr(model, name, None)
        if value is None:
            continue
        key = expand_iri(meta.predicate, prefixes)
        node[key] = value

    for name, field_info, _ in model.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        value = getattr(model, name, None)
        if value is None:
            continue
        key = expand_iri(meta.predicate, prefixes)
        if isinstance(value, SPARQLModel):
            node[key] = model_to_jsonld(value)
        elif isinstance(value, IRI):
            node[key] = {"@id": expand_iri(str(value), prefixes)}

    return {**ctx, **node}


def model_from_jsonld(model_cls: type[T], data: dict[str, Any]) -> T:
    """Deserialize a model from JSON-LD."""
    prefixes = {**model_cls.get_prefixes()}
    context = data.get("@context", {})
    if isinstance(context, dict):
        prefixes.update({k: v for k, v in context.items() if isinstance(v, str)})

    from sparqlmodel.types import compact_iri

    raw_type = data.get("@type")
    if raw_type is not None:
        type_str = str(raw_type)
        if type_str.startswith("http"):
            type_str = compact_iri(type_str, prefixes)
        expected = expand_iri(model_cls.rdf_type, prefixes)
        actual = expand_iri(type_str, prefixes)
        if actual != expected:
            raise ValueError(
                f"JSON-LD @type {type_str!r} does not match {model_cls.__name__} "
                f"(expected {model_cls.rdf_type!r})"
            )

    raw_id = data.get("@id", data.get("id"))
    if raw_id is None:
        raise ValueError("JSON-LD document must contain @id")
    raw_id_str = str(raw_id)
    if raw_id_str.startswith("http"):
        model_id = IRI(compact_iri(raw_id_str, prefixes))
    else:
        model_id = IRI(raw_id_str)

    kwargs: dict[str, Any] = {"id": model_id}

    for name, field_info in model_cls.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        expanded = expand_iri(meta.predicate, prefixes)
        if expanded in data:
            kwargs[name] = data[expanded]
        elif meta.predicate in data:
            kwargs[name] = data[meta.predicate]

    for name, field_info, related_cls in model_cls.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        expanded = expand_iri(meta.predicate, prefixes)
        rel_data = data.get(expanded) or data.get(meta.predicate)
        if rel_data is None:
            continue
        if isinstance(rel_data, dict):
            child_doc: dict[str, Any] = dict(rel_data)
            if "@context" not in child_doc:
                child_doc["@context"] = prefixes
            kwargs[name] = model_from_jsonld(related_cls, child_doc)
        else:
            kwargs[name] = IRI(str(rel_data))

    return model_cls.model_validate(kwargs)


def _normalize_format(format: str) -> str:
    fmt = format.lower().replace("_", "-")
    mapping = {
        "ttl": "turtle",
        "nt": "nt",
        "ntriples": "nt",
        "jsonld": "json-ld",
    }
    normalized = mapping.get(fmt, fmt)
    if normalized not in SUPPORTED_FORMATS and fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {format}")
    return normalized
