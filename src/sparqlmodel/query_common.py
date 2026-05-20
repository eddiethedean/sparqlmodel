"""Shared query-builder state for sync and async queries."""

from __future__ import annotations

from dataclasses import dataclass, field

from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, CompareExpr, OrExpr
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import NamespaceRegistry


@dataclass
class QueryState:
    model_cls: type[SPARQLModel]
    expressions: list[CompareExpr | AndExpr | OrExpr] = field(default_factory=list)
    limit: int | None = None
    use_not_exists_for_ne: bool = True
    use_inequality_for_ne: bool = False
    use_optional_for_comparisons: bool = False

    def compile(
        self,
        namespaces: NamespaceRegistry,
        *,
        limit: int | None = None,
    ) -> str:
        merged = {**namespaces.prefixes, **self.model_cls.get_prefixes()}
        reg = NamespaceRegistry(merged)
        effective_limit = self.limit if limit is None else limit
        return compile_where(
            self.model_cls,
            tuple(self.expressions),
            reg,
            limit=effective_limit,
            use_not_exists_for_ne=self.use_not_exists_for_ne,
        )


def apply_where(state: QueryState, *expressions: CompareExpr | AndExpr | OrExpr) -> None:
    state.expressions.extend(expressions)


def apply_limit(state: QueryState, n: int) -> None:
    if n < 0:
        raise QueryError("limit must be non-negative")
    state.limit = n


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
