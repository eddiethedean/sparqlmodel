"""Model ↔ RDF graph conversion."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.term import Node

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.fields import get_field_metadata
from sparqlmodel.types import IRI, expand_iri

if TYPE_CHECKING:
    from sparqlmodel.model import SPARQLModel

RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")


def _subject_ref(iri: str | IRI, prefixes: dict[str, str]) -> URIRef | BNode:
    expanded = expand_iri(str(iri), prefixes)
    if expanded.startswith("urn:") or expanded.startswith("http"):
        return URIRef(expanded)
    if expanded.startswith("_:"):
        return BNode(expanded[2:])
    return URIRef(expanded)


def _predicate_ref(predicate: str, prefixes: dict[str, str]) -> URIRef:
    return URIRef(expand_iri(predicate, prefixes))


def _object_node(value: Any, prefixes: dict[str, str]) -> Node:
    if isinstance(value, IRI):
        return _subject_ref(value, prefixes)
    if isinstance(value, bool):
        return Literal(value, datatype=URIRef("http://www.w3.org/2001/XMLSchema#boolean"))
    if isinstance(value, int):
        return Literal(value, datatype=URIRef("http://www.w3.org/2001/XMLSchema#integer"))
    if isinstance(value, float):
        return Literal(value, datatype=URIRef("http://www.w3.org/2001/XMLSchema#double"))
    return Literal(str(value))


def model_to_triples(model: SPARQLModel) -> list[tuple[Node, Node, Node]]:
    """Serialize a model instance to RDF triples."""
    from sparqlmodel.model import SPARQLModel

    if not isinstance(model, SPARQLModel):
        raise TypeError("Expected SPARQLModel instance")

    subject_iri = model.ensure_id()
    prefixes = model.get_prefixes()
    subject = _subject_ref(subject_iri, prefixes)
    type_iri = expand_iri(model.rdf_type, prefixes)
    triples: list[tuple[Node, Node, Node]] = [(subject, RDF_TYPE, URIRef(type_iri))]

    for name, field_info in model.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        value = getattr(model, name, None)
        if value is None:
            continue
        pred = _predicate_ref(meta.predicate, prefixes)
        triples.append((subject, pred, _object_node(value, prefixes)))

    for name, field_info, _ in model.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        value = getattr(model, name, None)
        if value is None:
            continue
        if isinstance(value, SPARQLModel):
            pred = _predicate_ref(meta.predicate, prefixes)
            obj = _subject_ref(value.ensure_id(), prefixes)
            triples.append((subject, pred, obj))
            triples.extend(model_to_triples(value))
        elif isinstance(value, IRI):
            pred = _predicate_ref(meta.predicate, prefixes)
            triples.append((subject, pred, _subject_ref(value, prefixes)))

    return triples


def triples_to_graph(triples: Iterable[tuple[Node, Node, Node]]) -> Graph:
    """Build an rdflib Graph from triples."""
    g = Graph()
    for s, p, o in triples:
        g.add((s, p, o))
    return g


def model_to_graph(model: SPARQLModel) -> Graph:
    """Serialize a model to an rdflib Graph."""
    g = Graph()
    registry = model.namespace_registry()
    registry.bind(g)
    for triple in model_to_triples(model):
        g.add(triple)
    return g


def owned_triples_for_subject(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Graph,
) -> list[tuple[Node, Node, Node]]:
    """Return triples owned by a subject for declared predicates + rdf:type."""
    prefixes = model_cls.get_prefixes()
    subject = _subject_ref(subject_iri, prefixes)
    predicates = {_predicate_ref("rdf:type", prefixes)}
    for _, field_info in model_cls.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta:
            predicates.add(_predicate_ref(meta.predicate, prefixes))
    for _, field_info, _ in model_cls.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta:
            predicates.add(_predicate_ref(meta.predicate, prefixes))

    return [(s, p, o) for s, p, o in graph if s == subject and p in predicates]


def load_scalars(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Graph,
) -> dict[str, Any]:
    """Load scalar field values from graph for a subject."""
    prefixes = model_cls.get_prefixes()
    subject = _subject_ref(subject_iri, prefixes)
    data: dict[str, Any] = {"id": IRI(str(subject_iri))}

    for name, field_info in model_cls.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        pred = _predicate_ref(meta.predicate, prefixes)
        values = list(graph.objects(subject, pred))
        if not values:
            continue
        val = values[0]
        if isinstance(val, Literal):
            if val.datatype is not None and "boolean" in str(val.datatype):
                data[name] = bool(val.toPython())
            elif val.datatype is not None and "integer" in str(val.datatype):
                data[name] = int(val.toPython())
            elif val.datatype is not None and "double" in str(val.datatype):
                data[name] = float(val.toPython())
            else:
                data[name] = str(val)
        else:
            data[name] = IRI(str(val))

    return data


def graph_to_model(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Graph,
    *,
    depth: int = 0,
    visited: set[str] | None = None,
) -> SPARQLModel:
    """Hydrate a model from graph data."""

    visited = visited or set()
    subject_key = str(subject_iri)
    if subject_key in visited:
        raise ConfigurationError(f"Cycle detected loading {subject_key}")
    visited.add(subject_key)

    data = load_scalars(model_cls, subject_iri, graph)

    if depth > 0:
        prefixes = model_cls.get_prefixes()
        subject = _subject_ref(subject_iri, prefixes)
        for name, field_info, related_cls in model_cls.get_relationship_fields():
            meta = get_field_metadata(field_info)
            if meta is None:
                continue
            pred = _predicate_ref(meta.predicate, prefixes)
            values = list(graph.objects(subject, pred))
            if not values:
                data[name] = None
                continue
            related_iri = IRI(str(values[0]))
            if depth >= 1:
                data[name] = graph_to_model(
                    related_cls,
                    related_iri,
                    graph,
                    depth=depth - 1,
                    visited=visited.copy(),
                )
            else:
                data[name] = related_iri

    return model_cls.model_validate(data)
