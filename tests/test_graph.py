"""Tests for graph mapping."""

from sparqlmodel import IRI, Field, SPARQLModel
from sparqlmodel.graph import owned_triples_for_subject
from sparqlmodel.rdf_bridge import model_to_graph
from tests.models import Organization, Person


def test_model_to_graph(odos: Person) -> None:
    g = model_to_graph(odos)
    assert len(g) >= 4


def test_round_trip_scalars(session, odos: Person) -> None:
    session.put(odos)
    loaded = session.get(Person, odos.id, depth=0)
    assert loaded is not None
    assert loaded.name == "Odos"


def test_owned_triples(session, odos: Person) -> None:
    session.put(odos)
    owned = owned_triples_for_subject(Person, odos.id, session.graph)
    assert len(owned) >= 2


def test_org_round_trip(acme: Organization) -> None:
    g = model_to_graph(acme)
    assert len(g) >= 2


def test_model_with_bool() -> None:
    class FlagModel(SPARQLModel):
        rdf_type = "urn:test:GraphFlagThing"
        active: bool = Field("schema:value")

    m = FlagModel(id=IRI("urn:flag"), active=True)
    g = model_to_graph(m)
    assert len(g) >= 2


def test_model_with_int_float() -> None:
    class NumModel(SPARQLModel):
        rdf_type = "urn:test:GraphNumThing"
        count: int = Field("schema:integerValue")
        score: float = Field("schema:value")

    m = NumModel(id=IRI("urn:n"), count=3, score=1.5)
    g = model_to_graph(m)
    assert len(g) >= 3
