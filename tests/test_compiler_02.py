"""Tests for SparqlModel 0.2 query compiler extensions."""

from __future__ import annotations

import pytest

from sparqlmodel import SPARQLSession
from sparqlmodel.compiler import compile_compare, compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, OrExpr
from sparqlmodel.query import Query
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
    assert sparql.count("EXISTS") == 3  # two OR branches; != uses nested NOT EXISTS
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


def test_in_bare_string_raises() -> None:
    with pytest.raises(QueryError, match="bare string"):
        Person.name.in_("ab")
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name.in_(("ab",)),), registry)
    assert '"ab"' in sparql


def test_compare_and_or_group_raises() -> None:
    with pytest.raises(QueryError, match="Cannot combine OR and AND"):
        _ = (Person.name == "C") & ((Person.name == "A") | (Person.name == "B"))
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        ((Person.name == "A") | (Person.name == "B"), Person.name == "C"),
        registry,
    )
    assert "||" in sparql


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


def test_ne_default_includes_missing_name(session) -> None:
    from sparqlmodel import IRI
    from tests.rdf_helpers import RDF_TYPE

    session.put(Person(id=IRI("urn:p:named"), name="Named"))
    noname = "urn:p:noname"
    person_type = "https://schema.org/Person"
    session.graph.add((noname, RDF_TYPE, person_type))
    default_bindings = session.execute(
        session.query(Person).where(Person.name != "Named")._compile()
    )
    assert any("urn:p:noname" in str(v) for b in default_bindings for v in b.values())
    inequality_bindings = session.execute(
        session.query(Person).where(Person.name != "Named").use_inequality_for_ne()._compile()
    )
    assert not any("urn:p:noname" in str(b.get("person", "")) for b in inequality_bindings)


def test_ne_multi_valued_uses_not_exists(session) -> None:
    from pyoxigraph import Literal

    from sparqlmodel import IRI
    from tests.rdf_helpers import RDF_TYPE

    person_type = "https://schema.org/Person"
    name_pred = "https://schema.org/name"
    multi = "urn:p:multi"
    session.graph.add((multi, RDF_TYPE, person_type))
    session.graph.add((multi, name_pred, Literal("Other")))
    session.graph.add((multi, name_pred, Literal("Odos")))
    session.put(Person(id=IRI("urn:p:only"), name="Ada"))
    results = session.query(Person).where(Person.name != "Other").all()
    names = {str(p.id) for p in results}
    assert multi not in names
    assert "urn:p:only" in names
    inequality = session.query(Person).where(Person.name != "Other").use_inequality_for_ne().all()
    assert any(str(p.id) == multi for p in inequality)


def test_or_expr_and_chaining_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="Cannot combine OR and AND"):
        _ = ((Person.name == "A") | (Person.name == "B")) & (Person.name != "C")
    sparql = compile_where(
        Person,
        ((Person.name == "A") | (Person.name == "B"), Person.name != "C"),
        registry,
    )
    assert "FILTER" in sparql
    assert "||" in sparql


def test_or_and_combined_where_separate_args_integration() -> None:
    from sparqlmodel import IRI, SPARQLSession

    session = SPARQLSession()
    session.put(Person(id=IRI("urn:p:a"), name="A"))
    session.put(Person(id=IRI("urn:p:b"), name="B"))
    session.put(Person(id=IRI("urn:p:c"), name="C"))
    names = {
        p.name
        for p in session.query(Person)
        .where((Person.name == "A") | (Person.name == "B"), Person.name != "C")
        .all()
    }
    assert names == {"A", "B"}
    with pytest.raises(QueryError, match="Cannot combine OR and AND"):
        session.query(Person).where(
            ((Person.name == "A") | (Person.name == "B")) & (Person.name != "C")
        ).all()


def test_in_list_accepted() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name.in_(["A", "B"]),), registry)
    assert '"A"' in sparql and '"B"' in sparql


def test_use_inequality_for_ne_disable_restores_not_exists() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (Person.name != "X",),
        registry,
        use_not_exists_for_ne=False,
    )
    assert "NOT EXISTS" not in sparql
    q = Query(SPARQLSession(), Person)
    q.use_inequality_for_ne().use_inequality_for_ne(False)
    sparql2 = q.where(Person.name != "X")._compile()
    assert "NOT EXISTS" in sparql2


def test_query_use_not_exists_for_ne() -> None:
    from sparqlmodel import IRI, SPARQLSession

    session = SPARQLSession()
    session.put(Person(id=IRI("urn:p:1"), name="Keep"))
    session.put(Person(id=IRI("urn:p:2"), name="Drop"))
    results = session.query(Person).where(Person.name != "Drop").use_not_exists_for_ne().all()
    assert len(results) == 1
    assert results[0].name == "Keep"


def test_use_optional_for_comparisons_disable(session) -> None:
    from sparqlmodel import IRI
    from tests.rdf_helpers import RDF_TYPE

    session.put(Person(id=IRI("urn:p:named"), name="Named"))
    noname = "urn:p:noname"
    person_type = "https://schema.org/Person"
    session.graph.add((noname, RDF_TYPE, person_type))
    default_bindings = session.execute(
        session.query(Person).where(Person.name != "Named")._compile()
    )
    toggled_bindings = session.execute(
        session.query(Person)
        .where(Person.name != "Named")
        .use_optional_for_comparisons()
        .use_optional_for_comparisons(False)
        ._compile()
    )
    assert toggled_bindings == default_bindings
    assert any("urn:p:noname" in str(v) for b in toggled_bindings for v in b.values())
    inequality_bindings = session.execute(
        session.query(Person)
        .where(Person.name != "Named")
        .use_optional_for_comparisons(False)
        .use_inequality_for_ne()
        ._compile()
    )
    assert not any("urn:p:noname" in str(b.get("person", "")) for b in inequality_bindings)


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
