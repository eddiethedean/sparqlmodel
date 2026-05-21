#!/usr/bin/env python3
"""DCAT data catalog: discover datasets and SPARQL endpoints with the query DSL.

Problem: governments and EU institutions publish metadata as DCAT/DCAT-AP so
users can find datasets and SPARQL/HTTP distributions before downloading data.

Data: ``examples/realworld/data/dcat_nobel_catalog.ttl``
"""

from __future__ import annotations

from pathlib import Path

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession

DATA_DIR = Path(__file__).resolve().parent / "data"

DCAT = "http://www.w3.org/ns/dcat#"
DCT = "http://purl.org/dc/terms/"
PREFIXES = {"dcat": DCAT, "dct": DCT}


class DataCatalog(SPARQLModel):
    rdf_type = "dcat:Catalog"
    __prefixes__ = PREFIXES

    id: IRI
    title: str = Field("dct:title")
    description: str | None = Field("dct:description", default=None)


class Dataset(SPARQLModel):
    rdf_type = "dcat:Dataset"
    __prefixes__ = PREFIXES

    id: IRI
    title: str = Field("dct:title")
    description: str | None = Field("dct:description", default=None)
    keyword: str | None = Field("dcat:keyword", default=None)


class Distribution(SPARQLModel):
    rdf_type = "dcat:Distribution"
    __prefixes__ = PREFIXES

    id: IRI
    title: str = Field("dct:title")
    access_url: IRI = Field("dcat:accessURL")


def main() -> None:
    with SPARQLSession.from_rdf_file(
        DATA_DIR / "dcat_nobel_catalog.ttl", prefixes=PREFIXES
    ) as session:
        catalogs = session.query(DataCatalog).all()
        datasets = session.query(Dataset).all()
        distributions = session.query(Distribution).all()

        print(f"Catalog: {catalogs[0].title}")
        for ds in datasets:
            print(f"  Dataset: {ds.title}")
            if ds.keyword:
                print(f"    Keyword: {ds.keyword}")
        for dist in distributions:
            print(f"  Distribution: {dist.title}")
            print(f"    accessURL: {dist.access_url}")

        sparql_dist = session.query(Distribution).where(
            Distribution.access_url == IRI("http://data.nobelprize.org/sparql")
        ).first()
        assert sparql_dist is not None
        assert "Nobel prize" in (datasets[0].keyword or "")
        print("DCAT catalog query OK")


# Example output:
# Catalog: Nobel Media Dataset catalog
#   Dataset: Linked Nobel prizes
#     Keyword: Nobel prize
#   Distribution: Nobel Prize SPARQL endpoint
#     accessURL: http://data.nobelprize.org/sparql
# DCAT catalog query OK

if __name__ == "__main__":
    main()
