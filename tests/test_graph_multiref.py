"""Cascade orphan cleanup when one of several relationship refs is removed."""

from __future__ import annotations

from triplemodel import ResourceRef

from sparqlmodel import IRI, Field, Relationship, SPARQLModel, SPARQLSession
from sparqlmodel.graph import _protected_relationship_key, cascade_subjects_for_removal
from tests.models import Person


class Tag(SPARQLModel):
    rdf_type = "schema:Thing"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")


class Article(SPARQLModel):
    rdf_type = "schema:Article"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    tags: set[ResourceRef] = Relationship("schema:about", model=Tag)


def test_protected_relationship_key_unsupported_returns_none() -> None:
    assert _protected_relationship_key(42, Person.get_prefixes()) is None


def test_cascade_subjects_drops_removed_multi_ref(session: SPARQLSession) -> None:
    t1 = Tag(id=IRI("urn:tag:1"), name="One")
    t2 = Tag(id=IRI("urn:tag:2"), name="Two")
    article = Article(
        id=IRI("urn:article:m"),
        tags={ResourceRef(str(t1.id)), ResourceRef(str(t2.id))},
    )
    session.put(t1)
    session.put(t2)
    session.put(article)
    article.tags = {ResourceRef(str(t2.id))}
    subjects = cascade_subjects_for_removal(article, session.graph, for_put=True)
    keys = {iri for _, iri in subjects}
    assert "urn:tag:1" in keys
    assert "urn:article:m" in keys
    assert "urn:tag:2" not in keys


def test_put_drops_removed_resource_ref_keeps_remaining(session: SPARQLSession) -> None:
    t1 = Tag(id=IRI("urn:tag:1"), name="One")
    t2 = Tag(id=IRI("urn:tag:2"), name="Two")
    article = Article(
        id=IRI("urn:article:m"),
        tags={ResourceRef(str(t1.id)), ResourceRef(str(t2.id))},
    )
    session.put(t1)
    session.put(t2)
    session.put(article)

    t1_key = str(t1.id.expand(t1.get_prefixes()))
    t2_key = str(t2.id.expand(t2.get_prefixes()))
    assert len(list(session.graph.triples((t1_key, None, None)))) >= 1
    assert len(list(session.graph.triples((t2_key, None, None)))) >= 1

    article.tags = {ResourceRef(str(t2.id))}
    session.put(article)

    assert len(list(session.graph.triples((t1_key, None, None)))) == 0
    assert session.get(Tag, t1.id) is None
    assert len(list(session.graph.triples((t2_key, None, None)))) >= 1
    assert session.get(Tag, t2.id) is not None
