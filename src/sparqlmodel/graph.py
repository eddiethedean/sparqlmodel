"""ORM persistence policy (cascade, orphans); RDF mapping via ``rdf_bridge``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from pyoxigraph import BlankNode, Literal, NamedNode
from triplemodel import Store
from triplemodel.config import RDF_TYPE as RDF_TYPE_URI
from triplemodel.store.terms import OxTerm, QuadPredicate, QuadSubject, term_str

from sparqlmodel.fields import get_field_metadata, iter_relationship_values
from sparqlmodel.types import IRI, expand_iri

if TYPE_CHECKING:
    from sparqlmodel.model import SPARQLModel

RDF_TYPE = RDF_TYPE_URI


def _expanded_iri_key(iri: str | IRI, prefixes: dict[str, str]) -> str:
    """Canonical expanded IRI string for set lookups and cycle detection."""
    return expand_iri(str(iri), prefixes)


def _is_resource_term(term: object) -> bool:
    return isinstance(term, (NamedNode, BlankNode))


def _term_subject_key(
    term: QuadSubject | str | Literal,
    prefixes: dict[str, str],
) -> str:
    if isinstance(term, Literal):
        return term_str(term)
    if isinstance(term, BlankNode):
        raw = str(term)
        return raw if raw.startswith("_:") else f"_:{raw}"
    if isinstance(term, NamedNode):
        return _expanded_iri_key(term.value, prefixes)
    raw = str(term)
    if raw.startswith("_:"):
        return raw
    return _expanded_iri_key(raw, prefixes)


def subject_has_rdf_type(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Store,
) -> bool:
    """Return True if the graph subject has the expected ``rdf:type`` for ``model_cls``."""
    prefixes = model_cls.get_prefixes()
    subject = _subject_pattern(subject_iri, prefixes)
    types = list(graph.objects(subject, RDF_TYPE))
    if not types:
        return False
    expected = expand_iri(model_cls.rdf_type, prefixes)
    return any(term_str(t) == expected for t in types)


def _subject_pattern(iri: str | IRI, prefixes: dict[str, str]) -> str | BlankNode:
    raw = str(iri)
    if raw.startswith("_:"):
        return BlankNode(raw[2:])
    expanded = expand_iri(raw, prefixes)
    if expanded.startswith("_:"):
        return BlankNode(expanded[2:])
    return expanded


def _predicate_pattern(predicate: str, prefixes: dict[str, str]) -> str:
    return expand_iri(predicate, prefixes)


def triples_to_graph(
    triples: Iterable[tuple[QuadSubject | str, QuadPredicate | str, OxTerm | str]],
    *,
    target: Store | None = None,
) -> Store:
    """Build a :class:`~triplemodel.Store` from triple patterns."""
    g = target or Store()
    for s, p, o in triples:
        g.add((s, p, o))
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
        for name, field_info, _ in model.get_relationship_fields():
            meta = get_field_metadata(field_info)
            if meta is not None and not meta.cascade:
                continue
            value = getattr(model, name, None)
            for item in iter_relationship_values(value):
                if isinstance(item, SPARQLModel):
                    walk(item)

    if not isinstance(root, SPARQLModel):
        raise TypeError("Expected SPARQLModel instance")
    walk(root)
    return models


def _object_referenced_from_outside(
    obj_key: str,
    graph: Store,
    exclude_subject_keys: set[str],
    prefixes: dict[str, str],
) -> bool:
    """Return True if a subject outside ``exclude_subject_keys`` links to ``obj_key``."""
    for s, _p, o in graph:
        if not _is_resource_term(o):
            continue
        if _term_subject_key(o, prefixes) != obj_key:
            continue
        if _term_subject_key(s, prefixes) not in exclude_subject_keys:
            return True
    return False


def orphaned_embedded_targets(
    model: SPARQLModel,
    graph: Store,
    *,
    exclude_subject_keys: set[str] | None = None,
) -> list[tuple[type[SPARQLModel], str]]:
    """Graph-linked resources dropped from an embedded relationship (put orphan cleanup)."""
    prefixes = model.get_prefixes()
    nested_iris = {
        _expanded_iri_key(m.ensure_id(), m.get_prefixes()) for m in iter_nested_models(model)
    }
    subject = _subject_pattern(model.ensure_id(), prefixes)
    orphans: list[tuple[type[SPARQLModel], str]] = []
    cascade_keys = exclude_subject_keys if exclude_subject_keys is not None else nested_iris

    from sparqlmodel.model import SPARQLModel as _SPARQLModel

    for name, field_info, related_cls in model.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is None or not meta.cascade:
            continue
        target_cls = meta.related_model if meta.related_model is not None else related_cls
        if not isinstance(target_cls, type) or not issubclass(target_cls, _SPARQLModel):
            continue
        value = getattr(model, name, None)
        protected = set(nested_iris)
        for item in iter_relationship_values(value):
            if isinstance(item, IRI):
                protected.add(_expanded_iri_key(item, prefixes))
            elif isinstance(item, _SPARQLModel):
                protected.add(_expanded_iri_key(item.ensure_id(), item.get_prefixes()))
        pred = _predicate_pattern(meta.predicate, prefixes)
        for obj in graph.objects(subject, pred):
            if _is_resource_term(obj):
                obj_key = _term_subject_key(obj, prefixes)
                if obj_key not in protected:
                    if _object_referenced_from_outside(obj_key, graph, cascade_keys, prefixes):
                        continue
                    orphans.append((target_cls, obj_key))
    return orphans


def cascade_subjects_for_removal(
    model: SPARQLModel,
    graph: Store,
    *,
    for_put: bool = False,
) -> list[tuple[type[SPARQLModel], str]]:
    """Subjects whose owned triples should be removed on put/delete of ``model``."""
    seen: set[str] = set()
    subjects: list[tuple[type[SPARQLModel], str]] = []

    def add(model_cls: type[SPARQLModel], iri: str | IRI) -> None:
        raw = str(iri)
        key = raw if raw.startswith("_:") else _expanded_iri_key(iri, model_cls.get_prefixes())
        if key in seen:
            return
        seen.add(key)
        subjects.append((model_cls, key))

    cascade_subject_keys: set[str] = set()
    for nested in iter_nested_models(model):
        nested_prefixes = nested.get_prefixes()
        raw = str(nested.ensure_id())
        key = (
            raw if raw.startswith("_:") else _expanded_iri_key(nested.ensure_id(), nested_prefixes)
        )
        cascade_subject_keys.add(key)
        add(type(nested), nested.ensure_id())

    if for_put:
        for nested in iter_nested_models(model):
            for model_cls, iri in orphaned_embedded_targets(
                nested, graph, exclude_subject_keys=cascade_subject_keys
            ):
                add(model_cls, iri)

    return subjects


def owned_triples_for_subjects(
    subjects: Iterable[tuple[type[SPARQLModel], str | IRI]],
    graph: Store,
) -> list[tuple[QuadSubject, QuadPredicate, OxTerm]]:
    """Union of owned triples for multiple subjects (deduplicated)."""
    triples: list[tuple[QuadSubject, QuadPredicate, OxTerm]] = []
    seen: set[tuple[str, str, str]] = set()
    for model_cls, iri in subjects:
        for triple in owned_triples_for_subject(model_cls, iri, graph):
            key = (term_str(triple[0]), term_str(triple[1]), term_str(triple[2]))
            if key not in seen:
                seen.add(key)
                triples.append(triple)
    return triples


def owned_triples_for_subject(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Store,
) -> list[tuple[QuadSubject, QuadPredicate, OxTerm]]:
    """Return triples owned by a subject for declared predicates + rdf:type."""
    prefixes = model_cls.get_prefixes()
    subject = _subject_pattern(subject_iri, prefixes)
    predicates = {_predicate_pattern("rdf:type", prefixes)}
    for _, field_info in model_cls.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta:
            predicates.add(_predicate_pattern(meta.predicate, prefixes))
    for _, field_info, _ in model_cls.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta:
            predicates.add(_predicate_pattern(meta.predicate, prefixes))

    return [
        (s, p, o) for s, p, o in graph.triples((subject, None, None)) if term_str(p) in predicates
    ]


# Internal aliases (tests, transitional imports)
_subject_ref = _subject_pattern
_graph_subject_key = _term_subject_key
