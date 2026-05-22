"""Shared SPARQL HTTP helpers for sync and async endpoint stores."""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping
from typing import Literal, cast
from urllib.parse import urljoin

from triplemodel import Store

from sparqlmodel.graph import _subject_pattern
from sparqlmodel.rdf_n3 import triple_to_n3
from sparqlmodel.types import IRI

MirrorMode = Literal["writer", "remote_authoritative"]

_VALID_MIRROR_MODES = frozenset({"writer", "remote_authoritative"})


def validate_mirror_mode(mirror_mode: str) -> MirrorMode:
    if mirror_mode not in _VALID_MIRROR_MODES:
        raise ValueError(
            f"mirror_mode must be 'writer' or 'remote_authoritative', got {mirror_mode!r}"
        )
    return cast(MirrorMode, mirror_mode)


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
    if endpoint.endswith("/sparql") or endpoint.endswith("/query"):
        return endpoint
    return urljoin(endpoint + "/", "sparql")


def is_select_query(sparql: str) -> bool:
    """Return True when ``sparql`` appears to be a SPARQL SELECT (not ASK/CONSTRUCT/DESCRIBE)."""
    text = sparql
    while True:
        stripped = text.lstrip()
        if not stripped:
            return False
        upper = stripped.upper()
        if upper.startswith("PREFIX "):
            newline = stripped.find("\n")
            if newline == -1:
                return False
            text = stripped[newline + 1 :]
            continue
        head = stripped.split(None, 1)[0].upper()
        return head == "SELECT"


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
