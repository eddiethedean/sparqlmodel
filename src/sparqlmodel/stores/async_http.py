"""Async HTTP SPARQL 1.1 store with a local graph mirror for ORM cascade reads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import httpx
from triplemodel import Store, load_graph

from sparqlmodel.exceptions import QueryError
from sparqlmodel.rdf_n3 import validate_iri_token
from sparqlmodel.stores import http_common
from sparqlmodel.stores.sparql_json import parse_sparql_json_bindings
from sparqlmodel.types import IRI, NamespaceRegistry

_CLOSED_STORE_MSG = "Cannot use a closed AsyncHttpStore"


class AsyncHttpStore:
    """Async SPARQL 1.1 endpoint store with a local ``triplemodel.Store`` mirror.

    ``update_graph`` pushes ``INSERT DATA`` / ``DELETE DATA`` to the remote endpoint
    and applies the same delta to the mirror on success. ``graph`` reads the mirror
    (for cascade / orphan logic and ``session.get``). ``query`` executes SELECT against
    the remote read endpoint.

    Optional ``read_endpoint`` / ``write_endpoint`` support Fuseki-style split URLs
    (defaults to ``endpoint`` for both). ``mirror_mode`` is ``writer`` (default) or
    ``remote_authoritative`` (see :class:`~sparqlmodel.stores.http.HttpStore`).

    **Mirror limitations:** Data written outside this store instance is visible to
    ``query`` / ``execute`` but not to ``graph``, ``get``, or cascade until the mirror
    is updated. Use :meth:`pull_subjects_into_mirror` or ``get`` (auto-pull) to hydrate
    from remote. Prefer :class:`~sparqlmodel.stores.async_memory.AsyncMemoryStore` for
    single-process asyncio tests. Assume a single writer per endpoint.

    If both ``auth`` and ``bearer_token`` are set, Basic ``auth`` wins for
    ``Authorization``.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        read_endpoint: str | None = None,
        write_endpoint: str | None = None,
        graph: Store | None = None,
        prefixes: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        bearer_token: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        mirror_mode: http_common.MirrorMode = "writer",
    ) -> None:
        self._mirror_mode = http_common.validate_mirror_mode(mirror_mode)
        self._endpoint = endpoint.rstrip("/")
        self._read_endpoint = (read_endpoint or endpoint).rstrip("/")
        self._write_endpoint = (write_endpoint or endpoint).rstrip("/")
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
            if timeout is not None:
                self._client.timeout = timeout
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

    def _read_url(self) -> str:
        return http_common.sparql_url(self._read_endpoint)

    def _write_url(self) -> str:
        return http_common.sparql_url(self._write_endpoint)

    def _sparql_url(self) -> str:
        return self._read_url()

    @property
    def graph(self) -> Store:
        return self._graph

    @property
    def namespaces(self) -> NamespaceRegistry:
        return self._registry

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def read_endpoint(self) -> str:
        return self._read_endpoint

    @property
    def write_endpoint(self) -> str:
        return self._write_endpoint

    @property
    def mirror_mode(self) -> http_common.MirrorMode:
        """Mirror mode — ``writer`` (default) or ``remote_authoritative``."""
        return self._mirror_mode

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
        try:
            response = await self._client.post(
                self._write_url(),
                content=update.encode("utf-8"),
                headers=http_common.SPARQL_UPDATE_HEADERS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QueryError(f"SPARQL UPDATE failed: {exc}") from exc

    async def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute SPARQL SELECT against the remote read endpoint."""
        self._check_open()
        if not http_common.is_select_query(sparql):
            raise QueryError("Expected SELECT query for AsyncHttpStore.query()")
        try:
            response = await self._client.post(
                self._read_url(),
                content=sparql.encode("utf-8"),
                headers=http_common.SPARQL_QUERY_HEADERS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QueryError(f"SPARQL query failed: {exc}") from exc

        try:
            return parse_sparql_json_bindings(response.content)
        except QueryError:
            raise
        except Exception as exc:
            raise QueryError(f"Failed to parse SPARQL JSON results: {exc}") from exc

    async def pull_subjects_into_mirror(self, iris: Iterable[str | IRI]) -> None:
        """Fetch triples for ``iris`` from the remote endpoint into the local mirror."""
        self._check_open()
        unique = list(dict.fromkeys(str(i) for i in iris))
        if not unique:
            return
        values = " ".join(f"<{validate_iri_token(iri)}>" for iri in unique)
        sparql = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ VALUES ?s {{ {values} }} ?s ?p ?o }}"
        headers = {
            **http_common.SPARQL_QUERY_HEADERS,
            "Accept": "text/turtle",
        }
        try:
            response = await self._client.post(
                self._read_url(),
                content=sparql.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QueryError(f"SPARQL CONSTRUCT failed: {exc}") from exc
        remote: Store | None = None
        if response.content.strip():
            try:
                remote = load_graph(data=response.content, format="turtle")
            except Exception as exc:
                raise QueryError(f"Failed to parse CONSTRUCT response: {exc}") from exc
        prefixes = dict(self._registry.prefixes)
        http_common.apply_construct_to_mirror(
            self._graph,
            remote,
            subjects=unique,
            prefixes=prefixes,
        )

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
