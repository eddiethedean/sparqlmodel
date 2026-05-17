"""Tests for serializers."""

import pytest

from sparqlmodel.serializers import export_model, import_graph, model_from_jsonld, model_to_jsonld
from tests.models import Person


def test_export_turtle(odos: Person) -> None:
    ttl = export_model(odos, format="turtle")
    assert "Odos" in ttl


def test_import_graph() -> None:
    ttl = (
        '@prefix schema: <https://schema.org/> .\n<urn:x> a schema:Organization ; schema:name "X" .'
    )
    g = import_graph(ttl, format="turtle")
    assert len(g) >= 2


def test_jsonld_round_trip(odos: Person) -> None:
    doc = model_to_jsonld(odos)
    assert "@id" in doc
    assert doc.get("@type") or "schema.org" in str(doc)


def test_jsonld_validate(odos: Person) -> None:
    doc = model_to_jsonld(odos)
    person = model_from_jsonld(Person, doc)
    assert person.name == "Odos"


def test_model_dump_jsonld(odos: Person) -> None:
    doc = odos.model_dump_jsonld()
    assert "@id" in doc


def test_export_nt(odos: Person) -> None:
    from sparqlmodel.serializers import export_model

    data = export_model(odos, format="nt")
    assert "Odos" in data


def test_unsupported_format(odos: Person) -> None:
    from sparqlmodel.serializers import export_model

    with pytest.raises(ValueError):
        export_model(odos, format="unsupported")


def test_model_validate_jsonld(odos: Person) -> None:
    restored = Person.model_validate_jsonld(odos.model_dump_jsonld())
    assert restored.name == "Odos"


def test_model_from_jsonld_compact_keys() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": "https://schema.org/Person",
        "schema:name": "X",
    }
    person = model_from_jsonld(Person, doc)
    assert person.name == "X"


def test_model_from_jsonld_missing_id() -> None:
    with pytest.raises(ValueError):
        model_from_jsonld(Person, {"schema:name": "X"})
