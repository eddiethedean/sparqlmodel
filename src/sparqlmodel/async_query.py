"""Async ORM query builder; compiles Python filters to SPARQL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sparqlmodel.expressions import AndExpr, CompareExpr, OrExpr
from sparqlmodel.hydration import validate_depth
from sparqlmodel.model import SPARQLModel
from sparqlmodel.query_common import (
    QueryState,
    apply_limit,
    apply_use_inequality_for_ne,
    apply_use_not_exists_for_ne,
    apply_use_optional_for_comparisons,
    apply_where,
)

if TYPE_CHECKING:
    from sparqlmodel.async_session import AsyncSPARQLSession


class AsyncQuery:
    """Async ORM query builder for a :class:`~sparqlmodel.model.SPARQLModel` class."""

    def __init__(
        self,
        session: AsyncSPARQLSession,
        model_cls: type[SPARQLModel],
    ) -> None:
        self._session = session
        self._state = QueryState(model_cls=model_cls)

    def where(self, *expressions: CompareExpr | AndExpr | OrExpr) -> AsyncQuery:
        apply_where(self._state, *expressions)
        return self

    def use_not_exists_for_ne(self, enabled: bool = True) -> AsyncQuery:
        apply_use_not_exists_for_ne(self._state, enabled)
        return self

    def use_inequality_for_ne(self, enabled: bool = True) -> AsyncQuery:
        apply_use_inequality_for_ne(self._state, enabled)
        return self

    def use_optional_for_comparisons(self, enabled: bool = True) -> AsyncQuery:
        apply_use_optional_for_comparisons(self._state, enabled)
        return self

    def limit(self, n: int) -> AsyncQuery:
        apply_limit(self._state, n)
        return self

    def _compile(self, *, limit: int | None = None) -> str:
        return self._state.compile(self._session.namespaces, limit=limit)

    async def all(self, *, depth: int = 0) -> list[SPARQLModel]:
        validate_depth(depth)
        sparql = self._state.compile(self._session.namespaces)
        bindings = await self._session.execute(sparql)
        return await self._session.hydrate_bindings(
            self._state.model_cls,
            bindings,
            depth=depth,
        )

    async def first(self, *, depth: int = 0) -> SPARQLModel | None:
        validate_depth(depth)
        sparql = self._state.compile(self._session.namespaces, limit=1)
        bindings = await self._session.execute(sparql)
        results = await self._session.hydrate_bindings(
            self._state.model_cls,
            bindings,
            depth=depth,
        )
        return results[0] if results else None
