"""Models with mutual relationships for cycle detection tests."""

from __future__ import annotations

from pydantic import create_model

from sparqlmodel import Field, Relationship, SPARQLModel


class _CycleABase(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}
    name: str = Field("schema:name")


class _CycleBBase(SPARQLModel):
    rdf_type = "schema:Organization"
    __prefixes__ = {"schema": "https://schema.org/"}
    name: str = Field("schema:name")


class CycleA(_CycleABase):
    b: _CycleBBase | None = Relationship("schema:worksFor", model=_CycleBBase)


CycleB = create_model(
    "CycleB",
    __base__=_CycleBBase,
    a_ref=(_CycleABase | None, Relationship("schema:relatedTo", model=CycleA)),
)
