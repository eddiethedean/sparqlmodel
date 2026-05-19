"""Query expression types for the SPARQL compiler."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sparqlmodel.model import SPARQLModel


class CompareOp(str, Enum):
    EQ = "=="
    NE = "!="
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="
    IN = "in"


@dataclass(frozen=True)
class FieldRef:
    """Reference to a model field in a query expression."""

    model_cls: type[SPARQLModel]
    field_name: str
    path: tuple[str, ...] = ()

    def __getattr__(self, name: str) -> FieldRef:
        if name.startswith("_"):
            raise AttributeError(name)
        return FieldRef(self.model_cls, name, self.path + (self.field_name,))

    def _compare(self, op: CompareOp, other: object) -> CompareExpr:
        return CompareExpr(self, op, other)

    def __eq__(self, other: object) -> CompareExpr:  # ty: ignore[invalid-method-override]
        return self._compare(CompareOp.EQ, other)

    def __ne__(self, other: object) -> CompareExpr:  # ty: ignore[invalid-method-override]
        return self._compare(CompareOp.NE, other)

    def __lt__(self, other: object) -> CompareExpr:
        return self._compare(CompareOp.LT, other)

    def __gt__(self, other: object) -> CompareExpr:
        return self._compare(CompareOp.GT, other)

    def __le__(self, other: object) -> CompareExpr:
        return self._compare(CompareOp.LTE, other)

    def __ge__(self, other: object) -> CompareExpr:
        return self._compare(CompareOp.GTE, other)

    def in_(self, values: tuple[object, ...] | Sequence[object]) -> CompareExpr:
        seq = values if isinstance(values, tuple) else tuple(values)
        return CompareExpr(self, CompareOp.IN, seq)


@dataclass(frozen=True)
class CompareExpr:
    """Comparison expression for query filtering."""

    left: FieldRef
    op: CompareOp
    right: object

    def __and__(self, other: CompareExpr | AndExpr) -> AndExpr:
        if isinstance(other, AndExpr):
            return AndExpr((self,) + other.expressions)
        return AndExpr((self, other))

    def __or__(self, other: CompareExpr | OrExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr((self,) + other.expressions)
        return OrExpr((self, other))


@dataclass(frozen=True)
class AndExpr:
    """AND combination of comparison expressions."""

    expressions: tuple[CompareExpr, ...]

    def __and__(self, other: CompareExpr | AndExpr) -> AndExpr:
        if isinstance(other, AndExpr):
            return AndExpr(self.expressions + other.expressions)
        return AndExpr(self.expressions + (other,))

    def __or__(self, other: CompareExpr | OrExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr((self,) + other.expressions)
        return OrExpr((self, other))


@dataclass(frozen=True)
class OrExpr:
    """OR combination of comparison or AND expressions."""

    expressions: tuple[CompareExpr | AndExpr, ...]

    def __and__(self, other: CompareExpr | AndExpr) -> AndExpr:
        if isinstance(other, AndExpr):
            return AndExpr(other.expressions + self.expressions)
        return AndExpr((other,) + self.expressions)

    def __rand__(self, other: CompareExpr | AndExpr) -> AndExpr:
        return self.__and__(other)

    def __or__(self, other: CompareExpr | AndExpr | OrExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr(self.expressions + other.expressions)
        return OrExpr(self.expressions + (other,))
