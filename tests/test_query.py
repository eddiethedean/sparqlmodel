"""Tests for query builder."""

from sparqlmodel import IRI
from tests.models import Organization, Person


def test_query_all(session, odos: Person) -> None:
    session.put(odos)
    results = session.query(Person).where(Person.name == "Odos").all()
    assert len(results) == 1
    assert results[0].name == "Odos"


def test_query_first(session, odos: Person) -> None:
    session.put(odos)
    result = session.query(Person).where(Person.name == "Odos").first()
    assert result is not None
    assert result.name == "Odos"


def test_query_first_none(session) -> None:
    result = session.query(Person).where(Person.name == "Nobody").first()
    assert result is None


def test_query_limit(session, odos: Person, acme: Organization) -> None:
    other = Person(id=IRI("urn:person:other"), name="Other")
    session.put(odos)
    session.put(other)
    session.put(acme)
    results = session.query(Person).limit(1).all()
    assert len(results) <= 1


def test_nested_query(session, odos: Person) -> None:
    session.put(odos)
    results = session.query(Person).where(Person.works_for.name == "Acme Corp").all()
    assert len(results) == 1
