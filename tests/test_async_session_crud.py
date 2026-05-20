"""Async SPARQLSession CRUD tests."""

from __future__ import annotations

import pytest

from sparqlmodel import IRI, AsyncSPARQLSession
from sparqlmodel.stores.async_memory import AsyncMemoryStore
from tests.models import Person


@pytest.fixture
async def async_session() -> AsyncSPARQLSession:
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        yield session


@pytest.fixture
async def odos(async_session: AsyncSPARQLSession) -> Person:
    from tests.models import Location, Organization

    loc = Location(id=IRI("urn:loc:hq"), name="HQ")
    org = Organization(id=IRI("urn:org:acme"), name="Acme Corp", located_in=loc)
    person = Person(id=IRI("urn:person:odos"), name="Odos", works_for=org)
    await async_session.put(person)
    return person


async def test_async_put_and_get(async_session: AsyncSPARQLSession, odos: Person) -> None:
    loaded = await async_session.get(Person, odos.id)
    assert loaded is not None
    assert loaded.name == "Odos"


async def test_async_delete(async_session: AsyncSPARQLSession, odos: Person) -> None:
    await async_session.delete(odos)
    assert await async_session.get(Person, odos.id) is None


async def test_async_execute_select(async_session: AsyncSPARQLSession, odos: Person) -> None:
    results = await async_session.execute("SELECT ?s WHERE { ?s a <https://schema.org/Person> . }")
    assert len(results) >= 1


async def test_async_delete_drops_pending_put(odos: Person) -> None:
    async with AsyncSPARQLSession(store=AsyncMemoryStore(), autoflush=False) as session:
        await session.put(odos, flush=False)
        await session.delete(odos)
        await session.flush()
        assert await session.get(Person, odos.id) is None
