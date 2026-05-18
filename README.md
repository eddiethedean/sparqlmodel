# SparqlModel

**SparqlModel — the SQLModel of SPARQL:** typed models, a persistent session, and Python queries that compile to SPARQL.

SparqlModel is a **session-first SPARQL ORM** built on **[TripleModel](https://github.com/eddiethedean/triplemodel)** (`triplemodel>=0.9`). TripleModel owns Pydantic ↔ RDF mapping, terms, and file I/O. SparqlModel owns everything application-shaped: **`SPARQLSession`**, the query DSL, stores, cascade policy, and hydration depth.

You do not choose between them for the same job: **apps use SparqlModel**; **libraries and ETL use TripleModel** when there is no session.

## Who this is for

- FastAPI and backend developers building knowledge-graph APIs
- Teams that want SQLModel-style ergonomics over SPARQL endpoints
- Applications that need CRUD, filters, relationship loading, and unit-of-work semantics

**Not for:** ontology editing, reasoning, or stateless Turtle round-trips without a session (use TripleModel directly).

## Install

```bash
pip install sparqlmodel
```

Pulls in **`triplemodel>=0.9`** automatically.

Development:

```bash
pip install -e ".[dev]"
# optional: editable TripleModel while hacking both packages
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

The ORM does not require export helpers. Prefer TripleModel when the task is file I/O without a session. From a session model today:

```python
from sparqlmodel.serializers import export_model
print(export_model(odos, format="turtle"))
```

SparqlModel serializers are being replaced by thin wrappers over TripleModel `parse` / `serialize` — see [roadmap](docs/ROADMAP.md).

## What SparqlModel owns

| Area | Examples |
|------|----------|
| **Session** | `add`, `put`, `delete`, `get`, `query`, `execute` |
| **Query DSL** | `session.query(Person).where(Person.name == "x")` |
| **SPARQL compiler** | `==`, `!=`, `&`, nested hops → SPARQL |
| **Hydration** | `get(..., depth=0\|1\|2)` |
| **Persistence policy** | Composition cascade, orphan cleanup, `add` vs `put` |
| **Stores** | `MemoryStore`; HTTP SPARQL (roadmap) |

## What TripleModel owns (via dependency)

| Area | Examples |
|------|----------|
| **Mapping** | Literals, XSD types, subject IRIs, nested embeds |
| **Graph sync** | `to_graph`, `sync_to_graph`, `from_graph` |
| **Files** | `parse`, `serialize`, Turtle, JSON-LD, N-Quads |
| **Terms** | `python_to_term`, registries, language tags |

SparqlModel **0.1.x** still contains interim code in `graph.py` and `serializers.py` that duplicates some TripleModel behavior. New mapping work lands in **TripleModel first**; SparqlModel wires it in — see [integration roadmap](docs/ROADMAP.md).

## Persistence and queries

- **`put`** — upsert with composition cascade and orphan cleanup; `IRI`-only links are not cascade-deleted
- **`add`** — insert only; repeat `add` can leave stale literals
- **`delete`** — same cascade rules as `put` for owned triples
- **Filters** — `==` / `!=`; combine with `.where(a, b)` or `(a) & (b)`; see [SPECS.md](docs/SPECS.md)

## SparqlModel vs TripleModel

| I need… | Use |
|---------|-----|
| An app with CRUD, queries, cascade | **SparqlModel** |
| `where(Model.field == x)` → SPARQL | **SparqlModel** |
| Correct triples, parse, serialize, no session | **[TripleModel](https://github.com/eddiethedean/triplemodel)** |

[ORM guide](docs/ORM.md) · [Ecosystem](docs/ECOSYSTEM.md) · [Roadmap](docs/ROADMAP.md)

## Stack

```text
SPARQLSession · Query · Compiler · Stores   ← SparqlModel (ORM)
        ↓
triplemodel>=0.9 · terms · parse/serialize  ← TripleModel (required)
        ↓
rdflib · pydantic
```

## Roadmap (summary)

| Release | SparqlModel (ORM) | TripleModel wiring |
|---------|-------------------|-------------------|
| **Now** | Session, query, cascade; `triplemodel>=0.9` required | Interim `graph.py` — retire through 0.3–0.4 |
| **0.2** | `HttpStore`, identity map, FastAPI | `_triple` adapter; contract tests |
| **0.3** | ORM API frozen | `put`/`get` via `sync_to_graph` / `from_graph` |
| **0.4** | Session + SPARQL only | Delegated `parse` / `serialize` |

Full detail: [docs/ROADMAP.md](docs/ROADMAP.md)

## Documentation

- [ORM guide](docs/ORM.md) — start here
- [Technical specification](docs/SPECS.md)
- [Project plan](docs/PLAN.md)
- [Roadmap](docs/ROADMAP.md)
- [Ecosystem boundaries](docs/ECOSYSTEM.md)
- [Changelog](CHANGELOG.md)

## License

MIT — see [LICENSE](LICENSE).
