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
    from sparqlmodel.graph import expand_iri
    from tests.rdf_helpers import RDF_TYPE

    lone = Person(id=IRI("urn:person:lone"), name="Lone", works_for=None)
    session.put(lone)
    person_uri = str(lone.id.expand(Person.get_prefixes()))
    works_for = expand_iri("schema:worksFor", Person.get_prefixes())
    org_type = expand_iri("schema:Organization", Person.get_prefixes())
    session.graph.add((person_uri, works_for, person_uri))
    session.graph.add((person_uri, RDF_TYPE, org_type))
    bindings = [{"person": str(lone.id)}]
    with pytest.raises(ConfigurationError, match="Cycle detected"):
        hydrate_from_bindings(Person, bindings, session.store, depth=1)
