"""Query compiler features for SparqlModel 0.13."""

from __future__ import annotations

from typing import ClassVar

from sparqlmodel import (
    IRI,
    Field,
    OntologyRegistry,
    SPARQLModel,
    SPARQLSession,
    not_,
    property_eq,
)
from sparqlmodel.compiler import compile_where
from sparqlmodel.types import NamespaceRegistry
from tests.models import Person


def test_polymorphic_query_compiles_subtypes() -> None:
    reg = OntologyRegistry()
    reg.register_subclasses(
        "https://schema.org/Person",
        ["https://schema.org/Employee"],
    )

    class Employee(SPARQLModel):
        rdf_type = "schema:Employee"
        __prefixes__ = {"schema": "https://schema.org/"}
        ontology_registry: ClassVar[OntologyRegistry] = reg
        id: IRI
        name: str = Field("schema:name")

    sparql = compile_where(
        Employee,
        (Employee.name == "Pat",),
        NamespaceRegistry(Employee.get_prefixes()),
        polymorphic=True,
    )
    assert "FILTER" in sparql
    assert "schema.org/Person" in sparql or "schema.org/Employee" in sparql


def test_values_clause_in_query() -> None:
    with SPARQLSession() as session:
        sparql = (
            session.query(Person)
            .values(person=IRI("urn:person:odos"))
            .where(Person.name == "Odos")
            ._compile()
        )
    assert "VALUES" in sparql
    assert "urn:person:odos" in sparql


def test_not_expression() -> None:
    sparql = compile_where(
        Person,
        (not_(Person.name == "Other"),),
        NamespaceRegistry(Person.get_prefixes()),
    )
    assert "NOT" in sparql


def test_iri_str_lower_filter() -> None:
    class WithIri(SPARQLModel):
        rdf_type = "schema:Person"
        __prefixes__ = {"schema": "https://schema.org/"}
        id: IRI
        alt_id: IRI | None = Field("schema:identifier")

    sparql = compile_where(
        WithIri,
        (WithIri.alt_id.lower() == "abc",),
        NamespaceRegistry(WithIri.get_prefixes()),
    )
    assert "LCASE" in sparql
    assert "STR" in sparql


def test_property_path_eq() -> None:
    sparql = compile_where(
        Person,
        (property_eq(Person, "schema:worksFor/schema:name", "Acme"),),
        NamespaceRegistry(Person.get_prefixes()),
    )
    assert "worksFor" in sparql
    assert "Acme" in sparql


def test_query_polymorphic_session() -> None:
    with SPARQLSession() as session:
        session.put(
            Person(id=IRI("urn:person:p"), name="Pat", works_for=None),
        )
        results = session.query(Person).polymorphic().where(Person.name == "Pat").all()
    assert len(results) >= 1
