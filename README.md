# SparqlModel

**SPARQL-native object graph mapper for RDF triple stores.**

SparqlModel brings SQLModel-style ergonomics to RDF: typed Pydantic models, Pythonic queries that compile to SPARQL, sessions over RDFLib (and remote stores on the roadmap), and RDF export.

## Stack

| Package | Role |
|---------|------|
| **[TripleModel](https://github.com/eddiethedean/triplemodel)** | Pydantic ↔ RDF mapping, terms, parse/serialize |
| **SparqlModel** (this repo) | `SPARQLSession`, queries, stores, cascade on `put`/`delete` |

SparqlModel **0.1.x** includes an interim local mapper; from **0.3** it depends on `triplemodel` for model ↔ triple conversion. See [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).

## Install

```bash
pip install sparqlmodel
```

Development:

```bash
pip install -e ".[dev]"
# optional, when working on TripleModel integration:
pip install -e ../triplemodel
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

found = session.query(Person).where(Person.name == "Odos").first()
team = session.query(Person).where(Person.works_for.name == "Acme Corp").all()
full = session.get(Person, odos.id, depth=1)

from sparqlmodel.serializers import export_model
print(export_model(odos, format="turtle"))
```

## Features (0.1.x)

- `SPARQLModel`, `Field`, `Relationship`, `IRI`
- `SPARQLSession` — in-memory CRUD (RDFLib)
- Query builder — `session.query(Model).where(Model.field == value)`
- SPARQL compiler — scalar and single-hop nested filters
- Hydration — `session.get(Model, iri, depth=0|1|2)`
- Serializers — Turtle, N-Triples, RDF/XML, JSON-LD (interim; TripleModel from 0.4+)

### Persistence

- **`put`** — upsert with composition cascade and orphan cleanup for embedded models; `IRI`-only links are not cascade-deleted
- **`add`** — insert only; can leave stale literals on repeat `add`
- **`delete`** — same cascade rules as `put` for owned triples

### Query filters

- **`==`** / **`!=`** — see [SPECS.md](docs/SPECS.md)
- Combine with `.where(a, b)` or `(a) & (b)`
- `None` values raise `QueryError`
- Nested filters require the related `rdf:type` in the graph

### Known limitations

See [SPECS.md](docs/SPECS.md) and the list in prior releases (shared embeds, multi-valued predicates, JSON-LD paths, `ensure_id()` on export).

Tests: `.venv/bin/pytest`

## Roadmap

| Release | SparqlModel | TripleModel |
|---------|-------------|-------------|
| **0.2** | HTTP SPARQL store, richer compiler, identity map, FastAPI | dev dependency + adapter |
| **0.3** | `triplemodel` required; thin `graph.py` | `>=0.2` |
| **0.4+** | delegate file I/O | `>=0.4` parse/serialize; `0.5` Dataset |

[docs/ROADMAP.md](docs/ROADMAP.md) · [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md)

## Documentation

- [Technical specification](docs/SPECS.md)
- [Project plan](docs/PLAN.md)
- [Roadmap](docs/ROADMAP.md)
- [Ecosystem (SparqlModel + TripleModel)](docs/ECOSYSTEM.md)
- [Changelog](CHANGELOG.md)

## License

MIT — see [LICENSE](LICENSE).
