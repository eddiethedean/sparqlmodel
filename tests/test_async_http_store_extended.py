"""Extended AsyncHttpStore tests (mirror sync HttpStore coverage)."""

from __future__ import annotations

import httpx
import pytest
from pyoxigraph import Literal
from triplemodel import Store

from sparqlmodel import IRI, Field, SPARQLModel
from sparqlmodel.async_session import AsyncSPARQLSession
from sparqlmodel.exceptions import ConfigurationError, QueryError
from sparqlmodel.stores import http_common
from sparqlmodel.stores.async_http import AsyncHttpStore


class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")


async def test_async_http_query_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            max_retries=0,
        )
        with pytest.raises(QueryError, match="SPARQL query failed"):
            await store.query("SELECT * WHERE { ?s ?p ?o }")


async def test_async_http_update_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            max_retries=0,
        )
        g = Store()
        g.add(("urn:s", "urn:p", "urn:o"))
        with pytest.raises(QueryError, match="SPARQL UPDATE failed"):
            await store.update_graph(add=g)
        assert len(store.graph) == 0


async def test_async_http_bearer_and_auth() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            bearer_token="secret",
            client=client,
        )
        await store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
        assert seen[0] == "Bearer secret"
        await store.aclose()

    async with httpx.AsyncClient(transport=transport) as client2:
        store2 = AsyncHttpStore(
            "http://example.org/sparql",
            auth=("user", "pass"),
            client=client2,
        )
        await store2.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
        await store2.aclose()


async def test_async_http_basic_auth_over_bearer() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            auth=("user", "pass"),
            bearer_token="secret",
            client=client,
        )
        await store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
        assert seen[0].startswith("Basic ")
        await store.aclose()


async def test_async_http_aclose_twice() -> None:
    store = AsyncHttpStore("http://example.org/sparql")
    await store.aclose()
    await store.aclose()


async def test_async_http_context_manager() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        async with AsyncHttpStore("http://example.org/sparql", client=client) as store:
            await store.query("SELECT * WHERE { ?s ?p ?o }")
        assert store._closed


async def test_async_http_read_write_endpoint_properties() -> None:
    store = AsyncHttpStore(
        "http://example.org/dataset",
        read_endpoint="http://read.example/query",
        write_endpoint="http://write.example/update",
    )
    assert store.read_endpoint == "http://read.example/query"
    assert store.write_endpoint == "http://write.example/update"
    await store.aclose()


async def test_async_http_sparql_url_and_owned_client() -> None:
    store = AsyncHttpStore("http://example.org/sparql")
    assert store._sparql_url() == "http://example.org/sparql"
    assert store.endpoint == "http://example.org/sparql"
    await store.aclose()
    store2 = AsyncHttpStore("http://example.org/dataset")
    assert store2._sparql_url().endswith("/sparql")
    await store2.aclose()


async def test_async_http_parse_errors() -> None:
    def bad_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    transport = httpx.MockTransport(bad_json)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        with pytest.raises(QueryError, match="Failed to parse"):
            await store.query("SELECT * WHERE { ?s ?p ?o }")

    def bad_shape(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "sparql-results"})

    transport2 = httpx.MockTransport(bad_shape)
    async with httpx.AsyncClient(transport=transport2) as client2:
        store2 = AsyncHttpStore("http://example.org/sparql", client=client2)
        with pytest.raises(QueryError, match="Failed to parse"):
            await store2.query("SELECT * WHERE { ?s ?p ?o }")


async def test_async_http_empty_update_and_remove_only() -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request.content.decode())
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        await store.update_graph()
        assert posts == []
        g = Store()
        g.add(("urn:s", "urn:p", "urn:o"))
        store.graph.add(("urn:s", "urn:p", "urn:o"))
        await store.update_graph(remove=g)
        assert "DELETE DATA" in posts[0]


def _seed_person_in_mirror(store: AsyncHttpStore, iri: str, name: str) -> None:
    store.graph.add(
        (
            iri,
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "https://schema.org/Person",
        )
    )
    store.graph.add((iri, "https://schema.org/name", Literal(name)))


async def test_async_http_pull_replaces_stale_predicate() -> None:
    remote_iri = "http://example.org/person/1"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f'<{remote_iri}> a schema:Person ; schema:name "Remote" .\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            return httpx.Response(
                200,
                content=remote_ttl.encode(),
                headers={"Content-Type": "text/turtle"},
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            prefixes={"schema": "https://schema.org/"},
        )
        _seed_person_in_mirror(store, remote_iri, "Stale")
        await store.pull_subjects_into_mirror([IRI(remote_iri)])
        names = [
            str(o)
            for _s, _p, o in store.graph.triples((remote_iri, "https://schema.org/name", None))
        ]
        assert names == ['"Remote"']
        await store.aclose()


async def test_async_http_pull_invalid_turtle_raises_query_error() -> None:
    remote_iri = "http://example.org/person/1"

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            return httpx.Response(
                200,
                content=b"not turtle",
                headers={"Content-Type": "text/turtle"},
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        with pytest.raises(QueryError, match="Failed to parse CONSTRUCT"):
            await store.pull_subjects_into_mirror([IRI(remote_iri)])
        await store.aclose()


async def test_async_http_writer_get_skips_pull_when_subject_in_mirror() -> None:
    remote_iri = "http://example.org/person/local"
    construct_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            construct_calls.append(body)
            return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            prefixes={"schema": "https://schema.org/"},
        )
        _seed_person_in_mirror(store, remote_iri, "Local")
        async with AsyncSPARQLSession(store=store) as session:
            loaded = await session.get(Person, IRI(remote_iri))
        assert loaded is not None
        assert loaded.name == "Local"
        assert construct_calls == []
        await store.aclose()


async def test_async_http_remote_authoritative_refresh_pulls_stale_mirror() -> None:
    remote_iri = "http://example.org/person/remote"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f'<{remote_iri}> a schema:Person ; schema:name "Remote" .\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") != "application/sparql-query":
            return httpx.Response(404)
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            return httpx.Response(
                200,
                content=remote_ttl.encode(),
                headers={"Content-Type": "text/turtle"},
            )
        return httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            prefixes={"schema": "https://schema.org/"},
            mirror_mode="remote_authoritative",
        )
        _seed_person_in_mirror(store, remote_iri, "Stale")
        async with AsyncSPARQLSession(store=store) as session:
            detached = Person(id=IRI(remote_iri), name="Stale")
            await session.merge(detached)
            refreshed = await session.refresh(detached)
        assert refreshed.name == "Remote"
        await store.aclose()


async def test_async_http_remote_authoritative_get_pulls_stale_mirror() -> None:
    remote_iri = "http://example.org/person/remote"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f'<{remote_iri}> a schema:Person ; schema:name "Remote" .\n'
    )
    construct_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") != "application/sparql-query":
            return httpx.Response(404)
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            construct_calls.append(body)
            return httpx.Response(
                200,
                content=remote_ttl.encode(),
                headers={"Content-Type": "text/turtle"},
            )
        return httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            prefixes={"schema": "https://schema.org/"},
            mirror_mode="remote_authoritative",
        )
        _seed_person_in_mirror(store, remote_iri, "Stale")
        async with AsyncSPARQLSession(store=store) as session:
            loaded = await session.get(Person, IRI(remote_iri))
        assert loaded is not None
        assert loaded.name == "Remote"
        assert len(construct_calls) == 1
        await store.aclose()


async def test_async_http_query_retries_on_503() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            max_retries=2,
            retry_backoff=0,
        )
        await store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
        assert attempts["n"] == 3
        await store.aclose()


async def test_async_http_query_get_method() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            query_method="get",
            max_retries=0,
        )
        await store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
        assert seen == ["GET"]
        await store.aclose()


async def test_async_http_update_chunks_multiple_posts() -> None:
    updates: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        updates.append(request.content.decode())
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            max_triples_per_update=1,
            max_retries=0,
        )
        g = Store()
        g.add(("urn:s1", "urn:p1", "urn:o1"))
        g.add(("urn:s2", "urn:p2", "urn:o2"))
        await store.update_graph(add=g)
        assert len(updates) == 2
        assert len(store.graph) == 2
        await store.aclose()


async def test_async_http_update_mirror_unchanged_on_mid_batch_failure() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200)
        return httpx.Response(400, text="bad")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            max_triples_per_update=1,
            max_retries=0,
        )
        g = Store()
        g.add(("urn:s1", "urn:p1", "urn:o1"))
        g.add(("urn:s2", "urn:p2", "urn:o2"))
        with pytest.raises(QueryError, match="SPARQL UPDATE failed"):
            await store.update_graph(add=g)
        assert len(store.graph) == 0
        await store.aclose()


async def test_async_http_store_query_method_property() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200))
    ) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            query_method="get",
        )
        assert store.query_method == "get"
        await store.aclose()


async def test_async_http_post_update_skips_blank() -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request.content.decode())
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        await store._post_update("   \n")
        assert posts == []
        await store.aclose()


async def test_async_http_query_wraps_non_query_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(http_common, "async_execute_select", boom)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200))
    ) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        with pytest.raises(QueryError, match="SPARQL query failed: boom"):
            await store.query("SELECT * WHERE { ?s ?p ?o }")
        await store.aclose()


async def test_async_http_construct_wraps_non_query_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(http_common, "async_request_with_retry", boom)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200))
    ) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        with pytest.raises(QueryError, match="SPARQL CONSTRUCT failed: boom"):
            await store.pull_subjects_into_mirror([IRI("http://example.org/person/1")])
        await store.aclose()


@pytest.mark.asyncio
async def test_async_http_graph_store_url_property() -> None:
    store = AsyncHttpStore(
        "http://example.org/sparql/",
        graph_store_url="http://example.org/data/",
    )
    assert store.graph_store_url == "http://example.org/data"
    await store.aclose()


@pytest.mark.asyncio
async def test_async_http_sync_mirror_requires_graph_store_url() -> None:
    store = AsyncHttpStore("http://example.org/sparql")
    with pytest.raises(ConfigurationError, match="graph_store_url"):
        await store.sync_mirror()
    await store.aclose()


@pytest.mark.asyncio
async def test_async_http_sync_mirror_replaces_mirror() -> None:
    remote_turtle = b'@prefix ex: <http://ex/> .\n<http://ex/s> <http://ex/p> "v" .\n'
    stale = Store()
    stale.add(("http://ex/s", "http://ex/p", "http://ex/old"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, content=remote_turtle, headers={"Content-Type": "text/turtle"}
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = AsyncHttpStore(
            "http://example.org/sparql",
            client=client,
            graph=stale,
            graph_store_url="http://example.org/data",
        )
        await store.sync_mirror()
        assert len(store.graph) == 1
        await store.aclose()
