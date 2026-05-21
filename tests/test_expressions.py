"""Tests for query expressions."""

import pytest

from sparqlmodel.exceptions import QueryError
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


def test_in_bare_string_raises_at_build() -> None:
    with pytest.raises(QueryError, match="bare string"):
        Person.name.in_("x")


def test_and_expr_and_or_group_raises() -> None:
    from sparqlmodel.expressions import OrExpr

    inner = AndExpr((Person.name == "A",))
    with pytest.raises(QueryError, match="Cannot combine OR and AND"):
        _ = inner & OrExpr((Person.name == "B", Person.name == "C"))
