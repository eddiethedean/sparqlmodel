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


def _ensure_dataset(base: str, name: str) -> None:
    """Create an in-memory dataset if the server does not already have it."""
    list_url = f"{base}/$/datasets"
    try:
        response = httpx.get(list_url, timeout=5.0)
        if response.status_code == 200 and name in response.text:
            return
    except httpx.HTTPError:
        pass
    create = httpx.post(
        f"{base}/$/datasets",
        data={"dbType": "mem", "dbName": name},
        timeout=10.0,
    )
    if create.status_code not in (200, 201, 409):
        create.raise_for_status()


def clear_fuseki_dataset(endpoints: FusekiEndpoints) -> None:
    """Remove all triples from the dataset default graph (Graph Store HTTP DELETE)."""
    try:
        response = httpx.delete(endpoints.graph_store_url, timeout=30.0)
        if response.status_code in (200, 204, 404):
            return
        response.raise_for_status()
    except httpx.HTTPError:
        update = "CLEAR ALL"
        response = httpx.post(
            endpoints.write_endpoint,
            content=update.encode("utf-8"),
            headers={
                "Content-Type": "application/sparql-update",
                "Accept": "*/*",
            },
            timeout=30.0,
        )
        response.raise_for_status()


@pytest.fixture(scope="session")
def fuseki_endpoints() -> FusekiEndpoints:
    """Session-scoped Fuseki URL bundle; waits for server and ensures dataset exists."""
    base = _fuseki_base_url()
    _wait_for_fuseki(base)
    _ensure_dataset(base, FUSEKI_DATASET)
    sparql = f"{base}/{FUSEKI_DATASET}/sparql"
    data = f"{base}/{FUSEKI_DATASET}/data"
    return FusekiEndpoints(
        base=base,
        dataset=FUSEKI_DATASET,
        read_endpoint=sparql,
        write_endpoint=sparql,
        graph_store_url=data,
    )


@pytest.fixture
def fuseki_clean(fuseki_endpoints: FusekiEndpoints) -> Generator[FusekiEndpoints, None, None]:
    """Clear the Fuseki dataset before and after each integration test."""
    clear_fuseki_dataset(fuseki_endpoints)
    yield fuseki_endpoints
    clear_fuseki_dataset(fuseki_endpoints)
