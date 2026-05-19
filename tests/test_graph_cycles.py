"""Tests for graph serialization cycles."""

import pytest

from sparqlmodel import SPARQLSession
from sparqlmodel._triple import model_to_graph, to_triplemodel
from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.graph import iter_nested_models
from sparqlmodel.types import IRI
from tests.cycle_models import CycleA, CycleB


def _cycle_pair() -> tuple[CycleA, CycleB]:
    b = CycleB(id=IRI("urn:cycle:b"), name="B")
    a = CycleA(id=IRI("urn:cycle:a"), name="A", b=b)
    b.a_ref = a
    return a, b


def test_to_triplemodel_cycle() -> None:
    a, _b = _cycle_pair()
    with pytest.raises(ConfigurationError, match="Cycle detected"):
        to_triplemodel(a)


def test_model_to_graph_cycle() -> None:
    a, _b = _cycle_pair()
    with pytest.raises(ConfigurationError, match="Cycle detected"):
        model_to_graph(a)


def test_session_put_cycle() -> None:
    a, _b = _cycle_pair()
    with pytest.raises(ConfigurationError, match="Cycle detected"):
        SPARQLSession().put(a)


def test_iter_nested_models_dedupes_shared_embed() -> None:
    b = CycleB(id=IRI("urn:cycle:b"), name="B")
    a = CycleA(id=IRI("urn:cycle:a"), name="A", b=b)
    nested = iter_nested_models(a)
    assert len([m for m in nested if m.id == b.id]) == 1
