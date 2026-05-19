"""Tests for serializers."""

import pytest

from sparqlmodel import IRI, Field, SPARQLModel
from sparqlmodel.serializers import export_model, import_graph, model_from_jsonld, model_to_jsonld
from tests.cycle_models import CycleA, CycleB
from tests.models import Organization, Person


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


def test_export_xml(odos: Person) -> None:
    data = export_model(odos, format="xml")
    assert "Odos" in data


def test_model_from_jsonld_empty_type_list() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": [],
        "schema:name": "X",
    }
    with pytest.raises(ValueError, match="@type"):
        model_from_jsonld(Person, doc)


def test_jsonld_scalar_iri_field() -> None:
    class Tagged(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        id: IRI
        same_as: IRI = Field("schema:sameAs")

    model = Tagged(id=IRI("urn:person:1"), same_as=IRI("urn:person:2"))
    doc = model_to_jsonld(model)
    assert doc["https://schema.org/sameAs"] == {"@id": "urn:person:2"}


def test_jsonld_scalar_iri_field_round_trip_compact_id() -> None:
    class Tagged(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        id: IRI
        same_as: IRI = Field("schema:sameAs")

    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:1",
        "@type": "schema:Person",
        "schema:sameAs": {"@id": "local-ref"},
    }
    restored = model_from_jsonld(Tagged, doc)
    assert restored.same_as == IRI("local-ref")


def test_jsonld_scalar_iri_field_round_trip() -> None:
    class Tagged(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        id: IRI
        same_as: IRI = Field("schema:sameAs")

    model = Tagged(id=IRI("urn:person:1"), same_as=IRI("urn:person:2"))
    restored = model_from_jsonld(Tagged, model_to_jsonld(model))
    assert restored.same_as == IRI("urn:person:2")


def test_jsonld_skips_non_cascade_embed() -> None:
    from sparqlmodel import Relationship

    class Org(SPARQLModel):
        rdf_type = "schema:Organization"
        __prefixes__ = {"schema": "https://schema.org/"}
        id: IRI
        name: str = Field("schema:name")

    class Employee(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        id: IRI
        name: str = Field("schema:name")
        works_for: Org | None = Relationship("schema:worksFor", model=Org, cascade=False)

    org = Org(id=IRI("urn:org:1"), name="Acme")
    emp = Employee(id=IRI("urn:p:1"), name="Pat", works_for=org)
    doc = model_to_jsonld(emp)
    assert "https://schema.org/worksFor" not in doc


def test_model_from_jsonld_empty_relationship_list_skipped() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:empty-rel",
        "@type": "schema:Person",
        "schema:name": "Empty",
        "schema:worksFor": [],
    }
    person = model_from_jsonld(Person, doc)
    assert person.works_for is None


def test_model_from_jsonld_relationship_array() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:arr",
        "@type": "schema:Person",
        "schema:name": "Arr",
        "schema:worksFor": [{"@id": "urn:org:acme"}],
    }
    person = model_from_jsonld(Person, doc)
    assert person.works_for == IRI("urn:org:acme")


def test_model_from_jsonld_wrong_type() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": "https://schema.org/Organization",
        "schema:name": "X",
    }
    with pytest.raises(ValueError, match="@type"):
        model_from_jsonld(Person, doc)


def test_jsonld_iri_reference_round_trip(acme: Organization) -> None:
    person = Person(id=IRI("urn:person:ref"), name="Ref", works_for=acme.id)
    doc = model_to_jsonld(person)
    restored = model_from_jsonld(Person, doc)
    assert restored.works_for == acme.id


def test_jsonld_ensure_id_on_export() -> None:
    person = Person(name="NoId")
    doc = model_to_jsonld(person)
    assert doc["@id"] is not None
    assert doc["@id"] != "None"
    assert person.id is not None


def test_jsonld_cycle_emits_reference() -> None:
    a = CycleA(id=IRI("urn:cycle:a"), name="A")
    b = CycleB(id=IRI("urn:cycle:b"), name="B", a_ref=a)
    a.b = b
    doc = model_to_jsonld(a)
    works = doc.get("https://schema.org/worksFor", doc.get("schema:worksFor"))
    assert isinstance(works, dict)
    assert works.get("@id") == "urn:cycle:b"
    assert "schema:name" not in works or works.get("schema:name") is None


def test_model_from_jsonld_nested_no_parent_leak() -> None:
    doc = {
        "@context": {"schema": "https://schema.org/"},
        "@id": "urn:person:x",
        "@type": "https://schema.org/Person",
        "schema:name": "X",
        "https://schema.org/worksFor": {
            "@id": "urn:org:y",
            "@type": "https://schema.org/Organization",
            "schema:name": "Y",
        },
    }
    person = model_from_jsonld(Person, doc)
    assert person.name == "X"
    assert person.works_for is not None
    assert person.works_for.name == "Y"
