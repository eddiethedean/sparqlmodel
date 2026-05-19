"""Shared test fixtures."""

from __future__ import annotations

import pytest

from sparqlmodel import IRI, SPARQLSession
from sparqlmodel import _triple as triple_mod
from tests.models import Organization, Person


@pytest.fixture(autouse=True)
def _clear_triple_class_cache() -> None:
    triple_mod._TRIPLE_CLASS_CACHE.clear()
    yield
    triple_mod._TRIPLE_CLASS_CACHE.clear()


@pytest.fixture
def session() -> SPARQLSession:
    return SPARQLSession()


@pytest.fixture
def acme() -> Organization:
    return Organization(id=IRI("urn:org:acme"), name="Acme Corp")


@pytest.fixture
def odos(acme: Organization) -> Person:
    return Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)
