"""Shared SPARQL string escaping for queries and UPDATE bodies."""

from __future__ import annotations


def escape_sparql_string(value: str) -> str:
    """Escape a string for use inside SPARQL double-quoted literals."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
