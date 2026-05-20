"""Tests for async FastAPI session dependency."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from sparqlmodel import IRI  # noqa: E402
from sparqlmodel.fastapi import (  # noqa: E402
    AsyncSessionDep,
    async_http_store_lifespan,
    async_session_dependency,
    get_async_session,
    init_async_app,
)
from sparqlmodel.stores.async_memory import AsyncMemoryStore  # noqa: E402
from tests.models import Person  # noqa: E402


def test_init_async_app_shared_store() -> None:
    app = FastAPI()
    init_async_app(app, AsyncMemoryStore())

    @app.post("/seed")
    async def seed(session: AsyncSessionDep) -> dict[str, str]:
        await session.put(Person(id=IRI("urn:p:async"), name="Async"))
        return {"ok": "true"}

    @app.get("/people/{iri}")
    async def read(iri: str, session: AsyncSessionDep) -> dict[str, str]:
        found = await session.get(Person, IRI(iri))
        if found is None:
            raise HTTPException(status_code=404)
        return {"name": found.name}

    with TestClient(app) as client:
        client.post("/seed")
        assert client.get("/people/urn:p:async").json()["name"] == "Async"


def test_async_http_store_lifespan_mock() -> None:
    updates: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/sparql-update":
            updates.append(request.content.decode())
            return httpx.Response(200)
        if request.headers.get("content-type") == "application/sparql-query":
            return httpx.Response(
                200,
                json={"head": {"vars": []}, "results": {"bindings": []}},
            )
        return httpx.Response(404)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            from sparqlmodel.stores.async_http import AsyncHttpStore

            store = AsyncHttpStore("http://example.org/sparql", client=client)
            init_async_app(app, store)
            yield
            await store.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.get("/ping")
    async def ping(session: AsyncSessionDep) -> bool:
        await session.put(Person(id=IRI("urn:p:ping"), name="Ping"))
        return True

    with TestClient(app) as client:
        assert client.get("/ping").json() is True
        assert updates


def test_get_async_session_without_init_app() -> None:
    app = FastAPI()

    @app.get("/count")
    async def count(session: AsyncSessionDep) -> int:
        await session.put(Person(id=IRI("urn:p:async-mem"), name="A"))
        return len(session.graph)

    with TestClient(app) as client:
        assert client.get("/count").json() >= 2


def test_async_session_dependency_override() -> None:
    app = FastAPI()
    shared = AsyncMemoryStore()
    custom = async_session_dependency(shared, close_on_exit=False)
    app.dependency_overrides[get_async_session] = custom

    @app.get("/touch")
    async def touch(session: AsyncSessionDep) -> str:
        if await session.get(Person, IRI("urn:p:ov")) is None:
            await session.put(Person(id=IRI("urn:p:ov"), name="OV"))
            return "created"
        return "found"

    with TestClient(app) as client:
        assert client.get("/touch").json() == "created"
        assert client.get("/touch").json() == "found"


def test_async_app_state_store_factory() -> None:
    app = FastAPI()
    app.state.sparql_async_store_factory = AsyncMemoryStore

    @app.get("/n")
    async def count(session: AsyncSessionDep) -> int:
        await session.put(Person(id=IRI("urn:p:f"), name="F"))
        return len(session.graph)

    with TestClient(app) as client:
        first = client.get("/n").json()
        second = client.get("/n").json()
    assert first == second


def test_async_http_store_lifespan() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        transport = httpx.MockTransport(handler)
        async with (
            httpx.AsyncClient(transport=transport) as client,
            async_http_store_lifespan(
                app,
                "http://example.invalid/sparql",
                client=client,
            ),
        ):
            yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/has-store")
    async def has_store(session: AsyncSessionDep) -> bool:
        return session.store is app.state.sparql_async_store

    with TestClient(app) as client:
        assert client.get("/has-store").json() is True


def test_async_session_dependency_factory() -> None:
    app = FastAPI()
    app.dependency_overrides[get_async_session] = async_session_dependency(
        store_factory=AsyncMemoryStore,
    )

    @app.get("/n")
    async def count(session: AsyncSessionDep) -> int:
        await session.put(Person(id=IRI("urn:p:sf"), name="SF"))
        return len(session.graph)

    with TestClient(app) as client:
        first = client.get("/n").json()
        second = client.get("/n").json()
    assert first == second


def test_async_session_dependency_explicit_store() -> None:
    app = FastAPI()
    shared = AsyncMemoryStore()
    custom = async_session_dependency(shared, close_on_exit=True)
    app.dependency_overrides[get_async_session] = custom

    @app.get("/n")
    async def count(session: AsyncSessionDep) -> int:
        await session.put(Person(id=IRI("urn:p:ex"), name="Ex"))
        return len(session.graph)

    with TestClient(app) as client:
        assert client.get("/n").json() >= 2


def test_async_session_dependency_init_app_close_override() -> None:
    app = FastAPI()
    init_async_app(app, AsyncMemoryStore())
    custom = async_session_dependency(close_on_exit=False)
    app.dependency_overrides[get_async_session] = custom

    @app.get("/n")
    async def count(session: AsyncSessionDep) -> int:
        await session.put(Person(id=IRI("urn:p:co"), name="CO"))
        return len(session.graph)

    with TestClient(app) as client:
        assert client.get("/n").json() >= 2


def test_async_session_dependency_close_on_exit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sparqlmodel.async_session import AsyncSPARQLSession
    from sparqlmodel.fastapi import deps as async_deps

    captured: list[dict[str, object]] = []

    class RecordingSession(AsyncSPARQLSession):
        def __init__(self, **kwargs: object) -> None:
            captured.append(dict(kwargs))
            super().__init__(**kwargs)

    monkeypatch.setattr(async_deps, "AsyncSPARQLSession", RecordingSession)
    app = FastAPI()
    app.state.sparql_async_store_factory = AsyncMemoryStore
    dep = async_session_dependency(close_on_exit=True)
    app.dependency_overrides[get_async_session] = dep

    @app.get("/n")
    async def touch(session: AsyncSessionDep) -> bool:
        return session.autoflush

    with TestClient(app) as client:
        client.get("/n")
    assert captured[-1]["close_on_exit"] is True


def test_async_session_dependency_does_not_close_shared_http_store() -> None:
    from unittest.mock import patch

    import httpx

    from sparqlmodel.stores.async_http import AsyncHttpStore

    close_calls = 0
    real_aclose = AsyncHttpStore.aclose

    async def counting_aclose(self: AsyncHttpStore) -> None:
        nonlocal close_calls
        close_calls += 1
        await real_aclose(self)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    store = AsyncHttpStore("http://example.invalid/sparql", client=http_client)

    app = FastAPI()
    init_async_app(app, store)
    app.dependency_overrides[get_async_session] = async_session_dependency(close_on_exit=True)

    with patch.object(AsyncHttpStore, "aclose", counting_aclose):

        @app.get("/touch")
        async def touch(session: AsyncSessionDep) -> str:
            if await session.get(Person, IRI("urn:p:async-http")) is None:
                await session.put(Person(id=IRI("urn:p:async-http"), name="Http"))
                return "created"
            return "found"

        with TestClient(app) as client:
            assert client.get("/touch").json() == "created"
            assert client.get("/touch").json() == "found"
    assert close_calls == 0
