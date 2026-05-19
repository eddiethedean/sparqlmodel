"""Tests for SPARQL compiler join variable uniqueness."""

from __future__ import annotations

from rdflib import URIRef

from sparqlmodel import IRI, Field, Relationship, SPARQLModel, SPARQLSession
from sparqlmodel.compiler import compile_where
from sparqlmodel.types import NamespaceRegistry, expand_iri
from tests.models import Location, Organization, Person


class DualOrgPerson(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
    employer: Organization | None = Relationship("schema:worksFor", model=Organization)
    volunteer_at: Organization | None = Relationship("schema:memberOf", model=Organization)


def test_parallel_nested_filters_use_distinct_join_vars() -> None:
    registry = NamespaceRegistry(DualOrgPerson.get_prefixes())
    expr = (DualOrgPerson.employer.located_in.name == "HQ A") & (
        DualOrgPerson.volunteer_at.located_in.name == "HQ B"
    )
    sparql = compile_where(DualOrgPerson, (expr,), registry)
    import re

    join_ids = set(re.findall(r"\?__join_\d+", sparql))
    assert len(join_ids) >= 4


def test_parallel_nested_filters_query_returns_correct_rows() -> None:
    hq_a = Location(id=IRI("urn:loc:a"), name="HQ A")
    hq_b = Location(id=IRI("urn:loc:b"), name="HQ B")
    employer = Organization(id=IRI("urn:org:emp"), name="Employer", located_in=hq_a)
    volunteer = Organization(id=IRI("urn:org:vol"), name="Volunteer", located_in=hq_b)
    match = DualOrgPerson(
        id=IRI("urn:person:match"),
        name="Match",
        employer=employer,
        volunteer_at=volunteer,
    )
    other = DualOrgPerson(
        id=IRI("urn:person:other"),
        name="Other",
        employer=Organization(
            id=IRI("urn:org:other-emp"),
            name="Other Emp",
            located_in=Location(id=IRI("urn:loc:not-a"), name="Not HQ A"),
        ),
        volunteer_at=Organization(
            id=IRI("urn:org:wrong"),
            name="Wrong",
            located_in=Location(id=IRI("urn:loc:wrong"), name="HQ B"),
        ),
    )

    session = SPARQLSession()
    session.put(match)
    session.put(other)

    results = (
        session.query(DualOrgPerson)
        .where(
            (DualOrgPerson.employer.located_in.name == "HQ A")
            & (DualOrgPerson.volunteer_at.located_in.name == "HQ B")
        )
        .all()
    )
    assert len(results) == 1
    assert results[0].name == "Match"


def test_same_relationship_path_and_reuses_single_join() -> None:
    registry = NamespaceRegistry(Person.get_prefixes())
    expr = (Person.works_for.name == "Acme") & (Person.works_for.located_in.name == "Boston")
    sparql = compile_where(Person, (expr,), registry)
    works_for_pred = expand_iri("schema:worksFor", Person.get_prefixes())
    works_for_edges = [line for line in sparql.split("\n") if f"<{works_for_pred}>" in line]
    assert len(works_for_edges) == 1


def test_same_relationship_path_and_no_false_positive_with_two_employers() -> None:
    boston = Location(id=IRI("urn:loc:boston"), name="Boston")
    acme = Organization(
        id=IRI("urn:org:acme"),
        name="Acme",
        located_in=Location(id=IRI("urn:loc:acme-hq"), name="Cambridge"),
    )
    other = Organization(
        id=IRI("urn:org:other"),
        name="Other",
        located_in=boston,
    )
    pat = Person(id=IRI("urn:person:pat"), name="Pat", works_for=acme)
    session = SPARQLSession()
    session.put(pat)
    g = session.graph
    person_subj = URIRef(expand_iri(str(pat.id), Person.get_prefixes()))
    works_for = URIRef(expand_iri("schema:worksFor", Person.get_prefixes()))
    other_subj = URIRef(expand_iri(str(other.id), Organization.get_prefixes()))
    g.add((person_subj, works_for, other_subj))

    results = (
        session.query(Person)
        .where((Person.works_for.name == "Acme") & (Person.works_for.located_in.name == "Boston"))
        .all()
    )
    assert results == []
