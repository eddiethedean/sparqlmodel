"""Tests for graph mapping."""

from sparqlmodel import IRI, Field, SPARQLModel
from sparqlmodel.graph import model_to_graph, model_to_triples, owned_triples_for_subject
from tests.models import Organization, Person


def test_model_to_triples(odos: Person) -> None:
    triples = model_to_triples(odos)
    assert len(triples) >= 4


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
        rdf_type = "schema:Thing"
        active: bool = Field("schema:value")

    m = FlagModel(id=IRI("urn:flag"), active=True)
    triples = model_to_triples(m)
    assert len(triples) >= 2


def test_model_with_int_float() -> None:
    class NumModel(SPARQLModel):
        rdf_type = "schema:Thing"
        count: int = Field("schema:value")
        score: float = Field("schema:value")

    m = NumModel(id=IRI("urn:n"), count=3, score=1.5)
    triples = model_to_triples(m)
    assert len(triples) >= 3
