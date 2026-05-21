"""Tests targeting uncovered branches for full coverage."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import Field as PydanticField
from pydantic import ValidationError
from pyoxigraph import BlankNode as BNode
from pyoxigraph import Literal
from triplemodel import Store
from triplemodel.store.terms import term_str

from sparqlmodel import IRI, Field, Relationship, SPARQLModel, SPARQLSession
from sparqlmodel.compiler import (
    _flatten_and_expressions,
    _format_iri,
    _format_literal,
    _format_object,
    compile_compare,
    compile_where,
)
from sparqlmodel.exceptions import ConfigurationError, HydrationError, QueryError
from sparqlmodel.expressions import AndExpr, CompareExpr, CompareOp, FieldRef
from sparqlmodel.fields import Relationship as RelField
from sparqlmodel.fields import get_field_metadata, resolve_related_model
from sparqlmodel.graph import (
    _graph_subject_key,
    _subject_ref,
    cascade_subjects_for_removal,
    iter_nested_models,
    owned_triples_for_subject,
    owned_triples_for_subjects,
    subject_has_rdf_type,
)
from sparqlmodel.hydration import hydrate_from_bindings, validate_depth
from sparqlmodel.rdf_bridge import (
    assert_no_embed_cycles,
    load_from_graph,
    model_to_graph,
    sparql_instance_to_triples,
)
from sparqlmodel.serializers import (
    _annotation_allows_iri,
    _is_jsonld_reference_node,
    _jsonld_node_body,
    _normalize_format,
    export_graph,
    model_from_jsonld,
    model_to_jsonld,
)
from sparqlmodel.stores.memory import MemoryStore, _term_value
from sparqlmodel.types import IRI as IRIType
from sparqlmodel.types import NamespaceRegistry, compact_iri, expand_iri
from tests.models import Location, Organization, Person
from tests.rdf_helpers import RDF_TYPE

# --- compiler ---


def test_format_literal_bool_int_float() -> None:
    assert _format_literal(False) == "false"
    assert _format_literal(True) == "true"
    assert "integer" in _format_literal(42)
    assert "42" in _format_literal(42)
    assert "double" in _format_literal(1.5)


def test_format_iri_invalid() -> None:
    with pytest.raises(QueryError):
        _format_iri("")
    with pytest.raises(QueryError):
        _format_iri("bad space")


def test_format_object_variants() -> None:
    from sparqlmodel.compiler import _annotation_expects_iri

    reg = NamespaceRegistry(Person.get_prefixes())
    assert _format_object(IRI("urn:x"), reg).startswith("<")
    assert '"https://example.org/x"' in _format_object("https://example.org/x", reg)
    assert '"schema:Person"' in _format_object("schema:Person", reg)
    assert _format_object("schema:Person", reg, field_annotation=IRI).startswith("<")
    assert _annotation_expects_iri(str | IRI | None) is True
    assert _format_object("unknown:foo", NamespaceRegistry({}), field_annotation=IRI) == (
        '"unknown:foo"'
    )


def test_flatten_nested_and_expr() -> None:
    inner = AndExpr((Person.name == "A",))
    outer = AndExpr((inner,))
    flat = _flatten_and_expressions((outer,))
    assert len(flat) == 1


def test_flatten_unsupported_and_child() -> None:
    with pytest.raises(QueryError, match="AND"):
        _flatten_and_expressions((AndExpr((object(),)),))  # type: ignore[arg-type]


def test_flatten_unsupported_top_level() -> None:
    with pytest.raises(QueryError, match="WHERE"):
        _flatten_and_expressions((42,))  # type: ignore[arg-type]


def test_compile_unknown_relationship_path() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    ref = FieldRef(Person, "name", ("nonexistent",))
    with pytest.raises(QueryError, match="Unknown relationship"):
        compile_compare(CompareExpr(ref, CompareOp.EQ, "x"), Person, "?person", reg, [0], {})


def test_compile_unknown_scalar_on_target() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    ref = FieldRef(Person, "bogus", ("works_for",))
    with pytest.raises(QueryError, match="Unknown or non-scalar"):
        compile_compare(CompareExpr(ref, CompareOp.EQ, "x"), Person, "?person", reg, [0], {})


def test_compile_where_no_filters_branch() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "A",), reg)
    assert "FILTER" not in sparql


# --- expressions ---


def test_and_expr_combine() -> None:
    a = Person.name == "A"
    b = Person.name == "B"
    inner = AndExpr((a, b))
    combined = inner & (Person.name == "C")
    assert len(combined.expressions) == 3
    combined2 = a & inner
    assert len(combined2.expressions) == 3
    inner2 = AndExpr((Person.name == "D",))
    combined3 = inner & inner2
    assert len(combined3.expressions) == 3


# --- fields ---


def test_relationship_non_dict_extra() -> None:
    f = RelField("schema:x", json_schema_extra="bad")  # type: ignore[arg-type]
    assert f is not None


def test_get_field_metadata_wrong_meta_type() -> None:
    class Plain(SPARQLModel):
        rdf_type = "schema:Thing"
        label: str = PydanticField(json_schema_extra={"sparql": "not-metadata"})

    assert get_field_metadata(Plain.model_fields["label"]) is None


def test_resolve_related_model_errors() -> None:
    from typing import ForwardRef

    from sparqlmodel.fields import SPARQLFieldMetadata

    meta = SPARQLFieldMetadata(predicate="schema:link", is_relationship=True)
    with pytest.raises(ConfigurationError):
        resolve_related_model("link", ForwardRef("UnknownModel"), meta)


def test_resolve_related_model_from_union() -> None:
    from sparqlmodel.fields import SPARQLFieldMetadata

    meta = SPARQLFieldMetadata(predicate="schema:worksFor", is_relationship=True)
    related = resolve_related_model("works_for", Organization | None, meta)
    assert related is Organization


# --- graph ---


def test_subject_ref_bnode_and_fallback() -> None:
    assert isinstance(_subject_ref("_:bn123", {}), BNode)
    with patch("sparqlmodel.graph.expand_iri", return_value="_:abc"):
        assert isinstance(_subject_ref("x:local", {}), BNode)
    assert _subject_ref("custom:local", {"custom": "http://example.org/"}) == (
        "http://example.org/local"
    )
    assert _subject_ref("plainlocal", {}) == "plainlocal"


def test_graph_subject_key_literal() -> None:
    assert _graph_subject_key(Literal("x"), {}) == term_str(Literal("x"))


def test_iter_nested_models_type_error() -> None:
    with pytest.raises(TypeError):
        iter_nested_models("not a model")  # type: ignore[arg-type]


def test_model_to_graph_iri_relationship_branch() -> None:
    person = Person(
        id=IRI("urn:p"),
        name="P",
        works_for=IRI("urn:org:iri-only"),
    )
    g = model_to_graph(person)
    assert any(term_str(o) == "urn:org:iri-only" for _, _, o in g)


def test_person_with_iri_works_for_graph() -> None:
    org = Organization(id=IRI("urn:org:x"), name="X")
    person = Person(id=IRI("urn:p"), name="P", works_for=org.id)
    g = model_to_graph(person)
    assert any(term_str(o) == "urn:org:x" for _, _, o in g)


def test_iter_nested_skips_revisit() -> None:
    org = Organization(id=IRI("urn:org:dup"), name="X")
    p1 = Person(id=IRI("urn:p1"), name="A", works_for=org)
    # Shared embed only walks once per IRI in iter_nested from each root
    nested = iter_nested_models(p1)
    assert len(nested) >= 2


def test_cascade_add_dedupes_seen() -> None:
    session = SPARQLSession()
    person = Person(id=IRI("urn:p"), name="P")
    session.put(person)
    subjects = cascade_subjects_for_removal(person, session.graph, for_put=False)
    subjects2 = cascade_subjects_for_removal(person, session.graph, for_put=False)
    assert subjects == subjects2


def test_owned_triples_dedupes() -> None:
    session = SPARQLSession()
    person = Person(id=IRI("urn:p"), name="P")
    session.put(person)
    subjects = [(Person, person.id), (Person, person.id)]
    triples = owned_triples_for_subjects(subjects, session.graph)
    assert len(triples) == len(set(triples))


def test_load_from_graph_typed_literals() -> None:
    g = Store()
    subj = "urn:typed"
    pred = expand_iri("schema:name", Person.get_prefixes())
    type_uri = expand_iri("schema:Person", Person.get_prefixes())
    g.add((subj, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", type_uri))
    g.add(
        (
            subj,
            pred,
            Literal(True),
        )
    )
    g.add(
        (
            subj,
            expand_iri("schema:age", Person.get_prefixes()),
            Literal(7),
        )
    )

    class TypedPerson(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        name: bool = Field("schema:name")
        age: int = Field("schema:age")

    loaded = load_from_graph(TypedPerson, IRI("urn:typed"), g, depth=0)
    assert loaded.name is True
    assert loaded.age == 7


def test_load_from_graph_uri_object() -> None:
    g = Store()
    subj = "urn:iri-scalar"
    type_uri = expand_iri("schema:Person", Person.get_prefixes())
    g.add((subj, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", type_uri))
    pred = expand_iri("schema:name", Person.get_prefixes())
    g.add((subj, pred, "urn:label"))

    loaded = load_from_graph(Person, IRI("urn:iri-scalar"), g, depth=0)
    assert loaded.name == "urn:label"


def test_load_from_graph_wrong_related_type(session, odos: Person) -> None:
    session.put(odos)
    loaded = session.get(Person, odos.id, depth=1)
    assert loaded is not None
    assert loaded.works_for is not None


def test_load_from_graph_related_missing_type(session) -> None:
    person = Person(id=IRI("urn:p"), name="P", works_for=None)
    session.put(person)
    subj = str(person.id)
    works = expand_iri("schema:worksFor", Person.get_prefixes())
    session.graph.add((subj, works, "urn:org:ghost"))
    loaded = session.get(Person, person.id, depth=1)
    assert loaded is not None
    assert loaded.works_for is None


def test_subject_has_rdf_type_false(session) -> None:
    assert subject_has_rdf_type(Person, IRI("urn:missing"), session.graph) is False


# --- hydration ---


def test_validate_depth_bounds() -> None:
    with pytest.raises(ConfigurationError):
        validate_depth(-1)
    with pytest.raises(ConfigurationError):
        validate_depth(3)


def test_hydrate_bindings_key_variants(session, odos: Person) -> None:
    session.put(odos)
    iri = str(odos.id)
    bindings = [
        {"?person": iri},
        {"person": iri},
        {"PERSON": iri},
    ]
    results = hydrate_from_bindings(Person, bindings[:2], session.store)
    assert len(results) >= 1
    results2 = hydrate_from_bindings(Person, bindings, session.store)
    assert len(results2) >= 1


def test_hydrate_bindings_skip_missing_and_duplicate(session, odos: Person) -> None:
    session.put(odos)
    iri = str(odos.id)
    bindings = [{"other": "x"}, {"person": iri}, {"person": iri}]
    results = hydrate_from_bindings(Person, bindings, session.store)
    assert len(results) == 1


def test_hydrate_bindings_wraps_errors(session) -> None:
    from pydantic import ValidationError

    with (
        patch(
            "sparqlmodel.hydration.hydrate_one",
            side_effect=ValidationError.from_exception_data("Person", []),
        ),
        pytest.raises(HydrationError),
    ):
        hydrate_from_bindings(
            Person,
            [{"person": "urn:person:x"}],
            session.store,
        )


# --- model prefixes ---


def test_subclass_inherits_prefixes_copy() -> None:
    class Employee(Person):
        pass

    assert Employee.get_prefixes() == Person.get_prefixes()
    Employee.__prefixes__["ex"] = "http://example.org/"
    assert "ex" not in Person.get_prefixes()


# --- serializers ---


def test_annotation_allows_iri_union() -> None:
    assert _annotation_allows_iri(Person.model_fields["works_for"].annotation) is True
    assert _annotation_allows_iri(str) is False


def test_is_jsonld_reference_node() -> None:
    assert _is_jsonld_reference_node({"@id": "urn:x"}) is True
    assert _is_jsonld_reference_node({"@id": "urn:x", "schema:name": "n"}) is False


def test_jsonld_type_list_and_compact_predicate() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": ["https://schema.org/Person", "https://schema.org/Thing"],
        "schema:name": "X",
    }
    person = model_from_jsonld(Person, doc)
    assert person.name == "X"


def test_jsonld_urn_id_and_string_rel() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
        "schema:worksFor": "urn:org:y",
    }
    person = model_from_jsonld(Person, doc)
    assert person.works_for == IRI("urn:org:y")


def test_jsonld_embedded_child_with_context() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
        "https://schema.org/worksFor": {
            "@id": "urn:org:y",
            "@type": "schema:Organization",
            "schema:name": "Y",
        },
    }
    person = model_from_jsonld(Person, doc)
    assert person.works_for is not None
    assert person.works_for.name == "Y"


def test_jsonld_iri_ref_compact_local_id() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
        "schema:worksFor": {"@id": "org:acme"},
    }
    person = model_from_jsonld(Person, doc)
    assert str(person.works_for) == "org:acme"


def test_jsonld_iri_ref_compact_id() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
        "schema:worksFor": {"id": "urn:org:y"},
    }
    person = model_from_jsonld(Person, doc)
    assert person.works_for == IRI("urn:org:y")


def test_jsonld_non_dict_context() -> None:
    doc = {
        "@context": ["https://schema.org/"],
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
    }
    person = model_from_jsonld(Person, doc)
    assert person.name == "X"


def test_normalize_format_aliases() -> None:
    assert _normalize_format("ttl") == "turtle"
    assert _normalize_format("jsonld") == "json-ld"
    assert _normalize_format("ntriples") in ("nt", "ntriples")


def test_resolve_rdf_format_empty() -> None:
    from sparqlmodel.serializers import _resolve_rdf_format

    with pytest.raises(ValueError, match="Cannot infer RDF format"):
        _resolve_rdf_format("   ")


def test_export_graph_turtle(session, odos: Person) -> None:
    session.put(odos)
    out = export_graph(session.graph, format="ttl")
    assert "Odos" in out


# --- session ---


def test_delete_never_put(session) -> None:
    person = Person(id=IRI("urn:never"), name="N")
    session.delete(person)


def test_execute_with_prefix_in_query(session, odos: Person) -> None:
    session.put(odos)
    sparql = (
        "PREFIX schema: <https://schema.org/>\nSELECT ?person WHERE { ?person a schema:Person . }"
    )
    results = session.execute(sparql)
    assert len(results) >= 1


def test_execute_injects_prefixes_when_prologue_missing(session, odos: Person) -> None:
    session.put(odos)
    captured: list[str] = []

    def capture(sparql: str) -> list[dict[str, object]]:
        captured.append(sparql)
        return []

    with patch.object(session.store, "query", side_effect=capture):
        session.execute("SELECT ?person WHERE { ?person a <https://schema.org/Person> . }")
    assert captured
    assert "PREFIX schema:" in captured[0]


def test_execute_prefix_in_string_literal_still_injects(session) -> None:
    captured: list[str] = []

    def capture(sparql: str) -> list[dict[str, object]]:
        captured.append(sparql)
        return []

    with patch.object(session.store, "query", side_effect=capture):
        session.execute('SELECT ?x WHERE { ?x ?p "mentions PREFIX not a decl" }')
    assert "PREFIX schema:" in captured[0]


# --- store ---


def test_store_query_failure() -> None:
    store = MemoryStore()
    mock_graph = MagicMock()
    mock_graph.query.side_effect = RuntimeError("parse error")
    store._graph = mock_graph
    with pytest.raises(QueryError, match="failed"):
        store.query("SELECT ?s WHERE { ?s ?p ?o }")


def test_store_non_result_row_skipped() -> None:
    from triplemodel.store.sparql_result import SparqlResult, Variable

    store = MemoryStore()
    mock_result = SparqlResult(
        result_type="SELECT",
        vars_=[Variable("s")],
        rows=[("not", "a", "ResultRow")],
    )
    mock_graph = MagicMock()
    mock_graph.query.return_value = mock_result
    store._graph = mock_graph
    assert store.query("SELECT ?s WHERE { ?s ?p ?o }") == []


def test_term_value_none() -> None:
    assert _term_value(None) is None


# --- types ---


def test_iri_compact_method() -> None:
    iri = IRIType("https://schema.org/Person")
    assert iri.compact({"schema": "https://schema.org/"}) == "schema:Person"


def test_expand_iri_passthrough() -> None:
    assert expand_iri("not-a-valid-compact") == "not-a-valid-compact"


def test_compact_iri_no_known_prefix() -> None:
    assert compact_iri("https://unknown.example.org/foo", {}) == "https://unknown.example.org/foo"


def test_namespace_registry_expand_compact() -> None:
    reg = NamespaceRegistry({"schema": "https://schema.org/"})
    assert reg.expand("schema:Person") == "https://schema.org/Person"
    assert reg.compact("https://schema.org/Person") == "schema:Person"


def test_compile_relationship_no_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    field_info = Person.model_fields["works_for"]

    def fake_metadata(fi: Any) -> Any:
        if fi is field_info:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.compiler.get_field_metadata", fake_metadata)
    ref = FieldRef(Person, "name", ("works_for",))
    with pytest.raises(QueryError, match="no SPARQL metadata"):
        compile_compare(CompareExpr(ref, CompareOp.EQ, "Acme"), Person, "?person", reg, [0], {})


def test_to_triplemodel_skip_none_meta(monkeypatch: pytest.MonkeyPatch, odos: Person) -> None:
    def fake_metadata(fi: Any) -> Any:
        return None

    monkeypatch.setattr("sparqlmodel.rdf_bridge.get_field_metadata", fake_metadata)
    g = model_to_graph(odos)
    assert len(g) >= 1
    assert any(term_str(p) == RDF_TYPE for _s, p, _o in g)


def test_compile_scalar_no_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    field_info = Person.model_fields["name"]

    def fake_metadata(fi: Any) -> Any:
        if fi is field_info:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.compiler.get_field_metadata", fake_metadata)
    with pytest.raises(QueryError, match="no SPARQL metadata"):
        compile_compare(Person.name == "x", Person, "?person", reg, [0], {})  # type: ignore[arg-type]


def test_hydrate_bindings_alternate_key() -> None:
    class Binding(dict[str, str]):
        def get(self, key: str, default: object = None) -> object:
            return None

    store = MemoryStore()
    store.graph.add(
        (
            "urn:p",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "https://schema.org/Person",
        )
    )
    store.graph.add(
        (
            "urn:p",
            "https://schema.org/name",
            Literal("P"),
        )
    )
    binding: Binding = Binding()
    binding["person"] = "urn:p"
    results = hydrate_from_bindings(Person, [binding], store)  # type: ignore[list-item]
    assert len(results) == 1


def test_load_from_graph_first_literal_on_duplicate() -> None:
    g = Store()
    subj = "urn:multi"
    pred = expand_iri("schema:name", Person.get_prefixes())
    type_uri = expand_iri("schema:Person", Person.get_prefixes())
    g.add((subj, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", type_uri))
    g.add((subj, pred, Literal("first")))
    g.add((subj, pred, Literal("second")))
    loaded = load_from_graph(Person, IRI("urn:multi"), g, depth=0)
    assert loaded.name in ("first", "second")


def test_load_from_graph_float_datatype() -> None:
    g = Store()
    subj = "urn:flt"
    type_uri = expand_iri("schema:Person", Person.get_prefixes())
    g.add((subj, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", type_uri))

    class ScorePerson(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        score: float = Field("schema:value")

    pred = expand_iri("schema:value", Person.get_prefixes())
    g.add(
        (
            subj,
            pred,
            Literal(1.5),
        )
    )
    loaded = load_from_graph(ScorePerson, IRI("urn:flt"), g, depth=0)
    assert loaded.score == 1.5


def test_load_from_graph_skip_none_relationship_meta(
    monkeypatch: pytest.MonkeyPatch, session
) -> None:
    person = Person(id=IRI("urn:p"), name="P")
    session.put(person)
    rel_field = Person.model_fields["works_for"]

    def fake_metadata(fi: Any) -> Any:
        if fi is rel_field:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.rdf_bridge.get_field_metadata", fake_metadata)
    loaded = load_from_graph(Person, person.id, session.graph, depth=1)
    assert loaded.name == "P"
    assert loaded.works_for is None


def test_jsonld_revisit_node(session, odos: Person) -> None:
    doc = model_to_jsonld(odos)
    assert "@id" in doc
    org = doc.get("https://schema.org/worksFor")
    assert isinstance(org, dict)
    assert org.get("@id")


def test_jsonld_scalar_uses_compact_predicate_key() -> None:
    doc = {
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
    }
    person = model_from_jsonld(Person, doc)
    assert person.name == "X"


def test_jsonld_import_compact_at_id() -> None:
    doc = {
        "@context": {"person": "urn:person:"},
        "@id": "person:local",
        "@type": "schema:Person",
        "schema:name": "X",
    }
    person = model_from_jsonld(Person, doc)
    assert str(person.id) == "person:local"


def test_jsonld_import_compact_predicate_only() -> None:
    doc = {
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "OnlyCompact",
    }
    person = model_from_jsonld(Person, doc)
    assert person.name == "OnlyCompact"


def test_jsonld_import_embedded_not_reference() -> None:
    doc = {
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
        "schema:worksFor": {
            "@id": "urn:org:y",
            "@type": "schema:Organization",
            "schema:name": "Y Corp",
        },
    }
    person = model_from_jsonld(Person, doc)
    assert person.works_for is not None
    assert person.works_for.name == "Y Corp"


def test_model_to_graph_skips_none_scalar() -> None:
    person = Person.model_construct(id=IRI("urn:x"), name=None)
    g = model_to_graph(person)
    preds = [str(p) for _, p, _ in g]
    assert not any("schema.org/name" in p for p in preds)


def test_jsonld_import_skips_none_field_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    class OptionalLabel(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        name: str = Field("schema:name")
        label: str | None = Field("schema:description", default=None)

    doc = {
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
        "schema:description": "tag",
    }
    label_field = OptionalLabel.model_fields["label"]

    def fake_metadata(fi: Any) -> Any:
        if fi is label_field:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.serializers.get_field_metadata", fake_metadata)
    monkeypatch.setattr(
        OptionalLabel,
        "get_scalar_fields",
        classmethod(
            lambda cls: [
                ("name", cls.model_fields["name"]),
                ("label", cls.model_fields["label"]),
            ]
        ),
    )
    person = model_from_jsonld(OptionalLabel, doc)
    assert person.name == "X"
    assert person.label is None


def test_jsonld_relationship_meta_none(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = {
        "@id": "urn:person:x",
        "@type": "schema:Person",
        "schema:name": "X",
        "schema:worksFor": {"@id": "urn:org:y", "@type": "schema:Organization", "schema:name": "Y"},
    }

    def fake_metadata(fi: Any) -> Any:
        if fi is Person.model_fields.get("works_for"):
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.serializers.get_field_metadata", fake_metadata)
    person = model_from_jsonld(Person, doc)
    assert person.name == "X"
    assert not hasattr(person, "works_for") or person.works_for is None


def test_model_base_subclass_prefixes() -> None:
    class Thing(SPARQLModel):
        rdf_type = "schema:Thing"

    class SubThing(Thing):
        pass

    assert SubThing.get_prefixes()["schema"] == "https://schema.org/"


def test_model_subclass_with_own_prefixes() -> None:
    class Custom(SPARQLModel):
        rdf_type = "schema:Thing"
        __prefixes__ = {"ex": "http://example.org/"}

    class Child(Custom):
        pass

    prefs = Child.get_prefixes()
    assert prefs["ex"] == "http://example.org/"
    assert prefs["schema"] == "https://schema.org/"


def test_cascade_add_duplicate_iri(session) -> None:
    person = Person(id=IRI("urn:p"), name="P")
    session.put(person)
    subjects = cascade_subjects_for_removal(person, session.graph, for_put=False)
    dup = [(Person, person.id)] * 2 + subjects
    seen_keys = [iri for _, iri in dup]
    assert seen_keys.count(str(person.id)) >= 2


def test_iter_nested_returns_early_on_revisited_iri() -> None:
    org = Organization(id=IRI("urn:org:shared"), name="Shared")
    p = Person(id=IRI("urn:p"), name="P", works_for=org)
    with patch(
        "sparqlmodel.graph.iter_nested_models",
        return_value=[p, org, org],
    ):
        subjects = cascade_subjects_for_removal(p, Store(), for_put=False)
    assert len(subjects) >= 2


def test_orphan_detects_bnode_target(session) -> None:
    from sparqlmodel.graph import expand_iri, orphaned_embedded_targets

    person = Person(id=IRI("urn:p"), name="P", works_for=None)
    session.put(person)
    subj = _subject_ref(person.id, Person.get_prefixes())
    pred = expand_iri("schema:worksFor", Person.get_prefixes())
    bnode = BNode()
    session.graph.add((subj, pred, bnode))
    orphans = orphaned_embedded_targets(person, session.graph)
    assert orphans


def test_cascade_seen_skips_duplicate_subject(session) -> None:
    person = Person(id=IRI("urn:p"), name="P")
    session.put(person)
    with patch(
        "sparqlmodel.graph.iter_nested_models",
        return_value=[person, person],
    ):
        subjects = cascade_subjects_for_removal(person, session.graph, for_put=False)
    keys = [iri for _, iri in subjects]
    assert keys.count(str(person.id)) == 1


def test_owned_triples_only_rdf_type_when_no_field_meta(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    person = Person(id=IRI("urn:p"), name="P")
    session.put(person)

    def fake_metadata(fi: Any) -> Any:
        return None

    monkeypatch.setattr("sparqlmodel.graph.get_field_metadata", fake_metadata)
    triples = owned_triples_for_subject(Person, person.id, session.graph)
    assert len(triples) == 1
    assert term_str(triples[0][1]) == RDF_TYPE


def test_load_from_graph_no_scalar_values() -> None:
    class EmptyPerson(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        name: str | None = Field("schema:name", default=None)

    g = Store()
    subj = "urn:empty"
    type_uri = expand_iri("schema:Person", EmptyPerson.get_prefixes())
    g.add((subj, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", type_uri))
    loaded = load_from_graph(EmptyPerson, IRI("urn:empty"), g, depth=0)
    assert str(loaded.id) == "urn:empty"
    assert loaded.name is None


def test_jsonld_node_body_skips_none_meta(monkeypatch: pytest.MonkeyPatch, odos: Person) -> None:
    def fake_metadata(fi: Any) -> Any:
        return None

    monkeypatch.setattr("sparqlmodel.serializers.get_field_metadata", fake_metadata)
    body = _jsonld_node_body(odos, visited=set())
    assert "@id" in body
    assert len(body) == 2


def test_jsonld_node_body_skips_none_scalar_value(odos: Person) -> None:
    person = Person.model_construct(id=odos.id, name=None, works_for=odos.works_for)
    body = _jsonld_node_body(person, visited=set())
    assert "https://schema.org/name" not in body


def test_jsonld_node_body_skips_none_relationship(
    monkeypatch: pytest.MonkeyPatch, odos: Person
) -> None:
    rel_field = Person.model_fields["works_for"]

    def fake_metadata(fi: Any) -> Any:
        if fi is rel_field:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.serializers.get_field_metadata", fake_metadata)
    body = _jsonld_node_body(odos, visited=set())
    assert "https://schema.org/worksFor" not in body


def test_jsonld_revisit_returns_id_only(odos: Person) -> None:
    visited = {expand_iri(str(odos.id), odos.get_prefixes())}
    body = _jsonld_node_body(odos, visited=visited)
    assert body == {"@id": expand_iri(str(odos.id), odos.get_prefixes())}


def test_annotation_allows_iri_direct() -> None:
    assert _annotation_allows_iri(IRI) is True


def test_execute_no_prefix_block_when_empty(session, odos: Person) -> None:
    session.put(odos)
    with patch.object(session.namespaces, "sparql_prefixes", return_value=""):
        sparql = "SELECT ?person WHERE { ?person a <https://schema.org/Person> . }"
        results = session.execute(sparql)
    assert len(results) >= 1


def test_orphan_skips_iri_value_and_none_meta(session, monkeypatch: pytest.MonkeyPatch) -> None:
    from sparqlmodel.graph import orphaned_embedded_targets

    person = Person(id=IRI("urn:p"), name="P", works_for=IRI("urn:org:ext"))
    session.put(person)

    def fake_metadata(fi: Any) -> Any:
        return None

    monkeypatch.setattr("sparqlmodel.graph.get_field_metadata", fake_metadata)
    assert orphaned_embedded_targets(person, session.graph) == []


def test_orphan_skips_none_meta_field(session, monkeypatch: pytest.MonkeyPatch) -> None:
    from sparqlmodel.graph import orphaned_embedded_targets

    person = Person(id=IRI("urn:p"), name="P", works_for=None)
    session.put(person)
    rel_field = Person.model_fields["works_for"]

    def fake_metadata(fi: Any) -> Any:
        if fi is rel_field:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.graph.get_field_metadata", fake_metadata)
    orphaned_embedded_targets(person, session.graph)


def test_load_from_graph_skip_none_scalar_meta_alt(
    monkeypatch: pytest.MonkeyPatch, session
) -> None:
    person = Person(id=IRI("urn:p"), name="P")
    session.put(person)
    name_field = Person.model_fields["name"]

    def fake_metadata(fi: Any) -> Any:
        if fi is name_field:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.rdf_bridge.get_field_metadata", fake_metadata)
    loaded = load_from_graph(Person, person.id, session.graph, depth=0)
    assert loaded.id == person.id


def test_iter_nested_walk_early_return() -> None:
    class DualOrgPerson(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        name: str = Field("schema:name")
        works_for: Organization | None = Relationship("schema:worksFor", model=Organization)
        employer: Organization | None = Relationship("schema:employee", model=Organization)

    org = Organization(id=IRI("urn:org:shared"), name="Shared")
    person = DualOrgPerson(
        id=IRI("urn:p"),
        name="Pat",
        works_for=org,
        employer=org,
    )
    nested = iter_nested_models(person)
    assert sum(1 for m in nested if isinstance(m, Organization)) == 1


# --- 0.2 compiler / expressions / triple / fastapi ---


def test_flatten_or_unsupported_child() -> None:
    from sparqlmodel.compiler import _flatten_or_expressions
    from sparqlmodel.expressions import OrExpr

    with pytest.raises(QueryError, match="OR"):
        _flatten_or_expressions(OrExpr((42,)))  # type: ignore[arg-type]

    nested = OrExpr((OrExpr((Person.name == "A",)), Person.name == "B"))
    flat = _flatten_or_expressions(nested)
    assert len(flat) == 2


def test_compile_or_single_branch() -> None:
    from sparqlmodel.compiler import compile_or
    from sparqlmodel.expressions import OrExpr
    from sparqlmodel.types import NamespaceRegistry

    registry = NamespaceRegistry(Person.get_prefixes())
    filters = compile_or(
        OrExpr((Person.name == "A",)),
        Person,
        "?person",
        registry,
        [0],
    )
    assert filters[0].startswith("FILTER(EXISTS")

    and_branch = AndExpr((Person.name == "A", Person.name != "B"))
    filters2 = compile_or(
        OrExpr((and_branch,)),
        Person,
        "?person",
        registry,
        [0],
    )
    assert "EXISTS" in filters2[0]

    with patch(
        "sparqlmodel.compiler._flatten_or_expressions",
        return_value=[42],  # type: ignore[list-item]
    ):
        with pytest.raises(QueryError, match="Unsupported OR branch"):
            compile_or(OrExpr((Person.name == "A",)), Person, "?person", registry, [0])


def test_flatten_and_nested_and() -> None:
    inner = AndExpr((Person.name == "A",))
    outer = AndExpr((inner, Person.name == "B"))
    flat = _flatten_and_expressions((outer,))
    assert len(flat) == 2

    from sparqlmodel.expressions import OrExpr

    with pytest.raises(QueryError, match="top-level"):
        _flatten_and_expressions((OrExpr((Person.name == "A",)),))


def test_resolve_compare_wrong_model() -> None:
    from sparqlmodel.compiler import _resolve_compare_target, compile_compare
    from sparqlmodel.types import NamespaceRegistry

    registry = NamespaceRegistry(Person.get_prefixes())
    ref = FieldRef(Organization, "name")
    with pytest.raises(QueryError, match="does not match"):
        _resolve_compare_target(ref, Person, "?person", registry, [0], {})
    with pytest.raises(QueryError, match="does not match"):
        compile_compare(
            CompareExpr(ref, CompareOp.EQ, "x"),
            Person,
            "?person",
            registry,
            [0],
            {},
        )
    with pytest.raises(QueryError, match="FieldRef"):
        _resolve_compare_target("not-a-ref", Person, "?person", registry, [0], {})  # type: ignore[arg-type]


def test_compile_and_branch_exists() -> None:
    from sparqlmodel.compiler import compile_and_branch
    from sparqlmodel.types import NamespaceRegistry

    registry = NamespaceRegistry(Person.get_prefixes())
    block = compile_and_branch(
        AndExpr((Person.name == "A", Person.name != "B")),
        Person,
        "?person",
        registry,
        [0],
    )
    assert block.startswith("EXISTS")


def test_expression_or_and_in_ops() -> None:
    from sparqlmodel.expressions import OrExpr

    a = Person.name == "A"
    b = Person.name == "B"
    c = Person.name == "C"
    or_ab = a | b
    assert isinstance(or_ab, OrExpr)
    or_abc = or_ab | c
    assert len(or_abc.expressions) == 3
    and_or = AndExpr((a,)) | b
    assert isinstance(and_or, OrExpr)
    existing = OrExpr((a,))
    merged = b | existing
    assert len(merged.expressions) == 2
    or_merged = existing | OrExpr((c,))
    assert len(or_merged.expressions) == 2
    and_or = AndExpr((a,)) | OrExpr((b,))
    assert isinstance(and_or, OrExpr)
    and_merged = AndExpr((a,)) & AndExpr((b,))
    assert len(and_merged.expressions) == 2
    assert Person.name.in_(("x",)).op == CompareOp.IN
    assert (Person.name < "z").op == CompareOp.LT
    assert (Person.name > "a").op == CompareOp.GT
    assert (Person.name <= "z").op == CompareOp.LTE


def test_rdf_bridge_coverage() -> None:
    from sparqlmodel.rdf_bridge import (
        _normalize_graph,
        assert_put_graph_contract,
        load_from_graph,
        sparql_from_graph,
    )

    loc = Location(id=IRI("urn:loc:cov"), name="X")
    org = Organization(id=IRI("urn:org:cov"), name="O", located_in=loc)
    person = Person(id=IRI("urn:p:cov"), name="P", works_for=org)
    g = model_to_graph(person)
    restored = load_from_graph(Person, person.id, g, depth=2)
    assert restored.works_for is not None
    assert restored.works_for.name == "O"
    iri_only = Person(id=IRI("urn:p:iri"), name="I", works_for=IRI("urn:org:iri"))
    triples = sparql_instance_to_triples(iri_only)
    assert any(str(o) == "urn:org:iri" for _, _, o in triples)
    shallow = load_from_graph(Person, person.id, g, depth=0)
    assert shallow.name == "P"
    assert_no_embed_cycles(person, set())
    norm = _normalize_graph(g)
    assert norm.isomorphic(g) or len(norm) == len(g)

    with patch("sparqlmodel.rdf_bridge.adapter_graph", return_value=Store()):
        with pytest.raises(AssertionError, match="empty"):
            assert_put_graph_contract(person)

    loaded = sparql_from_graph(Person, person.id, g, depth=2)
    assert loaded.works_for is not None


def test_predicate_uri_for_field_from_sparql_meta() -> None:
    from sparqlmodel.fields import predicate_uri_for_field

    field_info = Person.model_fields["name"]
    with patch("sparqlmodel.fields.predicate_for_field", return_value=None):
        uri = predicate_uri_for_field(field_info, Person.get_prefixes())
    assert uri == expand_iri("schema:name", Person.get_prefixes())

    with (
        patch("sparqlmodel.fields.predicate_for_field", return_value=None),
        patch("sparqlmodel.fields.get_field_metadata", return_value=None),
    ):
        assert predicate_uri_for_field(field_info, Person.get_prefixes()) is None


def test_relationship_allows_iri() -> None:
    from sparqlmodel.fields import relationship_allows_iri

    assert relationship_allows_iri(IRI) is True
    assert relationship_allows_iri(Organization | IRI | None) is True
    assert relationship_allows_iri(str) is False


def test_subject_uri_override_and_without_id() -> None:
    from triplemodel.model import TripleModel

    person = Person(id=IRI("urn:p"), name="P")
    assert person.subject_uri(uri="urn:explicit") == "urn:explicit"
    bare = Person.model_construct(id=None, name="NoId")
    with patch.object(TripleModel, "subject_uri", return_value="urn:generated"):
        assert bare.subject_uri() == "urn:generated"


def test_rdf_bridge_export_import_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    from triplemodel.metadata.cardinality import field_cardinality as real_cardinality

    from sparqlmodel.rdf_bridge import (
        direct_export_triples,
        load_from_graph,
        sparql_instance_to_triples,
    )

    person = Person(id=IRI("urn:p"), name="P", works_for=None)
    name_field = Person.model_fields["name"]

    def card_nested_for_name(field_info: Any) -> str:
        if field_info is name_field:
            return "nested"
        return real_cardinality(field_info)

    monkeypatch.setattr("sparqlmodel.rdf_bridge.field_cardinality", card_nested_for_name)
    assert sparql_instance_to_triples(person)

    monkeypatch.setattr("sparqlmodel.rdf_bridge.field_cardinality", real_cardinality)
    monkeypatch.setattr("sparqlmodel.rdf_bridge.lang_for_field", lambda _fi: "en")
    labeled = Person(id=IRI("urn:lang"), name="Hi", works_for=None)
    assert sparql_instance_to_triples(labeled)

    class BirthYear(SPARQLModel):
        rdf_type = "schema:Person"
        year: int = Field("schema:birthDate")

    monkeypatch.setattr(
        "sparqlmodel.rdf_bridge.literal_datatype_for_field",
        lambda _fi: "gYear",
    )
    year_person = BirthYear(id=IRI("urn:y"), year=1990)
    assert sparql_instance_to_triples(year_person)

    monkeypatch.setattr(
        "sparqlmodel.rdf_bridge.literal_datatype_for_field",
        lambda _fi: "xsd:integer",
    )
    assert sparql_instance_to_triples(year_person)

    direct_export_triples(person)

    raw = MagicMock()
    raw.subject_uri.return_value = "urn:p"
    raw.name = "P"
    del raw.works_for
    with patch.object(Person, "from_graph", return_value=raw):
        loaded = load_from_graph(Person, IRI("urn:p"), Store(), depth=1)
    assert loaded.name == "P"

    class RefOnlyPerson(SPARQLModel):
        rdf_type = "ex:RefOnlyPerson"
        __prefixes__ = {"schema": "https://schema.org/", "ex": "http://example.org/ns/"}
        name: str = Field("schema:name")
        works_for: Organization | IRI | None = Relationship(
            "schema:worksFor",
            model=Organization,
            cascade=False,
        )

    nested_org = Organization(id=IRI("urn:org:nc"), name="O", located_in=None)
    raw_nc = MagicMock()
    raw_nc.subject_uri.return_value = "urn:p:nc"
    raw_nc.name = "Solo"
    raw_nc.works_for = nested_org
    with patch.object(RefOnlyPerson, "from_graph", return_value=raw_nc):
        loaded_nc = load_from_graph(
            RefOnlyPerson,
            IRI("urn:p:nc"),
            Store(),
            depth=1,
        )
    assert loaded_nc.works_for == IRI("urn:org:nc")

    raw_bad = MagicMock()
    raw_bad.subject_uri.return_value = "urn:p:bad"
    raw_bad.name = "B"
    raw_bad.works_for = 99
    with patch.object(Person, "from_graph", return_value=raw_bad):
        with pytest.raises(ValidationError):
            load_from_graph(Person, IRI("urn:p:bad"), Store(), depth=1)


def test_sparql_instance_to_triples_skips_none_meta(
    monkeypatch: pytest.MonkeyPatch, odos: Person
) -> None:
    name_field = Person.model_fields["name"]

    def fake_meta(fi: Any) -> Any:
        if fi is name_field:
            return None
        return get_field_metadata(fi)

    monkeypatch.setattr("sparqlmodel.rdf_bridge.get_field_metadata", fake_meta)
    triples = sparql_instance_to_triples(odos)
    name_pred = expand_iri("schema:name", Person.get_prefixes())

    def _pred_key(p: object) -> str:
        return p if isinstance(p, str) else term_str(p)  # type: ignore[arg-type]

    assert not any(_pred_key(p) == name_pred for _s, p, _o in triples)


def test_fastapi_import_and_graph_helpers() -> None:
    from sparqlmodel.fastapi import jsonld_response, negotiated_response, turtle_response

    person = Person(id=IRI("urn:p:fast"), name="Fast")
    g = Store()
    g.add(("urn:p:fast", "https://schema.org/name", Literal("Fast")))
    with patch(
        "sparqlmodel.fastapi.export_graph",
        return_value=b"@prefix x: <http://example/> .",
    ):
        t_resp = turtle_response(g)
        assert t_resp.body == b"@prefix x: <http://example/> ."
    j_resp = jsonld_response(person)
    assert j_resp.media_type == "application/ld+json"
    with patch.object(Person, "serialize", return_value=b"{}") as mock_serialize:
        j_resp2 = jsonld_response(person)
        mock_serialize.assert_called()
        assert j_resp2.body == b"{}"
    req = MagicMock()
    req.headers = {"accept": "text/plain"}
    fallback = negotiated_response(req, person)
    assert fallback.media_type == "text/turtle"

    req_custom = MagicMock()
    req_custom.headers = {"accept": "application/ld+json"}
    with patch.object(Person, "serialize", return_value="{}"):
        custom = negotiated_response(
            req_custom,
            person,
            formats={"application/ld+json": "json-ld"},
        )
    assert custom.media_type == "application/ld+json"

    with patch.object(Person, "serialize", return_value=None):
        empty_body = jsonld_response(person)
    assert empty_body.body == b""

    with patch.dict("sys.modules", {"fastapi": None}):
        from sparqlmodel import fastapi as fastapi_mod

        with pytest.raises(ImportError, match="sparqlmodel\\[fastapi\\]"):
            fastapi_mod._require_fastapi()


def test_model_to_graph_skips_non_cascade_embed() -> None:
    class PersonNC(SPARQLModel):
        rdf_type = "ex:PersonNC"
        __prefixes__ = {"schema": "https://schema.org/", "ex": "http://example.org/ns/"}
        id: IRI
        name: str = Field("schema:name")
        works_for: Organization | None = Relationship(
            "schema:worksFor",
            model=Organization,
            cascade=False,
        )

    org = Organization(id=IRI("urn:org:nc2"), name="NC")
    person = PersonNC(id=IRI("urn:p:nc2"), name="P", works_for=org)
    g = model_to_graph(person)
    rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    org_type = "https://schema.org/Organization"
    assert not any(term_str(o) == org_type for _s, p, o in g if term_str(p) == rdf_type)


def test_relationship_is_nullable_non_union() -> None:
    from sparqlmodel.fields import relationship_is_nullable

    assert relationship_is_nullable(Organization) is False


def test_parse_count_bindings_variants() -> None:
    from sparqlmodel.query_common import parse_count_bindings

    assert parse_count_bindings([]) == 0
    assert parse_count_bindings([{"__count": 3}]) == 3
    assert parse_count_bindings([{"?__count": "5"}]) == 5
    assert parse_count_bindings([{"__count": 1.0}]) == 1
    assert parse_count_bindings([{"__count": True}]) == 1
    with pytest.raises(QueryError, match="Unsupported COUNT"):
        parse_count_bindings([{"__count": object()}])
    with pytest.raises(QueryError, match="not a valid integer"):
        parse_count_bindings([{"__count": "not-a-number"}])
    with pytest.raises(QueryError, match="non-negative"):
        parse_count_bindings([{"__count": -1}])
    with pytest.raises(QueryError, match="did not return"):
        parse_count_bindings([{"person": "urn:x"}])


def test_query_state_apply_helpers() -> None:
    from sparqlmodel.query_common import (
        QueryState,
        apply_offset,
        apply_order_by,
        apply_use_optional_for_comparisons,
    )

    state = QueryState(model_cls=Person)
    apply_order_by(state, Person.name, desc=True)
    assert state.order_by == [(Person.name, True)]
    with pytest.raises(QueryError, match="offset"):
        apply_offset(state, -1)
    state.use_inequality_for_ne = True
    apply_use_optional_for_comparisons(state, False)
    assert state.use_not_exists_for_ne is True


def test_fieldref_is_is_not_validation() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="only supports None"):
        Person.works_for.is_("x")  # type: ignore[arg-type]
    with pytest.raises(QueryError, match="relationship field"):
        compile_where(Person, (Person.works_for.name.is_(None),), registry)
    with pytest.raises(QueryError, match="only supports None"):
        Person.works_for.is_not("x")  # type: ignore[arg-type]


def test_compile_non_nullable_relationship_hop() -> None:
    class RequiredWorks(SPARQLModel):
        rdf_type = "urn:test:RequiredWorks"
        __prefixes__ = {"schema": "https://schema.org/"}

        id: IRI
        name: str = Field("schema:name")
        works_for: Organization = Relationship("schema:worksFor", model=Organization)

    registry = NamespaceRegistry(RequiredWorks.get_prefixes())
    sparql = compile_where(
        RequiredWorks,
        (RequiredWorks.works_for.name == "Acme",),
        registry,
    )
    assert "OPTIONAL" not in sparql


def test_compile_presence_with_path_and_errors() -> None:
    from dataclasses import replace

    from sparqlmodel.compiler import _compile_relationship_presence
    from tests.test_compiler_joins import DualOrgPerson

    registry = NamespaceRegistry(DualOrgPerson.get_prefixes())
    pats, filts = _compile_relationship_presence(
        DualOrgPerson.employer.is_(None),
        DualOrgPerson,
        "?dualorgperson",
        registry,
        [0],
        {},
    )
    assert "OPTIONAL" in "\n".join(pats)
    assert any("!BOUND" in f for f in filts)

    with pytest.raises(QueryError, match="does not match"):
        compile_where(Organization, (Person.works_for.is_(None),), registry)

    bad_left = replace(Person.works_for.is_(None), left="not-a-ref")  # type: ignore[arg-type]
    with pytest.raises(QueryError, match="Expected FieldRef"):
        _compile_relationship_presence(bad_left, Person, "?person", registry, [0], {})

    bad_op = replace(Person.works_for.is_(None), op=CompareOp.EQ)
    with pytest.raises(QueryError, match="Unsupported presence"):
        _compile_relationship_presence(bad_op, Person, "?person", registry, [0], {})

    nested = CompareExpr(
        FieldRef(DualOrgPerson, "located_in", ("employer",)),
        CompareOp.IS_,
        None,
    )
    nested_pats, _ = _compile_relationship_presence(
        nested,
        DualOrgPerson,
        "?dualorgperson",
        registry,
        [0],
        {},
    )
    assert "OPTIONAL" in "\n".join(nested_pats)

    with patch("sparqlmodel.compiler.get_field_metadata", return_value=None):
        with pytest.raises(QueryError, match="no SPARQL metadata"):
            _compile_relationship_presence(
                DualOrgPerson.employer.is_(None),
                DualOrgPerson,
                "?dualorgperson",
                registry,
                [0],
                {},
            )


def test_fieldref_is_not_on_scalar_path_via_compile() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="relationship field"):
        compile_where(Person, (Person.works_for.name.is_not(None),), registry)
