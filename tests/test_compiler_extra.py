"""Additional compiler tests."""

from sparqlmodel.compiler import compile_where
from sparqlmodel.types import NamespaceRegistry, is_compact_iri
from tests.models import Person


def test_format_object_colon_literal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "12:30",), registry)
    assert '"12:30"' in sparql
    assert "12:30>" not in sparql


def test_format_object_multi_colon_literal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name == "a:b:c",), registry)
    assert '"a:b:c"' in sparql


def test_is_compact_iri() -> None:
    assert is_compact_iri("schema:Person")
    assert not is_compact_iri("12:30")
    assert not is_compact_iri("a:b:c")
    assert not is_compact_iri("http://example.org/x")
