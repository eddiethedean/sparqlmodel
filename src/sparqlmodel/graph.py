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


def _expanded_iri_key(iri: str | IRI, prefixes: dict[str, str]) -> str:
    """Canonical expanded IRI string for set lookups and cycle detection."""
    return expand_iri(str(iri), prefixes)


def subject_has_rdf_type(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Graph,
) -> bool:
    """Return True if the graph subject has the expected ``rdf:type`` for ``model_cls``."""
    prefixes = model_cls.get_prefixes()
    subject = _subject_ref(subject_iri, prefixes)
    types = list(graph.objects(subject, RDF_TYPE))
    if not types:
        return False
    expected = expand_iri(model_cls.rdf_type, prefixes)
    return any(str(t) == expected for t in types)


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


def model_to_triples(
    model: SPARQLModel,
    *,
    visited: set[str] | None = None,
) -> list[tuple[Node, Node, Node]]:
    """Serialize a model instance to RDF triples."""
    from sparqlmodel.model import SPARQLModel

    if not isinstance(model, SPARQLModel):
        raise TypeError("Expected SPARQLModel instance")

    visited = visited or set()
    subject_iri = model.ensure_id()
    prefixes = model.get_prefixes()
    subject_key = _expanded_iri_key(subject_iri, prefixes)
    if subject_key in visited:
        raise ConfigurationError(f"Cycle detected serializing {subject_key}")
    visited.add(subject_key)
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
            triples.extend(model_to_triples(value, visited=visited.copy()))
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


def iter_nested_models(root: SPARQLModel) -> list[SPARQLModel]:
    """Return root and embedded ``SPARQLModel`` instances (composition tree)."""
    from sparqlmodel.model import SPARQLModel

    visited: set[str] = set()
    models: list[SPARQLModel] = []

    def walk(model: SPARQLModel) -> None:
        prefixes = model.get_prefixes()
        iri = _expanded_iri_key(model.ensure_id(), prefixes)
        if iri in visited:
            return
        visited.add(iri)
        models.append(model)
        for name, _field_info, _ in model.get_relationship_fields():
            value = getattr(model, name, None)
            if isinstance(value, SPARQLModel):
                walk(value)

    if not isinstance(root, SPARQLModel):
        raise TypeError("Expected SPARQLModel instance")
    walk(root)
    return models


def orphaned_embedded_targets(
    model: SPARQLModel,
    graph: Graph,
) -> list[tuple[type[SPARQLModel], str]]:
    """Graph-linked resources dropped from an embedded relationship (put orphan cleanup)."""
    prefixes = model.get_prefixes()
    nested_iris = {
        _expanded_iri_key(m.ensure_id(), m.get_prefixes()) for m in iter_nested_models(model)
    }
    subject = _subject_ref(model.ensure_id(), prefixes)
    orphans: list[tuple[type[SPARQLModel], str]] = []

    for name, field_info, related_cls in model.get_relationship_fields():
        value = getattr(model, name, None)
        if isinstance(value, IRI):
            continue
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        pred = _predicate_ref(meta.predicate, prefixes)
        for obj in graph.objects(subject, pred):
            if isinstance(obj, (URIRef, BNode)):
                obj_key = _expanded_iri_key(str(obj), prefixes)
                if obj_key not in nested_iris:
                    orphans.append((related_cls, str(obj)))
    return orphans


def cascade_subjects_for_removal(
    model: SPARQLModel,
    graph: Graph,
    *,
    for_put: bool = False,
) -> list[tuple[type[SPARQLModel], str]]:
    """Subjects whose owned triples should be removed on put/delete of ``model``."""
    seen: set[str] = set()
    subjects: list[tuple[type[SPARQLModel], str]] = []

    def add(model_cls: type[SPARQLModel], iri: str | IRI) -> None:
        key = str(iri)
        if key in seen:
            return
        seen.add(key)
        subjects.append((model_cls, key))

    for nested in iter_nested_models(model):
        add(type(nested), nested.ensure_id())

    if for_put:
        for nested in iter_nested_models(model):
            for model_cls, iri in orphaned_embedded_targets(nested, graph):
                add(model_cls, iri)

    return subjects


def owned_triples_for_subjects(
    subjects: Iterable[tuple[type[SPARQLModel], str | IRI]],
    graph: Graph,
) -> list[tuple[Node, Node, Node]]:
    """Union of owned triples for multiple subjects (deduplicated)."""
    triples: list[tuple[Node, Node, Node]] = []
    seen: set[tuple[Node, Node, Node]] = set()
    for model_cls, iri in subjects:
        for triple in owned_triples_for_subject(model_cls, iri, graph):
            if triple not in seen:
                seen.add(triple)
                triples.append(triple)
    return triples


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
    prefixes = model_cls.get_prefixes()
    subject_key = _expanded_iri_key(subject_iri, prefixes)
    if subject_key in visited:
        raise ConfigurationError(f"Cycle detected loading {subject_key}")
    visited.add(subject_key)

    data = load_scalars(model_cls, subject_iri, graph)

    if depth > 0:
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
            if not subject_has_rdf_type(related_cls, related_iri, graph):
                data[name] = None
                continue
            data[name] = graph_to_model(
                related_cls,
                related_iri,
                graph,
                depth=depth - 1,
                visited=visited.copy(),
            )

    return model_cls.model_validate(data)
