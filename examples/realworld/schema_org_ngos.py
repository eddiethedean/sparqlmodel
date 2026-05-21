#!/usr/bin/env python3
"""Schema.org NGOs: nonprofit registry records via session query and get.

Problem: transparency portals publish organization metadata with schema.org;
map it into Pydantic models for validation and filter with the ORM query DSL.

Data: ``examples/realworld/data/schema_org_ngos.ttl``
"""

from __future__ import annotations

from pathlib import Path

from sparqlmodel import IRI, Field, SPARQLModel, SPARQLSession

DATA_DIR = Path(__file__).resolve().parent / "data"

SCHEMA = "https://schema.org/"


class NgoOrganization(SPARQLModel):
    rdf_type = "schema:NGO"
    __prefixes__ = {"schema": SCHEMA, "xsd": "http://www.w3.org/2001/XMLSchema#"}

    id: IRI
    name: str = Field("schema:name")
    url: str = Field("schema:url")
    nonprofit_status: str | None = Field("schema:nonprofitStatus", default=None)
    founding_year: int | None = Field("schema:foundingDate", default=None)


def main() -> None:
    with SPARQLSession.from_rdf_file(DATA_DIR / "schema_org_ngos.ttl") as session:
        ngos = session.query(NgoOrganization).all()
        print(f"Loaded {len(ngos)} NGO records")
        for org in sorted(ngos, key=lambda o: o.name):
            founded = org.founding_year if org.founding_year is not None else "n/a"
            print(f"  {org.name} (founded {founded}) — {org.url}")

        wwf = session.get(NgoOrganization, IRI("https://example.org/org/wwf"))
        assert wwf is not None
        ttl = wwf.serialize(format="turtle")
        assert "World Wide Fund" in ttl or "schema:name" in ttl

        with_status = session.query(NgoOrganization).where(
            NgoOrganization.nonprofit_status == "NonprofitANBI"
        ).all()
        assert len(with_status) == len(ngos)
        print("Schema.org NGO session OK")


# Example output:
# Loaded 3 NGO records
#   International Committee of the Red Cross (founded 1863) — https://www.icrc.org/
#   Médecins Sans Frontières (founded n/a) — https://www.msf.org/
#   World Wide Fund for Nature (founded 1961) — https://www.worldwildlife.org/
# Schema.org NGO session OK

if __name__ == "__main__":
    main()
