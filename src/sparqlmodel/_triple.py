"""Adapter between :class:`~sparqlmodel.model.SPARQLModel` and TripleModel."""

from __future__ import annotations

from typing import Annotated, Any, Union, get_args, get_origin

from rdflib import Graph, Literal, URIRef
from triplemodel import IriId, TripleModel, rdf_field, sync_to_graph

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.fields import get_field_metadata
from sparqlmodel.graph import iter_nested_models, subject_has_rdf_type
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import IRI, expand_iri

_TRIPLE_CLASS_CACHE: dict[type[SPARQLModel], type[TripleModel]] = {}


def _expanded_iri_key(iri: str | IRI, prefixes: dict[str, str]) -> str:
    return expand_iri(str(iri), prefixes)


def _annotation_label(annotation: Any) -> str:
    if annotation is str:
        return "str"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is bool:
        return "bool"
    origin = get_origin(annotation)
    from types import UnionType

    if origin in (Union, UnionType):
        args = get_args(annotation)
        parts = [_annotation_label(a) for a in args if a is not type(None)]
        return " | ".join(parts) + (" | None" if type(None) in args else "")
    if isinstance(annotation, type) and issubclass(annotation, SPARQLModel):
        return triple_model_class_for(annotation).__name__
    return "Any"


def _build_class_source(model_cls: type[SPARQLModel]) -> str:
    prefixes = model_cls.get_prefixes()
    type_uri = expand_iri(model_cls.rdf_type, prefixes)
    class_name = f"_{model_cls.__name__}Triple"

    lines = [
        "from __future__ import annotations",
        f"class {class_name}(TripleModel):",
        "    class Rdf:",
        f"        type_uri = {type_uri!r}",
        "        id_field = 'id'",
        f"        prefixes = {prefixes!r}",
        "        namespace = 'urn:sparqlmodel:unused/'",
        "        embed = 'iri'",
        "    id: Annotated[str, IriId()]",
    ]

    for name, field_info in model_cls.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        pred = expand_iri(meta.predicate, prefixes)
        ann = _annotation_label(field_info.annotation)
        lines.append(f"    {name}: {ann} = rdf_field({pred!r}, default=None)")

    for name, field_info, _related_cls in model_cls.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        pred = expand_iri(meta.predicate, prefixes)
        lines.append(f"    {name}: str | None = rdf_field({pred!r}, default=None)")

    return "\n".join(lines)


def triple_model_class_for(model_cls: type[SPARQLModel]) -> type[TripleModel]:
    """Return a cached TripleModel subclass mapped from ``model_cls`` metadata."""
    cached = _TRIPLE_CLASS_CACHE.get(model_cls)
    if cached is not None:
        return cached

    for _name, _field_info, related_cls in model_cls.get_relationship_fields():
        triple_model_class_for(related_cls)

    source = _build_class_source(model_cls)
    class_name = f"_{model_cls.__name__}Triple"
    namespace: dict[str, Any] = {
        "TripleModel": TripleModel,
        "IriId": IriId,
        "Annotated": Annotated,
        "rdf_field": rdf_field,
    }
    for _name, _field_info, related_cls in model_cls.get_relationship_fields():
        namespace[f"_{related_cls.__name__}Triple"] = triple_model_class_for(related_cls)

    exec(source, namespace)  # noqa: S102
    triple_cls = namespace[class_name]
    triple_cls.model_rebuild(_types_namespace=namespace)
    _TRIPLE_CLASS_CACHE[model_cls] = triple_cls
    return triple_cls


def _assert_no_embed_cycles(
    instance: SPARQLModel,
    visited: set[str],
) -> None:
    """Raise if nested ``SPARQLModel`` embeds form a cycle (shared leaves are allowed)."""
    from sparqlmodel.model import SPARQLModel as _SPARQLModel

    prefixes = instance.get_prefixes()
    subject_key = _expanded_iri_key(instance.ensure_id(), prefixes)
    if subject_key in visited:
        raise ConfigurationError(f"Cycle detected serializing {subject_key}")
    path = visited | {subject_key}
    for name, field_info, _related_cls in instance.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is not None and not meta.cascade:
            continue
        value = getattr(instance, name, None)
        if isinstance(value, _SPARQLModel):
            _assert_no_embed_cycles(value, path.copy())


def to_triplemodel(
    instance: SPARQLModel,
    *,
    visited: set[str] | None = None,
) -> TripleModel:
    """Convert a SPARQLModel instance to a dynamically mapped TripleModel."""
    from sparqlmodel.model import SPARQLModel as _SPARQLModel

    if not isinstance(instance, _SPARQLModel):
        raise TypeError("Expected SPARQLModel instance")

    _assert_no_embed_cycles(instance, visited or set())

    tm_cls = triple_model_class_for(type(instance))
    data: dict[str, Any] = {"id": str(instance.ensure_id())}

    for name, _field_info in instance.get_scalar_fields():
        value = getattr(instance, name, None)
        if value is not None:
            data[name] = value

    for name, _field_info, _related_cls in instance.get_relationship_fields():
        value = getattr(instance, name, None)
        if value is None:
            data[name] = None
        elif isinstance(value, (IRI, _SPARQLModel)):
            data[name] = str(value if isinstance(value, IRI) else value.ensure_id())
        else:
            data[name] = value

    return tm_cls.model_validate(data)


def _tm_to_sparqlmodel(
    tm: TripleModel,
    sparql_cls: type[SPARQLModel],
    graph: Graph,
    *,
    depth: int,
    visited: set[str],
) -> SPARQLModel:
    """Map a loaded TripleModel instance to SPARQLModel with relationship depth."""
    data: dict[str, Any] = {"id": IRI(tm.subject_uri())}

    for name, _field_info in sparql_cls.get_scalar_fields():
        if hasattr(tm, name):
            value = getattr(tm, name)
            if value is not None:
                data[name] = value

    if depth > 0:
        for name, _field_info, related_cls in sparql_cls.get_relationship_fields():
            if not hasattr(tm, name):
                continue
            value = getattr(tm, name)
            if value is None:
                data[name] = None
            elif isinstance(value, str) and (
                value.startswith("http://")
                or value.startswith("https://")
                or value.startswith("urn:")
                or value.startswith("_:")
            ):
                if subject_has_rdf_type(related_cls, value, graph):
                    data[name] = sparql_from_graph(
                        related_cls,
                        value,
                        graph,
                        depth=depth - 1,
                        visited=visited,
                    )
                else:
                    data[name] = None
            else:
                data[name] = None

    return sparql_cls.model_validate(data)


def sparql_from_graph(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Graph,
    *,
    depth: int = 0,
    visited: set[str] | None = None,
) -> SPARQLModel:
    """Hydrate a SPARQLModel from graph data via TripleModel ``from_graph``."""
    visited = visited or set()
    prefixes = model_cls.get_prefixes()
    subject_key = _expanded_iri_key(subject_iri, prefixes)
    if subject_key in visited:
        raise ConfigurationError(f"Cycle detected loading {subject_key}")
    visited.add(subject_key)

    tm_cls = triple_model_class_for(model_cls)
    uri = expand_iri(str(subject_iri), prefixes)
    tm = tm_cls.from_graph(graph, uri, validate_type=True, on_duplicate="warn")
    return _tm_to_sparqlmodel(tm, model_cls, graph, depth=depth, visited=visited)


def from_triplemodel(
    tm: TripleModel,
    graph: Graph,
    *,
    sparql_cls: type[SPARQLModel],
    depth: int = 0,
) -> SPARQLModel:
    """Hydrate a SPARQLModel from an existing TripleModel instance."""
    return _tm_to_sparqlmodel(tm, sparql_cls, graph, depth=depth, visited=set())


def adapter_graph(root: SPARQLModel) -> Graph:
    """Build an rdflib graph via TripleModel ``sync_to_graph`` for nested cascade models."""
    g = Graph()
    for nested in iter_nested_models(root):
        tm = to_triplemodel(nested)
        sync_to_graph(tm, g, uri=str(nested.ensure_id()), mode="replace")
    return g


def model_to_graph(model: SPARQLModel) -> Graph:
    """Serialize a model to an rdflib Graph (TripleModel ``sync_to_graph``)."""
    g = _normalize_graph(adapter_graph(model))
    model.namespace_registry().bind(g)
    return g


_XSD_STRING = URIRef("http://www.w3.org/2001/XMLSchema#string")


def _normalize_graph(graph: Graph) -> Graph:
    """Normalize XSD string literals to plain literals for comparison."""
    normalized = Graph()
    for subject, pred, obj in graph:
        if isinstance(obj, Literal) and obj.datatype == _XSD_STRING:
            normalized.add((subject, pred, Literal(str(obj))))
        else:
            normalized.add((subject, pred, obj))
    return normalized


def graphs_isomorphic(left: Graph, right: Graph) -> bool:
    """Return whether two graphs are isomorphic (after literal normalization)."""
    return _normalize_graph(left).isomorphic(_normalize_graph(right))


def assert_put_graph_contract(root: SPARQLModel) -> None:
    """Raise AssertionError if the adapter graph is empty for a model with data."""
    g = adapter_graph(root)
    if len(g) == 0 and root.id is not None:
        raise AssertionError(f"Adapter graph empty for {type(root).__name__}")
