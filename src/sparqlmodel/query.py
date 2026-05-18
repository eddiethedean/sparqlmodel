"""ORM query builder; compiles Python filters to SPARQL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, CompareExpr
from sparqlmodel.hydration import hydrate_from_bindings, validate_depth
from sparqlmodel.model import SPARQLModel

if TYPE_CHECKING:
    from sparqlmodel.session import SPARQLSession


class Query:
    """ORM query builder for a :class:`~sparqlmodel.model.SPARQLModel` class."""

    def __init__(
        self,
        session: SPARQLSession,
        model_cls: type[SPARQLModel],
    ) -> None:
        self._session = session
        self._model_cls = model_cls
        self._expressions: list[CompareExpr | AndExpr] = []
        self._limit: int | None = None

    def where(self, *expressions: CompareExpr | AndExpr) -> Query:
        """Add WHERE filter expressions."""
        self._expressions.extend(expressions)
        return self

    def limit(self, n: int) -> Query:
        """Limit the number of results."""
        if n < 0:
            raise QueryError("limit must be non-negative")
        self._limit = n
        return self

    def _compile(self) -> str:
        registry = self._session.namespaces
        merged = {**registry.prefixes, **self._model_cls.get_prefixes()}
        from sparqlmodel.types import NamespaceRegistry

        reg = NamespaceRegistry(merged)
        return compile_where(
            self._model_cls,
            tuple(self._expressions),
            reg,
            limit=self._limit,
        )

    def all(self, *, depth: int = 0) -> list[SPARQLModel]:
        """Execute query and return all matching models."""
        validate_depth(depth)
        sparql = self._compile()
        bindings = self._session.execute(sparql)
        return hydrate_from_bindings(
            self._model_cls,
            bindings,
            self._session.store,
            depth=depth,
        )

    def first(self, *, depth: int = 0) -> SPARQLModel | None:
        """Return the first matching model or None."""
        validate_depth(depth)
        original_limit = self._limit
        self._limit = 1
        try:
            sparql = self._compile()
            bindings = self._session.execute(sparql)
            results = hydrate_from_bindings(
                self._model_cls,
                bindings,
                self._session.store,
                depth=depth,
            )
        finally:
            self._limit = original_limit
        return results[0] if results else None
