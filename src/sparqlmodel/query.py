"""ORM query builder; compiles Python filters to SPARQL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sparqlmodel.compiler import compile_where
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, CompareExpr, OrExpr
from sparqlmodel.hydration import validate_depth
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
        self._expressions: list[CompareExpr | AndExpr | OrExpr] = []
        self._limit: int | None = None
        self._use_not_exists_for_ne = True
        self._use_inequality_for_ne = False
        self._use_optional_for_comparisons = False

    def where(self, *expressions: CompareExpr | AndExpr | OrExpr) -> Query:
        """Add WHERE filter expressions."""
        self._expressions.extend(expressions)
        return self

    def use_not_exists_for_ne(self, enabled: bool = True) -> Query:
        """Compile ``!=`` filters with ``FILTER NOT EXISTS`` (default since 0.5.2)."""
        self._use_not_exists_for_ne = enabled
        if enabled:
            self._use_inequality_for_ne = False
        return self

    def use_inequality_for_ne(self, enabled: bool = True) -> Query:
        """Compile ``!=`` with inequality (pre-0.5.2 default; excludes unbound values)."""
        self._use_inequality_for_ne = enabled
        if enabled:
            self._use_not_exists_for_ne = False
        else:
            self._use_not_exists_for_ne = True
        return self

    def use_optional_for_comparisons(self, enabled: bool = True) -> Query:
        """Treat missing predicates like SQL NULL for ``!=`` (via ``FILTER NOT EXISTS``).

        Despite the name, this does not emit SPARQL ``OPTIONAL`` blocks; it enables
        NOT EXISTS semantics for ``!=`` so resources with no value for the field match.
        Ordering (``<``, ``>``, …) and ``in_`` still require a bound predicate value.
        Disabling restores the default NOT EXISTS mode unless
        :meth:`use_inequality_for_ne` was set.
        """
        self._use_optional_for_comparisons = enabled
        if enabled:
            self._use_not_exists_for_ne = True
            self._use_inequality_for_ne = False
        elif not self._use_inequality_for_ne:
            self._use_not_exists_for_ne = True
        return self

    def limit(self, n: int) -> Query:
        """Limit the number of results."""
        if n < 0:
            raise QueryError("limit must be non-negative")
        self._limit = n
        return self

    def _compile(self, *, limit: int | None = None) -> str:
        registry = self._session.namespaces
        merged = {**registry.prefixes, **self._model_cls.get_prefixes()}
        from sparqlmodel.types import NamespaceRegistry

        reg = NamespaceRegistry(merged)
        effective_limit = self._limit if limit is None else limit
        return compile_where(
            self._model_cls,
            tuple(self._expressions),
            reg,
            limit=effective_limit,
            use_not_exists_for_ne=self._use_not_exists_for_ne,
        )

    def all(self, *, depth: int = 0) -> list[SPARQLModel]:
        """Execute query and return all matching models."""
        validate_depth(depth)
        sparql = self._compile()
        bindings = self._session.execute(sparql)
        return self._session.hydrate_bindings(
            self._model_cls,
            bindings,
            depth=depth,
        )

    def first(self, *, depth: int = 0) -> SPARQLModel | None:
        """Return the first matching model or None."""
        validate_depth(depth)
        sparql = self._compile(limit=1)
        bindings = self._session.execute(sparql)
        results = self._session.hydrate_bindings(
            self._model_cls,
            bindings,
            depth=depth,
        )
        return results[0] if results else None
