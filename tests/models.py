"""Sample models for tests."""

from __future__ import annotations

from sparqlmodel import Field, Relationship, SPARQLModel


class Organization(SPARQLModel):
    rdf_type = "schema:Organization"
    __prefixes__ = {"schema": "https://schema.org/"}

    name: str = Field("schema:name")


class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    name: str = Field("schema:name")
    works_for: Organization | None = Relationship("schema:worksFor", model=Organization)
