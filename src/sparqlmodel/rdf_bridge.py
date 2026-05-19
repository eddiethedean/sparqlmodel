"""Graph I/O for :class:`~sparqlmodel.model.SPARQLModel` (TripleModel-backed, no adapter)."""

from __future__ import annotations

from rdflib import XSD, Graph, Literal, URIRef
from triplemodel._typing import TripleRow
from triplemodel.config import RDF_TYPE, get_rdf_config
from triplemodel.fields.metadata import lang_for_field, literal_datatype_for_field
from triplemodel.io.export import _field_values_for_export, model_to_triples
from triplemodel.io.sync import remove_owned_triples
from triplemodel.io.writer import apply_triple_rows
from triplemodel.metadata.cardinality import field_cardinality, raise_if_nested_collection
from triplemodel.metadata.predicate_map import predicate_map_for_class
from triplemodel.namespaces import resolve_predicate
from triplemodel.terms.lang import LangString

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.fields import get_field_metadata, relationship_allows_iri
from sparqlmodel.graph import iter_nested_models, subject_has_rdf_type
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import IRI, expand_iri


def _expanded_iri_key(iri: str | IRI, prefixes: dict[str, str]) -> str:
    return expand_iri(str(iri), prefixes)


def assert_no_embed_cycles(
    instance: SPARQLModel,
    visited: set[str],
) -> None:
    """Raise if nested ``SPARQLModel`` embeds form a cycle (shared leaves are allowed)."""
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
        if isinstance(value, SPARQLModel):
            assert_no_embed_cycles(value, path.copy())


def _relationship_field_names(cls: type[SPARQLModel]) -> set[str]:
    return {name for name, _, _ in cls.get_relationship_fields()}


def sparql_instance_to_triples(instance: SPARQLModel) -> list[TripleRow]:
    """Export one instance: scalars via TripleModel; relationships as links or nested embed."""
    cls = type(instance)
    cfg = get_rdf_config(cls)
    prefixes = cfg.prefixes_dict
    subject = instance.subject_uri()
    triples: list[TripleRow] = []

    if cfg.type_uri:
        triples.append((subject, RDF_TYPE, cfg.type_uri))

    rel_names = _relationship_field_names(cls)

    for name, predicate in predicate_map_for_class(cls).items():
        if predicate is None or name in rel_names:
            continue
        field_info = cls.model_fields[name]
        raise_if_nested_collection(field_info)
        value = getattr(instance, name)
        card = field_cardinality(field_info)
        if card in ("nested", "ref", "list", "set"):
            continue

        lang = lang_for_field(field_info)
        dt_raw = literal_datatype_for_field(field_info)
        for item in _field_values_for_export(name, value, field_info):
            obj = item
            if lang and isinstance(obj, str):
                obj = LangString(obj, lang)
            elif dt_raw is not None and isinstance(item, int):
                if dt_raw in ("gYear", "xsd:gYear") or dt_raw == str(XSD.gYear):
                    obj = Literal(str(item), datatype=XSD.gYear)
                else:
                    dt_uri = resolve_predicate(dt_raw, prefixes)
                    obj = Literal(str(item), datatype=URIRef(dt_uri))
            triples.append((subject, predicate, obj))

    for name, field_info, _related_cls in cls.get_relationship_fields():
        meta = get_field_metadata(field_info)
        if meta is None:
            continue
        value = getattr(instance, name, None)
        if value is None:
            continue
        predicate = resolve_predicate(meta.predicate, prefixes)

        if isinstance(value, SPARQLModel):
            triples.append((subject, predicate, value.subject_uri()))
        elif isinstance(value, IRI):
            triples.append((subject, predicate, str(value)))

    return triples


def sync_sparql_to_graph(
    instance: SPARQLModel,
    graph: Graph,
    *,
    uri: str | None = None,
    mode: str = "replace",
) -> None:
    """Write instance triples to ``graph`` (per-subject replace, matching session put)."""
    subject = uri or instance.subject_uri()
    triples = sparql_instance_to_triples(instance)
    if mode == "replace":
        remove_owned_triples(graph, subject, type(instance))
    apply_triple_rows(graph, triples)


def adapter_graph(root: SPARQLModel) -> Graph:
    """Build an rdflib graph for nested cascade models (one sync per nested node)."""
    assert_no_embed_cycles(root, set())
    g = Graph()
    for nested in iter_nested_models(root):
        sync_sparql_to_graph(nested, g, uri=nested.subject_uri(), mode="replace")
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


def model_to_graph(model: SPARQLModel) -> Graph:
    """Serialize a model to an rdflib Graph."""
    g = _normalize_graph(adapter_graph(model))
    model.namespace_registry().bind(g)
    return g


def _iri_like(value: str) -> bool:
    return value.startswith(("http://", "https://", "urn:", "_:"))


def load_from_graph(
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

    uri = expand_iri(str(subject_iri), prefixes)
    raw = model_cls.from_graph(graph, uri, validate_type=True, on_duplicate="warn")
    data: dict[str, object] = {"id": IRI(raw.subject_uri())}

    for name, _field_info in model_cls.get_scalar_fields():
        if hasattr(raw, name):
            value = getattr(raw, name)
            if value is not None:
                data[name] = value

    if depth > 0:
        for name, field_info, related_cls in model_cls.get_relationship_fields():
            if not hasattr(raw, name):
                continue
            value = getattr(raw, name)
            if value is None:
                data[name] = None
                continue

            meta = get_field_metadata(field_info)
            allows_iri = relationship_allows_iri(field_info.annotation)

            if isinstance(value, SPARQLModel):
                if meta is not None and meta.cascade:
                    data[name] = load_from_graph(
                        related_cls,
                        IRI(value.subject_uri()),
                        graph,
                        depth=depth - 1,
                        visited=visited,
                    )
                else:
                    data[name] = IRI(value.subject_uri()) if allows_iri else value
            elif isinstance(value, str) and _iri_like(value):
                if subject_has_rdf_type(related_cls, value, graph):
                    data[name] = load_from_graph(
                        related_cls,
                        IRI(value),
                        graph,
                        depth=depth - 1,
                        visited=visited,
                    )
                else:
                    data[name] = None
            else:
                data[name] = value

    return model_cls.model_validate(data)


def sparql_from_graph(
    model_cls: type[SPARQLModel],
    subject_iri: str | IRI,
    graph: Graph,
    *,
    depth: int = 0,
    visited: set[str] | None = None,
) -> SPARQLModel:
    """Alias for :func:`load_from_graph` (hydration and tests)."""
    return load_from_graph(model_cls, subject_iri, graph, depth=depth, visited=visited)


def graphs_isomorphic(left: Graph, right: Graph) -> bool:
    """Return whether two graphs are isomorphic (after literal normalization)."""
    return _normalize_graph(left).isomorphic(_normalize_graph(right))


def assert_put_graph_contract(root: SPARQLModel) -> None:
    """Raise AssertionError if the export graph is empty for a model with data."""
    g = adapter_graph(root)
    if len(g) == 0 and root.id is not None:
        raise AssertionError(f"Export graph empty for {type(root).__name__}")


def direct_export_triples(instance: SPARQLModel) -> list[TripleRow]:
    """Full TripleModel export (includes union misclassified fields); for tests only."""
    return model_to_triples(instance, uri=instance.subject_uri())
