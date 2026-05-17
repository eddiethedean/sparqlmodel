"""Additional compiler coverage."""

from sparqlmodel.compiler import compile_where
from sparqlmodel.types import NamespaceRegistry
from tests.models import Person


def test_compile_not_equal() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    sparql = compile_where(Person, (Person.name != "Other",), registry)
    assert "FILTER" in sparql
