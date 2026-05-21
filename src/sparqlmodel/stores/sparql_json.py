"""Parse SPARQL 1.1 Query Results JSON via pyoxigraph."""

from __future__ import annotations

from typing import Any

from pyoxigraph import (
    BlankNode,
    Literal,
    NamedNode,
    QueryBoolean,
    QueryResultsFormat,
    QuerySolutions,
    parse_query_results,
)

from sparqlmodel.exceptions import QueryError


def parse_sparql_json_bindings(payload: bytes) -> list[dict[str, Any]]:
    """Return SELECT variable bindings from a SPARQL Results JSON document."""
    try:
        parsed = parse_query_results(payload, QueryResultsFormat.JSON)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(f"Invalid SPARQL JSON: {exc}") from exc

    if isinstance(parsed, QueryBoolean):
        raise QueryError(f"Expected SELECT query, got ASK (boolean={parsed})")

    if not isinstance(parsed, QuerySolutions):
        raise QueryError(f"Unexpected SPARQL result type: {type(parsed).__name__}")

    bindings: list[dict[str, Any]] = []
    variables = parsed.variables
    for row in parsed:
        binding: dict[str, Any] = {}
        for var in variables:
            name = str(var).lstrip("?")
            binding[name] = _term_value(row[var])
        bindings.append(binding)
    return bindings


def _term_value(term: object) -> Any:
    if term is None:
        return None
    if isinstance(term, NamedNode):
        return term.value
    if isinstance(term, BlankNode):
        raw = str(term)
        return raw if raw.startswith("_:") else f"_:{raw}"
    if isinstance(term, Literal):
        return term.value
    return str(term)
