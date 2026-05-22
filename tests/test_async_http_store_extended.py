"""Extended AsyncHttpStore tests (mirror sync HttpStore coverage)."""

from __future__ import annotations

import httpx
import pytest
from pyoxigraph import Literal
from triplemodel import Store

from sparqlmodel import IRI, Field, SPARQLModel
from sparqlmodel.async_session import AsyncSPARQLSession
from sparqlmodel.exceptions import QueryError
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
        store = AsyncHttpStore("http://example.org/sparql", client=client)
        with pytest.raises(QueryError, match="SPARQL query failed"):
            await store.query("SELECT * WHERE { ?s ?p ?o }")


async def test_async_http_update_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        store = AsyncHttpStore("http://example.org/sparql", client=client)
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
