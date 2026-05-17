"""Unit tests for cascade subject collection."""

from sparqlmodel.graph import (
    cascade_subjects_for_removal,
    iter_nested_models,
    owned_triples_for_subjects,
)
from sparqlmodel.types import IRI
from tests.models import Location, Organization, Person


def test_iter_nested_models_includes_location(session) -> None:
    hq = Location(id=IRI("urn:loc:hq"), name="HQ")
    acme = Organization(id=IRI("urn:org:acme"), name="Acme", located_in=hq)
    odos = Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)
    nested = iter_nested_models(odos)
    assert len(nested) == 3
    assert {type(m).__name__ for m in nested} == {"Person", "Organization", "Location"}


def test_cascade_subjects_includes_graph_orphan_on_put(session) -> None:
    acme = Organization(id=IRI("urn:org:old"), name="Old")
    other = Organization(id=IRI("urn:org:new"), name="New")
    person = Person(id=IRI("urn:person:p"), name="Pat", works_for=acme)
    session.put(person)
    person.works_for = other
    subjects = cascade_subjects_for_removal(person, session.graph, for_put=True)
    keys = {iri for _, iri in subjects}
    assert "urn:org:old" in keys
    assert "urn:org:new" in keys
    assert "urn:person:p" in keys


def test_cascade_subjects_includes_nested_location_orphan_on_put(session) -> None:
    hq = Location(id=IRI("urn:loc:hq"), name="HQ")
    acme = Organization(id=IRI("urn:org:acme"), name="Acme", located_in=hq)
    person = Person(id=IRI("urn:person:p"), name="Pat", works_for=acme)
    session.put(person)
    acme.located_in = Location(id=IRI("urn:loc:new"), name="New HQ")
    subjects = cascade_subjects_for_removal(person, session.graph, for_put=True)
    keys = {iri for _, iri in subjects}
    assert "urn:loc:hq" in keys


def test_cascade_subjects_skips_iri_reference_orphans(session, acme: Organization) -> None:
    session.put(acme)
    person = Person(id=IRI("urn:person:ref"), name="Ref", works_for=acme.id)
    session.put(person)
    subjects = cascade_subjects_for_removal(person, session.graph, for_put=True)
    keys = {iri for _, iri in subjects}
    assert keys == {"urn:person:ref"}


def test_owned_triples_for_subjects_dedupes(session, odos: Person) -> None:
    session.put(odos)
    subjects = cascade_subjects_for_removal(odos, session.graph)
    triples = owned_triples_for_subjects(subjects, session.graph)
    assert len(triples) == len(set(triples))
