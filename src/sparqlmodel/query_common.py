"""Shared query-builder state for sync and async queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, CompareExpr, FieldRef, OrExpr
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import NamespaceRegistry

COUNT_BINDING_KEYS = ("__count", "?__count")
_NOT_PROVIDED = object()


def _resolve_pagination(
    value: int | None | object,
    state_value: int | None,
) -> int | None:
    if value is _NOT_PROVIDED:
        return state_value
    return cast(int | None, value)


@dataclass
class QueryState:
    model_cls: type[SPARQLModel]
    expressions: list[CompareExpr | AndExpr | OrExpr] = field(default_factory=list)
    limit: int | None = None
    offset: int | None = None
    order_by: list[tuple[FieldRef, bool]] = field(default_factory=list)
    use_not_exists_for_ne: bool = True
    use_inequality_for_ne: bool = False
    use_optional_for_comparisons: bool = False

    def compile(
        self,
        namespaces: NamespaceRegistry,
        *,
        limit: int | None | object = _NOT_PROVIDED,
        offset: int | None | object = _NOT_PROVIDED,
        count: bool = False,
    ) -> str:
        merged = {**namespaces.prefixes, **self.model_cls.get_prefixes()}
        reg = NamespaceRegistry(merged)
        effective_limit = _resolve_pagination(limit, self.limit)
        effective_offset = _resolve_pagination(offset, self.offset)
        if count:
            effective_limit = None
            effective_offset = None
        return compile_where(
            self.model_cls,
            tuple(self.expressions),
            reg,
            limit=effective_limit,
            offset=effective_offset,
            order_by=tuple(self.order_by),
            count=count,
            use_not_exists_for_ne=self.use_not_exists_for_ne,
        )


def parse_count_bindings(bindings: list[dict[str, Any]]) -> int:
    """Extract integer count from a COUNT query binding row."""
    if not bindings:
        return 0
    row = bindings[0]
    for key in COUNT_BINDING_KEYS:
        if key in row:
            value = row[key]
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                return int(value)
            raise QueryError(f"Unsupported COUNT binding type: {type(value).__name__}")
    raise QueryError("COUNT query did not return ?__count binding")


def apply_where(state: QueryState, *expressions: CompareExpr | AndExpr | OrExpr) -> None:
    state.expressions.extend(expressions)


def apply_limit(state: QueryState, n: int) -> None:
    if n < 0:
        raise QueryError("limit must be non-negative")
    state.limit = n


def apply_offset(state: QueryState, n: int) -> None:
    if n < 0:
        raise QueryError("offset must be non-negative")
    state.offset = n


def apply_order_by(state: QueryState, field: FieldRef, *, desc: bool = False) -> None:
    state.order_by.append((field, desc))


def apply_use_not_exists_for_ne(state: QueryState, enabled: bool) -> None:
    state.use_not_exists_for_ne = enabled
    if enabled:
        state.use_inequality_for_ne = False


def apply_use_inequality_for_ne(state: QueryState, enabled: bool) -> None:
    state.use_inequality_for_ne = enabled
    if enabled:
        state.use_not_exists_for_ne = False
    else:
        state.use_not_exists_for_ne = True


def apply_use_optional_for_comparisons(state: QueryState, enabled: bool) -> None:
    state.use_optional_for_comparisons = enabled
    if enabled:
        state.use_not_exists_for_ne = True
        state.use_inequality_for_ne = False
    elif not state.use_inequality_for_ne:
        state.use_not_exists_for_ne = True
