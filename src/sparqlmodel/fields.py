"""ORM field and relationship definitions for :class:`~sparqlmodel.model.SPARQLModel`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, ForwardRef, TypeVar, cast, get_args, get_origin

from pydantic import Field as PydanticField
from pydantic.fields import FieldInfo
from triplemodel import ref_field
from triplemodel.fields.metadata import predicate_for_field

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.types import IRI

T = TypeVar("T")


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
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(extra or {})
    merged["sparql"] = metadata
    merged["rdf_predicate"] = predicate
    return merged


def Field(predicate: str, **kwargs: Any) -> Any:
    """Map a model attribute to an RDF predicate.

    Args:
        predicate: Compact or absolute IRI (e.g. ``schema:name``).
        **kwargs: Additional arguments passed to ``pydantic.Field``.
    """
    metadata = SPARQLFieldMetadata(predicate=predicate, is_relationship=False)
    json_schema_extra = kwargs.pop("json_schema_extra", {}) or {}
    if not isinstance(json_schema_extra, dict):
        json_schema_extra = {}
    return PydanticField(
        **kwargs,
        json_schema_extra=_merge_json_schema_extra(predicate, metadata, json_schema_extra),
    )


def Relationship(
    predicate: str,
    *,
    model: type[Any] | None = None,
    cascade: bool = True,
    **kwargs: Any,
) -> Any:
    """Map a model attribute to an RDF object relationship.

    Args:
        predicate: Compact or absolute IRI (e.g. ``schema:worksFor``).
        model: Related ``SPARQLModel`` class (inferred from annotation when omitted).
        cascade: When ``False``, nested resources are not included in put/delete cascade.
            Pass ``model=`` to use TripleModel ``ref_field`` (URI reference only on write).
            When ``model`` is omitted, cascade policy still applies; pass ``model=`` for
            strict ref semantics matching :class:`~triplemodel.TripleModel` imports.
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
        return ref_field(
            predicate,
            model=model,
            default=None,
            json_schema_extra=_merge_json_schema_extra(predicate, metadata, json_schema_extra),
            **kwargs,
        )

    return PydanticField(
        default=None,
        **kwargs,
        json_schema_extra=_merge_json_schema_extra(predicate, metadata, json_schema_extra),
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

    if isinstance(annotation, ForwardRef):
        evaluated = _evaluate_forward_ref(annotation)
        if isinstance(evaluated, type):
            return evaluated
        return None
    if isinstance(annotation, type):
        return annotation
    origin = get_origin(annotation)
    if origin is not None:
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            if isinstance(arg, ForwardRef):
                evaluated = _evaluate_forward_ref(arg)
                if isinstance(evaluated, type) and issubclass(evaluated, SPARQLModel):
                    return evaluated
            if isinstance(arg, type) and issubclass(arg, SPARQLModel):
                return arg
        for arg in get_args(annotation):
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


def relationship_allows_iri(annotation: Any) -> bool:
    """True when the relationship annotation includes ``IRI`` (composition or reference)."""
    if annotation is IRI:
        return True
    origin = get_origin(annotation)
    if origin is not None:
        return any(arg is IRI for arg in get_args(annotation))
    return False


# Type alias for annotated relationship fields
SPARQLField = Annotated[T, SPARQLFieldMetadata]
