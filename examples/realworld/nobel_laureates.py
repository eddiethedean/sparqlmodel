#!/usr/bin/env python3
"""Nobel Prize linked data (1901): query laureates with :class:`~sparqlmodel.session.SPARQLSession`.

Problem: integrate biographical linked open data where resources already have
stable URIs and a published ontology (common in cultural heritage and science).

Data: ``examples/realworld/data/nobel_laureates_1901.ttl``
Source: https://www.nobelprize.org/about/linked-data-examples/
"""

from __future__ import annotations

from pathlib import Path

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession

DATA_DIR = Path(__file__).resolve().parent / "data"

NOBEL = "http://data.nobelprize.org/terms/"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
PREFIXES = {
    "nobel": NOBEL,
    "rdfs": RDFS,
    "foaf": "http://xmlns.com/foaf/0.1/",
}


class Laureate(SPARQLModel):
    """Person or organisation receiving a Nobel Prize (``nobel:Laureate``)."""

    rdf_type = "nobel:Laureate"
    __prefixes__ = PREFIXES

    id: IRI
    name: str = Field("rdfs:label")
    gender: str | None = Field("foaf:gender", default=None)


class NobelPrize(SPARQLModel):
    """Award instance for a category and year (``nobel:NobelPrize``)."""

    rdf_type = "nobel:NobelPrize"
    __prefixes__ = PREFIXES

    id: IRI
    title: str = Field("rdfs:label")
    year: str = Field("nobel:year")


def main() -> None:
    with SPARQLSession.from_rdf_file(
        DATA_DIR / "nobel_laureates_1901.ttl", prefixes=PREFIXES
    ) as session:
        laureates = session.query(Laureate).all()
        prizes = session.query(NobelPrize).all()
        print(
            f"Loaded {len(laureates)} laureates and {len(prizes)} prizes from 1901 excerpt"
        )
        for person in sorted(laureates, key=lambda m: m.name):
            print(f"  {person.name} ({person.gender})")

        roentgen = next(p for p in laureates if "Röntgen" in p.name)
        physics = session.query(NobelPrize).where(NobelPrize.year == "1901").all()
        physics_1901 = next(p for p in physics if "Physics" in p.title)
        assert physics_1901.year == "1901"

        male_laureates = session.query(Laureate).where(Laureate.gender == "male").all()
        assert roentgen in male_laureates

        loaded = session.get(Laureate, roentgen.id)
        assert loaded is not None and loaded.name == roentgen.name
        print("Round-trip OK for Wilhelm Conrad Röntgen")


# Example output:
# Loaded 6 laureates and 5 prizes from 1901 excerpt
#   Emil Adolf von Behring (male)
#   Frédéric Passy (male)
#   Jacobus Henricus van 't Hoff (male)
#   Jean Henry Dunant (male)
#   Sully Prudhomme (male)
#   Wilhelm Conrad Röntgen (male)
# Round-trip OK for Wilhelm Conrad Röntgen

if __name__ == "__main__":
    main()
