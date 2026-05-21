"""Tests for optional FastAPI RDF response helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from sparqlmodel import IRI  # noqa: E402
from sparqlmodel.fastapi import (  # noqa: E402
    _DEFAULT_JSONLD,
    _DEFAULT_TURTLE,
    SessionDep,
    _negotiate_rdf_format,
    init_app,
    jsonld_response,
    negotiated_response,
    turtle_response,
)
from sparqlmodel.stores.memory import MemoryStore  # noqa: E402
from tests.models import Person  # noqa: E402


def test_turtle_response() -> None:
    person = Person(id=IRI("urn:p:api"), name="API")
    response = turtle_response(person)
    assert response.media_type == "text/turtle"
    assert b"urn:p:api" in response.body or b"API" in response.body


def test_jsonld_response() -> None:
    person = Person(id=IRI("urn:p:api2"), name="JSONLD")
    response = jsonld_response(person)
    assert response.media_type == "application/ld+json"
    assert len(response.body) > 0


def test_negotiated_response_turtle() -> None:
    person = Person(id=IRI("urn:p:neg"), name="Neg")
    request = httpx.Request("GET", "http://test/", headers={"accept": "text/turtle"})
    response = negotiated_response(request, person)
    assert response.media_type == "text/turtle"


def test_negotiated_response_jsonld() -> None:
    person = Person(id=IRI("urn:p:neg2"), name="Neg2")
    request = httpx.Request("GET", "http://test/", headers={"accept": "application/ld+json"})
    response = negotiated_response(request, person)
    assert response.media_type == "application/ld+json"


def test_negotiate_rdf_format_edge_cases() -> None:
    media = (_DEFAULT_TURTLE, _DEFAULT_JSONLD)
    assert _negotiate_rdf_format("", media) == "turtle"
    assert _negotiate_rdf_format("*/*", media) == "turtle"
    assert _negotiate_rdf_format("  , text/turtle", media) == "turtle"
    assert _negotiate_rdf_format("application/ld+json;q=not-a-number", media) == "json-ld"
    assert _negotiate_rdf_format("*/*;q=0.5", media) == "turtle"


def test_negotiated_response_respects_q_values() -> None:
    person = Person(id=IRI("urn:p:q"), name="Q")
    request = httpx.Request(
        "GET",
        "http://test/",
        headers={"accept": "application/ld+json;q=1.0, text/turtle;q=0.5"},
    )
    response = negotiated_response(request, person)
    assert response.media_type == "application/ld+json"

    request_turtle = httpx.Request(
        "GET",
        "http://test/",
        headers={"accept": "text/turtle;q=1.0, application/ld+json;q=0.1"},
    )
    response_turtle = negotiated_response(request_turtle, person)
    assert response_turtle.media_type == "text/turtle"


def test_fastapi_app_with_session() -> None:
    app = FastAPI()
    init_app(app, MemoryStore())

    @app.post("/seed")
    def seed(session: SessionDep) -> dict[str, str]:
        session.put(Person(id=IRI("urn:p:app"), name="App"))
        return {"ok": "true"}

    @app.get("/person/{iri}")
    def get_person(iri: str, request: Request, session: SessionDep) -> object:
        person = session.get(Person, IRI(iri))
        if person is None:
            raise HTTPException(status_code=404)
        return negotiated_response(request, person)

    with TestClient(app) as client:
        client.post("/seed")
        res = client.get(
            "/person/urn:p:app",
            headers={"accept": "text/turtle"},
        )
    assert res.status_code == 200
    assert "turtle" in res.headers.get("content-type", "")
