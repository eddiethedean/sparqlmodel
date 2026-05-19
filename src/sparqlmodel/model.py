"""ORM entity base class (:class:`SPARQLModel`); use with :class:`~sparqlmodel.session.SPARQLSession`."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, ClassVar, cast, get_origin

from pydantic import ConfigDict
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
from triplemodel import IriId, TripleModel
from triplemodel.fields.metadata import id_field_is_iri_id
from typing_extensions import Self

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.expressions import FieldRef
from sparqlmodel.fields import get_field_metadata, resolve_related_model
from sparqlmodel.types import DEFAULT_PREFIXES, IRI, NamespaceRegistry, expand_iri


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


class SPARQLModel(TripleModel, metaclass=SPARQLModelMetaclass):
    """ORM entity mapped to RDF; persist and query via :class:`~sparqlmodel.session.SPARQLSession`."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=False,
    )

    rdf_type: ClassVar[str]
    __prefixes__: ClassVar[dict[str, str]] = {}
    Rdf: ClassVar[type]

    id: Annotated[IRI | None, IriId()] = None

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
        _apply_rdf_config(cls)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        _ensure_id_field_has_iri_id(cls)
        cls._validate_unique_predicates()

    @classmethod
    def _validate_unique_predicates(cls) -> None:
        """Raise if two mapped fields share the same expanded RDF predicate."""
        prefixes = cls.get_prefixes()
        by_predicate: dict[str, list[str]] = {}
        for name, field_info, _ in cls.iter_sparql_fields():
            meta = get_field_metadata(field_info)
            assert meta is not None  # ``iter_sparql_fields`` only yields mapped fields
            pred = expand_iri(meta.predicate, prefixes)
            by_predicate.setdefault(pred, []).append(name)
        duplicates = {pred: names for pred, names in by_predicate.items() if len(names) > 1}
        if duplicates:
            detail = "; ".join(
                f"{', '.join(names)} -> {pred}" for pred, names in duplicates.items()
            )
            raise ConfigurationError(
                f"{cls.__name__} maps multiple fields to the same predicate: {detail}"
            )

    @classmethod
    def get_prefixes(cls) -> dict[str, str]:
        """Return namespace prefixes for this model (includes built-in RDF prefixes)."""
        return {**DEFAULT_PREFIXES, **dict(cls.__prefixes__)}

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

    def subject_uri(self, *, uri: str | None = None) -> str:
        """Return the RDF subject IRI for this instance (expanded when compact)."""
        if uri is not None:
            return uri
        if self.id is not None:
            return expand_iri(str(self.id), self.get_prefixes())
        return super().subject_uri()

    def model_dump_jsonld(self) -> dict[str, Any]:
        """Serialize model to a JSON-LD compatible dict."""
        from sparqlmodel.serializers import model_to_jsonld

        return model_to_jsonld(self)

    @classmethod
    def model_validate_jsonld(cls, data: dict[str, Any]) -> Self:
        """Deserialize model from JSON-LD dict."""
        from sparqlmodel.serializers import model_from_jsonld

        return model_from_jsonld(cls, data)


def _ensure_id_field_has_iri_id(cls: type[SPARQLModel]) -> None:
    """Ensure ``id`` carries :class:`~triplemodel.IriId` so graph import fills subject IRIs."""
    if "id" not in cls.model_fields or id_field_is_iri_id(cls, "id"):
        return
    fi = cls.model_fields["id"]
    existing = tuple(fi.metadata)
    if not any(isinstance(meta, IriId) for meta in existing):
        object.__setattr__(fi, "metadata", existing + (IriId(),))
    ann = cls.__annotations__.get("id", IRI | None)
    if get_origin(ann) is not Annotated:
        cls.__annotations__["id"] = Annotated[ann, IriId()]


def _apply_rdf_config(cls: type[SPARQLModel]) -> None:
    """Inject TripleModel ``Rdf`` config from SparqlModel class variables."""
    merged_prefixes = cls.get_prefixes()
    expanded_type_uri = expand_iri(cls.rdf_type, merged_prefixes)

    class Rdf:
        type_uri = expanded_type_uri
        prefixes = merged_prefixes
        namespace = "urn:sparqlmodel:unused/"
        embed = "iri"
        id_field = "id"

    cls.Rdf = Rdf
