"""Query expression types for the SPARQL compiler."""

from __future__ import annotations

import builtins as _builtins
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Union

from sparqlmodel.exceptions import QueryError

if TYPE_CHECKING:
    from sparqlmodel.model import SPARQLModel

_OR_AND_MSG = (
    "Cannot combine OR and AND with `&`. Use `.where((A | B), C)` with separate "
    "arguments, or parenthesize as `(A & B) | C`."
)

WhereExpr = Union[
    "CompareExpr",
    "AndExpr",
    "OrExpr",
    "NotExpr",
    "PropertyPathCompare",
    "IriStrCompare",
]


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
    field_name: _builtins.str
    path: tuple[_builtins.str, ...] = ()

    def __getattr__(self, name: _builtins.str) -> FieldRef:
        if name.startswith("_"):
            raise AttributeError(name)
        return FieldRef(self.model_cls, name, self.path + (self.field_name,))

    def _compare(self, op: CompareOp, other: object) -> CompareExpr:
        return CompareExpr(self, op, other)

    def str(self) -> IriStrFieldRef:
        """IRI field compared via ``STR(?)`` (after path hops)."""
        return IriStrFieldRef(self, mode="str")

    def lower(self) -> IriStrFieldRef:
        """Case-insensitive compare via ``LCASE(STR(?))``."""
        return IriStrFieldRef(self, mode="lower")

    def upper(self) -> IriStrFieldRef:
        """Compare via ``UCASE(STR(?))``."""
        return IriStrFieldRef(self, mode="upper")

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
        return CompareExpr(self, CompareOp.IS_, value)

    def is_not(self, value: object) -> CompareExpr:
        if value is not None:
            raise QueryError(
                "is_not() only supports None for nullable relationship presence checks"
            )
        return CompareExpr(self, CompareOp.IS_NOT, value)


@dataclass(frozen=True)
class IriStrFieldRef:
    """IRI field with SPARQL string function wrapper."""

    field: FieldRef
    mode: str  # str, lower, upper

    def _compare(self, op: CompareOp, other: object) -> IriStrCompare:
        return IriStrCompare(self, op, other)

    def __eq__(self, other: object) -> IriStrCompare:  # ty: ignore[invalid-method-override]
        return self._compare(CompareOp.EQ, other)

    def __ne__(self, other: object) -> IriStrCompare:  # ty: ignore[invalid-method-override]
        return self._compare(CompareOp.NE, other)

    def in_(self, values: tuple[object, ...] | Sequence[object]) -> IriStrCompare:
        if isinstance(values, str):
            raise QueryError("in_() does not accept a bare string on IRI string filters")
        seq = values if isinstance(values, tuple) else tuple(values)
        return IriStrCompare(self, CompareOp.IN, seq)


@dataclass(frozen=True)
class IriStrCompare:
    """Compare ``STR`` / ``LCASE`` / ``UCASE`` of an IRI binding."""

    left: IriStrFieldRef
    op: CompareOp
    right: object


@dataclass(frozen=True)
class PropertyPathCompare:
    """Filter using a SPARQL property path (escape hatch for ``^``, ``+``, ``*``)."""

    model_cls: type[SPARQLModel]
    sparql_path: str
    op: CompareOp
    right: object


@dataclass(frozen=True)
class CompareExpr:
    """Comparison expression for query filtering."""

    left: FieldRef
    op: CompareOp
    right: object

    def __and__(self, other: WhereExpr) -> AndExpr:
        if isinstance(other, OrExpr):
            raise QueryError(_OR_AND_MSG)
        if isinstance(other, AndExpr):
            return AndExpr((self,) + other.expressions)
        return AndExpr((self, other))

    def __or__(self, other: CompareExpr | OrExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr((self,) + other.expressions)
        return OrExpr((self, other))

    def __invert__(self) -> NotExpr:
        return NotExpr(self)


@dataclass(frozen=True)
class NotExpr:
    """Boolean NOT of a filter expression."""

    inner: WhereExpr

    def __invert__(self) -> WhereExpr:
        return self.inner


@dataclass(frozen=True)
class AndExpr:
    """AND combination of comparison expressions."""

    expressions: tuple[WhereExpr, ...]

    def __and__(self, other: WhereExpr) -> AndExpr:
        if isinstance(other, OrExpr):
            raise QueryError(_OR_AND_MSG)
        if isinstance(other, AndExpr):
            return AndExpr(self.expressions + other.expressions)
        return AndExpr(self.expressions + (other,))

    def __or__(self, other: CompareExpr | OrExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr((self,) + other.expressions)
        return OrExpr((self, other))

    def __invert__(self) -> NotExpr:
        return NotExpr(self)


def _flatten_and_parts(parts: tuple[WhereExpr, ...]) -> tuple[CompareExpr, ...]:
    """Flatten nested ``AndExpr`` nodes into comparisons only."""
    out: list[CompareExpr] = []
    for part in parts:
        if isinstance(part, AndExpr):
            for child in part.expressions:
                if isinstance(child, AndExpr):
                    out.extend(_flatten_and_parts(child.expressions))
                elif isinstance(child, CompareExpr):
                    out.append(child)
                else:
                    raise QueryError(
                        f"AND branch may only contain comparisons, not {type(child).__name__}"
                    )
        elif isinstance(part, CompareExpr):
            out.append(part)
    return tuple(out)


@dataclass(frozen=True)
class OrExpr:
    """OR combination of comparison or AND expressions."""

    expressions: tuple[WhereExpr, ...]

    def __and__(self, other: CompareExpr | AndExpr) -> AndExpr:
        raise QueryError(_OR_AND_MSG)

    def __rand__(self, other: CompareExpr | AndExpr) -> AndExpr:
        raise QueryError(_OR_AND_MSG)

    def __or__(self, other: WhereExpr) -> OrExpr:
        if isinstance(other, OrExpr):
            return OrExpr(self.expressions + other.expressions)
        return OrExpr(self.expressions + (other,))

    def __invert__(self) -> NotExpr:
        return NotExpr(self)


def not_(expr: WhereExpr) -> NotExpr:
    """Negate a filter expression (SPARQL ``FILTER NOT EXISTS`` / boolean NOT)."""
    return NotExpr(expr)


def property_path(
    model_cls: type[SPARQLModel],
    path: str,
    op: CompareOp,
    value: object,
) -> PropertyPathCompare:
    """Build a property-path filter (path uses ``/``, ``^``, ``*``, ``+`` as in SPARQL)."""
    return PropertyPathCompare(model_cls, path, op, value)


def property_eq(model_cls: type[SPARQLModel], path: str, value: object) -> PropertyPathCompare:
    """``property_path`` shorthand for equality."""
    return property_path(model_cls, path, CompareOp.EQ, value)
