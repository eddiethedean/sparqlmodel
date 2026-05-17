"""Tests for namespace / SPARQL prefix validation."""

import pytest

from sparqlmodel.exceptions import QueryError
from sparqlmodel.types import NamespaceRegistry


def test_sparql_prefixes_rejects_invalid_namespace_uri() -> None:
    registry = NamespaceRegistry({"bad": "http://example.org/ns>\n"})
    with pytest.raises(QueryError, match="namespace"):
        registry.sparql_prefixes()


def test_sparql_prefixes_rejects_invalid_prefix_name() -> None:
    registry = NamespaceRegistry({"bad prefix": "http://example.org/ns"})
    with pytest.raises(QueryError, match="prefix"):
        registry.sparql_prefixes()
