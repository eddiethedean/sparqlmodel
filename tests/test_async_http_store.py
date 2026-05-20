"""Tests for AsyncHttpStore (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest
from pyoxigraph import Literal
from triplemodel import Store

from sparqlmodel.stores.async_http import AsyncHttpStore
from sparqlmodel.stores.http_common import graph_to_delete_data, graph_to_insert_data


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
