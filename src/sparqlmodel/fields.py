"""SPARQL field and relationship definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, TypeVar, cast, get_args, get_origin

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
    **kwargs: Any,
) -> Any:
    """Map a model attribute to an RDF object relationship.

    Args:
        predicate: Compact or absolute IRI (e.g. ``schema:worksFor``).
        model: Related ``SPARQLModel`` class (inferred from annotation when omitted).
        **kwargs: Additional arguments passed to ``pydantic.Field``.
    """
    metadata = SPARQLFieldMetadata(
        predicate=predicate,
        is_relationship=True,
        related_model=model,
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


def resolve_related_model(
    field_name: str, annotation: Any, metadata: SPARQLFieldMetadata
) -> type[Any]:
    """Resolve the related model class for a relationship field."""
    if metadata.related_model is not None:
        return metadata.related_model
    origin = get_origin(annotation)
    if origin is not None:
        for arg in get_args(annotation):
            if arg is not type(None) and isinstance(arg, type):
                return arg
    if isinstance(annotation, type):
        return annotation
    raise ConfigurationError(
        f"Cannot infer related model for relationship field '{field_name}'. "
        "Pass model=YourModel to Relationship()."
    )


# Type alias for annotated relationship fields
SPARQLField = Annotated[T, SPARQLFieldMetadata]
