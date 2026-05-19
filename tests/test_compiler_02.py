"""Tests for SparqlModel 0.2 query compiler extensions."""

from __future__ import annotations

import pytest

from sparqlmodel.compiler import compile_compare, compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, OrExpr
from sparqlmodel.types import NamespaceRegistry
from tests.models import Location, Organization, Person


def test_compile_or_disjunction() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    expr = (Person.name == "Odos") | (Person.name == "Ada")
    sparql = compile_where(Person, (expr,), registry)
    assert "FILTER" in sparql
    assert "||" in sparql
    assert "EXISTS" in sparql
    assert '"Odos"' in sparql
    assert '"Ada"' in sparql


def test_compile_or_with_and_branch() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    branch = AndExpr((Person.name == "Odos", Person.name != "Other"))
    expr = branch | (Person.name == "Ada")
    sparql = compile_where(Person, (expr,), registry)
    assert sparql.count("EXISTS") >= 2


def test_and_or_operator_precedence() -> None:
    """(A & B) | C must be two disjuncts, not three."""
    registry = NamespaceRegistry(Person.get_prefixes())
    expr = (Person.name == "Odos") & (Person.name != "Other") | (Person.name == "Ada")
    sparql = compile_where(Person, (expr,), registry)
    assert sparql.count("EXISTS") == 2
    assert sparql.count("||") == 1


def test_and_or_precedence_query_integration() -> None:
    from sparqlmodel import IRI, SPARQLSession

    session = SPARQLSession()
    session.put(Person(id=IRI("urn:p:1"), name="Odos"))
    session.put(Person(id=IRI("urn:p:2"), name="Ada"))
    session.put(Person(id=IRI("urn:p:3"), name="Other"))
    results = (
        session.query(Person)
        .where((Person.name == "Odos") & (Person.name != "Other") | (Person.name == "Ada"))
        .all()
    )
    names = {p.name for p in results}
    assert names == {"Odos", "Ada"}


def test_use_not_exists_for_ne_multiple_in_and_branch() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    branch = AndExpr((Person.name != "A", Person.name != "B"))
    expr = branch | (Person.name == "C")
    sparql = compile_where(Person, (expr,), registry, use_not_exists_for_ne=True)
    assert sparql.count("?__ne_") >= 2
    assert "?__ne_o" not in sparql


def test_or_inside_and_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    bad = AndExpr((OrExpr((Person.name == "A", Person.name == "B")), Person.name == "C"))
    with pytest.raises(QueryError, match="OR|OrExpr"):
        compile_where(Person, (bad,), registry)


def test_compile_in() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name.in_(("Odos", "Ada")),), registry)
    assert " IN (" in sparql
    assert '"Odos"' in sparql
    assert '"Ada"' in sparql


def test_compile_in_empty_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="non-empty"):
        compile_where(Person, (Person.name.in_(()),), registry)


def test_compile_ordering() -> None:
    registry = NamespaceRegistry(Organization.get_prefixes())
    sparql = compile_where(
        Organization,
        (Organization.name >= "A",),
        registry,
    )
    assert ">=" in sparql
    assert "FILTER" in sparql


def test_compile_lt_on_name() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name < "Z",), registry)
    assert "FILTER" in sparql
    assert "<" in sparql


def test_multi_hop_path() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (Person.works_for.located_in.name == "Boston",),
        registry,
    )
    assert sparql.count("?__join_") >= 2
    assert "Boston" in sparql


def test_use_not_exists_for_ne() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (Person.name != "Other",),
        registry,
        use_not_exists_for_ne=True,
    )
    assert "NOT EXISTS" in sparql
    assert "?__neq_" not in sparql


def test_nested_or_flattens() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    inner = OrExpr((Person.name == "A", Person.name == "B"))
    expr = inner | (Person.name == "C")
    sparql = compile_where(Person, (expr,), registry)
    assert sparql.count("EXISTS") >= 3


def test_compile_or_empty_branch_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="at least one"):
        compile_where(Person, (OrExpr(()),), registry)


def test_compile_in_none_value_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="None"):
        compile_where(Person, (Person.name.in_(("a", None)),), registry)  # type: ignore[arg-type]


def test_multi_hop_query_integration() -> None:
    from sparqlmodel import IRI, SPARQLSession

    loc = Location(id=IRI("urn:loc:boston"), name="Boston")
    org = Organization(id=IRI("urn:org:1"), name="Acme", located_in=loc)
    person = Person(id=IRI("urn:p:1"), name="Pat", works_for=org)
    session = SPARQLSession()
    session.put(person)
    results = session.query(Person).where(Person.works_for.located_in.name == "Boston").all(depth=2)
    assert len(results) == 1
    assert results[0].name == "Pat"


def test_or_query_integration() -> None:
    from sparqlmodel import IRI, SPARQLSession

    session = SPARQLSession()
    session.put(Person(id=IRI("urn:p:1"), name="Odos"))
    session.put(Person(id=IRI("urn:p:2"), name="Ada"))
    session.put(Person(id=IRI("urn:p:3"), name="Other"))
    results = session.query(Person).where((Person.name == "Odos") | (Person.name == "Ada")).all()
    names = {p.name for p in results}
    assert names == {"Odos", "Ada"}


def test_ne_default_excludes_missing_name(session) -> None:
    from rdflib import URIRef

    from sparqlmodel import IRI

    session.put(Person(id=IRI("urn:p:named"), name="Named"))
    noname = URIRef("urn:p:noname")
    person_type = URIRef("https://schema.org/Person")
    rdf_type = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    session.graph.add((noname, rdf_type, person_type))
    default_bindings = session.execute(
        session.query(Person).where(Person.name != "Named")._compile()
    )
    assert not any("urn:p:noname" in str(b.get("person", "")) for b in default_bindings)
    optional_bindings = session.execute(
        session.query(Person)
        .where(Person.name != "Named")
        .use_optional_for_comparisons()
        ._compile()
    )
    assert any("urn:p:noname" in str(v) for b in optional_bindings for v in b.values())


def test_or_expr_and_chaining() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    combined = ((Person.name == "A") | (Person.name == "B")) & (Person.name != "C")
    assert isinstance(combined, AndExpr)
    sparql = compile_where(
        Person,
        ((Person.name == "A") | (Person.name == "B"), Person.name != "C"),
        registry,
    )
    assert "FILTER" in sparql


def test_in_list_accepted() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name.in_(["A", "B"]),), registry)
    assert '"A"' in sparql and '"B"' in sparql


def test_query_use_not_exists_for_ne() -> None:
    from sparqlmodel import IRI, SPARQLSession

    session = SPARQLSession()
    session.put(Person(id=IRI("urn:p:1"), name="Keep"))
    session.put(Person(id=IRI("urn:p:2"), name="Drop"))
    results = session.query(Person).where(Person.name != "Drop").use_not_exists_for_ne().all()
    assert len(results) == 1
    assert results[0].name == "Keep"


def test_compile_in_non_tuple_raises_type_error() -> None:
    from dataclasses import replace

    from sparqlmodel.expressions import CompareExpr, CompareOp

    registry = NamespaceRegistry(Person.get_prefixes())
    expr = replace(Person.name.in_(("a",)), right="not-a-tuple")  # type: ignore[arg-type]
    assert isinstance(expr, CompareExpr)
    assert expr.op == CompareOp.IN
    with pytest.raises(QueryError, match="tuple or sequence"):
        compile_compare(expr, Person, "?person", registry, [0], {})


def test_compare_unsupported_op() -> None:
    from dataclasses import replace

    from sparqlmodel.expressions import CompareExpr

    registry = NamespaceRegistry(Person.get_prefixes())
    expr = replace(Person.name == "x", op="bogus")  # type: ignore[arg-type]
    assert isinstance(expr, CompareExpr)
    with pytest.raises(QueryError, match="Unsupported comparison"):
        compile_compare(expr, Person, "?person", registry, [0], {})
