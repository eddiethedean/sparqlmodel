"""Tests for SPARQL compiler."""

import pytest

from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr
from sparqlmodel.types import NamespaceRegistry
from tests.models import Person


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
