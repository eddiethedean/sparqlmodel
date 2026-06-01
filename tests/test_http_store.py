"""Tests for HttpStore (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest
from pyoxigraph import Literal
from triplemodel import Store

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession
from sparqlmodel.exceptions import ConfigurationError, QueryError
from sparqlmodel.stores import http_common
from sparqlmodel.stores.http import HttpStore, _graph_to_delete_data, _graph_to_insert_data
from sparqlmodel.stores.http_common import is_select_query


class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")


def test_is_select_query_prefix_and_empty() -> None:
    assert not is_select_query("")
    assert not is_select_query("PREFIX schema: <https://schema.org/>")
    assert is_select_query("PREFIX schema: <https://schema.org/>\nSELECT ?s WHERE { ?s ?p ?o }")
    assert not is_select_query("ASK { ?s ?p ?o }")


def test_is_select_query_inline_prefix_and_comments() -> None:
    assert is_select_query("PREFIX ex: <http://ex/> SELECT ?s WHERE {}")
    assert is_select_query("# comment\nSELECT ?s WHERE { ?s ?p ?o }")
    assert is_select_query("BASE <http://ex/>\nSELECT ?s WHERE {}")
    assert not is_select_query("BASE <http://ex/>")
    assert not is_select_query("   ")
    assert not is_select_query("# only a comment")


def test_is_select_query_rejects_block_comment_disguised_ask() -> None:
    assert not is_select_query("/* SELECT */ ASK { ?s ?p ?o }")


def test_http_store_pull_empty_iris_no_request() -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request.content.decode())
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    store.pull_subjects_into_mirror([])
    assert posts == []
    store.close()


def test_http_store_construct_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        max_retries=0,
    )
    with pytest.raises(QueryError, match="CONSTRUCT failed"):
        store.pull_subjects_into_mirror([IRI("http://example.org/person/1")])
    store.close()


def test_http_store_construct_empty_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    store.pull_subjects_into_mirror([IRI("http://example.org/person/1")])
    assert len(store.graph) == 0
    store.close()


def test_insert_delete_data_helpers() -> None:
    g = Store()
    s = "urn:s"
    p = "urn:p"
    g.add((s, p, "urn:o"))
    assert "INSERT DATA" in _graph_to_insert_data(g)
    assert "DELETE DATA" in _graph_to_delete_data(g)
    assert _graph_to_insert_data(Store()) == ""


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
    store = HttpStore("http://example.org/sparql", client=client, max_retries=0)
    with pytest.raises(QueryError, match="SPARQL query failed"):
        store.query("SELECT * WHERE { ?s ?p ?o }")
    store.close()


def test_http_store_update_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad update")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client, max_retries=0)
    g = Store()
    g.add(("urn:s", "urn:p", "urn:o"))
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
    from sparqlmodel.stores.http import _graph_to_delete_data
    from sparqlmodel.stores.memory import _term_value

    assert _graph_to_delete_data(Store()) == ""
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
        return httpx.Response(200, json={"not": "sparql-results"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore("http://example.org/sparql", client=client)
    with pytest.raises(QueryError, match="Failed to parse"):
        store.query("SELECT * WHERE { ?s ?p ?o }")
    store.close()


def test_http_store_query_ask_rejected() -> None:
    store = HttpStore("http://example.org/sparql")
    with pytest.raises(QueryError, match="Expected SELECT query"):
        store.query("ASK { ?s ?p ?o }")
    store.close()


def test_http_store_query_select_with_ask_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"head": {}, "boolean": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    with pytest.raises(QueryError, match="ASK"):
        store.query("SELECT * WHERE { ?s ?p ?o }")
    store.close()


def test_http_store_read_write_endpoints() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.headers.get("content-type") == "application/sparql-update":
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/dataset",
        read_endpoint="http://read.example/query",
        write_endpoint="http://write.example/update",
        client=client,
    )
    assert store.read_endpoint == "http://read.example/query"
    assert store.write_endpoint == "http://write.example/update"
    store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
    g = Store()
    g.add(("urn:s", "urn:p", "urn:o"))
    store.update_graph(add=g)
    assert any("read.example" in url for url in seen)
    assert any("write.example" in url for url in seen)
    store.close()


def test_http_store_operations_after_close_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    store.close()
    with pytest.raises(RuntimeError, match="closed HttpStore"):
        store.query("SELECT * WHERE { ?s ?p ?o }")
    g = Store()
    g.add(("urn:s", "urn:p", "urn:o"))
    with pytest.raises(RuntimeError, match="closed HttpStore"):
        store.update_graph(add=g)
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
    g = Store()
    g.add(("urn:s", "urn:p", "urn:o"))
    store.update_graph(remove=g)
    assert "DELETE DATA" in updates[0]
    assert len(store.graph) == 0
    store.close()


def test_http_store_basic_auth_over_bearer() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore(
        "http://example.org/sparql",
        auth=("user", "pass"),
        bearer_token="secret",
        client=client,
    )
    store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
    assert seen[0].startswith("Basic ")
    store.close()


def test_http_store_refresh_pulls_remote_subject_into_mirror() -> None:
    """refresh() CONSTRUCT-syncs remote subjects before hydration (parity with get)."""
    remote_iri = "http://example.org/person/remote"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f"<{remote_iri}> a schema:Person ;\n"
        '  schema:name "Remote" .\n'
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

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
    )
    session = SPARQLSession(store=store)
    detached = Person(id=IRI(remote_iri), name="Stale")
    session.merge(detached)
    refreshed = session.refresh(detached)
    assert refreshed.name == "Remote"
    assert len(store.graph) >= 2
    store.close()


def test_http_store_get_pulls_remote_subject_into_mirror() -> None:
    """get() CONSTRUCT-syncs remote subjects before hydration."""
    remote_iri = "http://example.org/person/remote"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f"<{remote_iri}> a schema:Person ;\n"
        '  schema:name "Remote" .\n'
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
    client = httpx.Client(transport=transport)
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
    )
    session = SPARQLSession(store=store)
    bindings = session.execute("SELECT ?person WHERE { ?person ?p ?o }")
    assert bindings[0]["person"] == remote_iri
    loaded = session.get(Person, IRI(remote_iri))
    assert loaded is not None
    assert loaded.name == "Remote"
    assert len(store.graph) >= 2
    store.close()


def test_http_store_query_all_hydrates_remote_rows() -> None:
    """query().all() pulls remote subjects into the mirror before hydration."""
    remote_iri = "http://example.org/person/remote"
    remote_ttl = (
        "@prefix schema: <https://schema.org/> .\n"
        f"<{remote_iri}> a schema:Person ;\n"
        '  schema:name "Remote" .\n'
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
    client = httpx.Client(transport=transport)
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
    )
    session = SPARQLSession(store=store)
    results = session.query(Person).all()
    assert len(results) == 1
    assert results[0].name == "Remote"
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
    loaded = session.get(Person, person.id, depth=0)
    assert loaded is not None
    assert loaded.name == "Odos"
    bindings = session.execute("SELECT ?person WHERE { ?person a <https://schema.org/Person> }")
    assert bindings[0]["person"] == "urn:person:odos"
    store.close()


def _seed_person_in_mirror(store: HttpStore, iri: str, name: str) -> None:
    store.graph.add(
        (
            iri,
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "https://schema.org/Person",
        )
    )
    store.graph.add((iri, "https://schema.org/name", Literal(name)))


def test_http_store_invalid_mirror_mode() -> None:
    with pytest.raises(ValueError, match="mirror_mode"):
        HttpStore("http://example.org/sparql", mirror_mode="invalid")  # type: ignore[arg-type]


def test_http_store_pull_replaces_stale_predicate() -> None:
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

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
    )
    _seed_person_in_mirror(store, remote_iri, "Stale")
    store.pull_subjects_into_mirror([IRI(remote_iri)])
    names = [
        str(o) for _s, _p, o in store.graph.triples((remote_iri, "https://schema.org/name", None))
    ]
    assert names == ['"Remote"']
    store.close()


def test_http_store_pull_empty_construct_clears_subject() -> None:
    remote_iri = "http://example.org/person/1"

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    _seed_person_in_mirror(store, remote_iri, "Gone")
    store.pull_subjects_into_mirror([IRI(remote_iri)])
    assert not list(store.graph.triples((remote_iri, None, None)))
    store.close()


def test_http_store_pull_invalid_turtle_raises_query_error() -> None:
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

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    with pytest.raises(QueryError, match="Failed to parse CONSTRUCT"):
        store.pull_subjects_into_mirror([IRI(remote_iri)])
    store.close()


def test_http_store_writer_get_skips_pull_when_subject_in_mirror() -> None:
    remote_iri = "http://example.org/person/local"
    construct_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            construct_calls.append(body)
            return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
    )
    _seed_person_in_mirror(store, remote_iri, "Local")
    session = SPARQLSession(store=store)
    loaded = session.get(Person, IRI(remote_iri))
    assert loaded is not None
    assert loaded.name == "Local"
    assert construct_calls == []
    store.close()


def test_http_store_remote_authoritative_get_pulls_stale_mirror() -> None:
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

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
        mirror_mode="remote_authoritative",
    )
    _seed_person_in_mirror(store, remote_iri, "Stale")
    session = SPARQLSession(store=store)
    loaded = session.get(Person, IRI(remote_iri))
    assert loaded is not None
    assert loaded.name == "Remote"
    assert len(construct_calls) == 1
    store.close()


def test_http_store_remote_authoritative_refresh_pulls_stale_mirror() -> None:
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

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
        mirror_mode="remote_authoritative",
    )
    _seed_person_in_mirror(store, remote_iri, "Stale")
    session = SPARQLSession(store=store)
    detached = Person(id=IRI(remote_iri), name="Stale")
    session.merge(detached)
    refreshed = session.refresh(detached)
    assert refreshed.name == "Remote"
    store.close()


def test_http_store_query_retries_on_503() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        max_retries=2,
        retry_backoff=0,
    )
    store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
    assert attempts["n"] == 3
    store.close()


def test_http_store_query_get_method() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        query_method="get",
        max_retries=0,
    )
    store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
    assert seen[0][0] == "GET"
    assert "query=SELECT" in seen[0][1]
    store.close()


def test_http_store_query_get_preserves_endpoint_query_params() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={"head": {"vars": []}, "results": {"bindings": []}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://fuseki.example/ds/sparql",
        read_endpoint="http://fuseki.example/ds/sparql?default-graph-uri=http://example.org/g",
        client=client,
        query_method="get",
        max_retries=0,
    )
    store.query("SELECT * WHERE { ?s ?p ?o } LIMIT 0")
    assert len(seen) == 1
    assert "default-graph-uri=" in seen[0]
    assert "query=SELECT" in seen[0]
    assert seen[0].count("?") == 1
    store.close()


def test_http_store_pull_expands_compact_iri_in_construct() -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode())
        return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
        max_retries=0,
    )
    store.pull_subjects_into_mirror([IRI("schema:Person/1")])
    assert len(bodies) == 1
    assert "https://schema.org/Person/1" in bodies[0]
    assert "schema:Person/1" not in bodies[0]
    store.close()


def test_http_store_get_pulls_when_mirror_lacks_person_rdf_type() -> None:
    from pyoxigraph import Literal, NamedNode

    remote_iri = "http://example.org/person/wrong-type"
    construct_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if body.strip().upper().startswith("CONSTRUCT"):
            construct_calls.append(body)
            return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        prefixes={"schema": "https://schema.org/"},
    )
    subj = NamedNode(remote_iri)
    store.graph.add(
        (
            subj,
            NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            NamedNode("https://schema.org/Organization"),
        )
    )
    store.graph.add((subj, NamedNode("https://schema.org/name"), Literal("Wrong")))
    session = SPARQLSession(store=store)
    loaded = session.get(Person, IRI(remote_iri))
    assert loaded is None
    assert len(construct_calls) == 1
    store.close()


def test_http_store_update_chunks_multiple_posts() -> None:
    updates: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        updates.append(request.content.decode())
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        max_triples_per_update=1,
        max_retries=0,
    )
    g = Store()
    g.add(("urn:s1", "urn:p1", "urn:o1"))
    g.add(("urn:s2", "urn:p2", "urn:o2"))
    store.update_graph(add=g)
    assert len(updates) == 2
    assert all("INSERT DATA" in u for u in updates)
    assert len(store.graph) == 2
    store.close()


def test_http_store_update_mirror_unchanged_on_mid_batch_failure() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200)
        return httpx.Response(400, text="bad")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        max_triples_per_update=1,
        max_retries=0,
    )
    g = Store()
    g.add(("urn:s1", "urn:p1", "urn:o1"))
    g.add(("urn:s2", "urn:p2", "urn:o2"))
    with pytest.raises(QueryError, match="SPARQL UPDATE failed"):
        store.update_graph(add=g)
    assert len(store.graph) == 0
    store.close()


def test_http_store_construct_retries_on_503() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        max_retries=2,
        retry_backoff=0,
    )
    store.pull_subjects_into_mirror([IRI("http://example.org/person/1")])
    assert attempts["n"] == 2
    store.close()


def test_http_store_invalid_resilience_params() -> None:
    with pytest.raises(ValueError, match="max_triples_per_update"):
        HttpStore("http://example.org/sparql", max_triples_per_update=0)
    with pytest.raises(ValueError, match="query_method"):
        HttpStore("http://example.org/sparql", query_method="put")  # type: ignore[arg-type]


def test_http_store_query_method_property() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    store = HttpStore("http://example.org/sparql", client=client, query_method="get")
    assert store.query_method == "get"
    store.close()


def test_http_store_post_update_skips_blank() -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request.content.decode())
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore("http://example.org/sparql", client=client)
    store._post_update("   \n")
    assert posts == []
    store.close()


def test_http_store_query_wraps_non_query_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(http_common, "execute_select", boom)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    store = HttpStore("http://example.org/sparql", client=client)
    with pytest.raises(QueryError, match="SPARQL query failed: boom"):
        store.query("SELECT * WHERE { ?s ?p ?o }")
    store.close()


def test_http_store_construct_wraps_non_query_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(http_common, "request_with_retry", boom)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    store = HttpStore("http://example.org/sparql", client=client)
    with pytest.raises(QueryError, match="SPARQL CONSTRUCT failed: boom"):
        store.pull_subjects_into_mirror([IRI("http://example.org/person/1")])
    store.close()


def test_http_store_sync_mirror_requires_graph_store_url() -> None:
    store = HttpStore("http://example.org/sparql")
    with pytest.raises(ConfigurationError, match="graph_store_url"):
        store.sync_mirror()
    store.close()


def test_http_store_sync_mirror_replaces_mirror() -> None:
    remote_turtle = (
        b"@prefix schema: <https://schema.org/> .\n"
        b'<http://example.org/person/1> a schema:Person ; schema:name "Remote" .\n'
    )
    stale = Store()
    stale.add(
        (
            "http://example.org/person/1",
            "https://schema.org/name",
            Literal("Stale"),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/data"):
            return httpx.Response(
                200, content=remote_turtle, headers={"Content-Type": "text/turtle"}
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/ds/sparql",
        client=client,
        graph=stale,
        graph_store_url="http://example.org/ds/data",
        prefixes={"schema": "https://schema.org/"},
    )
    store.sync_mirror()
    assert len(store.graph) >= 2
    assert any("Remote" in str(o) for _s, _p, o in store.graph)
    assert not any("Stale" in str(o) for _s, _p, o in store.graph)
    store.close()


def test_http_store_sync_mirror_refreshes_session_cache() -> None:
    remote_turtle = (
        b"@prefix schema: <https://schema.org/> .\n"
        b'<http://example.org/person/1> a schema:Person ; schema:name "Remote" .\n'
    )
    stale = Store()
    stale.add(
        (
            "http://example.org/person/1",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "https://schema.org/Person",
        )
    )
    stale.add(
        (
            "http://example.org/person/1",
            "https://schema.org/name",
            Literal("Stale"),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/data"):
            return httpx.Response(
                200, content=remote_turtle, headers={"Content-Type": "text/turtle"}
            )
        if request.method == "POST" and b"SELECT" in request.content:
            return httpx.Response(
                200,
                content=b'{"head":{"vars":["person"]},"results":{"bindings":[]}}',
                headers={"Content-Type": "application/sparql-results+json"},
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/ds/sparql",
        client=client,
        graph=stale,
        graph_store_url="http://example.org/ds/data",
        prefixes={"schema": "https://schema.org/"},
    )
    person_iri = IRI("http://example.org/person/1")
    with SPARQLSession(store=store, close_on_exit=False) as session:
        cached = session.get(Person, person_iri)
        assert cached is not None
        assert cached.name == "Stale"
        store.sync_mirror()
        fresh = session.get(Person, person_iri)
        assert fresh is not None
        assert fresh.name == "Remote"
    store.close()


def test_http_store_sync_mirror_empty_remote_clears_mirror() -> None:
    stale = Store()
    stale.add(("http://ex/s", "http://ex/p", "http://ex/o"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = HttpStore(
        "http://example.org/sparql",
        client=client,
        graph=stale,
        graph_store_url="http://example.org/data",
    )
    store.sync_mirror()
    assert len(store.graph) == 0
    store.close()


def test_http_store_sync_mirror_closed_raises() -> None:
    store = HttpStore(
        "http://example.org/sparql",
        graph_store_url="http://example.org/data",
    )
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        store.sync_mirror()


def test_http_store_graph_store_url_property() -> None:
    store = HttpStore(
        "http://example.org/sparql/",
        graph_store_url="http://example.org/data/",
    )
    assert store.graph_store_url == "http://example.org/data"
    store.close()
