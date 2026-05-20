"""Tests for AsyncMemoryStore."""

from __future__ import annotations

from triplemodel import Store

from sparqlmodel.stores.async_memory import AsyncMemoryStore


async def test_async_memory_query_and_update() -> None:
    store = AsyncMemoryStore()
    g = Store()
    g.add(("urn:s", "urn:p", "urn:o"))
    await store.update_graph(add=g)
    assert len(store.graph) == 1
    bindings = await store.query("SELECT ?s WHERE { ?s ?p ?o }")
    assert len(bindings) >= 1
    await store.aclose()
