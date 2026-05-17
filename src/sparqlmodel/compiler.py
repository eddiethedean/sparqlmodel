"""Python expression → SPARQL compiler."""

from __future__ import annotations

from rdflib import Literal

from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, CompareExpr, CompareOp
from sparqlmodel.fields import get_field_metadata
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import IRI, NamespaceRegistry, expand_iri, is_compact_iri


def _model_var_name(model_cls: type[SPARQLModel]) -> str:
    return f"?{model_cls.__name__.lower()}"


def _format_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return Literal(str(value)).n3()


def _format_iri(iri: str) -> str:
    if not iri or any(c in iri for c in " \n\r\t<>"):
        raise QueryError(f"Invalid IRI for SPARQL: {iri!r}")
    return f"<{iri}>"


def _format_object(value: object, registry: NamespaceRegistry) -> str:
    if isinstance(value, IRI):
        expanded = registry.expand(str(value))
        return _format_iri(expanded)
    if isinstance(value, str) and value.startswith(("http://", "https://", "urn:")):
        return _format_iri(value)
    if isinstance(value, str) and is_compact_iri(value):
        expanded = registry.expand(value)
        return _format_iri(expanded)
    return _format_literal(value)


def _flatten_expressions(
    expressions: tuple[CompareExpr | AndExpr, ...],
) -> list[CompareExpr]:
    """Flatten ``AndExpr`` trees into a list of ``CompareExpr``."""
    flat: list[CompareExpr] = []
    for expr in expressions:
        if isinstance(expr, AndExpr):
            for child in expr.expressions:
                if isinstance(child, AndExpr):
                    flat.extend(_flatten_expressions((child,)))
                elif isinstance(child, CompareExpr):
                    flat.append(child)
                else:
                    raise QueryError(f"Unsupported expression type in AND: {type(child).__name__}")
        elif isinstance(expr, CompareExpr):
            flat.append(expr)
        else:
            raise QueryError(f"Unsupported WHERE expression type: {type(expr).__name__}")
    return flat


def _follow_path(
    model_cls: type[SPARQLModel],
    path: tuple[str, ...],
    root_var: str,
    registry: NamespaceRegistry,
) -> tuple[type[SPARQLModel], str, list[str]]:
    """Walk relationship path; return target model, final variable, patterns."""
    patterns: list[str] = []
    current_cls = model_cls
    current_var = root_var

    for i, segment in enumerate(path):
        rel_map = {n: (fi, rc) for n, fi, rc in current_cls.get_relationship_fields()}
        if segment not in rel_map:
            raise QueryError(f"Unknown relationship field '{segment}' on {current_cls.__name__}")
        field_info, related_cls = rel_map[segment]
        meta = get_field_metadata(field_info)
        if meta is None:
            raise QueryError(f"Field '{segment}' has no SPARQL metadata")
        join_var = f"?{segment}{i}"
        pred_expanded = expand_iri(meta.predicate, registry.prefixes)
        patterns.append(f"{current_var} <{pred_expanded}> {join_var} .")
        type_expanded = expand_iri(related_cls.rdf_type, registry.prefixes)
        patterns.append(f"{join_var} a <{type_expanded}> .")
        current_cls = related_cls
        current_var = join_var

    return current_cls, current_var, patterns


def compile_compare(
    expr: CompareExpr,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
) -> tuple[list[str], list[str]]:
    """Compile a comparison; return (patterns, filters)."""
    if expr.right is None:
        raise QueryError("Filter value cannot be None; use explicit existence checks")

    left = expr.left
    path = left.path
    field_name = left.field_name

    patterns: list[str] = []
    filters: list[str] = []

    if path:
        target_model, subject_var, path_patterns = _follow_path(model_cls, path, root_var, registry)
        patterns.extend(path_patterns)
    else:
        target_model = model_cls
        subject_var = root_var

    scalar_map = {n: fi for n, fi in target_model.get_scalar_fields()}
    if field_name not in scalar_map:
        raise QueryError(f"Unknown or non-scalar field '{field_name}' on {target_model.__name__}")

    meta = get_field_metadata(scalar_map[field_name])
    if meta is None:
        raise QueryError(f"Field '{field_name}' has no SPARQL metadata")

    pred_expanded = expand_iri(meta.predicate, registry.prefixes)
    obj = _format_object(expr.right, registry)

    if expr.op == CompareOp.EQ:
        patterns.append(f"{subject_var} <{pred_expanded}> {obj} .")
    else:
        neq_var = f"?__neq_{field_name}_{id(expr)}"
        patterns.append(f"{subject_var} <{pred_expanded}> {neq_var} .")
        filters.append(f"{neq_var} != {obj}")

    return patterns, filters


def compile_where(
    model_cls: type[SPARQLModel],
    expressions: tuple[CompareExpr | AndExpr, ...],
    registry: NamespaceRegistry,
    *,
    limit: int | None = None,
) -> str:
    """Compile WHERE expressions into a full SELECT SPARQL query."""
    root_var = _model_var_name(model_cls)
    type_expanded = expand_iri(model_cls.rdf_type, registry.prefixes)

    all_patterns: list[str] = [f"{root_var} a <{type_expanded}> ."]
    all_filters: list[str] = []

    flat_exprs = _flatten_expressions(expressions)

    for compare in flat_exprs:
        pats, filts = compile_compare(compare, model_cls, root_var, registry)
        all_patterns.extend(pats)
        all_filters.extend(filts)

    where_body = "\n    ".join(all_patterns)
    if all_filters:
        filter_lines = "\n    ".join(f"FILTER({f})" for f in all_filters)
        where_clause = f"{where_body}\n    {filter_lines}"
    else:
        where_clause = where_body

    limit_clause = f"\nLIMIT {limit}" if limit is not None else ""
    prefixes = registry.sparql_prefixes()
    prefix_block = f"{prefixes}\n\n" if prefixes else ""

    return (
        f"{prefix_block}SELECT DISTINCT {root_var} WHERE {{\n    {where_clause}\n}}{limit_clause}"
    )
