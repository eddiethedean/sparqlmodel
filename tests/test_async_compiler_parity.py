"""Async session parity with sync query compiler and Query behavior."""

from __future__ import annotations

import math

import pytest

from sparqlmodel import IRI, AsyncSPARQLSession, Field, SPARQLModel
from sparqlmodel.async_query import AsyncQuery
from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import ConfigurationError, QueryError
from sparqlmodel.stores.async_memory import AsyncMemoryStore
from tests.models import Organization, Person
from tests.test_compiler_joins import DualOrgPerson


@pytest.fixture
async def async_session() -> AsyncSPARQLSession:
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        yield session


async def test_async_in_bare_string_raises(async_session: AsyncSPARQLSession) -> None:
    with pytest.raises(QueryError, match="bare string"):
        async_session.query(Person).where(Person.name.in_("ab"))
    with pytest.raises(QueryError, match="bare string"):
        Person.name.in_("x")


async def test_async_compare_and_or_group_raises(async_session: AsyncSPARQLSession) -> None:
    with pytest.raises(QueryError, match="Cannot combine OR and AND"):
        async_session.query(Person).where(
            (Person.name == "C") & ((Person.name == "A") | (Person.name == "B"))
        )
    results = (
        await async_session.query(Person)
        .where(
            (Person.name == "A") | (Person.name == "B"),
            Person.name == "C",
        )
        .all()
    )
    assert results == []


async def test_async_or_disjunction(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="Odos"))
    await async_session.put(Person(id=IRI("urn:p:2"), name="Ada"))
    names = {
        p.name
        for p in await async_session.query(Person)
        .where((Person.name == "Odos") | (Person.name == "Ada"))
        .all()
    }
    assert names == {"Odos", "Ada"}


async def test_async_in_filter(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="Odos"))
    await async_session.put(Person(id=IRI("urn:p:2"), name="Ada"))
    await async_session.put(Person(id=IRI("urn:p:3"), name="Other"))
    names = {
        p.name
        for p in await async_session.query(Person).where(Person.name.in_(("Odos", "Ada"))).all()
    }
    assert names == {"Odos", "Ada"}


async def test_async_in_list_filter(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="A"))
    results = await async_session.query(Person).where(Person.name.in_(["A", "B"])).all()
    assert len(results) == 1
    assert results[0].name == "A"


async def test_async_in_empty_raises(async_session: AsyncSPARQLSession) -> None:
    with pytest.raises(QueryError, match="non-empty"):
        await async_session.query(Person).where(Person.name.in_(())).all()


async def test_async_ordering(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Organization(id=IRI("urn:o:1"), name="Beta"))
    await async_session.put(Organization(id=IRI("urn:o:2"), name="Alpha"))
    sparql = async_session.query(Organization).where(Organization.name >= "A")._compile()
    assert ">=" in sparql
    rows = await async_session.execute(sparql)
    assert len(rows) >= 2


async def test_async_not_exists_ne(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:keep"), name="Keep"))
    await async_session.put(Person(id=IRI("urn:p:drop"), name="Drop"))
    results = await async_session.query(Person).where(Person.name != "Drop").all()
    assert len(results) == 1
    assert results[0].name == "Keep"


async def test_async_use_inequality_for_ne(async_session: AsyncSPARQLSession) -> None:
    from tests.rdf_helpers import RDF_TYPE

    await async_session.put(Person(id=IRI("urn:p:named"), name="Named"))
    noname = "urn:p:noname"
    person_type = "https://schema.org/Person"
    async_session.graph.add((noname, RDF_TYPE, person_type))
    default_bindings = await async_session.execute(
        async_session.query(Person).where(Person.name != "Named")._compile()
    )
    assert any("urn:p:noname" in str(v) for b in default_bindings for v in b.values())
    inequality_bindings = await async_session.execute(
        async_session.query(Person).where(Person.name != "Named").use_inequality_for_ne()._compile()
    )
    assert not any("urn:p:noname" in str(b.get("person", "")) for b in inequality_bindings)


async def test_async_multi_hop(async_session: AsyncSPARQLSession) -> None:
    acme = Organization(id=IRI("urn:org:acme"), name="Acme Corp")
    odos = Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)
    await async_session.put(odos)
    results = await async_session.query(Person).where(Person.works_for.name == "Acme Corp").all()
    assert len(results) == 1
    assert results[0].name == "Odos"


async def test_async_parallel_nested_filters(async_session: AsyncSPARQLSession) -> None:
    from tests.models import Location

    hq_a = Location(id=IRI("urn:loc:a"), name="HQ A")
    hq_b = Location(id=IRI("urn:loc:b"), name="HQ B")
    employer = Organization(id=IRI("urn:org:emp"), name="Employer", located_in=hq_a)
    volunteer = Organization(id=IRI("urn:org:vol"), name="Volunteer", located_in=hq_b)
    match = DualOrgPerson(
        id=IRI("urn:person:match"),
        name="Match",
        employer=employer,
        volunteer_at=volunteer,
    )
    await async_session.put(match)
    results = await (
        async_session.query(DualOrgPerson)
        .where(
            (DualOrgPerson.employer.located_in.name == "HQ A")
            & (DualOrgPerson.volunteer_at.located_in.name == "HQ B")
        )
        .all()
    )
    assert len(results) == 1
    assert results[0].name == "Match"


async def test_async_first_ignores_limit(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="A"))
    await async_session.put(Person(id=IRI("urn:p:2"), name="B"))
    found = await async_session.query(Person).limit(10).where(Person.name == "A").first()
    assert found is not None
    assert found.name == "A"
    compiled_first = (
        async_session.query(Person)
        .limit(10)
        .where(Person.name == "A")
        ._state.compile(
            async_session.namespaces,
            limit=1,
        )
    )
    assert "LIMIT 1" in compiled_first


async def test_async_limit_zero(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="Only"))
    results = await async_session.query(Person).limit(0).all()
    assert results == []


async def test_async_invalid_depth(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="X"))
    with pytest.raises(ConfigurationError):
        await async_session.query(Person).all(depth=5)


async def test_async_non_finite_float_raises() -> None:
    class ScorePerson(SPARQLModel):
        rdf_type = "urn:test:ScorePerson"
        __prefixes__ = {}
        id: IRI
        score: float = Field("schema:value")

    registry = ScorePerson.namespace_registry()
    with pytest.raises(QueryError, match="Non-finite"):
        compile_where(ScorePerson, (ScorePerson.score == float("nan"),), registry)
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        with pytest.raises(QueryError, match="Non-finite"):
            await session.query(ScorePerson).where(ScorePerson.score == math.nan).all()


async def test_async_query_options_toggle() -> None:
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        q: AsyncQuery = session.query(Person)
        q.use_not_exists_for_ne().use_inequality_for_ne().use_optional_for_comparisons()
        sparql = q.where(Person.name != "X")._compile()
        assert "NOT EXISTS" not in sparql or "FILTER" in sparql


async def test_async_compile_offset_order_count(async_session: AsyncSPARQLSession) -> None:
    registry = Person.namespace_registry()
    sparql = compile_where(
        Person,
        (Person.name == "A",),
        registry,
        limit=5,
        offset=2,
        order_by=((Person.name, False),),
        count=True,
    )
    assert "COUNT(DISTINCT" in sparql
    assert "OFFSET" not in sparql
    list_sparql = compile_where(
        Person,
        (Person.name == "A",),
        registry,
        limit=5,
        offset=2,
        order_by=((Person.name, False),),
    )
    assert "OFFSET 2" in list_sparql
    assert "ORDER BY" in list_sparql


async def test_async_count_and_pagination(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="Amy"))
    await async_session.put(Person(id=IRI("urn:p:2"), name="Zed"))
    assert await async_session.query(Person).count() == 2
    names = [
        p.name
        for p in await async_session.query(Person).order_by(Person.name).offset(1).limit(1).all()
    ]
    assert names == ["Zed"]
