"""Tests for SPARQLSession CRUD."""

from sparqlmodel import SPARQLSession
from tests.models import Organization, Person


def test_put_and_get(session, odos: Person) -> None:
    session.put(odos)
    loaded = session.get(Person, odos.id)
    assert loaded is not None
    assert loaded.name == "Odos"


def test_add(session, acme: Organization) -> None:
    session.add(acme)
    loaded = session.get(Organization, acme.id)
    assert loaded is not None
    assert loaded.name == "Acme Corp"


def test_delete(session, odos: Person) -> None:
    session.put(odos)
    session.delete(odos)
    assert session.get(Person, odos.id) is None


def test_execute_select(session, odos: Person) -> None:
    session.put(odos)
    results = session.execute("SELECT ?s WHERE { ?s a <https://schema.org/Person> . }")
    assert len(results) >= 1


def test_put_updates(session, odos: Person) -> None:
    session.put(odos)
    odos.name = "Odos M."
    session.put(odos)
    loaded = session.get(Person, odos.id)
    assert loaded is not None
    assert loaded.name == "Odos M."


def test_auto_id(session) -> None:
    person = Person(name="Anonymous")
    session.put(person)
    assert person.id is not None
    loaded = session.get(Person, person.id)
    assert loaded is not None


def test_get_wrong_model_type(session, odos: Person) -> None:
    session.put(odos)
    assert session.get(Organization, odos.id) is None


def test_put_flush_true_clears_pending_queue(session: SPARQLSession) -> None:
    from sparqlmodel import IRI

    session.autoflush = False
    v1 = Person(id=IRI("urn:p:v1"), name="Version 1")
    v2 = Person(id=IRI("urn:p:v1"), name="Version 2")
    session.put(v1, flush=False)
    session.put(v2, flush=True)
    session.flush()
    loaded = session.get(Person, v1.id)
    assert loaded is not None
    assert loaded.name == "Version 2"


def test_delete_drops_pending_put(session: SPARQLSession, odos: Person) -> None:
    session.autoflush = False
    session.put(odos, flush=False)
    session.delete(odos)
    session.flush()
    assert session.get(Person, odos.id) is None


def test_get_miss_then_put_returns_instance(session: SPARQLSession) -> None:
    from sparqlmodel import IRI

    iri = IRI("urn:person:late")
    session.autoflush = False
    assert session.get(Person, iri) is None
    person = Person(id=iri, name="Late")
    session.put(person, flush=False)
    session.flush()
    loaded = session.get(Person, iri)
    assert loaded is not None
    assert loaded.name == "Late"


def test_put_invalidates_cross_type_hydration_miss(session: SPARQLSession) -> None:
    from sparqlmodel import IRI

    iri = IRI("urn:person:cross")
    assert session.get(Organization, iri) is None
    session.put(Person(id=iri, name="Cross"))
    assert session.get(Person, iri) is not None
    assert session.get(Person, iri).name == "Cross"
