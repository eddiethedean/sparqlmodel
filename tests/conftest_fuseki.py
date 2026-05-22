"""Fuseki fixtures for HttpStore integration tests (requires running Fuseki)."""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from dataclasses import dataclass

import httpx
import pytest

FUSEKI_DATASET = "sparqlmodel_test"
FUSEKI_BASE_ENV = "FUSEKI_BASE_URL"
FUSEKI_ADMIN_PASSWORD_ENV = "FUSEKI_ADMIN_PASSWORD"
FUSEKI_ADMIN_USER_ENV = "FUSEKI_ADMIN_USER"

SPARQL_QUERY_HEADERS = {
    "Content-Type": "application/sparql-query",
    "Accept": "application/sparql-results+json",
}


@dataclass(frozen=True)
class FusekiEndpoints:
    """URLs for a Fuseki dataset used by integration tests."""

    base: str
    dataset: str
    read_endpoint: str
    write_endpoint: str
    graph_store_url: str


def _fuseki_base_url() -> str:
    base = os.environ.get(FUSEKI_BASE_ENV, "http://127.0.0.1:3030").rstrip("/")
    return base


def _fuseki_admin_auth() -> httpx.BasicAuth | None:
    password = os.environ.get(FUSEKI_ADMIN_PASSWORD_ENV)
    if not password:
        return None
    user = os.environ.get(FUSEKI_ADMIN_USER_ENV, "admin")
    return httpx.BasicAuth(user, password)


def fuseki_basic_auth_tuple() -> tuple[str, str]:
    """Basic auth tuple for :class:`~sparqlmodel.stores.http.HttpStore` constructors."""
    password = os.environ.get(FUSEKI_ADMIN_PASSWORD_ENV, "testadmin")
    user = os.environ.get(FUSEKI_ADMIN_USER_ENV, "admin")
    return (user, password)


def _wait_for_fuseki(base: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    ping = f"{base}/$/ping"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(ping, timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.5)
    msg = (
        f"Fuseki not reachable at {ping} (set {FUSEKI_BASE_ENV} or start Docker Fuseki). "
        f"Last error: {last_error}"
    )
    raise RuntimeError(msg)


def _dataset_sparql_url(base: str, name: str) -> str:
    return f"{base}/{name}/sparql"


def _dataset_update_url(base: str, name: str) -> str:
    """Fuseki SPARQL Update endpoint (distinct from query ``/sparql``)."""
    return f"{base}/{name}/update"


def _dataset_is_ready(base: str, name: str) -> bool:
    """Return True when the dataset SPARQL endpoint accepts queries (no admin API)."""
    sparql = _dataset_sparql_url(base, name)
    auth = _fuseki_admin_auth()
    try:
        response = httpx.post(
            sparql,
            content=b"SELECT * WHERE { ?s ?p ?o } LIMIT 1",
            headers=SPARQL_QUERY_HEADERS,
            auth=auth,
            timeout=10.0,
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _create_dataset_via_admin(base: str, name: str) -> None:
    """Create dataset through Fuseki admin API (optional Basic auth)."""
    auth = _fuseki_admin_auth()
    list_url = f"{base}/$/datasets"
    try:
        response = httpx.get(list_url, auth=auth, timeout=5.0)
        if response.status_code == 200 and name in response.text:
            return
        if response.status_code == 401 and _dataset_is_ready(base, name):
            return
    except httpx.HTTPError:
        pass
    create = httpx.post(
        f"{base}/$/datasets",
        data={"dbType": "mem", "dbName": name},
        auth=auth,
        timeout=10.0,
    )
    if create.status_code in (200, 201, 409):
        return
    if create.status_code == 401 and _dataset_is_ready(base, name):
        return
    create.raise_for_status()


def _ensure_dataset(base: str, name: str) -> None:
    """Ensure dataset exists — probe SPARQL first; admin API only when needed."""
    if _dataset_is_ready(base, name):
        return
    _create_dataset_via_admin(base, name)
    if not _dataset_is_ready(base, name):
        raise RuntimeError(
            f"Fuseki dataset {name!r} is not available at {_dataset_sparql_url(base, name)}. "
            f"Start Fuseki with FUSEKI_DATASET_1={name} or set {FUSEKI_ADMIN_PASSWORD_ENV} "
            "for admin dataset creation."
        )


def clear_fuseki_dataset(endpoints: FusekiEndpoints) -> None:
    """Remove all triples from the dataset default graph (SPARQL UPDATE CLEAR ALL)."""
    auth = _fuseki_admin_auth()
    response = httpx.post(
        endpoints.write_endpoint,
        content=b"CLEAR ALL",
        headers={
            "Content-Type": "application/sparql-update",
            "Accept": "*/*",
        },
        auth=auth,
        timeout=30.0,
    )
    if response.status_code in (200, 204):
        return
    response.raise_for_status()


@pytest.fixture(scope="session")
def fuseki_endpoints() -> FusekiEndpoints:
    """Session-scoped Fuseki URL bundle; waits for server and ensures dataset exists."""
    base = _fuseki_base_url()
    _wait_for_fuseki(base)
    _ensure_dataset(base, FUSEKI_DATASET)
    sparql = _dataset_sparql_url(base, FUSEKI_DATASET)
    update = _dataset_update_url(base, FUSEKI_DATASET)
    data = f"{base}/{FUSEKI_DATASET}/data"
    return FusekiEndpoints(
        base=base,
        dataset=FUSEKI_DATASET,
        read_endpoint=sparql,
        write_endpoint=update,
        graph_store_url=data,
    )


@pytest.fixture
def fuseki_clean(fuseki_endpoints: FusekiEndpoints) -> Generator[FusekiEndpoints, None, None]:
    """Clear the Fuseki dataset before and after each integration test."""
    clear_fuseki_dataset(fuseki_endpoints)
    yield fuseki_endpoints
    clear_fuseki_dataset(fuseki_endpoints)
