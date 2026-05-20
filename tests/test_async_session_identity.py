"""Async session identity map, cache, and flush."""

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


async def test_async_identity_map(async_session: AsyncSPARQLSession) -> None:
    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    await async_session.put(plain)
    assert await async_session.get(Person, plain.id) is plain


async def test_async_put_flush_false(async_session: AsyncSPARQLSession) -> None:
    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    async_session.autoflush = False
    await async_session.put(plain, flush=False)
    assert len(async_session.graph) == 0
    await async_session.flush()
    assert await async_session.get(Person, plain.id) is plain


async def test_async_flush_requeues_on_failure(
    async_session: AsyncSPARQLSession,
    odos: Person,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = Person(id=IRI("urn:person:other"), name="Other")
    async_session.autoflush = False
    await async_session.put(odos, flush=False)
    await async_session.put(other, flush=False)
    calls = {"n": 0}
    from sparqlmodel import session_core

    orig = session_core.put_impl_async

    async def failing_put_impl(store, state, model):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("put failed")
        return await orig(store, state, model)

    monkeypatch.setattr(session_core, "put_impl_async", failing_put_impl)
    with pytest.raises(RuntimeError, match="put failed"):
        await async_session.flush()
    assert len(async_session._state.pending) == 1


async def test_async_rollback_pending() -> None:
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        plain = Person(id=IRI("urn:person:plain"), name="Plain")
        session.autoflush = False
        await session.put(plain, flush=False)
        await session.rollback_pending()
        await session.flush()
        assert len(session.graph) == 0


async def test_async_expire() -> None:
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
        plain = Person(id=IRI("urn:person:plain"), name="Plain")
        session.autoflush = False
        await session.put(plain, flush=False)
        await session.expire(Person, plain.id)
        await session.flush()
        assert await session.get(Person, plain.id) is None


async def test_async_hydrate_bindings_keys(async_session: AsyncSPARQLSession, odos: Person) -> None:
    bindings = [{"?person": str(odos.id)}]
    results = await async_session.hydrate_bindings(Person, bindings, depth=0)
    assert len(results) == 1
    alt = await async_session.hydrate_bindings(Person, [{"??person": str(odos.id)}])
    assert len(alt) == 1
    assert await async_session.hydrate_bindings(Person, [{"other": "x"}]) == []
    dup = await async_session.hydrate_bindings(
        Person,
        [{"person": str(odos.id)}, {"person": str(odos.id)}],
    )
    assert len(dup) == 1


async def test_async_session_closed_operations() -> None:
    session = AsyncSPARQLSession(store=AsyncMemoryStore(), close_on_exit=False)
    await session.close()
    with pytest.raises(RuntimeError, match="closed"):
        session._check_open()
    await session.close()


async def test_async_exit_reraises_close_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncSPARQLSession(store=AsyncMemoryStore())

    async def boom_close() -> None:
        raise RuntimeError("close failed")

    monkeypatch.setattr(session, "close", boom_close)
    with pytest.raises(RuntimeError, match="close failed"):
        async with session:
            pass


async def test_async_close_with_pending_raises() -> None:
    session = AsyncSPARQLSession(store=AsyncMemoryStore(), close_on_exit=False)
    await session.put(Person(id=IRI("urn:p:1"), name="A"), flush=False)
    with pytest.raises(RuntimeError, match="pending"):
        await session.close()


async def test_async_context_manager_rollback() -> None:
    with pytest.raises(ValueError):
        async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session:
            await session.put(Person(id=IRI("urn:p:err"), name="E"), flush=False)
            raise ValueError("boom")
    async with AsyncSPARQLSession(store=AsyncMemoryStore()) as session2:
        assert await session2.get(Person, IRI("urn:p:err")) is None


def test_check_stale_add_skips_none_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    from sparqlmodel import SPARQLSession, session_core
    from sparqlmodel import fields as fields_mod
    from sparqlmodel.stores.memory import MemoryStore

    orig = fields_mod.get_field_metadata
    calls = {"n": 0}

    def fake_meta(field_info: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            return orig(field_info)
        if calls["n"] == 2:
            return None
        return orig(field_info)

    person = Person(id=IRI("urn:p:meta"), name="X")
    store = MemoryStore()
    with SPARQLSession(store=store, close_on_exit=False) as session:
        session.put(person)
    monkeypatch.setattr(fields_mod, "get_field_metadata", fake_meta)
    session_core.check_stale_add(store.graph, person)


async def test_async_add_stale_warning(async_session: AsyncSPARQLSession) -> None:
    from sparqlmodel.exceptions import StaleTripleWarning

    p = Person(id=IRI("urn:p:add"), name="First")
    await async_session.put(p)
    with pytest.warns(StaleTripleWarning):
        await async_session.add(Person(id=IRI("urn:p:add"), name="Second"))


async def test_async_autoflush_before_query(
    async_session: AsyncSPARQLSession,
    odos: Person,
) -> None:
    async_session.autoflush = True
    await async_session.put(odos, flush=False)
    found = await async_session.query(Person).where(Person.name == "Odos").first()
    assert found is not None


async def test_async_exit_suppresses_close_error_when_not_rollback() -> None:
    with pytest.raises(ValueError, match="boom"):
        async with AsyncSPARQLSession(
            store=AsyncMemoryStore(),
            rollback_on_error=False,
        ) as session:
            await session.put(Person(id=IRI("urn:p:x"), name="X"), flush=False)
            raise ValueError("boom")


async def test_async_query_options(async_session: AsyncSPARQLSession) -> None:
    await async_session.put(Person(id=IRI("urn:p:q"), name="Q"))
    q = (
        async_session.query(Person)
        .where(Person.name != "X")
        .use_inequality_for_ne()
        .use_not_exists_for_ne(False)
        .use_optional_for_comparisons()
        .use_optional_for_comparisons(False)
        .limit(5)
    )
    sparql = q._compile()
    assert "SELECT" in sparql
    assert len(await q.all()) >= 1
