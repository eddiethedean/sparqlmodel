"""Tests for field metadata."""

from sparqlmodel import IRI, Field, Relationship, SPARQLModel
from sparqlmodel.fields import get_field_metadata, resolve_related_model


class _Org(SPARQLModel):
    rdf_type = "schema:Organization"
    name: str = Field("schema:name")


class _Person(SPARQLModel):
    rdf_type = "schema:Person"
    works_for: _Org | None = Relationship("schema:worksFor", model=_Org)


def test_get_field_metadata() -> None:
    field_info = _Person.model_fields["works_for"]
    meta = get_field_metadata(field_info)
    assert meta is not None
    assert meta.predicate == "schema:worksFor"
    assert meta.is_relationship is True


def test_resolve_related_model() -> None:
    field_info = _Person.model_fields["works_for"]
    meta = get_field_metadata(field_info)
    assert meta is not None
    related = resolve_related_model("works_for", _Person.model_fields["works_for"].annotation, meta)
    assert related is _Org


def test_field_non_dict_extra() -> None:
    f = Field("schema:label", json_schema_extra="invalid")  # type: ignore[arg-type]
    assert f is not None


def test_resolve_related_direct_annotation() -> None:
    class Direct(SPARQLModel):
        rdf_type = "schema:Person"
        works_for: _Org = Relationship("schema:worksFor")

    field_info = Direct.model_fields["works_for"]
    meta = get_field_metadata(field_info)
    assert meta is not None
    related = resolve_related_model("works_for", Direct.model_fields["works_for"].annotation, meta)
    assert related is _Org


def test_resolve_related_model_iri_only_union() -> None:
    class IriOnly(SPARQLModel):
        rdf_type = "schema:Person"
        ref: IRI | None = Relationship("schema:ref")

    field_info = IriOnly.model_fields["ref"]
    meta = get_field_metadata(field_info)
    assert meta is not None
    related = resolve_related_model("ref", field_info.annotation, meta)
    assert related is IRI


def test_resolve_related_model_prefers_sparqlmodel_over_iri() -> None:
    class RefFirst(SPARQLModel):
        rdf_type = "schema:Person"
        works_for: IRI | _Org | None = Relationship("schema:worksFor")

    field_info = RefFirst.model_fields["works_for"]
    meta = get_field_metadata(field_info)
    assert meta is not None
    related = resolve_related_model("works_for", field_info.annotation, meta)
    assert related is _Org


def test_get_field_metadata_none() -> None:
    from pydantic import Field as PydanticField

    class Plain(SPARQLModel):
        rdf_type = "schema:Thing"
        label: str = PydanticField()

    assert get_field_metadata(Plain.model_fields["label"]) is None
