"""Tests for field metadata."""

from sparqlmodel import Field, Relationship, SPARQLModel
from sparqlmodel.fields import get_field_metadata, resolve_related_model


class _Org(SPARQLModel):
    rdf_type = "schema:Organization"
    name: str = Field("schema:name")


class _Person(SPARQLModel):
    rdf_type = "schema:Person"
    works_for: _Org | None = Relationship("schema:worksFor", model=_Org)


def test_get_field_metadata() -> None:
    info = _Person.model_fields.get("name")
    assert info is None or get_field_metadata(info) is None


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


def test_get_field_metadata_none() -> None:
    from pydantic import Field as PydanticField

    class Plain(SPARQLModel):
        rdf_type = "schema:Thing"
        label: str = PydanticField()

    assert get_field_metadata(Plain.model_fields["label"]) is None
