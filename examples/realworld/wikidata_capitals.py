#!/usr/bin/env python3
"""Wikidata capital cities: session execute + graph load (P31, not only rdf:type).

Problem: knowledge-graph pipelines (Wikidata) often use property assertions
(``wdt:P31``) instead of ``rdf:type``; combine raw SPARQL with ``from_graph``.

Data: ``examples/realworld/data/wikidata_capitals.ttl``
Source: Wikidata Q90, Q84 — CC0 1.0
"""

from __future__ import annotations

from pathlib import Path

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession

DATA_DIR = Path(__file__).resolve().parent / "data"

WD = "http://www.wikidata.org/entity/"
WIKIDATA_PREFIXES = {
    "wd": WD,
    "wdt": "http://www.wikidata.org/prop/direct/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}


class Country(SPARQLModel):
    """Wikidata item with an English label (e.g. France, United Kingdom)."""

    rdf_type = "wd:Q6256"
    __prefixes__ = WIKIDATA_PREFIXES

    id: IRI
    label_en: str | None = Field("rdfs:label", default=None)


class CapitalCity(SPARQLModel):
    """Capital city facts: label, population, country item IRI."""

    rdf_type = "wd:Q174844"
    __prefixes__ = WIKIDATA_PREFIXES

    id: IRI
    label_en: str | None = Field("rdfs:label", default=None)
    population: int = Field("wdt:P1082")
    country: IRI = Field("wdt:P17")


def main() -> None:
    with SPARQLSession.from_rdf_file(
        DATA_DIR / "wikidata_capitals.ttl", prefixes=WIKIDATA_PREFIXES
    ) as session:
        large_cities = session.execute(
            """
            PREFIX wdt: <http://www.wikidata.org/prop/direct/>
            SELECT ?city WHERE {
              wd:Q90 wdt:P1082 ?pop .
              FILTER(?pop > 2000000)
              BIND(wd:Q90 AS ?city)
            }
            """
        )
        assert len(large_cities) == 1

        capital_rows = session.execute(
            """
            PREFIX wdt: <http://www.wikidata.org/prop/direct/>
            SELECT ?city ?pop WHERE {
              ?city wdt:P31 wd:Q174844 ; wdt:P1082 ?pop .
            }
            ORDER BY DESC(?pop)
            """
        )
        cities: list[CapitalCity] = []
        for row in capital_rows:
            city = CapitalCity.from_graph(
                session.graph,
                row["city"],
                validate_type=False,
            )
            cities.append(city)

        print("European capitals (Wikidata excerpt):")
        for city in cities:
            country = Country.from_graph(
                session.graph,
                str(city.country),
                validate_type=False,
            )
            print(
                f"  {city.label_en}: population={city.population:,} "
                f"country={country.label_en} ({city.country})"
            )

        paris = next(c for c in cities if str(c.id).endswith("Q90"))
        assert paris.label_en == "Paris"
        assert paris.population == 2_103_778
        france = Country.from_graph(session.graph, str(paris.country), validate_type=False)
        assert france.label_en == "France"
        print("Paris load OK (country link via wdt:P17)")


# Example output:
# European capitals (Wikidata excerpt):
#   London: population=8,799,728 country=United Kingdom (http://www.wikidata.org/entity/Q145)
#   Paris: population=2,103,778 country=France (http://www.wikidata.org/entity/Q142)
# Paris load OK (country link via wdt:P17)

if __name__ == "__main__":
    main()
