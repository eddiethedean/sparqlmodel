"""Tests for nested resource cascade on put/delete."""

from rdflib import URIRef

from sparqlmodel import IRI
from tests.models import Organization, Person


def test_delete_cascades_embedded_org_triples(session, odos: Person, acme: Organization) -> None:
    session.put(odos)
    org_ref = URIRef(str(acme.id.expand(acme.get_prefixes())))
    assert len(list(session.graph.triples((org_ref, None, None)))) >= 1

    session.delete(odos)
    assert session.get(Person, odos.id) is None
    assert len(list(session.graph.triples((org_ref, None, None)))) == 0


def test_put_changing_works_for_removes_old_org(session, acme: Organization) -> None:
    other = Organization(id=IRI("urn:org:other"), name="Other Corp")
    person = Person(id=IRI("urn:person:p1"), name="Pat", works_for=acme)
    session.put(person)

    old_org_ref = URIRef(str(acme.id.expand(acme.get_prefixes())))
    assert len(list(session.graph.triples((old_org_ref, None, None)))) >= 1

    person.works_for = other
    session.put(person)

    assert len(list(session.graph.triples((old_org_ref, None, None)))) == 0
    assert session.get(Organization, other.id) is not None
    assert session.get(Organization, other.id).name == "Other Corp"


def test_delete_does_not_cascade_iri_only_reference(session, acme: Organization) -> None:
    session.put(acme)
    person = Person(id=IRI("urn:person:ref"), name="Ref", works_for=acme.id)
    session.put(person)

    org_ref = URIRef(str(acme.id.expand(acme.get_prefixes())))
    session.delete(person)
    assert session.get(Person, person.id) is None
    assert len(list(session.graph.triples((org_ref, None, None)))) >= 1


def test_add_same_id_leaves_stale_literals(session) -> None:
    person = Person(id=IRI("urn:person:dup"), name="First")
    session.add(person)
    person.name = "Second"
    session.add(person)
    loaded = session.get(Person, person.id)
    assert loaded is not None
    from sparqlmodel.graph import expand_iri

    pred = URIRef(expand_iri("schema:name", Person.get_prefixes()))
    subj = URIRef(str(person.id.expand(Person.get_prefixes())))
    names = [str(o) for o in session.graph.objects(subj, pred)]
    assert "First" in names
    assert "Second" in names
