"""Query expression types for the SPARQL compiler."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from sparqlmodel.exceptions import QueryError

if TYPE_CHECKING:
    from sparqlmodel.model import SPARQLModel

_OR_AND_MSG = (
    "Cannot combine OR and AND with `&`. Use `.where((A | B), C)` with separate "
    "arguments, or parenthesize as `(A & B) | C`."
)


class CompareOp(str, Enum):
    EQ = "=="
    NE = "!="
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="
    IN = "in"
    IS_ = "is"
    IS_NOT = "is_not"


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
        if isinstance(values, str):
            raise QueryError(
                "in_() does not accept a bare string (it would split into characters). "
                "Use a one-element tuple or list, e.g. in_((value,)) or in_([value])."
            )
        seq = values if isinstance(values, tuple) else tuple(values)
        return CompareExpr(self, CompareOp.IN, seq)

    def is_(self, value: object) -> CompareExpr:
        if value is not None:
            raise QueryError("is_() only supports None for nullable relationship absence checks")
        if self.path:
            raise QueryError("is_(None) applies to a relationship field, not a nested scalar path")
        return CompareExpr(self, CompareOp.IS_, value)

    def is_not(self, value: object) -> CompareExpr:
        if value is not None:
            raise QueryError(
                "is_not() only supports None for nullable relationship presence checks"
            )
        if self.path:
            raise QueryError(
                "is_not(None) applies to a relationship field, not a nested scalar path"
            )
        return CompareExpr(self, CompareOp.IS_NOT, value)


@dataclass(frozen=True)
class CompareExpr:
    """Comparison expression for query filtering."""

    left: FieldRef
    op: CompareOp
    right: object

    def __and__(self, other: CompareExpr | AndExpr | OrExpr) -> AndExpr:
        if isinstance(other, OrExpr):
            raise QueryError(_OR_AND_MSG)
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

    def __and__(self, other: CompareExpr | AndExpr | OrExpr) -> AndExpr:
        if isinstance(other, OrExpr):
            raise QueryError(_OR_AND_MSG)
        if isinstance(other, AndExpr):
            return AndExpr(self.expressions + other.expressions)
        return AndExpr(self.expressions + (other,))

    def __or__(self, other: CompareExpr | OrExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr((self,) + other.expressions)
        return OrExpr((self, other))


def _flatten_and_parts(
    parts: tuple[CompareExpr | AndExpr, ...],
) -> tuple[CompareExpr, ...]:
    """Flatten nested ``AndExpr`` nodes into a single AND tuple of comparisons."""
    out: list[CompareExpr] = []
    for part in parts:
        if isinstance(part, AndExpr):
            out.extend(part.expressions)
        else:
            out.append(part)
    return tuple(out)


@dataclass(frozen=True)
class OrExpr:
    """OR combination of comparison or AND expressions."""

    expressions: tuple[CompareExpr | AndExpr, ...]

    def __and__(self, other: CompareExpr | AndExpr) -> AndExpr:
        raise QueryError(_OR_AND_MSG)

    def __rand__(self, other: CompareExpr | AndExpr) -> AndExpr:
        raise QueryError(_OR_AND_MSG)

    def __or__(self, other: CompareExpr | AndExpr | OrExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr(self.expressions + other.expressions)
        return OrExpr(self.expressions + (other,))
