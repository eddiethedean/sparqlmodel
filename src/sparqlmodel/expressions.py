"""Query expression types for the SPARQL compiler."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sparqlmodel.model import SPARQLModel


class CompareOp(str, Enum):
    EQ = "=="
    NE = "!="


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

    def __eq__(self, other: object) -> CompareExpr:  # ty: ignore[invalid-method-override]
        return CompareExpr(self, CompareOp.EQ, other)

    def __ne__(self, other: object) -> CompareExpr:  # ty: ignore[invalid-method-override]
        return CompareExpr(self, CompareOp.NE, other)


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


@dataclass(frozen=True)
class AndExpr:
    """AND combination of comparison expressions."""

    expressions: tuple[CompareExpr, ...]

    def __and__(self, other: CompareExpr | AndExpr) -> AndExpr:
        if isinstance(other, AndExpr):
            return AndExpr(self.expressions + other.expressions)
        return AndExpr(self.expressions + (other,))
