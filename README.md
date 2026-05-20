# SparqlModel

[![PyPI version](https://img.shields.io/pypi/v/sparqlmodel.svg)](https://pypi.org/project/sparqlmodel/)
[![Python](https://img.shields.io/pypi/pyversions/sparqlmodel.svg)](https://pypi.org/project/sparqlmodel/)
[![Documentation](https://readthedocs.org/projects/sparqlmodel/badge/?version=latest)](https://sparqlmodel.readthedocs.io/en/latest/?badge=latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/eddiethedean/sqarqlmodel/blob/main/LICENSE)

**The SQLModel of SPARQL** — **Pydantic v2** entity models mapped to RDF, a persistent session, and Python filters that compile to SPARQL.

Build knowledge-graph and metadata apps with typed `SPARQLModel` classes, `with SPARQLSession() as session:`, and ORM-style `put`, `get`, nested relationships, and a query builder — on in-memory graphs or remote SPARQL 1.1 endpoints. Same validation ergonomics as FastAPI and SQLModel: invalid data fails at construction and on load, before bad triples reach the store.

**Requires Python 3.10+** · Built on [TripleModel](https://github.com/eddiethedean/triplemodel) 0.10 + **pyoxigraph** · [Changelog](https://github.com/eddiethedean/sqarqlmodel/blob/main/CHANGELOG.md#050---2026-05-18) (0.5.0)

---

## Features

| Area | What you get |
|------|----------------|
| **Models** | `SPARQLModel`, `Field`, `Relationship`, `IRI` — **Pydantic v2** validation (`model_validate`, constraints, `extra="forbid"`) |
| **RDF mapping** | `rdf_type`, compact predicates, TripleModel `sync_to_graph` / `from_graph` under the hood |
| **Session** | `add`, `put`, `delete`, `get`, identity map, `flush` / pending queue |
| **Queries** | `session.query(Person).where(Person.name == "x")` → SPARQL (`&`, `\|`, `in_`, comparisons, multi-hop) |
| **Stores** | `MemoryStore` (default), `HttpStore` for Fuseki/Jena-style endpoints |
| **FastAPI** | `SessionDep`, `http_store_lifespan`, Turtle/JSON-LD responses |
| **Cascade** | Composition on `put`/`delete`; `Relationship(..., cascade=False)` for references |

---

## Install

```bash
pip install sparqlmodel
```

```bash
pip install "sparqlmodel[http]"      # HttpStore (httpx)
pip install "sparqlmodel[fastapi]"   # FastAPI session + RDF responses
pip install -e ".[dev,http,fastapi]" # development
```

---

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

with SPARQLSession() as session:
    session.put(odos)

    found = session.query(Person).where(Person.name == "Odos").first()
    team = session.query(Person).where(Person.works_for.name == "Acme Corp").all()
    full = session.get(Person, odos.id, depth=1)
```

---

## Pydantic models

`SPARQLModel` subclasses [`pydantic.BaseModel`](https://docs.pydantic.dev/latest/). You get the same advantages as in FastAPI or SQLModel: typed fields, IDE support, and validation on create and on load.

| When | What runs |
|------|-----------|
| `Person(...)` / API body | Pydantic validates types and `Field` constraints |
| `session.put(model)` | Validated instance → `sync_to_graph` (0.4+: same `SPARQLModel` instance subclasses `TripleModel`) |
| `session.get` / query hydration | Graph → `model_validate` → `SPARQLModel` instance |

```python
# Field forwards pydantic.Field kwargs (min_length, ge, description, …)
class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}
    id: IRI
    name: str = Field("schema:name", min_length=1)
```

- **`extra="forbid"`** — unknown fields on a model raise at validation time (safer for APIs).
- **FastAPI** — reuse the same `SPARQLModel` classes for request/response bodies (see [FastAPI](#fastapi) below).
- **JSON-LD** — `model_dump_jsonld()` / `model_validate_jsonld()` on each model (serializers delegate to TripleModel; prefer TripleModel `load_graph` / `dump_graph` for file I/O).

Details: [Models guide](https://sparqlmodel.readthedocs.io/en/latest/guides/models.html) · [ORM guide](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ORM.md#pydantic-integration)

---

## Session

`SPARQLSession` is the unit of work. Use it as a context manager: flush pending writes on success, roll back the pending queue on error, close HTTP stores when done.

| Method | Purpose |
|--------|---------|
| `add(model)` | Append triples (no delete of existing subject data) |
| `put(model)` | Upsert with cascade and orphan cleanup |
| `delete(model)` | Remove owned triples for root + composition tree |
| `get(Model, iri, depth=0)` | Load one resource; `depth` 0–2 eager-loads relationships |
| `query(Model).where(...)` | Fluent query; filters compile to SPARQL |
| `execute(sparql)` | Raw SPARQL SELECT (auto-prefixes when configured) |
| `flush()` / `rollback_pending()` | Apply or discard `put(..., flush=False)` queue |
| `expire(Model, iri)` | Evict identity map and hydration cache |

Nested `SPARQLModel` values are **composition** (cascade on `put`/`delete`). Use `Relationship(..., cascade=False)` or an `IRI` when the target is owned elsewhere.

---

## Query DSL

```python
with SPARQLSession() as session:
    session.query(Person).where(Person.name == "Odos").all()

    session.query(Person).where(
        (Person.name == "Odos") | (Person.name == "Ada")
    ).all()

    session.query(Person).where(
        Person.works_for.located_in.name == "Boston"
    ).all(depth=2)

    session.query(Person).where(Person.name.in_(("Odos", "Ada"))).all()

    session.query(Person).where(Person.name != "Other").use_not_exists_for_ne().all()
    # or .use_optional_for_comparisons() for NOT EXISTS semantics on !=
```

Operators: `==`, `!=`, `&`, `|`, `<`, `>`, `<=`, `>=`, `.in_(tuple)` (also accepts lists), multi-hop paths (`Person.works_for.name`), `.limit(n)`, `.use_not_exists_for_ne()`, `.use_optional_for_comparisons()`.

---

## Stores

**MemoryStore** (default) — in-memory `triplemodel.Store` (pyoxigraph); tests and single-process apps:

```python
with SPARQLSession() as session:
    session.put(model)
```

**HttpStore** — SPARQL 1.1 over HTTP with a local mirror for `get` and cascade (`sparqlmodel[http]`):

```python
from sparqlmodel import HttpStore, SPARQLSession

with SPARQLSession(store=HttpStore("http://localhost:3030/ds/sparql")) as session:
    session.put(odos)
```

`query` / `execute` use the remote endpoint; `get` and cascade read the mirror updated by this store’s writes. See the [production guide](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/PRODUCTION.md) for mirror semantics and deployment notes.

---

## FastAPI

Per-request sessions with a shared store — same pattern as SQLModel + SQLAlchemy:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from sparqlmodel import IRI
from sparqlmodel.fastapi import SessionDep, http_store_lifespan, negotiated_response

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with http_store_lifespan(app, "http://localhost:3030/ds/sparql"):
        yield

app = FastAPI(lifespan=lifespan)

@app.get("/person/{iri}")
def person(iri: str, request: Request, session: SessionDep) -> object:
    model = session.get(Person, IRI(iri))
    if model is None:
        raise HTTPException(status_code=404)
    return negotiated_response(request, model)
```

---

## Export

```python
from sparqlmodel.serializers import export_model

print(export_model(odos, format="turtle"))
```

Long term, file I/O moves to [TripleModel](https://github.com/eddiethedean/triplemodel) `parse` / `serialize`; see the [roadmap](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ROADMAP.md).

---

## Documentation

| Guide | Description |
|-------|-------------|
| **[Read the Docs](https://sparqlmodel.readthedocs.io/en/latest/)** | Full site: install, guides, API reference, troubleshooting |
| [Getting started](https://sparqlmodel.readthedocs.io/en/latest/getting-started.html) | Quickstart and first session |
| [Guides](https://sparqlmodel.readthedocs.io/en/latest/guides/index.html) | Models (Pydantic), sessions, queries, FastAPI |
| [ORM guide](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ORM.md) | Lifecycle, cascade, hydration, when to use SparqlModel vs TripleModel |
| [Technical specification](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/SPECS.md) | Normative API; [production checklist](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/SPECS.md#production-orm-checklist-12-ga-gate) |
| [Production guide](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/PRODUCTION.md) | HttpStore, sessions, deployment |
| [Roadmap](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ROADMAP.md) | 0.5–1.3 milestones; [SQLModel parity](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ROADMAP.md#sqlmodel-parity-checklist) |
| [Project plan](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/PLAN.md) | Vision and release strategy |
| [Ecosystem](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ECOSYSTEM.md) | SparqlModel vs TripleModel boundaries |

---

## Known limitations (0.5)

- Multi-valued predicates: first value per predicate on load; prefer `put` over `add` for upserts
- `HttpStore`: mirror may lag behind the remote dataset for `get` / cascade (production mirror sync planned **1.0**)
- No async session or `AsyncHttpStore` yet — planned **0.6** ([roadmap](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ROADMAP.md))
- Query: `limit` only — `offset` / `order_by` / `count` planned **0.8** ([roadmap](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ROADMAP.md))
- `session.graph` is a `triplemodel.Store` (pyoxigraph), not an rdflib `Graph` — use TripleModel I/O for file round-trip
- Default `!=` excludes resources with no value for the field; use `.use_not_exists_for_ne()` or `.use_optional_for_comparisons()`
- Sessions are not thread-safe; one session per request/task
- Each model field must map to a unique RDF predicate; duplicate predicates raise `ConfigurationError` at class definition
- Cyclic embedded models raise `ConfigurationError` on `put` / `model_to_graph`
- Shared embedded resources referenced from multiple roots are preserved on `put` when another subject still links to them

---

## License

MIT — see [LICENSE](https://github.com/eddiethedean/sqarqlmodel/blob/main/LICENSE).
