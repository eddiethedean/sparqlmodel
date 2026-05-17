"""Tests for hydration."""

from sparqlmodel import IRI
from tests.models import Organization, Person


def test_hydration_depth_0(session, odos: Person) -> None:
    session.put(odos)
    loaded = session.get(Person, odos.id, depth=0)
    assert loaded is not None
    assert loaded.name == "Odos"
    assert loaded.works_for is None


def test_hydration_depth_1(session, odos: Person) -> None:
    session.put(odos)
    loaded = session.get(Person, odos.id, depth=1)
    assert loaded is not None
    assert loaded.works_for is not None
    assert isinstance(loaded.works_for, Organization)
    assert loaded.works_for.name == "Acme Corp"


def test_hydration_depth_2(session, odos: Person) -> None:
    session.put(odos)
    loaded = session.get(Person, odos.id, depth=2)
    assert loaded is not None
    assert loaded.works_for is not None
    assert loaded.works_for.name == "Acme Corp"


def test_missing_related(session, odos: Person) -> None:
    session.put(odos)
    orphan = Person(id=IRI("urn:person:orphan"), name="Orphan", works_for=None)
    session.put(orphan)
    loaded = session.get(Person, orphan.id, depth=1)
    assert loaded is not None
    assert loaded.works_for is None
