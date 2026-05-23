"""Cascade orphan cleanup when one of several relationship refs is removed."""

from __future__ import annotations

from triplemodel import ResourceRef

from sparqlmodel import IRI, Field, Relationship, SPARQLModel, SPARQLSession
from sparqlmodel.graph import cascade_subjects_for_removal


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
