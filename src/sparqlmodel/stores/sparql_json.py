"""Parse SPARQL 1.1 Query Results JSON without rdflib."""

from __future__ import annotations

import json
from typing import Any, cast


def parse_sparql_json_bindings(payload: bytes) -> list[dict[str, Any]]:
    """Return SELECT variable bindings from a SPARQL Results JSON document."""
    data = json.loads(payload)
    if not isinstance(data, dict) or "head" not in data or "results" not in data:
        raise ValueError("Invalid SPARQL JSON: missing head or results")
    head = data.get("head", {})
    if not isinstance(head, dict):
        raise ValueError("Invalid SPARQL JSON: head must be an object")
    vars_ = head.get("vars", [])
    if not isinstance(vars_, list):
        raise ValueError("Invalid SPARQL JSON: head.vars must be a list")
    results = data.get("results", {})
    bindings_raw = results.get("bindings", [])
    if not isinstance(bindings_raw, list):
        raise ValueError("Invalid SPARQL JSON: results.bindings must be a list")

    out: list[dict[str, Any]] = []
    for row in bindings_raw:
        if not isinstance(row, dict):
            continue
        binding: dict[str, Any] = {}
        for var in vars_:
            cell = row.get(var)
            if cell is None:
                continue
            binding[str(var)] = _binding_value(cell)
        out.append(binding)
    return out


def _binding_value(cell: object) -> Any:
    if not isinstance(cell, dict):
        return cell
    binding_cell = cast(dict[str, Any], cell)
    value = binding_cell.get("value")
    if value is None:
        return None
    type_ = binding_cell.get("type", "literal")
    if type_ == "uri":
        return str(value)
    if type_ == "bnode":
        return f"_:{value}"
    return str(value)
