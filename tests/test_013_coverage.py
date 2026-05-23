"""Additional branch coverage for SparqlModel 0.13 features."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from triplemodel import MultiLangString, ResourceRef, TypedLiteral
from triplemodel.terms.lang import LangString

from sparqlmodel import (
    IRI,
    Field,
    OntologyRegistry,
    SPARQLModel,
    not_,
    property_eq,
    property_path,
)
from sparqlmodel.compiler import (
    _flatten_and_expressions,
    _format_object,
    _format_values_term,
    _values_clause,
    compile_compare,
    compile_filter_expr,
    compile_not,
    compile_property_path_compare,
    compile_where,
)
from sparqlmodel.exceptions import ConfigurationError, QueryError
from sparqlmodel.expressions import (
    AndExpr,
    CompareExpr,
    CompareOp,
    FieldRef,
    IriStrCompare,
    IriStrFieldRef,
    NotExpr,
    OrExpr,
    PropertyPathCompare,
    _flatten_and_parts,
)
from sparqlmodel.fields import Field as SmField
from sparqlmodel.fields import Relationship as SmRelationship
from sparqlmodel.fields import get_field_metadata
from sparqlmodel.rdf_bridge import load_from_graph, sparql_instance_to_triples
from sparqlmodel.schema_registry import apply_schema_hints, registry_for_model
from sparqlmodel.types import NamespaceRegistry
from tests.models import Organization, Person


def test_format_object_lang_and_multilang() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    assert "@en" in _format_object(LangString("hi", "en"), reg)
    empty = MultiLangString()
    assert _format_object(empty, reg) == '""'
    ml = MultiLangString(en="one", fr="deux")
    assert "@en" in _format_object(ml, reg) or '"one"' in _format_object(ml, reg)
    tl = TypedLiteral(42, datatype="xsd:integer")
    out = _format_object(tl, reg)
    assert "42" in out and "integer" in out


def test_flatten_and_compare_expr_top_level() -> None:
    flat = _flatten_and_expressions((Person.name == "A",))
    assert len(flat) == 1


def test_flatten_and_parts_rejects_not_expr() -> None:
    with pytest.raises(QueryError, match="comparisons"):
        _flatten_and_parts((AndExpr((not_(Person.name == "X"),)),))


def test_fieldref_str_upper_and_invert() -> None:
    class WithAlt(SPARQLModel):
        rdf_type = "urn:test:WithAlt"
        id: IRI
        alt: IRI | None = Field("schema:identifier")

    assert isinstance(WithAlt.alt.str(), IriStrFieldRef)
    assert WithAlt.alt.upper().mode == "upper"
    assert isinstance(~(Person.name == "A"), NotExpr)
    assert isinstance(~~(Person.name == "A"), CompareExpr)


def test_iri_str_compare_in_and_ne() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())

    class WithId(SPARQLModel):
        rdf_type = "urn:test:WithId"
        id: IRI
        alt: IRI | None = Field("schema:identifier")

    sparql = compile_where(
        WithId,
        (WithId.alt.str().in_(("a", "b")),),
        reg,
    )
    assert "STR" in sparql and " IN " in sparql
    sparql_ne = compile_where(
        WithId,
        (WithId.alt.upper() != "X",),
        reg,
        use_not_exists_for_ne=False,
    )
    assert "UCASE" in sparql_ne


def test_iri_str_wrong_field_type_raises() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="IRI-typed"):
        compile_where(Person, (Person.name.str() == "x",), reg)


def test_property_path_variants() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    pats, _ = compile_property_path_compare(
        property_eq(Person, "^schema:worksFor+", "urn:org:1"),
        "?person",
        reg,
    )
    assert "^" in pats[0]
    pats2, _ = compile_property_path_compare(
        property_eq(Person, "schema:knows*", "urn:x"),
        "?person",
        reg,
    )
    assert "*" in pats2[0]
    with pytest.raises(QueryError, match="empty"):
        compile_property_path_compare(
            PropertyPathCompare(Person, "  ", CompareOp.EQ, "x"),
            "?person",
            reg,
        )
    with pytest.raises(QueryError, match="== only"):
        compile_property_path_compare(
            property_path(Person, "schema:name", CompareOp.NE, "x"),
            "?person",
            reg,
        )


def test_compile_not_and_or_and_andexpr() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    _, filts = compile_not(
        not_(Person.name == "Ghost"),
        Person,
        "?person",
        reg,
        [0],
        {},
    )
    assert filts and "NOT" in filts[0]
    _, filts_and = compile_not(
        not_(AndExpr((Person.name == "A", Person.name == "B"))),
        Person,
        "?person",
        reg,
        [0],
        {},
    )
    assert "NOT" in filts_and[0]
    _, filts_or = compile_not(
        not_((Person.name == "A") | (Person.name == "B")),
        Person,
        "?person",
        reg,
        [0],
        {},
    )
    assert "!" in filts_or[0]
    with pytest.raises(QueryError, match="not_\\(and\\)"):
        compile_not(not_(AndExpr(())), Person, "?person", reg, [0], {})
    with pytest.raises(QueryError, match="does not support"):
        compile_not(not_(object()), Person, "?person", reg, [0], {})  # type: ignore[arg-type]

    pats, filts = compile_filter_expr(
        AndExpr((Person.name == "Z",)),
        Person,
        "?person",
        reg,
        [0],
        {},
    )
    assert not pats and filts


def test_values_clause_mismatch_raises() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="same variables"):
        _values_clause(
            ({"a": 1}, {"b": 2}),
            reg,
        )


def test_values_compact_iri_configuration_fallback() -> None:
    reg = NamespaceRegistry({"ex": "https://example.org/"})
    clause = _values_clause(({"x": "ex:bad"},), reg)
    assert "VALUES" in clause


def test_compile_scalar_relationship_eq_raises() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="not a collection"):
        compile_compare(
            CompareExpr(FieldRef(Person, "works_for"), CompareOp.EQ, IRI("urn:org:x")),
            Person,
            "?person",
            reg,
            [0],
            {},
        )


def test_schema_registry_helpers() -> None:
    reg = OntologyRegistry()
    assert registry_for_model(Person) is None

    class WithReg(SPARQLModel):
        rdf_type = "urn:test:WithReg"
        ontology_registry: ClassVar[OntologyRegistry] = reg
        id: IRI

    assert registry_for_model(WithReg) is reg
    apply_schema_hints(WithReg, reg)


def test_field_sugar_options() -> None:
    class M(SPARQLModel):
        rdf_type = "urn:test:M"
        id: IRI
        name: str = SmField(
            "schema:name",
            inverse="schema:inverseName",
            literal_datatype="xsd:string",
            transitive=True,
        )
        link: Organization | None = SmRelationship(
            "schema:worksFor",
            model=Organization,
            cascade=False,
        )

    meta = get_field_metadata(M.model_fields["name"])
    assert meta is not None
    extra = M.model_fields["name"].json_schema_extra
    assert isinstance(extra, dict)
    assert extra.get("rdf_inverse") == "schema:inverseName"


def test_export_rdf_lang_and_str_ref() -> None:
    class Langged(SPARQLModel):
        rdf_type = "urn:test:Langged"
        id: IRI
        label: str = SmField("schema:name", lang="en")

    class Refs(SPARQLModel):
        rdf_type = "urn:test:Refs"
        id: IRI
        about: set[ResourceRef] = Field("schema:about", default_factory=set)

    triples = sparql_instance_to_triples(
        Langged(id=IRI("urn:l:1"), label="Hello"),
    )
    assert triples
    assert any("Hello" in str(t) for t in triples)
    triples2 = sparql_instance_to_triples(
        Refs(id=IRI("urn:r:1"), about={ResourceRef("urn:tag:a")}),
    )
    assert len(triples2) >= 2


def test_load_collection_refs_hydrate(session) -> None:
    from tests.test_multivalue_roundtrip import Article

    article = Article(
        id=IRI("urn:article:hc"),
        title=MultiLangString(en="T"),
        tags={"a"},
        related={ResourceRef("urn:tag:hc")},
    )
    session.put(article)
    loaded = session.get(Article, article.id, depth=0)
    assert loaded is not None
    assert loaded.related


def test_iri_str_in_bare_string_raises() -> None:
    class WithAlt(SPARQLModel):
        rdf_type = "urn:test:WithAlt2"
        id: IRI
        alt: IRI | None = Field("schema:identifier")

    with pytest.raises(QueryError, match="bare string"):
        WithAlt.alt.str().in_("ab")  # type: ignore[arg-type]


def test_compare_expr_invert() -> None:
    assert isinstance(~(Person.name == "x"), NotExpr)


def test_and_or_invert() -> None:
    inner = AndExpr((Person.name == "A",))
    assert isinstance(~inner, NotExpr)
    or_expr = OrExpr((Person.name == "A",))
    assert isinstance(~or_expr, NotExpr)


def test_flatten_and_parts_nested_and() -> None:
    inner = AndExpr((Person.name == "A", Person.name == "B"))
    outer = AndExpr((inner,))
    flat = _flatten_and_parts(outer.expressions)
    assert len(flat) == 2


def test_flatten_and_parts_doubly_nested_and() -> None:
    deep = AndExpr((Person.name == "A",))
    mid = AndExpr((deep, Person.name == "B"))
    flat = _flatten_and_parts((mid,))
    assert len(flat) == 2


def test_format_object_multilang_non_langstring_first() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    ml = MultiLangString()
    object.__setattr__(ml, "by_lang", {"x": "plain"})  # type: ignore[arg-type]
    assert '"plain"' in _format_object(ml, reg)


def test_format_object_typed_literal_plain() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    tl = TypedLiteral("3.14")
    assert "3.14" in _format_object(tl, reg)


def test_iri_str_ne_with_not_exists() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())

    class WithAlt(SPARQLModel):
        rdf_type = "urn:test:WithAlt3"
        id: IRI
        alt: IRI | None = Field("schema:identifier")

    sparql = compile_where(
        WithAlt,
        (WithAlt.alt.str() != "x",),
        reg,
        use_not_exists_for_ne=True,
    )
    assert "!" in sparql or "NOT" in sparql


def test_property_path_skips_empty_segment() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    pats, _ = compile_property_path_compare(
        property_eq(Person, "schema:name//schema:givenName", "Pat"),
        "?person",
        reg,
    )
    assert "givenName" in pats[0]


def test_values_empty_bindings_raises() -> None:
    from sparqlmodel.query_common import QueryState, apply_values

    state = QueryState(model_cls=Person)
    with pytest.raises(QueryError, match="at least one"):
        apply_values(state, {})


def test_relationship_inverse_on_ref_field_raises() -> None:
    with pytest.raises(ConfigurationError, match="inverse="):
        SmRelationship("schema:about", model=Organization, cascade=False, inverse="schema:x")


def test_field_metadata_tuple_lang_and_inverse() -> None:
    from triplemodel.fields import InverseOf
    from triplemodel.terms.lang import Lang

    from sparqlmodel.fields import _field_metadata_tuple

    tup = _field_metadata_tuple(lang="en", inverse="schema:inv")
    assert any(isinstance(x, Lang) for x in tup)
    assert any(isinstance(x, InverseOf) for x in tup)


def test_field_back_populates_and_inverse_lang() -> None:
    from triplemodel.fields.back_populates import BackPopulates

    class BP(SPARQLModel):
        rdf_type = "urn:test:BP"
        id: IRI
        name: str = SmField(
            "schema:name",
            lang="fr",
            inverse="schema:inverse",
            back_populates=BackPopulates("BP", "id"),
        )

    assert get_field_metadata(BP.model_fields["name"]) is not None


def test_is_relationship_field_set_iri_refs() -> None:
    from sparqlmodel.fields import is_relationship_field

    class M(SPARQLModel):
        rdf_type = "urn:test:M"
        id: IRI
        refs: set[IRI] = SmRelationship("schema:about", model=Organization)

    fi = M.model_fields["refs"]
    meta = get_field_metadata(fi)
    assert meta is not None
    assert is_relationship_field(fi, meta) is True


def test_model_ontology_registry_from_base() -> None:
    reg = OntologyRegistry()

    class BaseModel(SPARQLModel):
        rdf_type = "urn:test:Base"
        ontology_registry: ClassVar[OntologyRegistry] = reg

    class ChildModel(BaseModel):
        rdf_type = "urn:test:Child"
        id: IRI

    assert ChildModel.Rdf.ontology_registry is reg


def test_export_str_iri_relationship() -> None:
    class RefStr(SPARQLModel):
        rdf_type = "urn:test:RefStr"
        id: IRI
        link: set[str] = SmRelationship("schema:about", model=Organization)

    triples = sparql_instance_to_triples(
        RefStr(id=IRI("urn:r:1"), link={"urn:org:1"}),
    )
    assert any("urn:org:1" in str(t) for t in triples)


def test_hydrate_collection_and_embed(session) -> None:
    org = Organization(id=IRI("urn:org:hc"), name="HC Org")
    person = Person(id=IRI("urn:person:hc"), name="HC", works_for=org)
    session.put(person)
    loaded = session.get(Person, person.id, depth=2)
    assert loaded is not None
    assert loaded.works_for is not None
    assert loaded.works_for.name == "HC Org"


def test_compile_not_or_multiple_filters_raises() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())
    with (
        patch("sparqlmodel.compiler.compile_or", return_value=["FILTER(a)", "FILTER(b)"]),
        pytest.raises(QueryError, match="single FILTER"),
    ):
        compile_not(
            not_((Person.name == "A") | (Person.name == "B")),
            Person,
            "?person",
            reg,
            [0],
            {},
        )


def test_get_scalar_and_rel_skip_unmapped_fields() -> None:
    name_fi = Person.model_fields["name"]

    def fake_iter(cls: type[SPARQLModel]) -> list[tuple[str, object, object]]:
        return [("ghost", name_fi, str)]

    with (
        patch.object(Person, "iter_sparql_fields", classmethod(fake_iter)),
        patch("sparqlmodel.model.get_field_metadata", return_value=None),
    ):
        assert Person.get_scalar_fields() == []
        assert Person.get_relationship_fields() == []


def test_iri_str_unsupported_op_raises() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())

    class WithAlt(SPARQLModel):
        rdf_type = "urn:test:WithAlt5"
        id: IRI
        alt: IRI | None = Field("schema:identifier")

    from sparqlmodel.compiler import compile_iri_str_compare

    with pytest.raises(QueryError, match="Unsupported IRI string"):
        compile_iri_str_compare(
            IriStrCompare(WithAlt.alt.str(), CompareOp.LT, "1"),
            WithAlt,
            "?withalt",
            reg,
            [0],
            {},
        )


def test_iri_str_ne_inequality_branch() -> None:
    reg = NamespaceRegistry(Person.get_prefixes())

    class WithAlt(SPARQLModel):
        rdf_type = "urn:test:WithAlt4"
        id: IRI
        alt: IRI | None = Field("schema:identifier")

    from sparqlmodel.compiler import compile_iri_str_compare

    _, filts = compile_iri_str_compare(
        IriStrCompare(WithAlt.alt.str(), CompareOp.NE, "x"),
        WithAlt,
        "?withalt",
        reg,
        [0],
        {},
        use_not_exists_for_ne=False,
    )
    assert filts and "!=" in filts[0]


def test_values_empty_keys_returns_empty() -> None:
    assert _values_clause(({},), NamespaceRegistry(Person.get_prefixes())) == ""


def test_values_configuration_error_literal() -> None:
    reg = NamespaceRegistry({})
    clause = _values_clause(({"v": "not:valid:curie"},), reg)
    assert "VALUES" in clause


def test_field_inverse_metadata_tuple() -> None:
    class Inv(SPARQLModel):
        rdf_type = "urn:test:Inv"
        id: IRI
        name: str = SmField("schema:name", inverse="schema:inverseName")

    extra = Inv.model_fields["name"].json_schema_extra
    assert isinstance(extra, dict)
    assert extra.get("rdf_inverse") == "schema:inverseName"


def test_is_relationship_ref_cardinality() -> None:
    from unittest.mock import MagicMock

    from sparqlmodel.fields import is_relationship_field

    mock_fi = MagicMock()
    with patch("sparqlmodel.fields.field_cardinality", return_value="ref"):
        assert is_relationship_field(mock_fi, None) is True


def test_is_relationship_resource_ref_import_error() -> None:
    import builtins

    from sparqlmodel.fields import is_relationship_field

    mock_fi = MagicMock()
    mock_fi.annotation = list[object]
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "triplemodel.fields.resource_ref":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    with (
        patch("sparqlmodel.fields.field_cardinality", return_value="set"),
        patch("sparqlmodel.fields.element_type", return_value=ResourceRef),
        patch("builtins.__import__", side_effect=fake_import),
    ):
        assert is_relationship_field(mock_fi, None) is False


def test_is_relationship_meta_flag_and_list_iri() -> None:
    from sparqlmodel.fields import SPARQLFieldMetadata, is_relationship_field

    class RelMeta(SPARQLModel):
        rdf_type = "urn:test:RelMeta"
        id: IRI
        flag: Organization = SmRelationship("schema:worksFor", model=Organization)

    fi = RelMeta.model_fields["flag"]
    meta = get_field_metadata(fi)
    assert meta is not None
    meta_rel = SPARQLFieldMetadata(predicate="schema:x", is_relationship=True)
    assert is_relationship_field(fi, meta_rel) is True
    assert is_relationship_field(fi, meta)

    class ListIri(SPARQLModel):
        rdf_type = "urn:test:ListIri"
        id: IRI
        refs: list[IRI] = Field("schema:about")

    fi2 = ListIri.model_fields["refs"]
    meta2 = get_field_metadata(fi2)
    assert meta2 is not None
    assert is_relationship_field(fi2, meta2) is False

    from unittest.mock import MagicMock

    from sparqlmodel.fields import SPARQLFieldMetadata

    mock_fi = MagicMock()
    mock_fi.annotation = list[Organization]
    mock_meta = SPARQLFieldMetadata(predicate="schema:x", is_relationship=False)
    assert is_relationship_field(mock_fi, mock_meta) is True


def test_ref_uri_resource_ref_and_model() -> None:
    from sparqlmodel.rdf_bridge import _ref_uri

    org = Organization(id=IRI("urn:org:ru"), name="RU")
    assert _ref_uri(ResourceRef("urn:tag:x")) == "urn:tag:x"
    assert _ref_uri(org) == str(org.id)


def test_load_from_graph_ref_embedded_model_ref_name(session, acme: Organization) -> None:
    person = Person(id=IRI("urn:person:emb"), name="Emb", works_for=acme)
    session.put(person)
    with (
        patch("sparqlmodel.rdf_bridge.relationship_is_ref_link", return_value=True),
        patch("triplemodel.io.hydrate.hydrate_refs") as hydrate_refs,
    ):
        hydrate_refs.return_value = [person]
        loaded = load_from_graph(Person, person.id, session.graph, depth=1)
    assert loaded is person


def test_load_from_graph_skips_iri_ref_field(session) -> None:
    from tests.test_graph_multiref import Article, Tag

    t1 = Tag(id=IRI("urn:tag:iri"), name="T")
    article = Article(id=IRI("urn:article:iri"), tags={ResourceRef(str(t1.id))})
    session.put(t1)
    session.put(article)
    person = Person(id=IRI("urn:person:iri"), name="Iri", works_for=IRI("urn:org:missing"))
    session.put(person)
    with patch("sparqlmodel.rdf_bridge.relationship_is_ref_link", return_value=True):
        loaded = load_from_graph(Person, person.id, session.graph, depth=1)
    assert loaded is not None


def test_load_from_graph_hydrate_refs_branch(session) -> None:
    from tests.test_graph_multiref import Article, Tag

    t1 = Tag(id=IRI("urn:tag:refs"), name="T")
    article = Article(
        id=IRI("urn:article:refs"),
        tags={ResourceRef(str(t1.id))},
    )
    session.put(t1)
    session.put(article)
    raw = MagicMock()
    raw.subject_uri = lambda: str(article.id)
    tags = {ResourceRef(str(t1.id))}
    raw.tags = tags
    from sparqlmodel import rdf_bridge as rb

    orig_hydrate = rb._hydrate_relationship_value

    def passthrough_collection(value: object, **kwargs: object) -> object:
        if isinstance(value, (list, set)):
            return value
        return orig_hydrate(value, **kwargs)  # type: ignore[arg-type]

    with (
        patch.object(Article, "from_graph", return_value=raw),
        patch.object(rb, "_hydrate_relationship_value", side_effect=passthrough_collection),
        patch("sparqlmodel.rdf_bridge.relationship_is_ref_link", return_value=True),
        patch("triplemodel.io.hydrate.hydrate_refs") as hydrate_refs,
    ):
        hydrate_refs.return_value = [article]
        loaded = load_from_graph(Article, article.id, session.graph, depth=1)
    assert loaded is article
    hydrate_refs.assert_called_once()


def test_hydrate_collection_returns_set_of_iri() -> None:
    from triplemodel import Store

    from sparqlmodel.fields import get_field_metadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    fi = Person.model_fields["works_for"]
    meta = get_field_metadata(fi)
    value = {ResourceRef("urn:org:one")}
    with patch("sparqlmodel.rdf_bridge.subject_has_rdf_type", return_value=False):
        out = _hydrate_relationship_value(
            value,
            model_cls=Person,
            field_name="works_for",
            field_info=fi,
            related_cls=Organization,
            graph=Store(),
            depth=1,
            branch_path=set(),
            meta=meta,
        )
    assert out == {IRI("urn:org:one")}


def test_hydrate_collection_returns_original_when_empty() -> None:
    from triplemodel import Store

    from sparqlmodel.fields import get_field_metadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    fi = Person.model_fields["works_for"]
    meta = get_field_metadata(fi)
    value = {ResourceRef("urn:org:missing")}
    with (
        patch("sparqlmodel.rdf_bridge.relationship_allows_iri", return_value=False),
        patch("sparqlmodel.rdf_bridge.subject_has_rdf_type", return_value=False),
    ):
        out = _hydrate_relationship_value(
            value,
            model_cls=Person,
            field_name="works_for",
            field_info=fi,
            related_cls=Organization,
            graph=Store(),
            depth=1,
            branch_path=set(),
            meta=meta,
        )
    assert out == value


def test_hydrate_uri_branch_returns_iri_for_ref_link() -> None:
    from triplemodel import Store

    from sparqlmodel.fields import SPARQLFieldMetadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    fi = Person.model_fields["works_for"]
    meta = SPARQLFieldMetadata(
        predicate="schema:worksFor",
        is_relationship=True,
        related_model=Organization,
        cascade=False,
    )
    with (
        patch("sparqlmodel.rdf_bridge.subject_has_rdf_type", return_value=True),
        patch("sparqlmodel.rdf_bridge.relationship_is_ref_link", return_value=True),
    ):
        out = _hydrate_relationship_value(
            ResourceRef("urn:org:ref"),
            model_cls=Person,
            field_name="works_for",
            field_info=fi,
            related_cls=Organization,
            graph=Store(),
            depth=1,
            branch_path=set(),
            meta=meta,
        )
    assert out == IRI("urn:org:ref")


def test_hydrate_uri_branch_returns_none_when_not_allowed() -> None:
    from triplemodel import Store

    from sparqlmodel.fields import SPARQLFieldMetadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    fi = Person.model_fields["works_for"]
    meta = SPARQLFieldMetadata(
        predicate="schema:worksFor",
        is_relationship=True,
        related_model=Organization,
        cascade=False,
    )
    with (
        patch("sparqlmodel.rdf_bridge.subject_has_rdf_type", return_value=True),
        patch("sparqlmodel.rdf_bridge.relationship_allows_iri", return_value=False),
        patch("sparqlmodel.rdf_bridge.relationship_is_ref_link", return_value=False),
    ):
        out = _hydrate_relationship_value(
            ResourceRef("urn:org:typed"),
            model_cls=Person,
            field_name="works_for",
            field_info=fi,
            related_cls=Organization,
            graph=Store(),
            depth=1,
            branch_path=set(),
            meta=meta,
        )
    assert out is None


def test_hydrate_ref_returns_none_without_iri_allowed() -> None:
    from triplemodel import Store

    from sparqlmodel.fields import get_field_metadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    class Strict(SPARQLModel):
        rdf_type = "urn:test:Strict2"
        id: IRI
        org: Organization = SmRelationship("schema:worksFor", model=Organization)

    fi = Strict.model_fields["org"]
    meta = get_field_metadata(fi)
    with (
        patch("sparqlmodel.rdf_bridge.relationship_allows_iri", return_value=False),
        patch("sparqlmodel.rdf_bridge.subject_has_rdf_type", return_value=False),
    ):
        out = _hydrate_relationship_value(
            ResourceRef("urn:org:ghost"),
            model_cls=Strict,
            field_name="org",
            field_info=fi,
            related_cls=Organization,
            graph=Store(),
            depth=1,
            branch_path=set(),
            meta=meta,
        )
    assert out is None


def test_hydrate_allows_iri_when_type_missing() -> None:
    from triplemodel import Store

    from sparqlmodel.fields import get_field_metadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    fi = Person.model_fields["works_for"]
    meta = get_field_metadata(fi)
    with patch("sparqlmodel.rdf_bridge.subject_has_rdf_type", return_value=False):
        out = _hydrate_relationship_value(
            ResourceRef("urn:org:ghost"),
            model_cls=Person,
            field_name="works_for",
            field_info=fi,
            related_cls=Organization,
            graph=Store(),
            depth=1,
            branch_path=set(),
            meta=meta,
        )
    assert isinstance(out, IRI)


def test_hydrate_iri_like_string_without_ref_uri_returns_none() -> None:
    from sparqlmodel.fields import get_field_metadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    fi = Person.model_fields["name"]
    with patch("sparqlmodel.rdf_bridge._ref_uri", return_value=None):
        out = _hydrate_relationship_value(
            "http://example.org/x",
            model_cls=Person,
            field_name="name",
            field_info=fi,
            related_cls=Person,
            graph=__import__("triplemodel").Store(),
            depth=0,
            branch_path=set(),
            meta=get_field_metadata(fi),
        )
    assert out is None


def test_relationship_field_with_inverse_and_lang() -> None:
    class InvRel(SPARQLModel):
        rdf_type = "urn:test:InvRel"
        id: IRI
        org: Organization | None = SmRelationship(
            "schema:worksFor",
            model=Organization,
            inverse="schema:inverseWorks",
        )
        label: str = SmField("schema:name", lang="de", inverse="schema:inverseLabel")

    assert InvRel.model_fields["org"] is not None
    assert InvRel.model_fields["label"].json_schema_extra["rdf_lang"] == "de"


def test_values_term_configuration_error_fallback() -> None:
    reg = NamespaceRegistry({"ex": "https://example.org/"})

    def boom(value: str) -> str:
        if value == "ex:bad":
            raise ConfigurationError("nope")
        return value

    with patch.object(reg, "expand", side_effect=boom):
        term = _format_values_term("ex:bad", reg)
    assert term.startswith('"')


def test_hydrate_allows_iri_without_type(session) -> None:
    person = Person(
        id=IRI("urn:person:ghost"),
        name="Ghost",
        works_for=IRI("urn:org:missing"),
    )
    session.put(person)
    loaded = session.get(Person, person.id, depth=1)
    assert loaded is not None
    assert isinstance(loaded.works_for, IRI)


def test_load_from_graph_iri_like_string_returns_none() -> None:
    from triplemodel import Store

    class Weird(SPARQLModel):
        rdf_type = "urn:test:Weird"
        id: IRI
        note: str | None = Field("schema:description")

    g = Store()
    subj = "urn:weird:1"
    g.add((subj, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "urn:test:Weird"))
    g.add((subj, "https://schema.org/description", "http://example.org/not-a-subject"))
    Weird.from_graph(g, subj)
    # force relationship-like hydration path via private helper
    from sparqlmodel.fields import get_field_metadata
    from sparqlmodel.rdf_bridge import _hydrate_relationship_value

    fi = Weird.model_fields["note"]
    meta = get_field_metadata(fi)
    out = _hydrate_relationship_value(
        "http://example.org/x",
        model_cls=Weird,
        field_name="note",
        field_info=fi,
        related_cls=Weird,
        graph=g,
        depth=0,
        branch_path=set(),
        meta=meta,
    )
    assert out is None


def test_depth_satisfied_empty_collection(session) -> None:
    from sparqlmodel.session_core import depth_satisfied
    from tests.test_multivalue_roundtrip import Article

    article = Article(
        id=IRI("urn:article:empty"),
        title=MultiLangString(en="T"),
        tags=set(),
        related=set(),
    )
    session.put(article)
    assert depth_satisfied(article, 1) is False
