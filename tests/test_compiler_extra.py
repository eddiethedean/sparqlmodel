"""Additional compiler tests."""

import pytest

from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr
from sparqlmodel.types import NamespaceRegistry, is_compact_iri
from tests.models import Person


def test_format_object_url_string_on_str_field_is_literal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (Person.name == "https://example.com/label",),
        registry,
    )
    assert '"https://example.com/label"' in sparql
    assert "<https://example.com/label>" not in sparql


def test_format_object_colon_literal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "12:30",), registry)
    assert '"12:30"' in sparql
    assert "12:30>" not in sparql


def test_format_object_multi_colon_literal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "a:b:c",), registry)
    assert '"a:b:c"' in sparql


def test_is_compact_iri() -> None:
    assert is_compact_iri("schema:Person")
    assert not is_compact_iri("12:30")
    assert not is_compact_iri("a:b:c")
    assert not is_compact_iri("http://example.org/x")


def test_literal_newline_escaped() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "a\nb",), registry)
    where = sparql.split("WHERE", 1)[1]
    assert '"""' in where or "\\n" in where


def test_filter_none_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="None"):
        compile_where(Person, (Person.name == None,), registry)  # noqa: E711


def test_nested_and_expr_flattens() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    inner = AndExpr((Person.name == "A", Person.name != "B"))
    sparql = compile_where(Person, (inner,), registry)
    assert "FILTER" in sparql
    assert sparql.count("https://schema.org/name") >= 2


def test_invalid_where_expression_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="Unsupported"):
        compile_where(Person, ("not an expr",), registry)  # type: ignore[arg-type]


def test_field_to_field_comparison_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="another field"):
        compile_where(Person, (Person.name == Person.works_for,), registry)


def test_term_to_n3_rejects_invalid_iri() -> None:
    from pyoxigraph import NamedNode

    from sparqlmodel.rdf_n3 import term_to_n3, validate_iri_token

    with pytest.raises(QueryError, match="Invalid IRI"):
        validate_iri_token("http://x> . ?hack <urn:y>")
    with pytest.raises(QueryError, match="Invalid IRI"):
        validate_iri_token('urn:foo"}')
    with pytest.raises((QueryError, ValueError), match="Invalid IRI|>"):
        term_to_n3(NamedNode("http://x> . ?hack <urn:y>"))
    with pytest.raises(QueryError, match="Invalid IRI"):
        term_to_n3("<http://x> . ?hack <urn:y>>")


def test_validate_language_tag_rejects_invalid() -> None:
    from sparqlmodel.rdf_n3 import validate_language_tag

    with pytest.raises(QueryError, match="Invalid language tag"):
        validate_language_tag("toolongggggg")
    with pytest.raises(QueryError, match="Invalid language tag"):
        validate_language_tag("9bad")


def test_escape_sparql_string_control_chars() -> None:
    from sparqlmodel.sparql_escape import escape_sparql_string

    assert "\\u0000" in escape_sparql_string("\x00")
    assert escape_sparql_string("a\x01b") == "a\\u0001b"
    assert escape_sparql_string('a"b') == 'a\\"b'
    assert escape_sparql_string("a\\b") == "a\\\\b"
    assert escape_sparql_string("a\rb") == "a\\rb"
    assert escape_sparql_string("a\tb") == "a\\tb"


def test_compile_where_rejects_non_finite_float() -> None:
    from sparqlmodel import Field, SPARQLModel

    class ScorePerson(SPARQLModel):
        rdf_type = "urn:test:ScorePerson"
        __prefixes__ = {"schema": "https://schema.org/"}
        score: float = Field("schema:value")

    registry = NamespaceRegistry(ScorePerson.get_prefixes())
    with pytest.raises(QueryError, match="Non-finite"):
        compile_where(ScorePerson, (ScorePerson.score == float("nan"),), registry)
