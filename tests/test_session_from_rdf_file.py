"""Tests for :meth:`~sparqlmodel.session.SPARQLSession.from_rdf_file`."""

from __future__ import annotations

from pathlib import Path

import pytest

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession

REALWORLD_DATA = Path(__file__).resolve().parents[1] / "examples" / "realworld" / "data"


class Laureate(SPARQLModel):
    rdf_type = "nobel:Laureate"
    __prefixes__ = {
        "nobel": "http://data.nobelprize.org/terms/",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "foaf": "http://xmlns.com/foaf/0.1/",
    }

    id: IRI
    name: str = Field("rdfs:label")


def test_from_rdf_file_loads_realworld_bundle() -> None:
    ttl = REALWORLD_DATA / "nobel_laureates_1901.ttl"
    prefixes = dict(Laureate.__prefixes__)
    with SPARQLSession.from_rdf_file(ttl, prefixes=prefixes) as session:
        laureates = session.query(Laureate).all()
    assert len(laureates) == 6


def test_from_rdf_file_missing_path() -> None:
    with pytest.raises(FileNotFoundError, match="RDF file not found"):
        SPARQLSession.from_rdf_file(REALWORLD_DATA / "missing.ttl")
