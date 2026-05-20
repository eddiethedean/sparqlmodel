"""Shared SPARQL string escaping for queries and UPDATE bodies."""

from __future__ import annotations


def escape_sparql_string(value: str) -> str:
    """Escape a string for use inside SPARQL double-quoted literals."""
    parts: list[str] = []
    for ch in value:
        if ch == "\\":
            parts.append("\\\\")
        elif ch == '"':
            parts.append('\\"')
        elif ch == "\n":
            parts.append("\\n")
        elif ch == "\r":
            parts.append("\\r")
        elif ch == "\t":
            parts.append("\\t")
        elif ord(ch) < 0x20:
            parts.append(f"\\u{ord(ch):04X}")
        else:
            parts.append(ch)
    return "".join(parts)
