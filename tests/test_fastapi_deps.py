"""Tests for FastAPI session dependency (SQLModel style)."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from sparqlmodel import IRI, SPARQLSession  # noqa: E402
from sparqlmodel.fastapi import (  # noqa: E402
    SessionDep,
    get_session,
    http_store_lifespan,
    init_app,
    negotiated_response,
    session_dependency,
)
from sparqlmodel.fastapi import deps as fastapi_deps  # noqa: E402
from sparqlmodel.stores.memory import MemoryStore  # noqa: E402
from tests.models import Person  # noqa: E402


def test_require_fastapi_depends_missing_extra() -> None:
    with (
        patch.object(fastapi_deps, "Depends", None),
        pytest.raises(ImportError, match="sparqlmodel\\[fastapi\\]"),
    ):
        fastapi_deps._require_fastapi_depends()


def test_get_session_without_init_app_isolated_memory() -> None:
    app = FastAPI()

    @app.get("/count")
    def count(session: SessionDep) -> int:
        session.put(Person(id=IRI("urn:p:1"), name="A"))
        return len(session.graph)

    with TestClient(app) as client:
        first = client.get("/count").json()
        second = client.get("/count").json()
    assert first == second


def test_init_app_shared_store_sqlmodel_style() -> None:
    app = FastAPI()
    init_app(app, MemoryStore())

    @app.post("/seed")
    def seed(session: SessionDep) -> dict[str, str]:
        session.put(Person(id=IRI("urn:p:app"), name="App"))
        return {"ok": "true"}

    @app.get("/people/{iri}")
    def read(iri: str, session: SessionDep) -> dict[str, str]:
        found = session.get(Person, IRI(iri))
        if found is None:
            raise HTTPException(status_code=404)
        return {"name": found.name}

    with TestClient(app) as client:
        client.post("/seed")
        assert client.get("/people/urn:p:app").json()["name"] == "App"


def test_dependency_override() -> None:
    app = FastAPI()
    shared = MemoryStore()

    def override_get_session() -> Generator[SPARQLSession, None, None]:
        with SPARQLSession(store=shared, close_on_exit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    @app.get("/touch")
    def touch(session: SessionDep) -> str:
        if session.get(Person, IRI("urn:p:ov")) is None:
            session.put(Person(id=IRI("urn:p:ov"), name="OV"))
            return "created"
        return "found"

    with TestClient(app) as client:
        assert client.get("/touch").json() == "created"
        assert client.get("/touch").json() == "found"


def test_session_dependency_custom_store() -> None:
    app = FastAPI()
    custom = session_dependency(MemoryStore(), close_on_exit=True)
    app.dependency_overrides[get_session] = custom

    @app.get("/n")
    def count(session: SessionDep) -> int:
        session.put(Person(id=IRI("urn:p:c"), name="C"))
        return len(session.graph)

    with TestClient(app) as client:
        first = client.get("/n").json()
        second = client.get("/n").json()
    assert first == second


def test_session_dependency_uses_init_app_store() -> None:
    app = FastAPI()
    init_app(app, MemoryStore())
    app.dependency_overrides[get_session] = session_dependency(close_on_exit=True)

    @app.get("/touch")
    def touch(session: SessionDep) -> str:
        if session.get(Person, IRI("urn:p:init")) is None:
            session.put(Person(id=IRI("urn:p:init"), name="Init"))
            return "created"
        return "found"

    with TestClient(app) as client:
        assert client.get("/touch").json() == "created"
        assert client.get("/touch").json() == "found"


def test_session_dependency_store_factory_close_on_exit() -> None:
    app = FastAPI()
    app.dependency_overrides[get_session] = session_dependency(
        store_factory=MemoryStore,
        close_on_exit=False,
    )

    @app.get("/n")
    def count(session: SessionDep) -> int:
        session.put(Person(id=IRI("urn:p:co"), name="CO"))
        return len(session.graph)

    with TestClient(app) as client:
        assert client.get("/n").json() >= 2


def test_session_dependency_store_factory() -> None:
    app = FastAPI()
    custom = session_dependency(store_factory=MemoryStore)

    @app.get("/n")
    def count(session: Annotated[SPARQLSession, Depends(custom)]) -> int:
        session.put(Person(id=IRI("urn:p:sf"), name="SF"))
        return len(session.graph)

    with TestClient(app) as client:
        first = client.get("/n").json()
        second = client.get("/n").json()
    assert first == second


def test_app_state_store_factory() -> None:
    app = FastAPI()
    app.state.sparql_store_factory = MemoryStore

    @app.get("/n")
    def count(session: SessionDep) -> int:
        session.put(Person(id=IRI("urn:p:f"), name="F"))
        return len(session.graph)

    with TestClient(app) as client:
        first = client.get("/n").json()
        second = client.get("/n").json()
    assert first == second


def test_http_store_lifespan_registers_store() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with http_store_lifespan(
            app,
            "http://example.invalid/sparql",
            client=http_client,
        ):
            yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/has-store")
    def has_store(session: SessionDep) -> bool:
        return session.store is app.state.sparql_store

    with TestClient(app) as client:
        assert client.get("/has-store").json() is True


def test_fastapi_rdf_with_session_dep() -> None:
    app = FastAPI()
    init_app(app, MemoryStore())

    @app.post("/seed")
    def seed(session: SessionDep) -> dict[str, str]:
        session.put(Person(id=IRI("urn:p:rdf"), name="RDF"))
        return {"ok": "true"}

    @app.get("/people/{iri}/rdf")
    def rdf(iri: str, request: Request, session: SessionDep) -> object:
        person = session.get(Person, IRI(iri))
        if person is None:
            raise HTTPException(status_code=404)
        return negotiated_response(request, person)

    with TestClient(app) as client:
        client.post("/seed")
        res = client.get(
            "/people/urn:p:rdf/rdf",
            headers={"accept": "text/turtle"},
        )
        assert res.status_code == 200
        assert "turtle" in res.headers.get("content-type", "")
