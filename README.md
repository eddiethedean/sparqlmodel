# SparqlModel

**SparqlModel — the SQLModel of SPARQL:** typed models, a persistent session, and Python queries that compile to SPARQL.

SparqlModel is a **session-first SPARQL ORM** for RDF triple stores — not a stateless mapping library. Use it when you want `session.put`, `session.query(Model).where(...)`, and graph persistence policy in application code. For Pydantic ↔ RDF mapping and file I/O without a session, use **[TripleModel](https://github.com/eddiethedean/triplemodel)**.

## Who this is for

- FastAPI and backend developers building knowledge-graph APIs
- Teams that want SQLModel-style ergonomics over SPARQL endpoints
- Applications that need CRUD, filters, and relationship loading — not ontology editing or reasoning

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
```

### Export (optional)

ORM workflows do not require export. To serialize a model to Turtle or other formats:

```python
from sparqlmodel.serializers import export_model
print(export_model(odos, format="turtle"))
```

Interim in 0.1.x; delegates to TripleModel from 0.4+.

## ORM features (0.1.x)

### Session and CRUD

- `SPARQLSession` — in-memory store today; HTTP SPARQL on the roadmap
- `add`, `put`, `delete`, `get`, `query`, `execute`

### Query language

- `session.query(Model).where(Model.field == value)`
- SPARQL compiler — `==`, `!=`, `&`, single-hop nested filters

### Graph navigation

- Hydration — `session.get(Model, iri, depth=0|1|2)` (eager-load relationships)

### Persistence policy

- **`put`** — upsert with composition cascade and orphan cleanup for embedded models; `IRI`-only links are not cascade-deleted
- **`add`** — insert only; can leave stale literals on repeat `add`
- **`delete`** — same cascade rules as `put` for owned triples

### Serialization

- Turtle, N-Triples, RDF/XML, JSON-LD via `export_model` (interim; TripleModel from 0.4+)

### Query filters

- **`==`** / **`!=`** — see [SPECS.md](docs/SPECS.md)
- Combine with `.where(a, b)` or `(a) & (b)`
- `None` values raise `QueryError`
- Nested filters require the related `rdf:type` in the graph

### Known limitations

See [SPECS.md](docs/SPECS.md) (shared embeds, multi-valued predicates, JSON-LD paths, `ensure_id()` on export).

Tests: `.venv/bin/pytest`

## SparqlModel vs TripleModel

| I need… | Use |
|---------|-----|
| CRUD, queries, cascade in an app | **SparqlModel** |
| Python `where(Model.field == x)` → SPARQL | **SparqlModel** |
| Load Turtle / ETL without a session | **[TripleModel](https://github.com/eddiethedean/triplemodel)** |
| Stateless `to_graph()` / `from_graph()` | **TripleModel** |

Full guide: [docs/ORM.md](docs/ORM.md) · Maintainer boundaries: [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md)

## Stack

| Package | Role |
|---------|------|
| **SparqlModel** (this repo) | **ORM** — `SPARQLSession`, query DSL, stores, cascade on `put`/`delete` |
| **[TripleModel](https://github.com/eddiethedean/triplemodel)** | **Mapping substrate** — Pydantic ↔ RDF, terms, parse/serialize (required from SparqlModel 0.3) |

SparqlModel **0.1.x** includes an interim local mapper until 0.3 delegates conversion to TripleModel. The ORM API stays the same.

## Roadmap

| Release | ORM (SparqlModel) | TripleModel integration |
|---------|-------------------|-------------------------|
| **0.2** | HTTP SPARQL store, identity map, richer compiler, FastAPI | dev dependency + adapter |
| **0.3** | Public ORM API unchanged; delegate mapping | `triplemodel` required |
| **0.4+** | Session + SPARQL focus | delegate file I/O |

[docs/ROADMAP.md](docs/ROADMAP.md) · [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md)

## Documentation

- [ORM guide](docs/ORM.md)
- [Technical specification](docs/SPECS.md)
- [Project plan](docs/PLAN.md)
- [Roadmap](docs/ROADMAP.md)
- [Ecosystem (SparqlModel + TripleModel)](docs/ECOSYSTEM.md)
- [Changelog](CHANGELOG.md)

Built on [TripleModel](https://github.com/eddiethedean/triplemodel).

## License

MIT — see [LICENSE](LICENSE).
