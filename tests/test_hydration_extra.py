"""Additional hydration coverage."""

import pytest

from sparqlmodel import IRI
from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.hydration import hydrate_from_bindings
from tests.models import Organization, Person


def test_hydrate_from_bindings(session, odos: Person) -> None:
    session.put(odos)
    bindings = session.execute("SELECT ?person WHERE { ?person a <https://schema.org/Person> . }")
    results = hydrate_from_bindings(Person, bindings, session.store, depth=1)
    assert len(results) >= 1


def test_hydrate_from_bindings_wrong_type(session, acme: Organization) -> None:
    session.put(acme)
    bindings = [{"person": str(acme.id)}]
    results = hydrate_from_bindings(Person, bindings, session.store)
    assert results == []


def test_hydrate_cycle_raises(session) -> None:
    from rdflib import URIRef

    from sparqlmodel.graph import expand_iri

    lone = Person(id=IRI("urn:person:lone"), name="Lone", works_for=None)
    session.put(lone)
    person_uri = URIRef(str(lone.id.expand(Person.get_prefixes())))
    works_for = URIRef(expand_iri("schema:worksFor", Person.get_prefixes()))
    org_type = URIRef(expand_iri("schema:Organization", Person.get_prefixes()))
    session.graph.add((person_uri, works_for, person_uri))
    rdf_type = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    session.graph.add((person_uri, rdf_type, org_type))
    bindings = [{"person": str(lone.id)}]
    with pytest.raises(ConfigurationError, match="Cycle detected"):
        hydrate_from_bindings(Person, bindings, session.store, depth=1)
