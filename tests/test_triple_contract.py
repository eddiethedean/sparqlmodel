"""Contract tests: SPARQLModel put graphs vs direct/rdf_bridge export."""

from __future__ import annotations

from rdflib import URIRef

from sparqlmodel import IRI, Field, Relationship, SPARQLModel, SPARQLSession
from sparqlmodel.rdf_bridge import (
    adapter_graph,
    assert_put_graph_contract,
    graphs_isomorphic,
    load_from_graph,
    model_to_graph,
)
from tests.models import Location, Organization, Person


def test_put_graph_isomorphic_person_org() -> None:
    loc = Location(id=IRI("urn:loc:1"), name="Boston")
    org = Organization(id=IRI("urn:org:1"), name="Acme", located_in=loc)
    person = Person(id=IRI("urn:p:1"), name="Pat", works_for=org)
    assert_put_graph_contract(person)


def test_model_to_graph_matches_adapter_graph() -> None:
    loc = Location(id=IRI("urn:loc:2"), name="NYC")
    org = Organization(id=IRI("urn:org:2"), name="Corp", located_in=loc)
    person = Person(id=IRI("urn:p:2"), name="Sam", works_for=org)
    assert graphs_isomorphic(model_to_graph(person), adapter_graph(person))


def test_load_from_graph_round_trip() -> None:
    loc = Location(id=IRI("urn:loc:rt"), name="Boston")
    org = Organization(id=IRI("urn:org:rt"), name="Acme", located_in=loc)
    person = Person(id=IRI("urn:p:rt"), name="Pat", works_for=org)
    g = model_to_graph(person)
    loaded = load_from_graph(Person, person.id, g, depth=2)
    assert loaded.name == "Pat"
    assert loaded.works_for is not None
    assert loaded.works_for.name == "Acme"


def test_load_from_graph_shallow() -> None:
    person = Person(id=IRI("urn:p:3"), name="Lee", works_for=None)
    g = adapter_graph(person)
    loaded = load_from_graph(Person, person.id, g, depth=0)
    assert loaded.name == "Lee"
    assert str(loaded.id) == "urn:p:3"


def test_session_put_matches_contract() -> None:
    loc = Location(id=IRI("urn:loc:3"), name="LA")
    org = Organization(id=IRI("urn:org:3"), name="Shop", located_in=loc)
    person = Person(id=IRI("urn:p:4"), name="Kim", works_for=org)
    session = SPARQLSession()
    session.put(person)
    interim = session.store.graph
    via = adapter_graph(person)
    assert graphs_isomorphic(interim, via)


class PersonNoCascadeInferred(SPARQLModel):
    rdf_type = "ex:PersonNoCascadeInferred"
    __prefixes__ = {"schema": "https://schema.org/", "ex": "http://example.org/ns/"}

    id: IRI
    name: str = Field("schema:name")
    works_for: Organization | None = Relationship("schema:worksFor", cascade=False)


class PersonNoCascade(SPARQLModel):
    rdf_type = "ex:PersonNoCascade"
    __prefixes__ = {"schema": "https://schema.org/", "ex": "http://example.org/ns/"}

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
        count: int = Field("schema:integerValue")
        score: float = Field("schema:value")

    assert_put_graph_contract(FlagModel(id=IRI("urn:flag"), active=True))
    assert_put_graph_contract(NumModel(id=IRI("urn:n"), count=3, score=1.5))


def test_relationship_cascade_false_inferred_skips_nested_put() -> None:
    org = Organization(id=IRI("urn:org:inf"), name="Detached", located_in=None)
    person = PersonNoCascadeInferred(id=IRI("urn:p:inf"), name="Solo", works_for=org)
    session = SPARQLSession()
    session.put(person)
    org_ref = URIRef("urn:org:inf")
    assert not any(session.store.graph.triples((org_ref, None, None)))


def test_relationship_cascade_false_skips_nested_put() -> None:
    org = Organization(id=IRI("urn:org:nc"), name="Detached", located_in=None)
    person = PersonNoCascade(id=IRI("urn:p:nc"), name="Solo", works_for=org)
    session = SPARQLSession()
    session.put(person)
    g = session.store.graph
    org_ref = URIRef("urn:org:nc")
    assert not any(g.triples((org_ref, None, None)))
