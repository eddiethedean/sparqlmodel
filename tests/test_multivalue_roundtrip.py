"""Multi-valued and language-tagged field round-trips (0.13)."""

from __future__ import annotations

from triplemodel import MultiLangString, ResourceRef

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession


class Tag(SPARQLModel):
    rdf_type = "schema:Thing"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")


class Article(SPARQLModel):
    rdf_type = "schema:Article"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    title: MultiLangString = Field("schema:name")
    tags: set[str] = Field("schema:keyword", default_factory=set)
    related: set[ResourceRef] = Field("schema:about", default_factory=set)


def test_set_tags_put_get_roundtrip() -> None:
    article = Article(
        id=IRI("urn:article:1"),
        title=MultiLangString(en="Hello", fr="Bonjour"),
        tags={"python", "rdf"},
        related={ResourceRef("urn:tag:py"), ResourceRef("urn:tag:rdf")},
    )
    with SPARQLSession() as session:
        session.put(article)
        loaded = session.get(Article, article.id, depth=0)
    assert loaded is not None
    assert loaded.tags == {"python", "rdf"}
    assert loaded.title.by_lang["en"].value == "Hello"


def test_collection_ref_in_filter() -> None:
    a = Article(
        id=IRI("urn:article:2"),
        title=MultiLangString(en="X"),
        tags=set(),
        related={ResourceRef("urn:tag:one")},
    )
    with SPARQLSession() as session:
        session.put(a)
        found = session.query(Article).where(Article.related.in_((IRI("urn:tag:one"),))).first()
    assert found is not None
    assert str(found.id) == "urn:article:2"


def test_collection_tags_in_filter() -> None:
    a = Article(
        id=IRI("urn:article:3"),
        title=MultiLangString(en="Y"),
        tags={"sparql"},
        related=set(),
    )
    with SPARQLSession() as session:
        session.put(a)
        found = session.query(Article).where(Article.tags.in_(("sparql",))).first()
    assert found is not None
