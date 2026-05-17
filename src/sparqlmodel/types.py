"""IRI and namespace utilities."""

from __future__ import annotations

import re
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

from sparqlmodel.exceptions import ConfigurationError

DEFAULT_PREFIXES: dict[str, str] = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "schema": "https://schema.org/",
}

_COMPACT_IRI_RE = re.compile(r"^([a-zA-Z_][\w-]*):([^:]+)$")


def is_compact_iri(value: str) -> bool:
    """Return True if value is a prefix:local compact IRI (not a plain literal with a colon)."""
    if value.startswith(("http://", "https://", "urn:")):
        return False
    return _COMPACT_IRI_RE.match(value) is not None


class IRI(str):
    """RDF IRI identifier (compact or absolute)."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(),
        )

    @classmethod
    def _validate(cls, value: str) -> IRI:
        if not value or not value.strip():
            raise ValueError("IRI cannot be empty")
        return cls(value.strip())

    def expand(self, prefixes: dict[str, str] | None = None) -> str:
        """Expand a compact IRI (e.g. schema:Person) to an absolute IRI."""
        return expand_iri(str(self), prefixes)

    def compact(self, prefixes: dict[str, str] | None = None) -> str:
        """Return the most compact form using known prefixes."""
        return compact_iri(str(self), prefixes)


def expand_iri(iri: str, prefixes: dict[str, str] | None = None) -> str:
    """Expand compact IRIs using prefix map."""
    if iri.startswith(("http://", "https://", "urn:")):
        return iri
    match = _COMPACT_IRI_RE.match(iri)
    if not match:
        return iri
    prefix, local = match.group(1), match.group(2)
    merged = {**DEFAULT_PREFIXES, **(prefixes or {})}
    if prefix not in merged:
        raise ConfigurationError(f"Unknown prefix '{prefix}' for IRI '{iri}'")
    return merged[prefix] + local


def compact_iri(iri: str, prefixes: dict[str, str] | None = None) -> str:
    """Compact an absolute IRI when a known prefix matches."""
    if not iri.startswith(("http://", "https://")):
        return iri
    merged = {**DEFAULT_PREFIXES, **(prefixes or {})}
    best_prefix = ""
    best_ns = ""
    for prefix, ns in sorted(merged.items(), key=lambda x: len(x[1]), reverse=True):
        if iri.startswith(ns) and len(ns) > len(best_ns):
            best_prefix = prefix
            best_ns = ns
    if best_ns:
        return f"{best_prefix}:{iri[len(best_ns) :]}"
    return iri


class NamespaceRegistry:
    """Registry of namespace prefixes for a session or model."""

    def __init__(self, prefixes: dict[str, str] | None = None) -> None:
        self._prefixes = {**DEFAULT_PREFIXES, **(prefixes or {})}

    @property
    def prefixes(self) -> dict[str, str]:
        return dict(self._prefixes)

    def bind(self, graph: Any) -> None:
        """Bind prefixes to an rdflib Graph."""
        for prefix, uri in self._prefixes.items():
            graph.bind(prefix, uri)

    def expand(self, iri: str) -> str:
        return expand_iri(iri, self._prefixes)

    def compact(self, iri: str) -> str:
        return compact_iri(iri, self._prefixes)

    def sparql_prefixes(self) -> str:
        """Return PREFIX declarations for SPARQL queries."""
        lines = [f"PREFIX {p}: <{uri}>" for p, uri in sorted(self._prefixes.items())]
        return "\n".join(lines)
