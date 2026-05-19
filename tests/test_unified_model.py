"""Phase 1 spike: SPARQLModel(TripleModel) scalar round-trip via session."""

from __future__ import annotations

from triplemodel import TripleModel

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession


def test_sparqlmodel_subclasses_triplemodel() -> None:
    assert issubclass(SPARQLModel, TripleModel)


class ScalarPerson(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    name: str = Field("schema:name")


def test_scalar_put_get_roundtrip() -> None:
    person = ScalarPerson(id=IRI("urn:person:scalar"), name="Pat")
    session = SPARQLSession()
    session.put(person)
    loaded = session.get(ScalarPerson, person.id)
    assert loaded is not None
    assert loaded.name == "Pat"
    assert str(loaded.id) == "urn:person:scalar"
