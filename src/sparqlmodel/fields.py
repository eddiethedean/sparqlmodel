"""ORM field and relationship definitions for :class:`~sparqlmodel.model.SPARQLModel`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, ForwardRef, TypeVar, cast, get_args, get_origin

from pydantic import Field as PydanticField
from pydantic.fields import FieldInfo
from triplemodel import ref_field
from triplemodel.fields import InverseOf, inverse_pair
from triplemodel.fields.metadata import predicate_for_field, ref_link_for_field
from triplemodel.metadata.cardinality import element_type, field_cardinality
from triplemodel.terms.lang import Lang

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.types import IRI

T = TypeVar("T")

BackPopulatesSpec = Any


@dataclass(frozen=True, slots=True)
class SPARQLFieldMetadata:
    """Metadata attached to a SPARQL-mapped model field."""

    predicate: str
    is_relationship: bool = False
    related_model: type[Any] | None = None
    cascade: bool = True


def _merge_json_schema_extra(
    predicate: str,
    metadata: SPARQLFieldMetadata,
    extra: dict[str, Any] | None,
    *,
    inverse: str | None = None,
    literal_datatype: str | None = None,
    transitive: bool = False,
    back_populates: BackPopulatesSpec = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(extra or {})
    merged["sparql"] = metadata
    merged["rdf_predicate"] = predicate
    if inverse is not None:
        merged["rdf_inverse"] = inverse
    if literal_datatype is not None:
        merged["rdf_literal_datatype"] = literal_datatype
    if transitive:
        merged["rdf_transitive"] = True
    if back_populates is not None:
        from triplemodel.fields.back_populates import (
            normalize_back_populates,
            store_back_populates_extra,
        )

        store_back_populates_extra(
            merged,
            normalize_back_populates(back_populates),
        )
    return merged


def _field_metadata_tuple(
    *,
    lang: str | None = None,
    inverse: str | None = None,
) -> tuple[Any, ...]:
    items: list[Any] = []
    if lang is not None:
        items.append(Lang(lang))
    if inverse is not None:
        items.append(InverseOf(inverse))
    return tuple(items)


def Field(
    predicate: str,
    *,
    lang: str | None = None,
    inverse: str | None = None,
    literal_datatype: str | None = None,
    transitive: bool = False,
    back_populates: BackPopulatesSpec = None,
    **kwargs: Any,
) -> Any:
    """Map a model attribute to an RDF predicate.

    Args:
        predicate: Compact or absolute IRI (e.g. ``schema:name``).
        lang: Default language tag for string literals (``Lang`` metadata).
        inverse: Inverse predicate IRI for import-only triples.
        literal_datatype: XSD datatype CURIE for typed literals.
        transitive: Expand multi-valued object URIs transitively on import.
        back_populates: ``BackPopulates``, ``inverse_pair``, or ``(Model, field)`` tuple.
        **kwargs: Additional arguments passed to ``pydantic.Field``.
    """
    metadata = SPARQLFieldMetadata(predicate=predicate, is_relationship=False)
    json_schema_extra = kwargs.pop("json_schema_extra", {}) or {}
    if not isinstance(json_schema_extra, dict):
        json_schema_extra = {}
    extra = _merge_json_schema_extra(
        predicate,
        metadata,
        json_schema_extra,
        inverse=inverse,
        literal_datatype=literal_datatype,
        transitive=transitive,
        back_populates=back_populates,
    )
    if lang is not None:
        extra["rdf_lang"] = lang
    return PydanticField(**kwargs, json_schema_extra=extra)


def Relationship(
    predicate: str,
    *,
    model: type[Any] | None = None,
    cascade: bool = True,
    inverse: str | None = None,
    back_populates: BackPopulatesSpec = None,
    **kwargs: Any,
) -> Any:
    """Map a model attribute to an RDF object relationship.

    Args:
        predicate: Compact or absolute IRI (e.g. ``schema:worksFor``).
        model: Related ``SPARQLModel`` class (inferred from annotation when omitted).
        cascade: When ``False``, nested resources are not included in put/delete cascade.
        inverse: Inverse predicate for import (not with ``ref_field``).
        back_populates: Paired inverse field on another model (TripleModel 0.12+).
        **kwargs: Additional arguments passed to ``pydantic.Field``.
    """
    metadata = SPARQLFieldMetadata(
        predicate=predicate,
        is_relationship=True,
        related_model=model,
        cascade=cascade,
    )
    json_schema_extra = kwargs.pop("json_schema_extra", {}) or {}
    if not isinstance(json_schema_extra, dict):
        json_schema_extra = {}

    if not cascade and model is not None:
        if inverse is not None:
            raise ConfigurationError("inverse= is not supported on ref_field relationships")
        return ref_field(
            predicate,
            model=model,
            default=None,
            json_schema_extra=_merge_json_schema_extra(
                predicate,
                metadata,
                json_schema_extra,
                back_populates=back_populates,
            ),
            **kwargs,
        )

    return PydanticField(
        default=None,
        **kwargs,
        json_schema_extra=_merge_json_schema_extra(
            predicate,
            metadata,
            json_schema_extra,
            inverse=inverse,
            back_populates=back_populates,
        ),
    )


def get_field_metadata(field_info: FieldInfo) -> SPARQLFieldMetadata | None:
    """Extract SPARQL metadata from a Pydantic field info object."""
    extra = field_info.json_schema_extra
    if not isinstance(extra, dict):
        return None
    meta = cast(dict[str, Any], extra).get("sparql")
    if isinstance(meta, SPARQLFieldMetadata):
        return meta
    return None


def predicate_uri_for_field(field_info: FieldInfo, prefixes: dict[str, str]) -> str | None:
    """Expanded predicate IRI for a mapped field (TripleModel or SparqlModel metadata)."""
    from sparqlmodel.types import expand_iri

    pred = predicate_for_field(field_info)
    if pred is None:
        meta = get_field_metadata(field_info)
        if meta is None:
            return None
        pred = meta.predicate
    return expand_iri(pred, prefixes)


def field_cardinality_for(field_info: FieldInfo) -> str:
    """TripleModel cardinality for a mapped field."""
    return field_cardinality(field_info)


def is_relationship_field(field_info: FieldInfo, meta: SPARQLFieldMetadata | None) -> bool:
    """True when the field maps to object references or nested models."""
    if meta is not None and meta.is_relationship:
        return True
    card = field_cardinality(field_info)
    if card in ("nested", "ref"):
        return True
    if card in ("list", "set"):
        inner = element_type(field_info.annotation)
        from sparqlmodel.model import SPARQLModel

        if inner is IRI:
            return bool(meta and meta.is_relationship)
        if isinstance(inner, type) and issubclass(inner, SPARQLModel):
            return True
        try:
            from triplemodel.fields.resource_ref import ResourceRef

            if inner is ResourceRef:
                return True
        except ImportError:
            pass
    return False


def _evaluate_forward_ref(ref: ForwardRef) -> Any:
    """Evaluate a ``ForwardRef`` using the runtime's public or legacy API."""
    evaluate = getattr(ref, "evaluate", None)
    if callable(evaluate):  # pragma: no cover -- future CPython versions
        try:
            return evaluate()
        except TypeError:
            return evaluate(
                globalns={},
                localns={},
                recursive_guard=frozenset(),
            )
        except NameError:
            return None
    legacy = getattr(ref, "_evaluate", None)
    if not callable(legacy):
        return None  # pragma: no cover
    for attempt in (
        lambda: legacy(
            globalns={},
            localns={},
            type_params=(),
            recursive_guard=frozenset(),
        ),
        lambda: legacy(
            globalns={},
            localns={},
            recursive_guard=frozenset(),
        ),
        lambda: legacy(globalns={}, localns={}, type_params=()),
        lambda: legacy({}, {}, frozenset()),
    ):
        try:
            return attempt()
        except TypeError:
            continue
        except NameError:
            return None
    return None  # pragma: no cover


def _resolve_annotation_type(annotation: Any) -> type[Any] | None:
    """Return a concrete type from an annotation, resolving ``ForwardRef`` when possible."""
    from sparqlmodel.model import SPARQLModel

    ann = element_type(annotation) if get_origin(annotation) in (list, set) else annotation
    if isinstance(ann, ForwardRef):
        evaluated = _evaluate_forward_ref(ann)
        if isinstance(evaluated, type):
            return evaluated
        return None
    if isinstance(ann, type):
        return ann
    origin = get_origin(ann)
    if origin is not None:
        for arg in get_args(ann):
            if arg is type(None):
                continue
            if isinstance(arg, ForwardRef):
                evaluated = _evaluate_forward_ref(arg)
                if isinstance(evaluated, type) and issubclass(evaluated, SPARQLModel):
                    return evaluated
            if isinstance(arg, type) and issubclass(arg, SPARQLModel):
                return arg
        for arg in get_args(ann):
            if arg is type(None):
                continue
            if isinstance(arg, ForwardRef):
                evaluated = _evaluate_forward_ref(arg)
                if isinstance(evaluated, type):
                    return evaluated
            if isinstance(arg, type):
                return arg
    return None


def resolve_related_model(
    field_name: str, annotation: Any, metadata: SPARQLFieldMetadata
) -> type[Any]:
    """Resolve the related model class for a relationship field."""
    if metadata.related_model is not None:
        return metadata.related_model
    resolved = _resolve_annotation_type(annotation)
    if resolved is not None:
        return resolved
    raise ConfigurationError(
        f"Cannot infer related model for relationship field '{field_name}'. "
        "Pass model=YourModel to Relationship()."
    )


def relationship_is_nullable(annotation: Any) -> bool:
    """True when a relationship annotation includes ``None`` (optional link)."""
    origin = get_origin(annotation)
    if origin is not None:
        return type(None) in get_args(annotation)
    return False


def relationship_allows_iri(annotation: Any) -> bool:
    """True when the relationship annotation includes ``IRI`` (composition or reference)."""
    if annotation is IRI:
        return True
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        if any(arg is IRI for arg in args):
            return True
        inner = element_type(annotation)
        return inner is IRI
    return False


def relationship_is_ref_link(field_info: FieldInfo) -> bool:
    """True when the field is a URI reference (``ref_field``), not embedded composition."""
    return ref_link_for_field(field_info)


def iter_relationship_values(value: object) -> Sequence[object]:
    """Normalize scalar or collection relationship values to a sequence."""
    if value is None:
        return ()
    if isinstance(value, (list, set, tuple)):
        return [v for v in value if v is not None]
    return (value,)


# Type alias for annotated relationship fields
SPARQLField = Annotated[T, SPARQLFieldMetadata]

__all__ = [
    "Field",
    "Relationship",
    "SPARQLField",
    "SPARQLFieldMetadata",
    "field_cardinality_for",
    "get_field_metadata",
    "inverse_pair",
    "is_relationship_field",
    "iter_relationship_values",
    "predicate_uri_for_field",
    "relationship_allows_iri",
    "relationship_is_nullable",
    "relationship_is_ref_link",
    "resolve_related_model",
]
