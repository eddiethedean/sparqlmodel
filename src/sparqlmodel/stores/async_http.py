"""Async HTTP SPARQL 1.1 store with a local graph mirror for ORM cascade reads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from triplemodel import Store

from sparqlmodel.exceptions import QueryError
from sparqlmodel.stores import http_common
from sparqlmodel.stores.sparql_json import parse_sparql_json_bindings
from sparqlmodel.types import NamespaceRegistry

_CLOSED_STORE_MSG = "Cannot use a closed AsyncHttpStore"


class AsyncHttpStore:
    """Async SPARQL 1.1 endpoint store with a local ``triplemodel.Store`` mirror.

    Same mirror semantics as :class:`~sparqlmodel.stores.http.HttpStore`, using
    ``httpx.AsyncClient`` for non-blocking remote I/O.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        graph: Store | None = None,
        prefixes: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        bearer_token: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._graph = graph or Store()
        self._registry = NamespaceRegistry(prefixes)
        self._registry.bind(self._graph)
        self._timeout = timeout
        self._owns_client = client is None
        req_headers = http_common.build_request_headers(
            headers=headers,
            auth=auth,
            bearer_token=bearer_token,
        )
        if client is not None:
            self._client = client
            if req_headers:
                self._client.headers.update(req_headers)
        else:
            self._client = httpx.AsyncClient(
                headers=req_headers,
                timeout=timeout,
                follow_redirects=True,
            )
        self._closed = False

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError(_CLOSED_STORE_MSG)

    def _sparql_url(self) -> str:
        return http_common.sparql_url(self._endpoint)

    @property
    def graph(self) -> Store:
        return self._graph

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._registry

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncHttpStore:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def _post_update(self, update: str) -> None:
        self._check_open()
        if not update.strip():
            return
        url = http_common.sparql_url(self._endpoint)
        try:
            response = await self._client.post(
                url,
                content=update.encode("utf-8"),
                headers=http_common.SPARQL_UPDATE_HEADERS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QueryError(f"SPARQL UPDATE failed: {exc}") from exc

    async def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute SPARQL SELECT against the remote endpoint."""
        self._check_open()
        url = http_common.sparql_url(self._endpoint)
        try:
            response = await self._client.post(
                url,
                content=sparql.encode("utf-8"),
                headers=http_common.SPARQL_QUERY_HEADERS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QueryError(f"SPARQL query failed: {exc}") from exc

        try:
            return parse_sparql_json_bindings(response.content)
        except Exception as exc:
            raise QueryError(f"Failed to parse SPARQL JSON results: {exc}") from exc

    async def update_graph(self, add: Store | None = None, remove: Store | None = None) -> None:
        """Apply graph delta to remote endpoint and local mirror."""
        self._check_open()
        parts: list[str] = []
        if remove is not None and len(remove):
            parts.append(http_common.graph_to_delete_data(remove))
        if add is not None and len(add):
            parts.append(http_common.graph_to_insert_data(add))
        update = "\n".join(parts)
        await self._post_update(update)

        if remove is not None:
            for triple in remove:
                self._graph.remove(triple)
        if add is not None:
            for triple in add:
                self._graph.add(triple)
