"""Tests for SPARQLModel."""

import pytest

from sparqlmodel import IRI, SPARQLModel
from sparqlmodel.exceptions import ConfigurationError
from tests.models import Person


def test_model_requires_rdf_type() -> None:
    with pytest.raises(ConfigurationError):

        class BadModel(SPARQLModel):
            id: IRI


def test_person_field_ref() -> None:
    expr = Person.name == "Odos"
    assert expr.left.field_name == "name"
    assert expr.right == "Odos"


def test_nested_field_ref() -> None:
    expr = Person.works_for.name == "Acme"
    assert expr.left.path == ("works_for",)
    assert expr.left.field_name == "name"


def test_iri_expand() -> None:
    iri = IRI("schema:Person")
    assert "schema.org" in iri.expand({"schema": "https://schema.org/"})
