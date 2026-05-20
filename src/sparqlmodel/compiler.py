"""ORM filter expressions → SPARQL WHERE clauses."""

from __future__ import annotations

import math
from typing import Any, get_args, get_origin

from sparqlmodel.exceptions import ConfigurationError, QueryError
from sparqlmodel.expressions import AndExpr, CompareExpr, CompareOp, FieldRef, OrExpr
from sparqlmodel.fields import get_field_metadata
from sparqlmodel.model import SPARQLModel
from sparqlmodel.rdf_n3 import term_to_n3, validate_iri_token
from sparqlmodel.sparql_escape import escape_sparql_string
from sparqlmodel.types import IRI, NamespaceRegistry, expand_iri, is_absolute_iri, is_compact_iri

_XSD_INTEGER = "http://www.w3.org/2001/XMLSchema#integer"
_XSD_DOUBLE = "http://www.w3.org/2001/XMLSchema#double"


def _model_var_name(model_cls: type[SPARQLModel]) -> str:
    return f"?{model_cls.__name__.lower()}"


def _annotation_expects_iri(annotation: Any) -> bool:
    if annotation is IRI:
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    return any(arg is IRI for arg in get_args(annotation))


def _format_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f'"{value}"^^{term_to_n3(_XSD_INTEGER)}'
    if isinstance(value, float):
        if not math.isfinite(value):
            raise QueryError(f"Non-finite float cannot be used in SPARQL filter: {value!r}")
        return f'"{value}"^^{term_to_n3(_XSD_DOUBLE)}'
    return f'"{escape_sparql_string(str(value))}"'


def _format_iri(iri: str) -> str:
    return term_to_n3(validate_iri_token(iri))


def _format_object(
    value: object,
    registry: NamespaceRegistry,
    *,
    field_annotation: Any = None,
) -> str:
    if isinstance(value, IRI):
        expanded = registry.expand(str(value))
        return _format_iri(expanded)
    if isinstance(value, str) and _annotation_expects_iri(field_annotation):
        if is_absolute_iri(value):
            return _format_iri(value)
        if is_compact_iri(value):
            try:
                expanded = registry.expand(value)
            except ConfigurationError:
                return _format_literal(value)
            return _format_iri(expanded)
    return _format_literal(value)


def _flatten_and_expressions(
    expressions: tuple[CompareExpr | AndExpr | OrExpr, ...],
) -> list[CompareExpr]:
    """Flatten ``AndExpr`` trees into a list of ``CompareExpr``."""
    flat: list[CompareExpr] = []
    for expr in expressions:
        if isinstance(expr, AndExpr):
            for child in expr.expressions:
                if isinstance(child, AndExpr):
                    flat.extend(_flatten_and_expressions((child,)))
                elif isinstance(child, CompareExpr):
                    flat.append(child)
                else:
                    raise QueryError(f"Unsupported expression type in AND: {type(child).__name__}")
        elif isinstance(expr, CompareExpr):
            flat.append(expr)
        elif isinstance(expr, OrExpr):
            raise QueryError("OR expressions must be top-level or nested inside OR, not AND")
        else:
            raise QueryError(f"Unsupported WHERE expression type: {type(expr).__name__}")
    return flat


def _flatten_or_expressions(expr: OrExpr) -> list[CompareExpr | AndExpr]:
    """Flatten nested ``OrExpr`` into disjunct branches."""
    flat: list[CompareExpr | AndExpr] = []
    for child in expr.expressions:
        if isinstance(child, OrExpr):
            flat.extend(_flatten_or_expressions(child))
        elif isinstance(child, (CompareExpr, AndExpr)):
            flat.append(child)
        else:
            raise QueryError(f"Unsupported expression type in OR: {type(child).__name__}")
    return flat


def _follow_path(
    model_cls: type[SPARQLModel],
    path: tuple[str, ...],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
) -> tuple[type[SPARQLModel], str, list[str]]:
    """Walk relationship path; return target model, final variable, patterns."""
    patterns: list[str] = []
    current_cls = model_cls
    current_var = root_var

    for index, segment in enumerate(path):
        partial = path[: index + 1]
        cached = join_cache.get(partial)
        if cached is not None:
            current_var, current_cls = cached
            continue
        rel_map = {n: (fi, rc) for n, fi, rc in current_cls.get_relationship_fields()}
        if segment not in rel_map:
            raise QueryError(f"Unknown relationship field '{segment}' on {current_cls.__name__}")
        field_info, related_cls = rel_map[segment]
        meta = get_field_metadata(field_info)
        if meta is None:
            raise QueryError(f"Field '{segment}' has no SPARQL metadata")
        join_counter[0] += 1
        join_var = f"?__join_{join_counter[0]}"
        pred_expanded = validate_iri_token(expand_iri(meta.predicate, registry.prefixes))
        patterns.append(f"{current_var} <{pred_expanded}> {join_var} .")
        type_expanded = validate_iri_token(expand_iri(related_cls.rdf_type, registry.prefixes))
        patterns.append(f"{join_var} a <{type_expanded}> .")
        current_cls = related_cls
        current_var = join_var
        join_cache[partial] = (current_var, current_cls)

    return current_cls, current_var, patterns


def _resolve_compare_target(
    left: FieldRef,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
) -> tuple[type[SPARQLModel], str, list[str], Any, str]:
    if not isinstance(left, FieldRef):
        raise QueryError("Expected FieldRef on left side of comparison")

    path = left.path
    field_name = left.field_name

    if left.model_cls is not model_cls:
        raise QueryError(
            f"Filter field {left.model_cls.__name__}.{left.field_name} does not match "
            f"query model {model_cls.__name__}"
        )

    patterns: list[str] = []
    if path:
        target_model, subject_var, path_patterns = _follow_path(
            model_cls, path, root_var, registry, join_counter, join_cache
        )
        patterns.extend(path_patterns)
    else:
        target_model = model_cls
        subject_var = root_var

    scalar_map = {n: fi for n, fi in target_model.get_scalar_fields()}
    if field_name not in scalar_map:
        raise QueryError(f"Unknown or non-scalar field '{field_name}' on {target_model.__name__}")

    field_info = scalar_map[field_name]
    meta = get_field_metadata(field_info)
    if meta is None:
        raise QueryError(f"Field '{field_name}' has no SPARQL metadata")

    return target_model, subject_var, patterns, field_info, field_name


def _exists_block(patterns: list[str], filters: list[str]) -> str:
    body = "\n        ".join(patterns)
    if filters:
        filter_lines = "\n        ".join(f"FILTER({f})" for f in filters)
        body = f"{body}\n        {filter_lines}"
    return f"EXISTS {{ {body} }}"


def compile_compare(
    expr: CompareExpr,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
    *,
    use_not_exists_for_ne: bool = True,
) -> tuple[list[str], list[str]]:
    """Compile a comparison; return (patterns, filters)."""
    if isinstance(expr.right, FieldRef):
        raise QueryError(
            "Cannot compare a field to another field; compare to a literal or IRI value"
        )
    if expr.right is None and expr.op != CompareOp.IN:
        raise QueryError("Filter value cannot be None; use explicit existence checks")

    if expr.op == CompareOp.IN and isinstance(expr.right, tuple):
        if len(expr.right) == 0:
            raise QueryError("IN filter requires a non-empty tuple of values")
        for item in expr.right:
            if item is None:
                raise QueryError("IN filter values cannot be None")

    _, subject_var, path_patterns, field_info, field_name = _resolve_compare_target(
        expr.left, model_cls, root_var, registry, join_counter, join_cache
    )

    patterns: list[str] = list(path_patterns)
    filters: list[str] = []

    meta = get_field_metadata(field_info)
    assert meta is not None
    pred_expanded = validate_iri_token(expand_iri(meta.predicate, registry.prefixes))

    if expr.op == CompareOp.IN:
        in_var = f"?__in_{field_name}_{id(expr)}"
        patterns.append(f"{subject_var} <{pred_expanded}> {in_var} .")
        if not isinstance(expr.right, tuple):
            raise QueryError("IN comparison requires a tuple or sequence of values")
        formatted = [
            _format_object(v, registry, field_annotation=field_info.annotation) for v in expr.right
        ]
        filters.append(f"{in_var} IN ({', '.join(formatted)})")
        return patterns, filters

    obj = _format_object(expr.right, registry, field_annotation=field_info.annotation)

    if expr.op == CompareOp.EQ:
        patterns.append(f"{subject_var} <{pred_expanded}> {obj} .")
    elif expr.op == CompareOp.NE:
        if use_not_exists_for_ne:
            ne_var = f"?__ne_{id(expr)}"
            inner = f"{subject_var} <{pred_expanded}> {ne_var} .\n        FILTER({ne_var} = {obj})"
            filters.append(f"NOT EXISTS {{ {inner} }}")
        else:
            neq_var = f"?__neq_{field_name}_{id(expr)}"
            patterns.append(f"{subject_var} <{pred_expanded}> {neq_var} .")
            filters.append(f"{neq_var} != {obj}")
    elif expr.op in (CompareOp.LT, CompareOp.GT, CompareOp.LTE, CompareOp.GTE):
        cmp_var = f"?__cmp_{field_name}_{id(expr)}"
        patterns.append(f"{subject_var} <{pred_expanded}> {cmp_var} .")
        op_map = {
            CompareOp.LT: "<",
            CompareOp.GT: ">",
            CompareOp.LTE: "<=",
            CompareOp.GTE: ">=",
        }
        filters.append(f"{cmp_var} {op_map[expr.op]} {obj}")
    else:
        raise QueryError(f"Unsupported comparison operator: {expr.op}")

    return patterns, filters


def compile_and_branch(
    expr: AndExpr,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    *,
    use_not_exists_for_ne: bool = True,
) -> str:
    """Compile an AND branch inside OR as a single EXISTS block."""
    compares = _flatten_and_expressions((expr,))
    patterns: list[str] = []
    filters: list[str] = []
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]] = {}
    for compare in compares:
        pats, filts = compile_compare(
            compare,
            model_cls,
            root_var,
            registry,
            join_counter,
            join_cache,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
        patterns.extend(pats)
        filters.extend(filts)
    return _exists_block(patterns, filters)


def compile_or(
    expr: OrExpr,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    *,
    use_not_exists_for_ne: bool = True,
) -> list[str]:
    """Compile OR into a FILTER with EXISTS disjunction."""
    branches = _flatten_or_expressions(expr)
    if not branches:
        raise QueryError("OR expression must have at least one branch")

    exists_parts: list[str] = []
    for branch in branches:
        branch_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]] = {}
        if isinstance(branch, CompareExpr):
            pats, filts = compile_compare(
                branch,
                model_cls,
                root_var,
                registry,
                join_counter,
                branch_cache,
                use_not_exists_for_ne=use_not_exists_for_ne,
            )
            exists_parts.append(_exists_block(pats, filts))
        elif isinstance(branch, AndExpr):
            exists_parts.append(
                compile_and_branch(
                    branch,
                    model_cls,
                    root_var,
                    registry,
                    join_counter,
                    use_not_exists_for_ne=use_not_exists_for_ne,
                )
            )
        else:
            raise QueryError(f"Unsupported OR branch type: {type(branch).__name__}")

    if len(exists_parts) == 1:
        return [f"FILTER({exists_parts[0]})"]
    disjunction = " || ".join(exists_parts)
    return [f"FILTER({disjunction})"]


def compile_where(
    model_cls: type[SPARQLModel],
    expressions: tuple[CompareExpr | AndExpr | OrExpr, ...],
    registry: NamespaceRegistry,
    *,
    limit: int | None = None,
    use_not_exists_for_ne: bool = True,
) -> str:
    """Compile WHERE expressions into a full SELECT SPARQL query."""
    root_var = _model_var_name(model_cls)
    type_expanded = validate_iri_token(expand_iri(model_cls.rdf_type, registry.prefixes))

    all_patterns: list[str] = [f"{root_var} a <{type_expanded}> ."]
    all_filters: list[str] = []

    join_counter = [0]
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]] = {}

    and_exprs: list[CompareExpr | AndExpr] = []
    or_exprs: list[OrExpr] = []
    for expr in expressions:
        if isinstance(expr, OrExpr):
            or_exprs.append(expr)
        elif isinstance(expr, (CompareExpr, AndExpr)):
            and_exprs.append(expr)
        else:
            raise QueryError(f"Unsupported WHERE expression type: {type(expr).__name__}")

    flat_and = _flatten_and_expressions(tuple(and_exprs))
    for compare in flat_and:
        pats, filts = compile_compare(
            compare,
            model_cls,
            root_var,
            registry,
            join_counter,
            join_cache,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
        all_patterns.extend(pats)
        all_filters.extend(filts)

    for or_expr in or_exprs:
        all_filters.extend(
            compile_or(
                or_expr,
                model_cls,
                root_var,
                registry,
                join_counter,
                use_not_exists_for_ne=use_not_exists_for_ne,
            )
        )

    where_body = "\n    ".join(all_patterns)
    if all_filters:
        filter_lines = "\n    ".join(
            f if f.startswith("FILTER(") else f"FILTER({f})" for f in all_filters
        )
        where_clause = f"{where_body}\n    {filter_lines}"
    else:
        where_clause = where_body

    if limit is not None and limit < 0:
        raise QueryError("limit must be non-negative")
    limit_clause = f"\nLIMIT {limit}" if limit is not None else ""
    prefixes = registry.sparql_prefixes()
    prefix_block = f"{prefixes}\n\n" if prefixes else ""

    return (
        f"{prefix_block}SELECT DISTINCT {root_var} WHERE {{\n    {where_clause}\n}}{limit_clause}"
    )
