"""SPARQLModel base class."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
from typing_extensions import Self

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.expressions import FieldRef
from sparqlmodel.fields import get_field_metadata, resolve_related_model
from sparqlmodel.types import IRI, NamespaceRegistry


class SPARQLModelMetaclass(ModelMetaclass):
    """Metaclass enabling ``Model.field == value`` query expressions."""

    def __getattr__(cls, name: str) -> Any:
        if name.startswith("_") or name in (
            "model_fields",
            "model_config",
            "model_computed_fields",
            "model_rebuild",
        ):
            raise AttributeError(name)
        if name in cls.model_fields and name != "id":
            return FieldRef(cast("type[SPARQLModel]", cls), name)
        raise AttributeError(f"{cls.__name__} has no attribute {name}")


class SPARQLModel(BaseModel, metaclass=SPARQLModelMetaclass):
    """Base class for RDF-backed Pydantic models."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    rdf_type: ClassVar[str]
    __prefixes__: ClassVar[dict[str, str]] = {}

    id: IRI | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "rdf_type", None):
            raise ConfigurationError(f"{cls.__name__} must define rdf_type")
        if "__prefixes__" not in cls.__dict__:
            prefixes: dict[str, str] = {}
            for base in cls.__mro__[1:]:
                if "__prefixes__" in base.__dict__:
                    prefixes = dict(base.__dict__["__prefixes__"])
                    break
            cls.__prefixes__ = prefixes

    @classmethod
    def get_prefixes(cls) -> dict[str, str]:
        """Return namespace prefixes for this model."""
        return dict(cls.__prefixes__)

    @classmethod
    def namespace_registry(cls) -> NamespaceRegistry:
        return NamespaceRegistry(cls.get_prefixes())

    @classmethod
    def iter_sparql_fields(cls) -> list[tuple[str, FieldInfo, Any]]:
        """Yield (name, field_info, annotation) for mapped fields excluding id."""
        results: list[tuple[str, FieldInfo, Any]] = []
        for name, field_info in cls.model_fields.items():
            if name == "id":
                continue
            if get_field_metadata(field_info) is not None:
                results.append((name, field_info, field_info.annotation))
        return results

    @classmethod
    def get_relationship_fields(cls) -> list[tuple[str, FieldInfo, type[SPARQLModel]]]:
        """Return relationship field definitions."""
        rels: list[tuple[str, FieldInfo, type[SPARQLModel]]] = []
        for name, field_info, annotation in cls.iter_sparql_fields():
            meta = get_field_metadata(field_info)
            if meta and meta.is_relationship:
                related = resolve_related_model(name, annotation, meta)
                rels.append((name, field_info, related))
        return rels

    @classmethod
    def get_scalar_fields(cls) -> list[tuple[str, FieldInfo]]:
        """Return scalar (non-relationship) field definitions."""
        scalars: list[tuple[str, FieldInfo]] = []
        for name, field_info, _ in cls.iter_sparql_fields():
            meta = get_field_metadata(field_info)
            if meta and not meta.is_relationship:
                scalars.append((name, field_info))
        return scalars

    def ensure_id(self) -> IRI:
        """Ensure the instance has an IRI id."""
        if self.id is None:
            object.__setattr__(self, "id", IRI(f"urn:uuid:{uuid.uuid4()}"))
        assert self.id is not None
        return self.id

    def model_dump_jsonld(self) -> dict[str, Any]:
        """Serialize model to a JSON-LD compatible dict."""
        from sparqlmodel.serializers import model_to_jsonld

        return model_to_jsonld(self)

    @classmethod
    def model_validate_jsonld(cls, data: dict[str, Any]) -> Self:
        """Deserialize model from JSON-LD dict."""
        from sparqlmodel.serializers import model_from_jsonld

        return model_from_jsonld(cls, data)
