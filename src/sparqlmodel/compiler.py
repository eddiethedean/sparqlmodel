"""ORM filter expressions → SPARQL WHERE clauses."""

from __future__ import annotations

import math
from typing import Any, get_args, get_origin

from sparqlmodel.exceptions import ConfigurationError, QueryError
from sparqlmodel.expressions import (
    AndExpr,
    CompareExpr,
    CompareOp,
    FieldRef,
    IriStrCompare,
    NotExpr,
    OrExpr,
    PropertyPathCompare,
    WhereExpr,
)
from sparqlmodel.fields import (
    field_cardinality_for,
    get_field_metadata,
    relationship_allows_iri,
    relationship_is_nullable,
)
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
    from triplemodel.terms.lang import LangString, MultiLangString
    from triplemodel.terms.typed_literal import TypedLiteral

    if isinstance(value, LangString):
        lang_part = f"@{value.lang}" if value.lang else ""
        return f'"{escape_sparql_string(str(value.value))}"{lang_part}'
    if isinstance(value, MultiLangString):
        first = next(iter(value.by_lang.values()), None)
        if first is None:
            return '""'
        if isinstance(first, LangString):
            return _format_object(first, registry, field_annotation=field_annotation)
        return _format_literal(str(first))
    if isinstance(value, TypedLiteral):
        if value.datatype:
            dt = validate_iri_token(expand_iri(value.datatype, registry.prefixes))
            return f'"{escape_sparql_string(str(value.value))}"^<{dt}>'
        return _format_literal(value.value)
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
    expressions: tuple[WhereExpr, ...],
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


def _optional_block(lines: list[str]) -> str:
    body = "\n    ".join(lines)
    return f"OPTIONAL {{\n    {body}\n    }}"


def _relationship_hop_patterns(
    current_var: str,
    join_var: str,
    predicate: str,
    related_cls: type[SPARQLModel],
    field_info: Any,
    registry: NamespaceRegistry,
) -> list[str]:
    """Edge patterns for one relationship hop; omit ``rdf:type`` when ``IRI`` refs are allowed."""
    pred_expanded = validate_iri_token(expand_iri(predicate, registry.prefixes))
    patterns = [f"{current_var} <{pred_expanded}> {join_var} ."]
    if not relationship_allows_iri(field_info.annotation):
        type_expanded = validate_iri_token(expand_iri(related_cls.rdf_type, registry.prefixes))
        patterns.append(f"{join_var} a <{type_expanded}> .")
    return patterns


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
        hop_patterns = _relationship_hop_patterns(
            current_var,
            join_var,
            meta.predicate,
            related_cls,
            field_info,
            registry,
        )
        if relationship_is_nullable(field_info.annotation):
            patterns.append(_optional_block(hop_patterns))
        else:
            patterns.extend(hop_patterns)
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
    rel_map = {n: fi for n, fi, _ in target_model.get_relationship_fields()}
    if field_name in scalar_map:
        field_info = scalar_map[field_name]
    elif field_name in rel_map:
        field_info = rel_map[field_name]
        if field_cardinality_for(field_info) not in ("list", "set"):
            raise QueryError(
                f"Field '{field_name}' on {target_model.__name__} is not a collection; "
                "use relationship navigation for scalar refs"
            )
    else:
        raise QueryError(f"Unknown field '{field_name}' on {target_model.__name__}")
    meta = get_field_metadata(field_info)
    if meta is None:
        raise QueryError(f"Field '{field_name}' has no SPARQL metadata")

    return target_model, subject_var, patterns, field_info, field_name


def _compile_relationship_presence(
    expr: CompareExpr,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
) -> tuple[list[str], list[str]]:
    """Compile ``relationship.is_(None)`` / ``is_not(None)``."""
    left = expr.left
    if not isinstance(left, FieldRef):
        raise QueryError("Expected FieldRef on left side of comparison")

    path = left.path
    field_name = left.field_name
    if left.model_cls is not model_cls:
        raise QueryError(
            f"Filter field {left.model_cls.__name__}.{field_name} does not match "
            f"query model {model_cls.__name__}"
        )

    patterns: list[str] = []
    if path:
        current_cls, current_var, path_patterns = _follow_path(
            model_cls, path, root_var, registry, join_counter, join_cache
        )
        patterns.extend(path_patterns)
    else:
        current_cls = model_cls
        current_var = root_var

    rel_map = {n: (fi, rc) for n, fi, rc in current_cls.get_relationship_fields()}
    if field_name not in rel_map:
        raise QueryError(
            f"is_(None) / is_not(None) requires a relationship field on {current_cls.__name__}"
        )

    field_info, related_cls = rel_map[field_name]
    meta = get_field_metadata(field_info)
    if meta is None:
        raise QueryError(f"Field '{field_name}' has no SPARQL metadata")

    join_counter[0] += 1
    join_var = f"?__join_{join_counter[0]}"
    hop_patterns = _relationship_hop_patterns(
        current_var,
        join_var,
        meta.predicate,
        related_cls,
        field_info,
        registry,
    )
    patterns.append(_optional_block(hop_patterns))

    if expr.op == CompareOp.IS_:
        return patterns, [f"!BOUND({join_var})"]
    if expr.op == CompareOp.IS_NOT:
        return patterns, [f"BOUND({join_var})"]
    raise QueryError(f"Unsupported presence operator: {expr.op}")


def _resolve_order_target(
    field_ref: FieldRef,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
) -> tuple[list[str], str]:
    """Return triple patterns and the variable for ORDER BY."""
    _, subject_var, patterns, field_info, field_name = _resolve_compare_target(
        field_ref, model_cls, root_var, registry, join_counter, join_cache
    )
    meta = get_field_metadata(field_info)
    assert meta is not None
    pred_expanded = validate_iri_token(expand_iri(meta.predicate, registry.prefixes))
    join_counter[0] += 1
    order_var = f"?__order_{field_name}_{join_counter[0]}"
    order_line = f"{subject_var} <{pred_expanded}> {order_var} ."
    if any("OPTIONAL" in pattern for pattern in patterns):
        patterns.append(_optional_block([order_line]))
    else:
        patterns.append(order_line)
    return patterns, order_var


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
    if expr.op in (CompareOp.IS_, CompareOp.IS_NOT):
        return _compile_relationship_presence(
            expr, model_cls, root_var, registry, join_counter, join_cache
        )

    if isinstance(expr.right, FieldRef):
        raise QueryError(
            "Cannot compare a field to another field; compare to a literal or IRI value"
        )
    if expr.right is None and expr.op != CompareOp.IN:
        raise QueryError(
            "Filter value cannot be None; use relationship.is_(None) for absence checks"
        )

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
            not_exists = f"NOT EXISTS {{ {inner} }}"
            if any("OPTIONAL" in pattern for pattern in path_patterns):
                filters.append(f"(!BOUND({subject_var}) || {not_exists})")
            else:
                filters.append(not_exists)
        else:
            neq_var = f"?__neq_{field_name}_{id(expr)}"
            patterns.append(f"{subject_var} <{pred_expanded}> {neq_var} .")
            neq_filter = f"{neq_var} != {obj}"
            if any("OPTIONAL" in pattern for pattern in path_patterns):
                filters.append(f"(!BOUND({subject_var}) || {neq_filter})")
            else:
                filters.append(neq_filter)
    elif expr.op in (CompareOp.LT, CompareOp.GT, CompareOp.LTE, CompareOp.GTE):
        cmp_var = f"?__cmp_{field_name}_{id(expr)}"
        patterns.append(f"{subject_var} <{pred_expanded}> {cmp_var} .")
        op_map = {
            CompareOp.LT: "<",
            CompareOp.GT: ">",
            CompareOp.LTE: "<=",
            CompareOp.GTE: ">=",
        }
        cmp_filter = f"{cmp_var} {op_map[expr.op]} {obj}"
        if any("OPTIONAL" in pattern for pattern in path_patterns):
            filters.append(f"(!BOUND({subject_var}) || {cmp_filter})")
        else:
            filters.append(cmp_filter)
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


def _iri_str_function(mode: str, var: str) -> str:
    if mode == "lower":
        return f"LCASE(STR({var}))"
    if mode == "upper":
        return f"UCASE(STR({var}))"
    return f"STR({var})"


def compile_iri_str_compare(
    expr: IriStrCompare,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
    *,
    use_not_exists_for_ne: bool = True,
) -> tuple[list[str], list[str]]:
    _, subject_var, path_patterns, field_info, _field_name = _resolve_compare_target(
        expr.left.field,
        model_cls,
        root_var,
        registry,
        join_counter,
        join_cache,
    )
    if not _annotation_expects_iri(field_info.annotation):
        raise QueryError("str()/lower()/upper() filters require an IRI-typed field")
    patterns = list(path_patterns)
    str_expr = _iri_str_function(expr.left.mode, subject_var)
    if expr.op == CompareOp.IN and isinstance(expr.right, tuple):
        formatted = [f'"{escape_sparql_string(str(v))}"' for v in expr.right]
        return patterns, [f"{str_expr} IN ({', '.join(formatted)})"]
    obj = _format_literal(expr.right)
    if expr.op == CompareOp.EQ:
        return patterns, [f"{str_expr} = {obj}"]
    if expr.op == CompareOp.NE:
        if use_not_exists_for_ne:
            return patterns, [f"!({str_expr} = {obj})"]
        return patterns, [f"{str_expr} != {obj}"]
    raise QueryError(f"Unsupported IRI string filter operator: {expr.op}")


def compile_property_path_compare(
    expr: PropertyPathCompare,
    root_var: str,
    registry: NamespaceRegistry,
) -> tuple[list[str], list[str]]:
    if expr.model_cls is not None and expr.op != CompareOp.EQ:
        raise QueryError("Property path filters support == only")
    obj = _format_object(expr.right, registry)
    path = expr.sparql_path.strip()
    if not path:
        raise QueryError("Property path must not be empty")
    parts: list[str] = []
    for seg in path.split("/"):
        seg = seg.strip()
        if not seg:
            continue
        if seg.startswith("^"):
            core = seg[1:].rstrip("*+")
            suffix = seg[len(core) + 1 :]
            parts.append(f"^{validate_iri_token(expand_iri(core, registry.prefixes))}{suffix}")
        elif seg.endswith("+") or seg.endswith("*"):
            core = seg.rstrip("*+")
            suffix = seg[len(core) :]
            parts.append(f"<{validate_iri_token(expand_iri(core, registry.prefixes))}>{suffix}")
        else:
            parts.append(f"<{validate_iri_token(expand_iri(seg, registry.prefixes))}>")
    sparql_path = "/".join(parts)
    return [f"{root_var} {sparql_path} {obj} ."], []


def compile_not(
    expr: NotExpr,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
    *,
    use_not_exists_for_ne: bool = True,
) -> tuple[list[str], list[str]]:
    inner = expr.inner
    if isinstance(inner, CompareExpr):
        pats, filts = compile_compare(
            inner,
            model_cls,
            root_var,
            registry,
            join_counter,
            join_cache,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
        exists = _exists_block(pats, filts)
        return [], [f"NOT ({exists})"]
    if isinstance(inner, AndExpr):
        compares = _flatten_and_expressions(inner.expressions)
        if not compares:
            raise QueryError("not_(and) requires comparison expressions")
        branch = compile_and_branch(
            inner,
            model_cls,
            root_var,
            registry,
            join_counter,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
        return [], [f"NOT ({branch})"]
    if isinstance(inner, OrExpr):
        or_filters = compile_or(
            inner,
            model_cls,
            root_var,
            registry,
            join_counter,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
        if len(or_filters) != 1:
            raise QueryError("not_(or) expects a single FILTER disjunction")
        inner_filter = or_filters[0]
        if inner_filter.startswith("FILTER(") and inner_filter.endswith(")"):
            inner_filter = inner_filter[7:-1]
        return [], [f"FILTER(!({inner_filter}))"]
    if isinstance(inner, PropertyPathCompare):
        pats, filts = compile_property_path_compare(inner, root_var, registry)
        exists = _exists_block(pats, filts)
        return [], [f"NOT ({exists})"]
    if isinstance(inner, IriStrCompare):
        pats, filts = compile_iri_str_compare(
            inner,
            model_cls,
            root_var,
            registry,
            join_counter,
            join_cache,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
        exists = _exists_block(pats, filts)
        return [], [f"NOT ({exists})"]
    raise QueryError(f"not_() does not support {type(inner).__name__}")


def compile_filter_expr(
    expr: WhereExpr,
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
    join_counter: list[int],
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]],
    *,
    use_not_exists_for_ne: bool = True,
) -> tuple[list[str], list[str]]:
    if isinstance(expr, CompareExpr):
        return compile_compare(
            expr,
            model_cls,
            root_var,
            registry,
            join_counter,
            join_cache,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
    if isinstance(expr, IriStrCompare):
        return compile_iri_str_compare(
            expr,
            model_cls,
            root_var,
            registry,
            join_counter,
            join_cache,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
    if isinstance(expr, PropertyPathCompare):
        return compile_property_path_compare(expr, root_var, registry)
    if isinstance(expr, NotExpr):
        return compile_not(
            expr,
            model_cls,
            root_var,
            registry,
            join_counter,
            join_cache,
            use_not_exists_for_ne=use_not_exists_for_ne,
        )
    if isinstance(expr, AndExpr):
        return [], [
            compile_and_branch(
                expr,
                model_cls,
                root_var,
                registry,
                join_counter,
                use_not_exists_for_ne=use_not_exists_for_ne,
            )
        ]
    raise QueryError(f"Unsupported filter expression: {type(expr).__name__}")


def _polymorphic_type_patterns(
    model_cls: type[SPARQLModel],
    root_var: str,
    registry: NamespaceRegistry,
) -> tuple[list[str], list[str]]:
    from sparqlmodel.schema_registry import registry_for_model

    base = validate_iri_token(expand_iri(model_cls.rdf_type, registry.prefixes))
    type_uris: set[str] = {base}
    reg = registry_for_model(model_cls)
    if reg is not None:
        type_uris |= {validate_iri_token(u) for u in reg.subtypes_of(base)}
    type_var = "?__ptype"
    patterns = [f"{root_var} a {type_var} ."]
    formatted = ", ".join(f"<{u}>" for u in sorted(type_uris))
    filters = [f"{type_var} IN ({formatted})"]
    return patterns, filters


def _format_values_term(value: object, registry: NamespaceRegistry) -> str:
    if isinstance(value, IRI):
        return _format_iri(registry.expand(str(value)))
    if isinstance(value, str) and (is_absolute_iri(value) or is_compact_iri(value)):
        try:
            return _format_iri(registry.expand(value))
        except ConfigurationError:
            return _format_literal(value)
    return _format_literal(value)


def _values_clause(
    bindings_rows: tuple[dict[str, object], ...],
    registry: NamespaceRegistry,
) -> str:
    if not bindings_rows:
        return ""
    keys = list(bindings_rows[0].keys())
    if not keys:
        return ""
    for row in bindings_rows:
        if set(row.keys()) != set(keys):
            raise QueryError("All values() rows must use the same variables")
    vars_part = " ".join(f"?{k}" for k in keys)
    rows: list[str] = []
    for row in bindings_rows:
        terms = " ".join(_format_values_term(row[k], registry) for k in keys)
        rows.append(f"({terms})")
    return f"VALUES ({vars_part}) {{ {' '.join(rows)} }}"


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
    expressions: tuple[WhereExpr, ...],
    registry: NamespaceRegistry,
    *,
    limit: int | None = None,
    offset: int | None = None,
    order_by: tuple[tuple[FieldRef, bool], ...] = (),
    count: bool = False,
    use_not_exists_for_ne: bool = True,
    polymorphic: bool = False,
    values_bindings: tuple[dict[str, object], ...] = (),
) -> str:
    """Compile WHERE expressions into a full SELECT SPARQL query."""
    root_var = _model_var_name(model_cls)
    type_expanded = validate_iri_token(expand_iri(model_cls.rdf_type, registry.prefixes))

    if polymorphic:
        all_patterns, all_filters = _polymorphic_type_patterns(model_cls, root_var, registry)
    else:
        all_patterns = [f"{root_var} a <{type_expanded}> ."]
        all_filters = []

    join_counter = [0]
    join_cache: dict[tuple[str, ...], tuple[str, type[SPARQLModel]]] = {}

    and_parts: list[WhereExpr] = []
    or_exprs: list[OrExpr] = []
    for expr in expressions:
        if isinstance(expr, OrExpr):
            or_exprs.append(expr)
        else:
            and_parts.append(expr)

    for part in and_parts:
        if isinstance(part, AndExpr):
            for child in part.expressions:
                pats, filts = compile_filter_expr(
                    child,
                    model_cls,
                    root_var,
                    registry,
                    join_counter,
                    join_cache,
                    use_not_exists_for_ne=use_not_exists_for_ne,
                )
                all_patterns.extend(pats)
                all_filters.extend(filts)
        else:
            pats, filts = compile_filter_expr(
                part,
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

    order_vars: list[tuple[str, bool]] = []
    if order_by and not count:
        for field_ref, desc in order_by:
            order_patterns, order_var = _resolve_order_target(
                field_ref,
                model_cls,
                root_var,
                registry,
                join_counter,
                join_cache,
            )
            all_patterns.extend(order_patterns)
            order_vars.append((order_var, desc))

    values_block = _values_clause(values_bindings, registry)
    if values_block:
        all_patterns.insert(0, values_block)

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
    if offset is not None and offset < 0:
        raise QueryError("offset must be non-negative")

    order_clause = ""
    if order_vars:
        order_parts = [
            f"{'DESC' if desc else 'ASC'}({order_var})" for order_var, desc in order_vars
        ]
        order_clause = f"\nORDER BY {' '.join(order_parts)}"

    offset_clause = f"\nOFFSET {offset}" if offset is not None and not count else ""
    limit_clause = f"\nLIMIT {limit}" if limit is not None and not count else ""
    prefixes = registry.sparql_prefixes()
    prefix_block = f"{prefixes}\n\n" if prefixes else ""

    if count:
        select_clause = f"SELECT (COUNT(DISTINCT {root_var}) AS ?__count)"
    else:
        select_clause = f"SELECT DISTINCT {root_var}"

    return (
        f"{prefix_block}{select_clause} WHERE {{\n    {where_clause}\n}}"
        f"{order_clause}{offset_clause}{limit_clause}"
    )
