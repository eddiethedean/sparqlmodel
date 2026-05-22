"""Shared SPARQL HTTP helpers for sync and async endpoint stores."""

from __future__ import annotations

import asyncio
import base64
import re
import time
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Literal, cast
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from triplemodel import Store, load_graph

from sparqlmodel.exceptions import ConfigurationError, QueryError
from sparqlmodel.graph import _subject_pattern
from sparqlmodel.rdf_n3 import triple_to_n3
from sparqlmodel.types import IRI, expand_iri

QueryMethod = Literal["post", "get"]
_VALID_QUERY_METHODS = frozenset({"post", "get"})
_RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})
_MAX_BACKOFF_SECONDS = 30.0

MirrorMode = Literal["writer", "remote_authoritative"]

_VALID_MIRROR_MODES = frozenset({"writer", "remote_authoritative"})


def validate_mirror_mode(mirror_mode: str) -> MirrorMode:
    if mirror_mode not in _VALID_MIRROR_MODES:
        raise ValueError(
            f"mirror_mode must be 'writer' or 'remote_authoritative', got {mirror_mode!r}"
        )
    return cast(MirrorMode, mirror_mode)


def validate_query_method(query_method: str) -> QueryMethod:
    if query_method not in _VALID_QUERY_METHODS:
        raise ValueError(f"query_method must be 'post' or 'get', got {query_method!r}")
    return cast(QueryMethod, query_method)


def validate_http_resilience(
    *,
    max_retries: int,
    retry_backoff: float,
    max_triples_per_update: int,
) -> None:
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    if retry_backoff < 0:
        raise ValueError(f"retry_backoff must be >= 0, got {retry_backoff}")
    if max_triples_per_update < 1:
        raise ValueError(f"max_triples_per_update must be >= 1, got {max_triples_per_update}")


def is_retryable_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_STATUS_CODES


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return is_retryable_status(exc.response.status_code)
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError))


def _backoff_seconds(retry_backoff: float, attempt: int) -> float:
    return min(retry_backoff * (2**attempt), _MAX_BACKOFF_SECONDS)


def _chunk_triples(graph: Store, max_triples: int) -> list[list[tuple[Any, Any, Any]]]:
    triples = list(graph)
    if not triples:
        return []
    chunks: list[list[tuple[Any, Any, Any]]] = []
    for index in range(0, len(triples), max_triples):
        chunks.append(triples[index : index + max_triples])
    return chunks


def iter_graph_chunks(graph: Store, max_triples: int) -> Iterator[Store]:
    """Yield sub-stores with at most ``max_triples`` triples each."""
    for batch in _chunk_triples(graph, max_triples):
        chunk = Store()
        for triple in batch:
            chunk.add(triple)
        yield chunk


def build_update_chunks(
    remove: Store | None,
    add: Store | None,
    max_triples: int,
) -> list[str]:
    """Build ordered SPARQL UPDATE strings: all DELETE chunks, then all INSERT chunks."""
    chunks: list[str] = []
    if remove is not None and len(remove):
        for graph_chunk in iter_graph_chunks(remove, max_triples):
            update = graph_to_delete_data(graph_chunk)
            if update:
                chunks.append(update)
    if add is not None and len(add):
        for graph_chunk in iter_graph_chunks(add, max_triples):
            update = graph_to_insert_data(graph_chunk)
            if update:
                chunks.append(update)
    return chunks


def append_query_params(url: str, **params: str) -> str:
    """Append query parameters to ``url``, preserving any existing query string."""
    parsed = urlparse(url)
    query_items = list(parse_qsl(parsed.query, keep_blank_values=True))
    query_items.extend(params.items())
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def expand_subject_iris(
    iris: Iterable[str | IRI],
    prefixes: dict[str, str],
) -> list[str]:
    """Expand compact IRIs to absolute form for CONSTRUCT VALUES and mirror sync."""
    unique_raw = list(dict.fromkeys(str(i) for i in iris))
    expanded: list[str] = []
    for raw in unique_raw:
        try:
            expanded.append(expand_iri(raw, prefixes))
        except ConfigurationError as exc:
            raise QueryError(f"Invalid IRI for CONSTRUCT: {exc}") from exc
    return expanded


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    operation: str,
    max_retries: int,
    retry_backoff: float,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with retries on transient failures."""
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.request(method.upper(), url, **kwargs)
            if is_retryable_status(response.status_code):
                if attempt >= max_retries:
                    response.raise_for_status()
                response.close()
                time.sleep(_backoff_seconds(retry_backoff, attempt))
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if not is_retryable_exception(exc) or attempt >= max_retries:
                raise QueryError(f"{operation} failed: {exc}") from exc
            time.sleep(_backoff_seconds(retry_backoff, attempt))
    raise QueryError(f"{operation} failed: {last_exc}") from last_exc  # pragma: no cover


async def async_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    operation: str,
    max_retries: int,
    retry_backoff: float,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an async HTTP request with retries on transient failures."""
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method.upper(), url, **kwargs)
            if is_retryable_status(response.status_code):
                if attempt >= max_retries:
                    response.raise_for_status()
                await response.aclose()
                await asyncio.sleep(_backoff_seconds(retry_backoff, attempt))
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if not is_retryable_exception(exc) or attempt >= max_retries:
                raise QueryError(f"{operation} failed: {exc}") from exc
            await asyncio.sleep(_backoff_seconds(retry_backoff, attempt))
    raise QueryError(f"{operation} failed: {last_exc}") from last_exc  # pragma: no cover


def execute_select(
    client: httpx.Client,
    url: str,
    sparql: str,
    *,
    query_method: QueryMethod,
    max_retries: int,
    retry_backoff: float,
) -> httpx.Response:
    """Run a remote SELECT using GET or POST."""
    if query_method == "get":
        query_url = append_query_params(url, query=sparql)
        return request_with_retry(
            client,
            "GET",
            query_url,
            operation="SPARQL query",
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            headers={"Accept": "application/sparql-results+json"},
        )
    return request_with_retry(
        client,
        "POST",
        url,
        operation="SPARQL query",
        max_retries=max_retries,
        retry_backoff=retry_backoff,
        content=sparql.encode("utf-8"),
        headers=SPARQL_QUERY_HEADERS,
    )


async def async_execute_select(
    client: httpx.AsyncClient,
    url: str,
    sparql: str,
    *,
    query_method: QueryMethod,
    max_retries: int,
    retry_backoff: float,
) -> httpx.Response:
    """Run a remote SELECT using GET or POST (async)."""
    if query_method == "get":
        query_url = append_query_params(url, query=sparql)
        return await async_request_with_retry(
            client,
            "GET",
            query_url,
            operation="SPARQL query",
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            headers={"Accept": "application/sparql-results+json"},
        )
    return await async_request_with_retry(
        client,
        "POST",
        url,
        operation="SPARQL query",
        max_retries=max_retries,
        retry_backoff=retry_backoff,
        content=sparql.encode("utf-8"),
        headers=SPARQL_QUERY_HEADERS,
    )


def remove_mirror_subjects(
    graph: Store,
    iris: Iterable[str | IRI],
    prefixes: dict[str, str],
) -> None:
    """Remove all mirror triples whose subject is one of ``iris``."""
    unique = list(dict.fromkeys(str(i) for i in iris))
    for iri in unique:
        subject = _subject_pattern(iri, prefixes)
        for triple in list(graph.triples((subject, None, None))):
            graph.remove(triple)


def apply_construct_to_mirror(
    graph: Store,
    remote: Store | None,
    *,
    subjects: Iterable[str | IRI],
    prefixes: dict[str, str],
) -> None:
    """Replace mirror triples for ``subjects`` with triples from ``remote`` (may be empty)."""
    remove_mirror_subjects(graph, subjects, prefixes)
    if remote is not None:
        for triple in remote:
            graph.add(triple)


def graph_to_insert_data(graph: Store) -> str:
    if len(graph) == 0:
        return ""
    lines = [f"  {triple_to_n3(s, p, o)} ." for s, p, o in graph]
    return "INSERT DATA {\n" + "\n".join(lines) + "\n}"


def graph_to_delete_data(graph: Store) -> str:
    if len(graph) == 0:
        return ""
    lines = [f"  {triple_to_n3(s, p, o)} ." for s, p, o in graph]
    return "DELETE DATA {\n" + "\n".join(lines) + "\n}"


def sparql_url(endpoint: str) -> str:
    """Normalize a SPARQL endpoint URL, preserving an existing query string."""
    base, sep, query = endpoint.partition("?")
    if base.endswith("/sparql") or base.endswith("/query") or base.endswith("/update"):
        path = base
    else:
        path = urljoin(base.rstrip("/") + "/", "sparql")
    if sep:
        return f"{path}?{query}"
    return path


_SPARQL_QUERY_KIND = re.compile(
    r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE|INSERT|DELETE)\b",
    re.IGNORECASE,
)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_block_comments(text: str) -> str:
    return _BLOCK_COMMENT_RE.sub("", text)


def is_select_query(sparql: str) -> bool:
    """Return True when ``sparql`` appears to be a SPARQL SELECT (not ASK/CONSTRUCT/DESCRIBE)."""
    text = _strip_block_comments(sparql)
    while True:
        stripped = text.lstrip()
        if not stripped:
            return False
        if stripped.startswith("#"):
            newline = stripped.find("\n")
            if newline == -1:
                return False
            text = stripped[newline + 1 :]
            continue
        upper = stripped.upper()
        if (upper.startswith("PREFIX ") or upper.startswith("BASE ")) and "\n" in stripped:
            newline = stripped.find("\n")
            text = stripped[newline + 1 :]
            continue
        match = _SPARQL_QUERY_KIND.search(stripped)
        if match is None:
            return False
        return match.group(1).upper() == "SELECT"


def build_request_headers(
    *,
    headers: Mapping[str, str] | None = None,
    auth: tuple[str, str] | None = None,
    bearer_token: str | None = None,
) -> dict[str, str]:
    req_headers = dict(headers or {})
    if bearer_token:
        req_headers["Authorization"] = f"Bearer {bearer_token}"
    if auth is not None:
        user, password = auth
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        req_headers["Authorization"] = f"Basic {token}"
    return req_headers


SPARQL_QUERY_HEADERS = {
    "Content-Type": "application/sparql-query",
    "Accept": "application/sparql-results+json",
}

SPARQL_UPDATE_HEADERS = {
    "Content-Type": "application/sparql-update",
    "Accept": "*/*",
}

GSP_ACCEPT_HEADERS = {
    "Accept": "text/turtle, application/n-triples;q=0.9, */*;q=0.1",
}


def default_graph_store_url(sparql_endpoint: str) -> str | None:
    """Heuristic Fuseki GSP URL from a SPARQL endpoint (``.../sparql`` → ``.../data``)."""
    base, sep, query = sparql_endpoint.partition("?")
    path = base.rstrip("/")
    if path.endswith("/sparql"):
        gsp = path[: -len("/sparql")] + "/data"
        return f"{gsp}?{query}" if sep else gsp
    return None


def replace_mirror_from_graph(target: Store, remote: Store | None) -> None:
    """Replace all triples in ``target`` with triples from ``remote`` (empty clears mirror)."""
    for triple in list(target):
        target.remove(triple)
    if remote is not None:
        for triple in remote:
            target.add(triple)


def _gsp_format_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return "turtle"
    media = content_type.split(";", 1)[0].strip().lower()
    if media in ("text/turtle", "application/x-turtle"):
        return "turtle"
    if media in ("application/n-triples", "text/plain"):
        return "nt"
    if media in ("application/trig", "application/x-trig"):
        return "trig"
    return "turtle"


def parse_gsp_response(content: bytes, content_type: str | None) -> Store:
    """Parse a Graph Store HTTP GET body into a :class:`~triplemodel.Store`."""
    if not content.strip():
        return Store()
    fmt = _gsp_format_from_content_type(content_type)
    try:
        return load_graph(data=content, format=fmt)
    except Exception as exc:
        raise QueryError(f"Failed to parse Graph Store response: {exc}") from exc


def fetch_graph_store(
    client: httpx.Client,
    url: str,
    *,
    max_retries: int,
    retry_backoff: float,
) -> tuple[bytes, str | None]:
    """GET an RDF graph via Graph Store HTTP; return body and ``Content-Type``."""
    response = request_with_retry(
        client,
        "GET",
        url,
        operation="Graph Store GET",
        max_retries=max_retries,
        retry_backoff=retry_backoff,
        headers=GSP_ACCEPT_HEADERS,
    )
    content_type = response.headers.get("Content-Type")
    return response.content, content_type


async def async_fetch_graph_store(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int,
    retry_backoff: float,
) -> tuple[bytes, str | None]:
    """Async GET for Graph Store HTTP."""
    response = await async_request_with_retry(
        client,
        "GET",
        url,
        operation="Graph Store GET",
        max_retries=max_retries,
        retry_backoff=retry_backoff,
        headers=GSP_ACCEPT_HEADERS,
    )
    content_type = response.headers.get("Content-Type")
    return response.content, content_type
