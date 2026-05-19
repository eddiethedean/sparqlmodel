"""Tests for graph serialization cycles."""

import pytest

from sparqlmodel import IRI, Field, Relationship, SPARQLModel, SPARQLSession
from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.graph import iter_nested_models
from sparqlmodel.rdf_bridge import assert_no_embed_cycles, model_to_graph
from tests.cycle_models import CycleA, CycleB


class _DagLeaf(SPARQLModel):
    rdf_type = "ex:Leaf"
    __prefixes__ = {"ex": "http://example.org/"}

    name: str = Field("ex:name")


class _DagRoot(SPARQLModel):
    rdf_type = "ex:Root"
    __prefixes__ = {"ex": "http://example.org/"}

    left: _DagLeaf | None = Relationship("ex:left", model=_DagLeaf)
    right: _DagLeaf | None = Relationship("ex:right", model=_DagLeaf)


def _cycle_pair() -> tuple[CycleA, CycleB]:
    b = CycleB(id=IRI("urn:cycle:b"), name="B")
    a = CycleA(id=IRI("urn:cycle:a"), name="A", b=b)
    b.a_ref = a
    return a, b


def test_assert_no_embed_cycles_detects_cycle() -> None:
    a, _b = _cycle_pair()
    with pytest.raises(ConfigurationError, match="Cycle detected"):
        assert_no_embed_cycles(a, set())


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


def test_get_depth_allows_dag_shared_embed() -> None:
    """Two relationship fields may reference the same embedded resource (diamond)."""
    leaf = _DagLeaf(id=IRI("urn:dag:leaf"), name="shared")
    root = _DagRoot(id=IRI("urn:dag:root"), left=leaf, right=leaf)
    with SPARQLSession() as session:
        session.put(root)
        loaded = session.get(_DagRoot, root.id, depth=1)
    assert loaded is not None
    assert loaded.left is not None
    assert loaded.right is not None
    assert loaded.left.name == "shared"
    assert loaded.right.name == "shared"
