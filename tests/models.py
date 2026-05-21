"""Sample models for tests."""

from __future__ import annotations

from sparqlmodel import IRI, Field, Relationship, SPARQLModel


class Location(SPARQLModel):
    rdf_type = "schema:Place"
    __prefixes__ = {"schema": "https://schema.org/"}

    name: str = Field("schema:name")


class Organization(SPARQLModel):
    rdf_type = "schema:Organization"
    __prefixes__ = {"schema": "https://schema.org/"}

    name: str = Field("schema:name")
    located_in: Location | None = Relationship("schema:location", model=Location)


class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    name: str = Field("schema:name")
    works_for: Organization | IRI | None = Relationship("schema:worksFor", model=Organization)


class TeamLead(SPARQLModel):
    rdf_type = "urn:test:TeamLead"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
    department: Organization | None = Relationship("schema:department", model=Organization)


class DualRelPerson(SPARQLModel):
    rdf_type = "urn:test:DualRelPerson"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
    works_for: Organization | None = Relationship("schema:worksFor", model=Organization)
    manager: TeamLead | None = Relationship("urn:test:manager", model=TeamLead)
