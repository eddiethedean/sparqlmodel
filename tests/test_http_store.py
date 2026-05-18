"""Tests for HttpStore (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from rdflib import Graph, URIRef

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession
from sparqlmodel.exceptions import QueryError
from sparqlmodel.stores.http import HttpStore, _graph_to_delete_data, _graph_to_insert_data


class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")


def test_insert_delete_data_helpers() -> None:
    g = Graph()
    s = URIRef("urn:s")
    p = URIRef("urn:p")
    g.add((s, p, URIRef("urn:o")))
    assert "INSERT DATA" in _graph_to_insert_data(g)
    assert "DELETE DATA" in _graph_to_delete_data(g)
    assert _graph_to_insert_data(Graph()) == ""


def test_http_store_update_and_mirror() -> None:
    updates: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/sparql-update":
            updates.append(request.content.decode())
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore(
        "http://example.org/", client=client, prefixes={"schema": "https://schema.org/"}
    )

    add_g = Graph()
    s = URIRef("urn:person:1")
    add_g.add(
        (
            s,
            URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            URIRef("https://schema.org/Person"),
        )
    )
    add_g.add((s, URIRef("https://schema.org/name"), URIRef("urn:literal:Alice")))
    store.update_graph(add=add_g)
    assert len(store.graph) == 2
    assert len(updates) == 1
    assert "INSERT DATA" in updates[0]
    store.close()


def test_http_store_query_json() -> None:
    payload = {
        "head": {"vars": ["person"]},
        "results": {
            "bindings": [
                {"person": {"type": "uri", "value": "urn:person:1"}},
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/sparql-query":
            return httpx.Response(200, json=payload)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://fuseki.example/sparql", client=client)
    bindings = store.query("SELECT ?person WHERE { ?person a <https://schema.org/Person> }")
    assert bindings == [{"person": "urn:person:1"}]
    store.close()


def test_http_store_query_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client)
    with pytest.raises(QueryError, match="SPARQL query failed"):
        store.query("SELECT * WHERE { ?s ?p ?o }")
    store.close()


def test_http_store_update_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad update")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client)
    g = Graph()
    g.add((URIRef("urn:s"), URIRef("urn:p"), URIRef("urn:o")))
    with pytest.raises(QueryError, match="SPARQL UPDATE failed"):
        store.update_graph(add=g)
    assert len(store.graph) == 0
    store.close()


def test_http_store_bearer_auth() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", bearer_token="secret", client=client)
    store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
    assert seen[0] == "Bearer secret"
    store.close()


def test_http_store_context_manager_and_auth() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    with HttpStore("http://example.org/sparql", auth=("user", "pass"), client=client) as store:
        store.query("SELECT * WHERE { ?s ?p ?o }")
    assert True


def test_http_store_sparql_url_suffix() -> None:
    store = HttpStore("http://example.org/sparql")
    assert store._sparql_url() == "http://example.org/sparql"
    store2 = HttpStore("http://example.org/dataset")
    assert store2._sparql_url().endswith("/sparql")


def test_http_store_delete_data_empty_and_term_value() -> None:
    from sparqlmodel.stores.http import _graph_to_delete_data, _term_value

    assert _graph_to_delete_data(Graph()) == ""
    assert _term_value(None) is None


def test_http_store_query_bad_result_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client)
    with pytest.raises(QueryError, match="Failed to parse"):
        store.query("SELECT * WHERE { ?s ?p ?o }")
    store.close()


def test_http_store_query_non_select() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    transport = httpx.MockTransport(handler)

    class FakeResult:
        type = "ASK"

        def __iter__(self):
            return iter([])

    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client)
    with patch("sparqlmodel.stores.http.JSONResultParser") as mock_parser:
        mock_parser.return_value.parse.return_value = FakeResult()
        with pytest.raises(QueryError, match="Expected SELECT"):
            store.query("SELECT * WHERE { ?s ?p ?o }")
    store.close()


def test_http_store_endpoint_and_owned_close() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}})

    store = HttpStore("http://example.org/sparql")
    assert store.endpoint == "http://example.org/sparql"
    store.close()

    with HttpStore("http://example.org/sparql") as store2:
        assert store2.endpoint.endswith("sparql")


def test_http_store_empty_update_skips_post() -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request.content.decode())
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    store.update_graph()
    assert posts == []
    store.close()


def test_http_store_update_remove_only() -> None:
    updates: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        updates.append(request.content.decode())
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client)
    g = Graph()
    g.add((URIRef("urn:s"), URIRef("urn:p"), URIRef("urn:o")))
    store.update_graph(remove=g)
    assert "DELETE DATA" in updates[0]
    assert len(store.graph) == 0
    store.close()


def test_http_store_get_uses_mirror_not_remote_select() -> None:
    """SELECT can see remote data that get() cannot until the mirror is updated."""
    state: dict[str, object] = {"select_count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/sparql-query":
            state["select_count"] = int(state["select_count"]) + 1
            return httpx.Response(
                200,
                json={
                    "head": {"vars": ["person"]},
                    "results": {
                        "bindings": [
                            {"person": {"type": "uri", "value": "urn:person:remote"}},
                        ]
                    },
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client)
    session = SPARQLSession(store=store)
    bindings = session.execute("SELECT ?person WHERE { ?person ?p ?o }")
    assert bindings[0]["person"] == "urn:person:remote"
    assert session.get(Person, IRI("urn:person:remote")) is None
    assert len(store.graph) == 0
    store.close()


def test_session_with_http_store_put_and_query() -> None:
    state: dict[str, object] = {"updates": [], "select_count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/sparql-update":
            state["updates"].append(request.content.decode())
            return httpx.Response(200)
        if request.headers.get("content-type") == "application/sparql-query":
            state["select_count"] = int(state["select_count"]) + 1
            return httpx.Response(
                200,
                json={
                    "head": {"vars": ["person"]},
                    "results": {
                        "bindings": [
                            {"person": {"type": "uri", "value": "urn:person:odos"}},
                        ]
                    },
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
    )
    session = SPARQLSession(store=store)
    person = Person(id=IRI("urn:person:odos"), name="Odos")
    session.put(person)
    assert len(store.graph) >= 2
    bindings = session.execute("SELECT ?person WHERE { ?person a <https://schema.org/Person> }")
    assert bindings[0]["person"] == "urn:person:odos"
    store.close()
