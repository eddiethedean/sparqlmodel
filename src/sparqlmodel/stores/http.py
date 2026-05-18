"""HTTP SPARQL 1.1 store with a local graph mirror for ORM cascade reads."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from io import BytesIO
from typing import Any
from urllib.parse import urljoin

import httpx
from rdflib import Graph
from rdflib.plugins.sparql.results.jsonresults import JSONResultParser
from rdflib.query import ResultRow

from sparqlmodel.exceptions import QueryError
from sparqlmodel.types import NamespaceRegistry

_CLOSED_STORE_MSG = "Cannot use a closed HttpStore"


def _graph_to_insert_data(graph: Graph) -> str:
    if len(graph) == 0:
        return ""
    lines: list[str] = []
    for s, p, o in graph:
        lines.append(f"  {s.n3()} {p.n3()} {o.n3()} .")
    return "INSERT DATA {\n" + "\n".join(lines) + "\n}"


def _graph_to_delete_data(graph: Graph) -> str:
    if len(graph) == 0:
        return ""
    lines: list[str] = []
    for s, p, o in graph:
        lines.append(f"  {s.n3()} {p.n3()} {o.n3()} .")
    return "DELETE DATA {\n" + "\n".join(lines) + "\n}"


def _term_value(term: Any) -> Any:
    if term is None:
        return None
    return str(term)


class HttpStore:
    """SPARQL 1.1 endpoint store with a local rdflib graph mirror.

    ``update_graph`` pushes ``INSERT DATA`` / ``DELETE DATA`` to the remote endpoint
    and applies the same delta to the mirror on success. ``graph`` reads the mirror
    (for cascade / orphan logic and ``session.get``). ``query`` executes SELECT against
    the remote endpoint only.

    **Mirror limitations:** Data written outside this store instance (another app,
    admin UI, or raw SPARQL UPDATE) is visible to ``query`` / ``execute`` but not to
    ``graph``, ``get``, or cascade/orphan logic until the mirror is updated. Prefer
    :class:`~sparqlmodel.stores.memory.MemoryStore` for single-process apps and tests.
    Assume a single writer per endpoint when using ``HttpStore``.

    If both ``auth`` and ``bearer_token`` are set, Basic ``auth`` wins for
    ``Authorization``.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        graph: Graph | None = None,
        prefixes: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        bearer_token: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._graph = graph or Graph()
        self._registry = NamespaceRegistry(prefixes)
        self._registry.bind(self._graph)
        self._timeout = timeout
        self._owns_client = client is None
        req_headers = dict(headers or {})
        if bearer_token is not None:
            req_headers["Authorization"] = f"Bearer {bearer_token}"
        if auth is not None:
            user, password = auth
            token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
            req_headers["Authorization"] = f"Basic {token}"
        if client is not None:
            self._client = client
            if req_headers:
                self._client.headers.update(req_headers)
        else:
            self._client = httpx.Client(
                headers=req_headers,
                timeout=timeout,
                follow_redirects=True,
            )
        self._closed = False

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError(_CLOSED_STORE_MSG)

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._registry

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HttpStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _post_update(self, update: str) -> None:
        self._check_open()
        if not update.strip():
            return
        url = self._sparql_url()
        try:
            response = self._client.post(
                url,
                content=update.encode("utf-8"),
                headers={
                    "Content-Type": "application/sparql-update",
                    "Accept": "*/*",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QueryError(f"SPARQL UPDATE failed: {exc}") from exc

    def _sparql_url(self) -> str:
        if self._endpoint.endswith("/sparql") or self._endpoint.endswith("/query"):
            return self._endpoint
        return urljoin(self._endpoint + "/", "sparql")

    def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute SPARQL SELECT against the remote endpoint."""
        self._check_open()
        url = self._sparql_url()
        try:
            response = self._client.post(
                url,
                content=sparql.encode("utf-8"),
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QueryError(f"SPARQL query failed: {exc}") from exc

        try:
            parser = JSONResultParser()
            result = parser.parse(BytesIO(response.content))
        except Exception as exc:
            raise QueryError(f"Failed to parse SPARQL JSON results: {exc}") from exc

        if result.type != "SELECT":
            raise QueryError(f"Expected SELECT query, got {result.type}")

        bindings: list[dict[str, Any]] = []
        for row in result:
            if isinstance(row, ResultRow):
                bindings.append({str(k): _term_value(row[k]) for k in row.labels})
        return bindings

    def update_graph(self, add: Graph | None = None, remove: Graph | None = None) -> None:
        """Apply graph delta to remote endpoint and local mirror."""
        self._check_open()
        parts: list[str] = []
        if remove is not None and len(remove):
            parts.append(_graph_to_delete_data(remove))
        if add is not None and len(add):
            parts.append(_graph_to_insert_data(add))
        update = "\n".join(parts)
        self._post_update(update)

        if remove is not None:
            for triple in remove:
                self._graph.remove(triple)
        if add is not None:
            for triple in add:
                self._graph.add(triple)
