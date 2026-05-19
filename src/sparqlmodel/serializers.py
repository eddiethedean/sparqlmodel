"""Optional RDF export (interim); prefer TripleModel parse/serialize. Not required for the ORM."""

from __future__ import annotations

from typing import Any, TypeVar, get_args, get_origin

from rdflib import Graph

from sparqlmodel._triple import model_to_graph
from sparqlmodel.fields import get_field_metadata
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import IRI, compact_iri, expand_iri

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


def _annotation_allows_iri(annotation: Any) -> bool:
    """Return True if the field annotation includes ``IRI``."""
    if annotation is IRI:
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    return any(arg is IRI for arg in get_args(annotation))


def _is_jsonld_reference_node(data: dict[str, Any]) -> bool:
    """True when ``data`` is a bare JSON-LD node reference (``@id`` only)."""
    keys = set(data.keys()) - {"@context"}
    return keys <= {"@id", "id"} and ("@id" in data or "id" in data)


def _jsonld_scalar_value(
    value: Any,
    field_info: Any,
    prefixes: dict[str, str],
) -> Any:
    """Coerce a JSON-LD scalar value for ``model_validate``."""
    if (
        isinstance(value, dict)
        and _is_jsonld_reference_node(value)
        and _annotation_allows_iri(field_info.annotation)
    ):
        ref_id = value.get("@id", value.get("id"))
        ref_str = str(ref_id)
        if ref_str.startswith(("http", "urn:")):
            return IRI(compact_iri(ref_str, prefixes))
        return IRI(ref_str)
    return value


def _jsonld_node_body(
    model: SPARQLModel,
    *,
    visited: set[str],
) -> dict[str, Any]:
    """Build JSON-LD node fields (excluding ``@context``) for ``model``."""
    prefixes = model.get_prefixes()
    model.ensure_id()
    subject_key = expand_iri(str(model.id), prefixes)
    if subject_key in visited:
        return {"@id": subject_key}
    visited.add(subject_key)

    node: dict[str, Any] = {
        "@id": subject_key,
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
        if isinstance(value, IRI):
            node[key] = {"@id": expand_iri(str(value), prefixes)}
        else:
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
            if meta.cascade:
                node[key] = _jsonld_node_body(value, visited=visited)
        elif isinstance(value, IRI):
            node[key] = {"@id": expand_iri(str(value), prefixes)}

    return node


def model_to_jsonld(model: SPARQLModel) -> dict[str, Any]:
    """Convert a model to a JSON-LD document."""
    prefixes = model.get_prefixes()
    ctx: dict[str, Any] = {"@context": dict(prefixes)}
    node = _jsonld_node_body(model, visited=set())
    return {**ctx, **node}


def model_from_jsonld(model_cls: type[T], data: dict[str, Any]) -> T:
    """Deserialize a model from JSON-LD."""
    prefixes = {**model_cls.get_prefixes()}
    context = data.get("@context", {})
    if isinstance(context, dict):
        prefixes.update({k: v for k, v in context.items() if isinstance(v, str)})

    raw_type = data.get("@type")
    if raw_type is not None:
        if isinstance(raw_type, list):
            if not raw_type:
                raise ValueError("JSON-LD @type list cannot be empty")
            type_str = str(raw_type[0])
        else:
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
    if raw_id_str.startswith(("http", "urn:")):
        model_id = IRI(compact_iri(raw_id_str, prefixes))
    else:
        model_id = IRI(raw_id_str)

    kwargs: dict[str, Any] = {"id": model_id}

    for name, field_info in model_cls.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        expanded = expand_iri(meta.predicate, prefixes)
        raw: Any | None = None
        if expanded in data:
            raw = data[expanded]
        elif meta.predicate in data:
            raw = data[meta.predicate]
        if raw is not None:
            kwargs[name] = _jsonld_scalar_value(raw, field_info, prefixes)

    for name, field_info, related_cls in model_cls.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        expanded = expand_iri(meta.predicate, prefixes)
        rel_data = data.get(expanded) or data.get(meta.predicate)
        if rel_data is None:
            continue
        if isinstance(rel_data, list):
            if not rel_data:
                continue
            rel_data = rel_data[0]
        if isinstance(rel_data, dict):
            if _is_jsonld_reference_node(rel_data) and _annotation_allows_iri(
                field_info.annotation
            ):
                ref_id = rel_data.get("@id", rel_data.get("id"))
                ref_str = str(ref_id)
                if ref_str.startswith(("http", "urn:")):
                    kwargs[name] = IRI(compact_iri(ref_str, prefixes))
                else:
                    kwargs[name] = IRI(ref_str)
            else:
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
