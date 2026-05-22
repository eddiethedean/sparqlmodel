"""HttpStore integration tests against a live Fuseki instance."""

from __future__ import annotations

import httpx
import pytest

from sparqlmodel import IRI, SPARQLSession
from sparqlmodel.async_session import AsyncSPARQLSession
from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.stores.async_http import AsyncHttpStore
from sparqlmodel.stores.http import HttpStore
from sparqlmodel.stores.http_common import SPARQL_UPDATE_HEADERS
from tests.conftest_fuseki import (
    FusekiEndpoints,
    _fuseki_admin_auth,
    clear_fuseki_dataset,
    fuseki_basic_auth_tuple,
)
from tests.models import Person

pytestmark = pytest.mark.integration

PREFIXES = {"schema": "https://schema.org/"}
PERSON_IRI = "http://example.org/integration/person/1"


def _http_store(endpoints: FusekiEndpoints) -> HttpStore:
    return HttpStore(
        endpoints.read_endpoint,
        read_endpoint=endpoints.read_endpoint,
        write_endpoint=endpoints.write_endpoint,
        graph_store_url=endpoints.graph_store_url,
        prefixes=PREFIXES,
        auth=fuseki_basic_auth_tuple(),
    )


def _async_http_store(endpoints: FusekiEndpoints) -> AsyncHttpStore:
    return AsyncHttpStore(
        endpoints.read_endpoint,
        read_endpoint=endpoints.read_endpoint,
        write_endpoint=endpoints.write_endpoint,
        graph_store_url=endpoints.graph_store_url,
        prefixes=PREFIXES,
        auth=fuseki_basic_auth_tuple(),
    )


def _external_update(endpoints: FusekiEndpoints, name: str) -> None:
    """Simulate another writer updating the remote dataset only."""
    update = f"""
PREFIX schema: <https://schema.org/>
INSERT DATA {{
  <{PERSON_IRI}> a schema:Person ;
    schema:name "{name}" .
}}
""".strip()
    response = httpx.post(
        endpoints.write_endpoint,
        content=update.encode("utf-8"),
        headers=SPARQL_UPDATE_HEADERS,
        auth=_fuseki_admin_auth(),
        timeout=30.0,
    )
    response.raise_for_status()


def _select_name(endpoints: FusekiEndpoints) -> str | None:
    sparql = f"""
PREFIX schema: <https://schema.org/>
SELECT ?name WHERE {{
  <{PERSON_IRI}> schema:name ?name .
}}
""".strip()
    response = httpx.post(
        endpoints.read_endpoint,
        content=sparql.encode("utf-8"),
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "application/sparql-results+json",
        },
        auth=_fuseki_admin_auth(),
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return None
    return bindings[0]["name"]["value"]


def test_fuseki_put_query_and_get_mirror(fuseki_clean: FusekiEndpoints) -> None:
    person = Person(id=IRI(PERSON_IRI), name="SessionWriter")
    with SPARQLSession(store=_http_store(fuseki_clean)) as session:
        session.put(person)
        assert _select_name(fuseki_clean) == "SessionWriter"
        loaded = session.get(Person, IRI(PERSON_IRI))
        assert loaded is not None
        assert loaded.name == "SessionWriter"


def test_fuseki_external_writer_sync_mirror(fuseki_clean: FusekiEndpoints) -> None:
    person = Person(id=IRI(PERSON_IRI), name="BeforeExternal")
    store = _http_store(fuseki_clean)
    try:
        with SPARQLSession(store=store, close_on_exit=False) as session:
            session.put(person)
        _external_update(fuseki_clean, "AfterExternal")
        assert _select_name(fuseki_clean) == "AfterExternal"

        with SPARQLSession(store=store, close_on_exit=False) as session:
            stale = session.get(Person, IRI(PERSON_IRI))
            assert stale is not None
            assert stale.name == "BeforeExternal"

            store.sync_mirror()
            session.expunge_all()
            fresh = session.get(Person, IRI(PERSON_IRI))
            assert fresh is not None
            assert fresh.name == "AfterExternal"
    finally:
        store.close()


def test_fuseki_sync_mirror_without_graph_store_url_raises() -> None:
    store = HttpStore("http://localhost:3030/ds/sparql", prefixes=PREFIXES)
    try:
        with pytest.raises(ConfigurationError, match="graph_store_url"):
            store.sync_mirror()
    finally:
        store.close()


def test_fuseki_sync_mirror_empty_remote_clears_mirror(fuseki_clean: FusekiEndpoints) -> None:
    clear_fuseki_dataset(fuseki_clean)
    person = Person(id=IRI(PERSON_IRI), name="Ghost")
    store = _http_store(fuseki_clean)
    try:
        with SPARQLSession(store=store, close_on_exit=False) as session:
            session.put(person)
        assert len(store.graph) > 0
        clear_fuseki_dataset(fuseki_clean)
        store.sync_mirror()
        assert len(store.graph) == 0
    finally:
        store.close()


@pytest.mark.asyncio
async def test_fuseki_async_external_writer_sync_mirror(fuseki_clean: FusekiEndpoints) -> None:
    person = Person(id=IRI(PERSON_IRI), name="AsyncBefore")
    store = _async_http_store(fuseki_clean)
    try:
        async with AsyncSPARQLSession(store=store, close_on_exit=False) as session:
            await session.put(person)
        _external_update(fuseki_clean, "AsyncAfter")
        async with AsyncSPARQLSession(store=store, close_on_exit=False) as session:
            stale = await session.get(Person, IRI(PERSON_IRI))
            assert stale is not None
            assert stale.name == "AsyncBefore"
            await store.sync_mirror()
            await session.expunge_all()
            fresh = await session.get(Person, IRI(PERSON_IRI))
            assert fresh is not None
            assert fresh.name == "AsyncAfter"
    finally:
        await store.aclose()


def test_fuseki_read_write_endpoints_same_dataset(fuseki_clean: FusekiEndpoints) -> None:
    """Read/write split URLs (Fuseki ``/sparql`` vs ``/update``) share one dataset."""
    assert fuseki_clean.read_endpoint.endswith("/sparql")
    assert fuseki_clean.write_endpoint.endswith("/update")
    _external_update(fuseki_clean, "ViaWriteUrl")
    store = _http_store(fuseki_clean)
    try:
        bindings = store.query(
            f"PREFIX schema: <https://schema.org/> "
            f"SELECT ?n WHERE {{ <{PERSON_IRI}> schema:name ?n }}"
        )
        assert bindings[0]["n"] == "ViaWriteUrl"
        store.sync_mirror()
        with SPARQLSession(store=store, close_on_exit=False) as session:
            loaded = session.get(Person, IRI(PERSON_IRI))
            assert loaded is not None
            assert loaded.name == "ViaWriteUrl"
    finally:
        store.close()
