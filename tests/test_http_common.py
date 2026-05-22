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
