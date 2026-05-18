"""Contract tests: SPARQLModel put graphs vs TripleModel adapter."""

from __future__ import annotations

import pytest

from sparqlmodel import IRI, Field, Relationship, SPARQLModel, SPARQLSession
from sparqlmodel import _triple as triple_mod
from sparqlmodel._triple import (
    adapter_graph,
    assert_put_graph_contract,
    from_triplemodel,
    graphs_isomorphic,
    to_triplemodel,
    triple_model_class_for,
)
from sparqlmodel.graph import model_to_graph
from tests.models import Location, Organization, Person


@pytest.fixture(autouse=True)
def _clear_triple_class_cache() -> None:
    triple_mod._TRIPLE_CLASS_CACHE.clear()
    yield
    triple_mod._TRIPLE_CLASS_CACHE.clear()


def test_triple_model_class_for_person() -> None:
    cls = triple_model_class_for(Person)
    assert issubclass(cls, triple_model_class_for(Person))


def test_to_triplemodel_roundtrip_scalars() -> None:
    person = Person(id=IRI("urn:p:1"), name="Odos", works_for=None)
    tm = to_triplemodel(person)
    assert tm.subject_uri() == "urn:p:1"
    assert tm.name == "Odos"


def test_put_graph_isomorphic_person_org() -> None:
    loc = Location(id=IRI("urn:loc:1"), name="Boston")
    org = Organization(id=IRI("urn:org:1"), name="Acme", located_in=loc)
    person = Person(id=IRI("urn:p:1"), name="Pat", works_for=org)
    assert_put_graph_contract(person)


def test_adapter_graph_matches_model_to_graph() -> None:
    loc = Location(id=IRI("urn:loc:2"), name="NYC")
    org = Organization(id=IRI("urn:org:2"), name="Corp", located_in=loc)
    person = Person(id=IRI("urn:p:2"), name="Sam", works_for=org)
    assert graphs_isomorphic(model_to_graph(person), adapter_graph(person))


def test_from_triplemodel_shallow() -> None:
    person = Person(id=IRI("urn:p:3"), name="Lee", works_for=None)
    tm = to_triplemodel(person)
    g = adapter_graph(person)
    restored = from_triplemodel(tm, g, sparql_cls=Person, depth=0)
    assert restored.name == "Lee"
    assert str(restored.id) == "urn:p:3"


def test_session_put_matches_contract() -> None:
    loc = Location(id=IRI("urn:loc:3"), name="LA")
    org = Organization(id=IRI("urn:org:3"), name="Shop", located_in=loc)
    person = Person(id=IRI("urn:p:4"), name="Kim", works_for=org)
    session = SPARQLSession()
    session.put(person)
    interim = session.store.graph
    via = adapter_graph(person)
    assert graphs_isomorphic(interim, via)


class LinkedOrg(SPARQLModel):
    rdf_type = "schema:Organization"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")


class PersonNoCascade(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
    works_for: Organization | None = Relationship(
        "schema:worksFor",
        model=Organization,
        cascade=False,
    )


def test_put_graph_contract_typed_literals() -> None:
    class FlagModel(SPARQLModel):
        rdf_type = "schema:Thing"
        __prefixes__ = {"schema": "https://schema.org/"}

        id: IRI
        active: bool = Field("schema:value")

    class NumModel(SPARQLModel):
        rdf_type = "schema:Thing"
        __prefixes__ = {"schema": "https://schema.org/"}

        id: IRI
        count: int = Field("schema:value")
        score: float = Field("schema:value")

    assert_put_graph_contract(FlagModel(id=IRI("urn:flag"), active=True))
    assert_put_graph_contract(NumModel(id=IRI("urn:n"), count=3, score=1.5))


def test_relationship_cascade_false_skips_nested_put() -> None:
    org = Organization(id=IRI("urn:org:nc"), name="Detached", located_in=None)
    person = PersonNoCascade(id=IRI("urn:p:nc"), name="Solo", works_for=org)
    session = SPARQLSession()
    session.put(person)
    g = session.store.graph
    from rdflib import URIRef

    org_ref = URIRef("urn:org:nc")
    assert not any(g.triples((org_ref, None, None)))
