"""Tests for AsyncHttpStore (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest
from pyoxigraph import Literal
from triplemodel import Store

from sparqlmodel import IRI, AsyncSPARQLSession, Field, SPARQLModel
from sparqlmodel.exceptions import QueryError
from sparqlmodel.stores.async_http import AsyncHttpStore
from sparqlmodel.stores.http_common import graph_to_delete_data, graph_to_insert_data


class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")


async def test_async_http_query_ask_rejected() -> None:
    store = AsyncHttpStore("http://example.org/sparql")
    with pytest.raises(QueryError, match="Expected SELECT query"):
        await store.query("ASK { ?s ?p ?o }")
    await store.aclose()


async def test_async_http_query_select_with_ask_json_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"head": {}, "boolean": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        with pytest.raises(QueryError, match="ASK"):
            await store.query("SELECT * WHERE { ?s ?p ?o }")
        await store.aclose()


async def test_async_http_construct_failure_raises() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        with pytest.raises(QueryError, match="CONSTRUCT failed"):
            await store.pull_subjects_into_mirror([IRI("http://example.org/person/1")])
        await store.aclose()


async def test_async_http_pull_empty_iris() -> None:
    store = AsyncHttpStore("http://example.org/sparql")
    await store.pull_subjects_into_mirror([])
    await store.aclose()


async def test_async_http_insert_delete_helpers() -> None:
    g = Store()
    g.add(("urn:s", "urn:p", "urn:o"))
    assert "INSERT DATA" in graph_to_insert_data(g)
    assert "DELETE DATA" in graph_to_delete_data(g)


async def test_async_http_store_update_and_mirror() -> None:
    updates: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/sparql-update":
            updates.append(request.content.decode())
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore("http://example.org/", client=client)
        add_g = Store()
        s = "urn:person:1"
        add_g.add(
            (
                s,
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                "https://schema.org/Person",
            )
        )
        add_g.add((s, "https://schema.org/name", Literal("Alice")))
        await store.update_graph(add=add_g)
        assert len(store.graph) == 2
        assert len(updates) == 1
        await store.aclose()


async def test_async_http_store_query_json() -> None:
    payload = {
        "head": {"vars": ["person"]},
        "results": {"bindings": [{"person": {"type": "uri", "value": "urn:person:1"}}]},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/sparql-query":
            return httpx.Response(200, json=payload)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore("http://fuseki.example/sparql", client=client)
        bindings = await store.query(
            "SELECT ?person WHERE { ?person a <https://schema.org/Person> }"
        )
        assert bindings == [{"person": "urn:person:1"}]
        await store.aclose()


async def test_async_http_store_closed_raises() -> None:
    store = AsyncHttpStore("http://example.org/sparql")
    await store.aclose()
    with pytest.raises(RuntimeError, match="closed"):
        await store.query("SELECT * WHERE { ?s ?p ?o }")


async def test_async_http_get_pulls_remote_subject_into_mirror() -> None:
    """Async get() CONSTRUCT-syncs remote subjects before hydration."""
    remote_iri = "http://example.org/person/remote"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f"<{remote_iri}> a schema:Person ;\n"
        '  schema:name "Remote" .\n'
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") != "application/sparql-query":
            return httpx.Response(404)
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            return httpx.Response(
                200,
                content=remote_ttl.encode(),
                headers={"Content-Type": "text/turtle"},
            )
        return httpx.Response(
            200,
            json={
                "head": {"vars": ["person"]},
                "results": {
                    "bindings": [
                        {"person": {"type": "uri", "value": remote_iri}},
                    ]
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            prefixes={"schema": "https://schema.org/"},
        )
        async with AsyncSPARQLSession(store=store) as session:
            bindings = await session.execute("SELECT ?person WHERE { ?person ?p ?o }")
            assert bindings[0]["person"] == remote_iri
            loaded = await session.get(Person, IRI(remote_iri))
            assert loaded is not None
            assert loaded.name == "Remote"
            assert len(store.graph) >= 2
        await store.aclose()


async def test_async_http_store_query_all_hydrates_remote_rows() -> None:
    """Async query().all() pulls remote subjects into the mirror before hydration."""
    remote_iri = "http://example.org/person/remote"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f"<{remote_iri}> a schema:Person ;\n"
        '  schema:name "Remote" .\n'
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") != "application/sparql-query":
            return httpx.Response(404)
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            return httpx.Response(
                200,
                content=remote_ttl.encode(),
                headers={"Content-Type": "text/turtle"},
            )
        return httpx.Response(
            200,
            json={
                "head": {"vars": ["person"]},
                "results": {
                    "bindings": [
                        {"person": {"type": "uri", "value": remote_iri}},
                    ]
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            prefixes={"schema": "https://schema.org/"},
        )
        async with AsyncSPARQLSession(store=store) as session:
            results = await session.query(Person).all()
            assert len(results) == 1
            assert results[0].name == "Remote"


async def test_async_http_update_graph_after_aclose_raises() -> None:
    store = AsyncHttpStore("http://example.org/sparql")
    await store.aclose()
    g = Store()
    g.add(("urn:s", "urn:p", "urn:o"))
    with pytest.raises(RuntimeError, match="closed"):
        await store.update_graph(add=g)
