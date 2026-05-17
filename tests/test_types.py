"""Tests for IRI and namespace utilities."""

import pytest

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.types import IRI, NamespaceRegistry, compact_iri, expand_iri


def test_iri_empty() -> None:
    from pydantic import TypeAdapter
    from pydantic_core import ValidationError

    with pytest.raises(ValidationError):
        TypeAdapter(IRI).validate_python("")


def test_expand_compact() -> None:
    assert expand_iri("schema:Person", {"schema": "https://schema.org/"}) == (
        "https://schema.org/Person"
    )


def test_expand_unknown_prefix() -> None:
    with pytest.raises(ConfigurationError):
        expand_iri("unknown:Thing", {})


def test_compact_iri() -> None:
    result = compact_iri("https://schema.org/Person", {"schema": "https://schema.org/"})
    assert result == "schema:Person"


def test_namespace_registry() -> None:
    reg = NamespaceRegistry({"ex": "http://example.org/"})
    assert "ex" in reg.prefixes
    sparql = reg.sparql_prefixes()
    assert "PREFIX ex:" in sparql


def test_iri_expand_method() -> None:
    iri = IRI("schema:Person")
    assert "schema.org" in iri.expand()
