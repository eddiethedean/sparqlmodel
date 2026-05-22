"""Tests for shared HTTP store helpers."""

from __future__ import annotations

import httpx
import pytest
from triplemodel import Store

from sparqlmodel.stores import http_common


def test_validate_http_resilience_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        http_common.validate_http_resilience(
            max_retries=-1, retry_backoff=0.5, max_triples_per_update=500
        )
    with pytest.raises(ValueError, match="max_triples_per_update"):
        http_common.validate_http_resilience(
            max_retries=0, retry_backoff=0.5, max_triples_per_update=0
        )


def test_is_retryable_status_and_exception() -> None:
    assert http_common.is_retryable_status(503)
    assert not http_common.is_retryable_status(400)
    response = httpx.Response(503)
    exc = httpx.HTTPStatusError("err", request=httpx.Request("GET", "http://x"), response=response)
    assert http_common.is_retryable_exception(exc)
    assert http_common.is_retryable_exception(httpx.ConnectError("down"))


def test_build_update_chunks_orders_delete_before_insert() -> None:
    remove = Store()
    remove.add(("urn:s1", "urn:p", "urn:o1"))
    remove.add(("urn:s1", "urn:p", "urn:o2"))
    add = Store()
    add.add(("urn:s2", "urn:p", "urn:o3"))
    chunks = http_common.build_update_chunks(remove, add, max_triples=1)
    assert len(chunks) == 3
    assert all(c.startswith("DELETE DATA") for c in chunks[:2])
    assert chunks[2].startswith("INSERT DATA")


def test_build_update_chunks_empty() -> None:
    assert http_common.build_update_chunks(None, None, max_triples=10) == []
    assert list(http_common.iter_graph_chunks(Store(), max_triples=10)) == []


def test_sparql_url_preserves_query_string() -> None:
    url = http_common.sparql_url(
        "http://fuseki.example/ds/sparql?default-graph-uri=http://example.org/g"
    )
    assert url == "http://fuseki.example/ds/sparql?default-graph-uri=http://example.org/g"


def test_append_query_params_preserves_existing_query() -> None:
    url = http_common.append_query_params(
        "http://fuseki.example/ds/sparql?default-graph-uri=http://example.org/g",
        query="SELECT * WHERE { ?s ?p ?o }",
    )
    assert url.startswith("http://fuseki.example/ds/sparql?")
    assert "default-graph-uri=" in url
    assert "query=SELECT" in url
    assert url.count("?") == 1


def test_expand_subject_iris_compact() -> None:
    expanded = http_common.expand_subject_iris(
        ["schema:Person/1"],
        {"schema": "https://schema.org/"},
    )
    assert expanded == ["https://schema.org/Person/1"]


def test_expand_subject_iris_unknown_prefix_raises() -> None:
    from sparqlmodel.exceptions import QueryError

    with pytest.raises(QueryError, match="Invalid IRI for CONSTRUCT"):
        http_common.expand_subject_iris(["bad:Thing/1"], {})


def test_validate_query_method_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="query_method"):
        http_common.validate_query_method("put")


def test_validate_http_resilience_retry_backoff() -> None:
    with pytest.raises(ValueError, match="retry_backoff"):
        http_common.validate_http_resilience(
            max_retries=0, retry_backoff=-1, max_triples_per_update=1
        )


def test_request_with_retry_recovers_from_connect_error() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = http_common.request_with_retry(
        client,
        "GET",
        "http://example.org/",
        operation="op",
        max_retries=1,
        retry_backoff=0,
    )
    assert response.status_code == 200
    assert attempts["n"] == 2
    client.close()


@pytest.mark.asyncio
async def test_async_request_with_retry_recovers_from_connect_error() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await http_common.async_request_with_retry(
            client,
            "GET",
            "http://example.org/",
            operation="op",
            max_retries=1,
            retry_backoff=0,
        )
    assert response.status_code == 200
    assert attempts["n"] == 2


def test_default_graph_store_url_fuseki() -> None:
    assert (
        http_common.default_graph_store_url("http://localhost:3030/ds/sparql")
        == "http://localhost:3030/ds/data"
    )
    assert (
        http_common.default_graph_store_url(
            "http://localhost:3030/ds/sparql?default-graph-uri=http://ex/g"
        )
        == "http://localhost:3030/ds/data?default-graph-uri=http://ex/g"
    )
    assert http_common.default_graph_store_url("http://example.org/query") is None


def test_replace_mirror_from_graph() -> None:
    target = Store()
    target.add(("http://ex/s", "http://ex/p", "http://ex/old"))
    remote = Store()
    remote.add(("http://ex/s", "http://ex/p", "http://ex/new"))
    http_common.replace_mirror_from_graph(target, remote)
    assert len(target) == 1


def test_replace_mirror_from_graph_empty_clears() -> None:
    target = Store()
    target.add(("http://ex/s", "http://ex/p", "http://ex/o"))
    http_common.replace_mirror_from_graph(target, None)
    assert len(target) == 0


def test_parse_gsp_response_empty() -> None:
    graph = http_common.parse_gsp_response(b"", None)
    assert len(graph) == 0


def test_parse_gsp_response_turtle() -> None:
    body = b"@prefix ex: <http://ex/> .\nex:s ex:p ex:o .\n"
    graph = http_common.parse_gsp_response(body, "text/turtle")
    assert len(graph) == 1


def test_parse_gsp_response_nt_content_type() -> None:
    body = b"<http://ex/s> <http://ex/p> <http://ex/o> .\n"
    graph = http_common.parse_gsp_response(body, "application/n-triples")
    assert len(graph) == 1


def test_parse_gsp_response_unknown_content_type_uses_turtle() -> None:
    body = b"@prefix ex: <http://ex/> .\nex:s ex:p ex:o .\n"
    graph = http_common.parse_gsp_response(body, "application/rdf+xml")
    assert len(graph) == 1


def test_parse_gsp_response_missing_content_type() -> None:
    body = b"@prefix ex: <http://ex/> .\nex:s ex:p ex:o .\n"
    graph = http_common.parse_gsp_response(body, None)
    assert len(graph) == 1


def test_gsp_format_from_content_type_trig() -> None:
    assert http_common._gsp_format_from_content_type("application/x-trig") == "trig"
    assert http_common._gsp_format_from_content_type("application/x-turtle") == "turtle"


def test_default_graph_store_url_non_sparql() -> None:
    assert http_common.default_graph_store_url("http://example.org/endpoint") is None


def test_parse_gsp_response_invalid_raises() -> None:
    from sparqlmodel.exceptions import QueryError

    with pytest.raises(QueryError, match="Failed to parse Graph Store"):
        http_common.parse_gsp_response(b"not valid turtle {{{", "text/turtle")


def test_fetch_graph_store() -> None:
    turtle = b"@prefix ex: <http://ex/> .\nex:s ex:p ex:o .\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == httpx.URL("http://example.org/data")
        return httpx.Response(200, content=turtle, headers={"Content-Type": "text/turtle"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    content, ctype = http_common.fetch_graph_store(
        client, "http://example.org/data", max_retries=0, retry_backoff=0
    )
    assert ctype == "text/turtle"
    graph = http_common.parse_gsp_response(content, ctype)
    assert len(graph) == 1
    client.close()


@pytest.mark.asyncio
async def test_async_fetch_graph_store() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"", headers={"Content-Type": "text/turtle"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        content, ctype = await http_common.async_fetch_graph_store(
            client, "http://example.org/data", max_retries=0, retry_backoff=0
        )
    assert content == b""
    assert ctype == "text/turtle"
