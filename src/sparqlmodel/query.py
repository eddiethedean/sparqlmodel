"""ORM query builder; compiles Python filters to SPARQL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sparqlmodel.expressions import FieldRef, WhereExpr
from sparqlmodel.hydration import validate_depth
from sparqlmodel.model import SPARQLModel
from sparqlmodel.query_common import (
    QueryState,
    apply_limit,
    apply_offset,
    apply_order_by,
    apply_polymorphic,
    apply_use_inequality_for_ne,
    apply_use_not_exists_for_ne,
    apply_use_optional_for_comparisons,
    apply_values,
    apply_where,
    parse_count_bindings,
)

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
        self._state = QueryState(model_cls=model_cls)

    def where(self, *expressions: WhereExpr) -> Query:
        apply_where(self._state, *expressions)
        return self

    def polymorphic(self, enabled: bool = True) -> Query:
        """Include ``rdfs:subClassOf`` descendants of this model's ``rdf_type``."""
        apply_polymorphic(self._state, enabled)
        return self

    def values(self, **bindings: object) -> Query:
        """Add a VALUES binding row (IRI/literal values for SPARQL variables)."""
        apply_values(self._state, bindings)
        return self

    def use_not_exists_for_ne(self, enabled: bool = True) -> Query:
        apply_use_not_exists_for_ne(self._state, enabled)
        return self

    def use_inequality_for_ne(self, enabled: bool = True) -> Query:
        apply_use_inequality_for_ne(self._state, enabled)
        return self

    def use_optional_for_comparisons(self, enabled: bool = True) -> Query:
        apply_use_optional_for_comparisons(self._state, enabled)
        return self

    def limit(self, n: int) -> Query:
        apply_limit(self._state, n)
        return self

    def offset(self, n: int) -> Query:
        apply_offset(self._state, n)
        return self

    def order_by(self, field: FieldRef, *, desc: bool = False) -> Query:
        apply_order_by(self._state, field, desc=desc)
        return self

    def _compile(self, *, limit: int | None = None, offset: int | None = None) -> str:
        return self._state.compile(
            self._session.namespaces,
            limit=limit,
            offset=offset,
        )

    def count(self) -> int:
        sparql = self._state.compile(self._session.namespaces, count=True)
        bindings = self._session.execute(sparql)
        return parse_count_bindings(bindings)

    def all(self, *, depth: int = 0) -> list[SPARQLModel]:
        validate_depth(depth)
        sparql = self._state.compile(self._session.namespaces)
        bindings = self._session.execute(sparql)
        return self._session.hydrate_bindings(
            self._state.model_cls,
            bindings,
            depth=depth,
            polymorphic=self._state.polymorphic,
        )

    def first(self, *, depth: int = 0) -> SPARQLModel | None:
        validate_depth(depth)
        sparql = self._state.compile(self._session.namespaces, limit=1, offset=None)
        bindings = self._session.execute(sparql)
        results = self._session.hydrate_bindings(
            self._state.model_cls,
            bindings,
            depth=depth,
            polymorphic=self._state.polymorphic,
        )
        return results[0] if results else None
