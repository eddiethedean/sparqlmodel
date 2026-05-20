"""Tests for async query builder."""

from __future__ import annotations

import pytest

from sparqlmodel import IRI, AsyncSPARQLSession
from sparqlmodel.stores.async_memory import AsyncMemoryStore
from tests.models import Person


@pytest.fixture
async def async_session() -> AsyncSPARQLSession:
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        yield session


async def test_async_query_equality(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="Odos"))
    await async_session.put(Person(id=IRI("urn:p:2"), name="Ada"))
    results = await async_session.query(Person).where(Person.name == "Odos").all()
    assert len(results) == 1
    assert results[0].name == "Odos"


async def test_async_query_first(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:1"), name="Only"))
    found = await async_session.query(Person).where(Person.name == "Only").first()
    assert found is not None
    assert found.name == "Only"
    missing = await async_session.query(Person).where(Person.name == "Nobody").first()
    assert missing is None
