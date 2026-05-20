"""Tests for SPARQL compiler."""

import pytest

from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr
from sparqlmodel.types import NamespaceRegistry
from tests.models import Organization, Person


def test_compile_equality() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "Odos",), registry)
    assert "schema:name" in sparql or "schema.org" in sparql
    assert '"Odos"' in sparql


def test_compile_nested() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.works_for.name == "Acme Corp",), registry)
    assert "worksfor" in sparql.lower() or "worksFor" in sparql or "works" in sparql


def test_compile_and() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    combined = AndExpr((Person.name == "Odos", Person.name != "Other"))
    sparql = compile_where(Person, (combined,), registry)
    assert '"Odos"' in sparql
    assert '"Other"' in sparql
    assert sparql.count("FILTER") >= 1


def test_unknown_field() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises((QueryError, AttributeError)):
        compile_where(Person, (Person.unknown == "x",), registry)  # type: ignore[attr-defined]


def test_wrong_model_field_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="does not match"):
        compile_where(Person, (Organization.name == "Acme",), registry)


def test_schema_prefixed_name_stays_literal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "schema:Person",), registry)
    assert '<https://schema.org/name> "schema:Person"' in sparql


def test_unknown_compact_prefix_stays_literal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "unknown:foo",), registry)
    assert '"unknown:foo"' in sparql


def test_compile_iri_field_absolute_strings() -> None:
    from sparqlmodel.compiler import _format_object

    registry = NamespaceRegistry(Person.get_prefixes())
    ann = Person.model_fields["works_for"].annotation
    assert _format_object("urn:org:acme", registry, field_annotation=ann) == "<urn:org:acme>"
    assert (
        _format_object(
            "https://example.org/org/acme",
            registry,
            field_annotation=ann,
        )
        == "<https://example.org/org/acme>"
    )


def test_compile_where_negative_limit() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="limit"):
        compile_where(Person, (Person.name == "x",), registry, limit=-1)
