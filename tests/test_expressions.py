"""Tests for query expressions."""

from sparqlmodel.expressions import AndExpr, CompareOp
from tests.models import Person


def test_compare_ne() -> None:
    expr = Person.name != "Other"
    assert expr.op == CompareOp.NE


def test_and_expr() -> None:
    a = Person.name == "A"
    b = Person.name == "B"
    combined = AndExpr((a, b))
    assert len(combined.expressions) == 2
