"""Tests for hydration."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from triplemodel import Store

from sparqlmodel import IRI, Field, Relationship, SPARQLModel
from sparqlmodel.exceptions import HydrationError
from sparqlmodel.hydration import hydrate_one
from sparqlmodel.rdf_bridge import load_from_graph
from tests.models import Organization, Person


def test_hydrate_one_wraps_validation_error(session, odos: Person) -> None:
    session.put(odos)
    with (
        patch(
            "sparqlmodel.hydration.load_from_graph",
            side_effect=ValidationError.from_exception_data("Person", []),
        ),
        pytest.raises(HydrationError),
    ):
        hydrate_one(Person, odos.id, session.store)


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


def test_hydration_depth_2(session, acme: Organization) -> None:
    from tests.models import Location

    hq = Location(id=IRI("urn:loc:hq"), name="HQ")
    acme.located_in = hq
    odos = Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)
    session.put(odos)
    loaded = session.get(Person, odos.id, depth=2)
    assert loaded is not None
    assert loaded.works_for is not None
    assert loaded.works_for.located_in is not None
    assert loaded.works_for.located_in.name == "HQ"


def test_load_from_graph_non_cascade_embed_without_iri_raises() -> None:
    class PersonNC(SPARQLModel):
        rdf_type = "ex:PersonNC"
        __prefixes__ = {"schema": "https://schema.org/", "ex": "http://example.org/ns/"}
        name: str = Field("schema:name")
        works_for: Organization | None = Relationship(
            "schema:worksFor",
            model=Organization,
            cascade=False,
        )

    nested_org = Organization(id=IRI("urn:org:nc"), name="O", located_in=None)
    raw_nc = MagicMock()
    raw_nc.subject_uri.return_value = "urn:p:nc"
    raw_nc.name = "Solo"
    raw_nc.works_for = nested_org
    with (
        patch.object(PersonNC, "from_graph", return_value=raw_nc),
        pytest.raises(HydrationError, match="Non-cascade relationship"),
    ):
        load_from_graph(PersonNC, IRI("urn:p:nc"), Store(), depth=1)


def test_load_from_graph_missing_related_type_without_iri_allowed() -> None:
    """When IRI refs are not allowed, a string object without rdf:type becomes None."""

    class StrictPerson(SPARQLModel):
        rdf_type = "urn:test:StrictPerson"
        __prefixes__ = {"schema": "https://schema.org/"}
        id: IRI
        name: str = Field("schema:name")
        works_for: Organization | None = Relationship(
            "schema:worksFor",
            model=Organization,
            cascade=False,
        )

    raw = MagicMock()
    raw.subject_uri.return_value = "urn:person:strict"
    raw.name = "Pat"
    raw.works_for = "urn:org:ghost"
    with patch.object(StrictPerson, "from_graph", return_value=raw):
        loaded = load_from_graph(StrictPerson, IRI("urn:person:strict"), Store(), depth=1)
    assert loaded.works_for is None


def test_load_from_graph_iri_ref_without_rdf_type() -> None:
    """IRI-only relationship edges hydrate as IRI when the target has no rdf:type."""
    from pyoxigraph import Literal

    g = Store()
    person_iri = "urn:person:1"
    org_iri = "urn:org:ref"
    g.add(
        (
            person_iri,
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "https://schema.org/Person",
        )
    )
    g.add((person_iri, "https://schema.org/name", Literal("Pat")))
    g.add((person_iri, "https://schema.org/worksFor", org_iri))
    loaded = load_from_graph(Person, IRI(person_iri), g, depth=1)
    assert isinstance(loaded.works_for, IRI)
    assert str(loaded.works_for) == org_iri


def test_missing_related(session, odos: Person) -> None:
    session.put(odos)
    orphan = Person(id=IRI("urn:person:orphan"), name="Orphan", works_for=None)
    session.put(orphan)
    loaded = session.get(Person, orphan.id, depth=1)
    assert loaded is not None
    assert loaded.works_for is None
