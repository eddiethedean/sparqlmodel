# SparqlModel

**SPARQL-native object graph mapper for RDF triple stores.**

SparqlModel brings SQLModel-style ergonomics to RDF: typed Pydantic models, Pythonic queries that compile to SPARQL, in-memory persistence via RDFLib, and JSON-LD serialization.

## Install

```bash
pip install sparqlmodel
```

For development:

```bash
pip install -e ".[dev]"
```

## Quickstart

```python
from sparqlmodel import Field, IRI, Relationship, SPARQLModel, SPARQLSession

class Organization(SPARQLModel):
    rdf_type = "schema:Organization"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")

class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
    works_for: Organization | None = Relationship(
        "schema:worksFor", model=Organization
    )

acme = Organization(id=IRI("urn:org:acme"), name="Acme Corp")
odos = Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)

session = SPARQLSession()
session.put(odos)

# Query with Python expressions
found = session.query(Person).where(Person.name == "Odos").first()
print(found.name)  # Odos

# Nested filter (single relationship hop)
team = session.query(Person).where(Person.works_for.name == "Acme Corp").all()

# Hydrate relationships
full = session.get(Person, odos.id, depth=1)
print(full.works_for.name)  # Acme Corp

# Export RDF
from sparqlmodel.serializers import export_model

print(export_model(odos, format="turtle"))
```

## Features (0.1.0)

- `SPARQLModel` — Pydantic v2 models mapped to RDF predicates
- `SPARQLSession` — in-memory CRUD against an RDFLib graph
- Query builder — `session.query(Model).where(Model.field == value)`
- SPARQL compiler — scalar and single-hop nested filters
- Graph hydration — `session.get(Model, iri, depth=0|1|2)`
- Serializers — Turtle, N-Triples, RDF/XML, JSON-LD

## Roadmap (0.2)

- HTTP SPARQL 1.1 endpoint store (`httpx`)
- FastAPI optional integration
- Identity map and session caching
- Richer query compiler (OR, numeric/date comparisons)

## Documentation

- [Technical specification](docs/SPECS.md)
- [Project plan](docs/PLAN.md)

## License

MIT — see [LICENSE](LICENSE).
