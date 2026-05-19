"""ORM field and relationship definitions for :class:`~sparqlmodel.model.SPARQLModel`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, ForwardRef, TypeVar, cast, get_args, get_origin

from pydantic import Field as PydanticField
from pydantic.fields import FieldInfo

from sparqlmodel.exceptions import ConfigurationError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SPARQLFieldMetadata:
    """Metadata attached to a SPARQL-mapped model field."""

    predicate: str
    is_relationship: bool = False
    related_model: type[Any] | None = None
    cascade: bool = True


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
    json_schema_extra["sparql"] = metadata
    return PydanticField(**kwargs, json_schema_extra=json_schema_extra)


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
    json_schema_extra["sparql"] = metadata
    return PydanticField(default=None, **kwargs, json_schema_extra=json_schema_extra)


def get_field_metadata(field_info: FieldInfo) -> SPARQLFieldMetadata | None:
    """Extract SPARQL metadata from a Pydantic field info object."""
    extra = field_info.json_schema_extra
    if not isinstance(extra, dict):
        return None
    meta = cast(dict[str, Any], extra).get("sparql")
    if isinstance(meta, SPARQLFieldMetadata):
        return meta
    return None


def _evaluate_forward_ref(ref: ForwardRef) -> Any:
    """Evaluate a ``ForwardRef`` when the runtime supports it (3.12+ uses ``evaluate``)."""
    evaluate = getattr(ref, "evaluate", None)
    if callable(evaluate):  # pragma: no cover -- Python 3.12+ only
        try:
            return evaluate()
        except TypeError:
            return evaluate(
                globalns={},
                localns={},
                recursive_guard=frozenset(),
            )
    legacy = getattr(ref, "_evaluate", None)
    if callable(legacy):
        try:
            return legacy(globalns={}, localns={}, type_params=())
        except TypeError:
            try:
                return legacy({}, {}, frozenset())
            except NameError:
                return None
        except NameError:  # pragma: no cover
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


# Type alias for annotated relationship fields
SPARQLField = Annotated[T, SPARQLFieldMetadata]
