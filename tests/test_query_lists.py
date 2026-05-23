"""Tests for 0.8 query lists: offset, order_by, count, nullable OPTIONAL."""

from __future__ import annotations

import pytest

from sparqlmodel import IRI
from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.stores.async_memory import AsyncMemoryStore
from sparqlmodel.types import NamespaceRegistry
from tests.models import Organization, Person


def test_compile_offset_order_limit() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (Person.name != "X",),
        registry,
        limit=10,
        offset=20,
        order_by=((Person.name, False),),
    )
    assert "OFFSET 20" in sparql
    assert "LIMIT 10" in sparql
    assert "ORDER BY ASC" in sparql
    assert sparql.index("ORDER BY") < sparql.index("OFFSET") < sparql.index("LIMIT")


def test_compile_count() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (Person.name == "Odos",),
        registry,
        count=True,
        limit=5,
        offset=10,
        order_by=((Person.name, False),),
    )
    assert "COUNT(DISTINCT ?person)" in sparql
    assert "?__count" in sparql
    assert "OFFSET" not in sparql
    assert "LIMIT" not in sparql
    assert "ORDER BY" not in sparql


def test_compile_order_by_desc() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (),
        registry,
        order_by=((Person.name, True),),
    )
    assert "ORDER BY DESC" in sparql


def test_compile_negative_offset_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="offset"):
        compile_where(Person, (), registry, offset=-1)


def test_compile_order_by_non_scalar_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="not a collection"):
        compile_where(Person, (), registry, order_by=((Person.works_for, False),))


def test_query_order_offset_limit(session) -> None:
    for i, name in enumerate(("Amy", "Bob", "Cal", "Dan")):
        session.put(Person(id=IRI(f"urn:p:{i}"), name=name))
    names = [p.name for p in session.query(Person).order_by(Person.name).offset(1).limit(2).all()]
    assert names == ["Bob", "Cal"]


def test_query_count(session) -> None:
    session.put(Person(id=IRI("urn:p:1"), name="Odos"))
    session.put(Person(id=IRI("urn:p:2"), name="Ada"))
    session.put(Person(id=IRI("urn:p:3"), name="Other"))
    total = session.query(Person).where(Person.name != "Other").count()
    assert total == 2


def test_query_count_ignores_limit(session) -> None:
    session.put(Person(id=IRI("urn:p:1"), name="A"))
    session.put(Person(id=IRI("urn:p:2"), name="B"))
    assert session.query(Person).limit(1).count() == 2


def test_query_first_ignores_offset_and_limit(session) -> None:
    session.put(Person(id=IRI("urn:p:1"), name="Amy"))
    session.put(Person(id=IRI("urn:p:2"), name="Zed"))
    first = session.query(Person).order_by(Person.name).offset(10).limit(1).first()
    assert first is not None
    assert first.name == "Amy"


def test_nullable_hop_optional_in_sparql() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(
        Person,
        (Person.works_for.name != "Acme",),
        registry,
    )
    assert "OPTIONAL" in sparql


def test_nullable_ne_includes_missing_relationship(session, acme: Organization) -> None:
    session.put(Person(id=IRI("urn:p:with"), name="With", works_for=acme))
    session.put(Person(id=IRI("urn:p:alone"), name="Alone"))
    names = {
        p.name for p in session.query(Person).where(Person.works_for.name != "Acme Corp").all()
    }
    assert names == {"Alone"}


def test_works_for_is_none(session, acme: Organization) -> None:
    session.put(Person(id=IRI("urn:p:with"), name="With", works_for=acme))
    session.put(Person(id=IRI("urn:p:alone"), name="Alone"))
    names = {p.name for p in session.query(Person).where(Person.works_for.is_(None)).all()}
    assert names == {"Alone"}


def test_works_for_is_not_none(session, acme: Organization) -> None:
    session.put(Person(id=IRI("urn:p:with"), name="With", works_for=acme))
    session.put(Person(id=IRI("urn:p:alone"), name="Alone"))
    names = {p.name for p in session.query(Person).where(Person.works_for.is_not(None)).all()}
    assert names == {"With"}


def test_is_none_scalar_raises() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    with pytest.raises(QueryError, match="relationship"):
        compile_where(Person, (Person.name.is_(None),), registry)


def test_nested_relationship_is_none(session) -> None:
    from tests.test_compiler_joins import DualOrgPerson

    employer = Organization(id=IRI("urn:org:e"), name="E")
    match = DualOrgPerson(
        id=IRI("urn:p:m"),
        name="Match",
        employer=employer,
        volunteer_at=None,
    )
    alone = DualOrgPerson(id=IRI("urn:p:a"), name="Alone", employer=None, volunteer_at=None)
    session.put(match)
    session.put(alone)
    names = {
        p.name for p in session.query(DualOrgPerson).where(DualOrgPerson.employer.is_(None)).all()
    }
    assert names == {"Alone"}


def test_order_by_nullable_includes_missing_relationship(session) -> None:
    session.put(Person(id=IRI("urn:p:1"), name="Zara"))
    session.put(Person(id=IRI("urn:p:2"), name="Amy"))
    names = [p.name for p in session.query(Person).order_by(Person.works_for.name).all()]
    assert names == ["Amy", "Zara"]


def test_works_for_iri_reference_is_not_none(session, acme: Organization) -> None:
    session.put(Person(id=IRI("urn:p:ref"), name="Ref", works_for=acme.id))
    session.put(Person(id=IRI("urn:p:alone"), name="Alone"))
    names = {p.name for p in session.query(Person).where(Person.works_for.is_not(None)).all()}
    assert names == {"Ref"}


def test_nullable_inequality_includes_missing(session, acme: Organization) -> None:
    session.put(Person(id=IRI("urn:p:with"), name="With", works_for=acme))
    session.put(Person(id=IRI("urn:p:alone"), name="Alone"))
    names = {
        p.name
        for p in session.query(Person)
        .where(Person.works_for.name != "Acme Corp")
        .use_inequality_for_ne()
        .all()
    }
    assert names == {"Alone"}


def test_compile_iri_hop_omits_rdf_type() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.works_for.is_not(None),), registry)
    assert "<https://schema.org/Organization>" not in sparql


def test_compile_works_for_is_none_has_bound_filter() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.works_for.is_(None),), registry)
    assert "OPTIONAL" in sparql
    assert "!BOUND" in sparql


@pytest.mark.asyncio
async def test_async_query_lists() -> None:
    from sparqlmodel import AsyncSPARQLSession

    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        await session.put(Person(id=IRI("urn:p:1"), name="Amy"))
        await session.put(Person(id=IRI("urn:p:2"), name="Zed"))
        total = await session.query(Person).count()
        assert total == 2
        page = await session.query(Person).order_by(Person.name).offset(1).limit(1).all()
        assert len(page) == 1
        assert page[0].name == "Zed"
        first = await session.query(Person).order_by(Person.name).offset(1).limit(1).first()
        assert first is not None
        assert first.name == "Amy"
