"""Tests for field metadata."""

from __future__ import annotations

from typing import ForwardRef

import pytest

from sparqlmodel import IRI, Field, Relationship, SPARQLModel
from sparqlmodel.fields import SPARQLFieldMetadata, get_field_metadata, resolve_related_model


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


def test_resolve_forward_ref_to_org() -> None:
    meta = SPARQLFieldMetadata(predicate="schema:worksFor", is_relationship=True)
    related = resolve_related_model(
        "works_for",
        ForwardRef("_Org", module=__name__),
        meta,
    )
    assert related is _Org


def test_evaluate_forward_ref_retries_on_typeerror() -> None:
    from sparqlmodel.fields import _evaluate_forward_ref

    class _Ref:
        pass

    ref = _Ref()
    calls = 0

    def _evaluate(*_args: object, **_kwargs: object) -> type[int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TypeError
        return int

    ref._evaluate = _evaluate

    assert _evaluate_forward_ref(ref) is int
    assert calls >= 2


def test_evaluate_forward_ref_all_attempts_typeerror() -> None:
    from sparqlmodel.fields import _evaluate_forward_ref

    class _Ref:
        pass

    ref = _Ref()
    def _always_typeerror(*_args: object, **_kwargs: object) -> None:
        raise TypeError

    ref._evaluate = _always_typeerror

    assert _evaluate_forward_ref(ref) is None


def test_resolve_forward_ref_unknown_raises() -> None:
    from sparqlmodel.exceptions import ConfigurationError
    from sparqlmodel.fields import _evaluate_forward_ref

    assert _evaluate_forward_ref(ForwardRef("NoSuchNameXYZ")) is None
    meta = SPARQLFieldMetadata(predicate="schema:link", is_relationship=True)
    with pytest.raises(ConfigurationError):
        resolve_related_model("link", ForwardRef("UnknownModel"), meta)


def test_resolve_annotation_type_returns_none() -> None:
    from sparqlmodel.exceptions import ConfigurationError
    from sparqlmodel.fields import _resolve_annotation_type

    class NotAType:
        pass

    assert _resolve_annotation_type(NotAType()) is None
    meta = SPARQLFieldMetadata(predicate="schema:link", is_relationship=True)
    with pytest.raises(ConfigurationError):
        resolve_related_model("link", NotAType(), meta)


def test_resolve_related_int_union() -> None:
    meta = SPARQLFieldMetadata(predicate="schema:count", is_relationship=True)
    related = resolve_related_model("count", int | None, meta)
    assert related is int


def test_resolve_forward_ref_in_optional_union() -> None:
    meta = SPARQLFieldMetadata(predicate="schema:worksFor", is_relationship=True)
    related = resolve_related_model(
        "works_for",
        ForwardRef("_Org", module=__name__) | None,
        meta,
    )
    assert related is _Org


def test_resolve_forward_ref_non_model_union_member() -> None:
    from sparqlmodel.fields import _resolve_annotation_type

    assert _resolve_annotation_type(ForwardRef("int", module="builtins") | None) is int
    assert _resolve_annotation_type(None | ForwardRef("int", module="builtins")) is int
    meta = SPARQLFieldMetadata(predicate="schema:count", is_relationship=True)
    related = resolve_related_model(
        "count",
        ForwardRef("int", module="builtins") | None,
        meta,
    )
    assert related is int


def test_get_field_metadata_none() -> None:
    from pydantic import Field as PydanticField

    class Plain(SPARQLModel):
        rdf_type = "schema:Thing"
        label: str = PydanticField()

    assert get_field_metadata(Plain.model_fields["label"]) is None
