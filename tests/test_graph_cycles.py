"""Tests for graph serialization cycles."""

import pytest

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.graph import iter_nested_models, model_to_triples
from sparqlmodel.types import IRI
from tests.cycle_models import CycleA, CycleB


def test_model_to_triples_cycle() -> None:
    b = CycleB(id=IRI("urn:cycle:b"), name="B")
    a = CycleA(id=IRI("urn:cycle:a"), name="A", b=b)
    b.a_ref = a
    with pytest.raises(ConfigurationError, match="Cycle detected"):
        model_to_triples(a)


def test_iter_nested_models_dedupes_shared_embed() -> None:
    b = CycleB(id=IRI("urn:cycle:b"), name="B")
    a = CycleA(id=IRI("urn:cycle:a"), name="A", b=b)
    nested = iter_nested_models(a)
    assert len([m for m in nested if m.id == b.id]) == 1
