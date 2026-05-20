"""Tests for nested resource cascade on put/delete."""

from pyoxigraph import BlankNode

from sparqlmodel import IRI
from sparqlmodel.graph import expand_iri
from tests.models import Location, Organization, Person


def test_delete_cascades_embedded_org_triples(session, odos: Person, acme: Organization) -> None:
    session.put(odos)
    org_ref = str(acme.id.expand(acme.get_prefixes()))
    assert len(list(session.graph.triples((org_ref, None, None)))) >= 1

    session.delete(odos)
    assert session.get(Person, odos.id) is None
    assert len(list(session.graph.triples((org_ref, None, None)))) == 0


def test_put_changing_works_for_removes_old_org(session, acme: Organization) -> None:
    other = Organization(id=IRI("urn:org:other"), name="Other Corp")
    person = Person(id=IRI("urn:person:p1"), name="Pat", works_for=acme)
    session.put(person)

    old_org_ref = str(acme.id.expand(acme.get_prefixes()))
    assert len(list(session.graph.triples((old_org_ref, None, None)))) >= 1

    person.works_for = other
    session.put(person)

    assert len(list(session.graph.triples((old_org_ref, None, None)))) == 0
    assert session.get(Organization, other.id) is not None
    assert session.get(Organization, other.id).name == "Other Corp"


def test_put_embedded_to_iri_removes_old_org_triples(session) -> None:
    old_org = Organization(id=IRI("urn:org:old"), name="Old Corp")
    new_org = Organization(id=IRI("urn:org:new"), name="New Corp")
    session.put(new_org)
    person = Person(id=IRI("urn:person:p1"), name="Pat", works_for=old_org)
    session.put(person)

    old_org_ref = str(old_org.id.expand(old_org.get_prefixes()))
    assert len(list(session.graph.triples((old_org_ref, None, None)))) >= 1

    person.works_for = new_org.id
    session.put(person)

    assert len(list(session.graph.triples((old_org_ref, None, None)))) == 0
    assert session.get(Organization, new_org.id) is not None


def test_delete_does_not_cascade_iri_only_reference(session, acme: Organization) -> None:
    session.put(acme)
    person = Person(id=IRI("urn:person:ref"), name="Ref", works_for=acme.id)
    session.put(person)

    org_ref = str(acme.id.expand(acme.get_prefixes()))
    session.delete(person)
    assert session.get(Person, person.id) is None
    assert len(list(session.graph.triples((org_ref, None, None)))) >= 1


def test_put_nested_location_orphan_removed(session) -> None:
    hq = Location(id=IRI("urn:loc:hq"), name="HQ")
    acme = Organization(id=IRI("urn:org:acme"), name="Acme", located_in=hq)
    odos = Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)
    session.put(odos)

    hq_ref = str(hq.id.expand(hq.get_prefixes()))
    assert len(list(session.graph.triples((hq_ref, None, None)))) >= 1

    acme.located_in = Location(id=IRI("urn:loc:new"), name="New HQ")
    session.put(odos)

    assert len(list(session.graph.triples((hq_ref, None, None)))) == 0
    assert session.get(Location, hq.id) is None
    assert session.get(Location, IRI("urn:loc:new")) is not None


def test_put_removes_stale_bnode_relationship_target(session) -> None:
    person = Person(id=IRI("urn:person:bnode"), name="Pat", works_for=None)
    session.put(person)
    subj = str(person.id.expand(Person.get_prefixes()))
    pred = expand_iri("schema:worksFor", Person.get_prefixes())
    bnode = BlankNode()
    session.graph.add((subj, pred, bnode))
    assert len(list(session.graph.triples((subj, pred, bnode)))) == 1

    acme = Organization(id=IRI("urn:org:acme"), name="Acme")
    person.works_for = acme
    session.put(person)

    assert len(list(session.graph.triples((subj, pred, bnode)))) == 0
    assert session.get(Organization, acme.id) is not None


def test_add_same_id_leaves_stale_literals(session) -> None:
    person = Person(id=IRI("urn:person:dup"), name="First")
    session.add(person)
    person.name = "Second"
    session.add(person)
    loaded = session.get(Person, person.id)
    assert loaded is not None
    pred = expand_iri("schema:name", Person.get_prefixes())
    subj = str(person.id.expand(Person.get_prefixes()))
    from triplemodel.store.terms import term_str

    names = [term_str(o) for o in session.graph.objects(subj, pred)]
    assert "First" in names
    assert "Second" in names
