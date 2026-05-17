"""Tests for query builder."""

import pytest

from sparqlmodel import IRI
from sparqlmodel.exceptions import ConfigurationError, QueryError
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
    assert len(results) == 1


def test_query_and_with_ampersand(session, odos: Person) -> None:
    session.put(odos)
    expr = (Person.name == "Odos") & (Person.name != "Nobody")
    results = session.query(Person).where(expr).all()
    assert len(results) == 1
    assert results[0].name == "Odos"


def test_query_not_equal(session, odos: Person) -> None:
    other = Person(id=IRI("urn:person:other"), name="Other")
    session.put(odos)
    session.put(other)
    results = session.query(Person).where(Person.name != "Other").all()
    assert len(results) == 1
    assert results[0].name == "Odos"


def test_query_without_where(session, odos: Person) -> None:
    session.put(odos)
    results = session.query(Person).all()
    assert len(results) >= 1


def test_query_colon_literal(session, odos: Person) -> None:
    colon = Person(id=IRI("urn:person:colon"), name="12:30")
    session.put(odos)
    session.put(colon)
    results = session.query(Person).where(Person.name == "12:30").all()
    assert len(results) == 1
    assert results[0].id == colon.id


def test_query_all_depth(session, odos: Person) -> None:
    session.put(odos)
    results = session.query(Person).where(Person.name == "Odos").all(depth=1)
    assert len(results) == 1
    assert results[0].works_for is not None
    assert results[0].works_for.name == "Acme Corp"


def test_query_invalid_depth(session, odos: Person) -> None:
    session.put(odos)
    with pytest.raises(ConfigurationError):
        session.query(Person).all(depth=5)


def test_nested_query(session, odos: Person) -> None:
    session.put(odos)
    results = session.query(Person).where(Person.works_for.name == "Acme Corp").all()
    assert len(results) == 1


def test_query_negative_limit(session) -> None:
    with pytest.raises(QueryError):
        session.query(Person).limit(-1)
