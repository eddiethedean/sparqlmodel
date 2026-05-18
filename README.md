# SparqlModel

**SparqlModel — the SQLModel of SPARQL:** typed RDF models, a persistent session, and Python filters that compile to SPARQL.

Define `SPARQLModel` classes, use `with SPARQLSession() as session:`, and work with graphs the way you would with a SQL ORM: `put` and `get`, nested relationships, a query builder, and optional remote stores.

## Install

```bash
pip install sparqlmodel
```

Optional extras:

```bash
pip install "sparqlmodel[http]"      # HttpStore (httpx)
pip install "sparqlmodel[fastapi]"   # RDF response helpers
```

Development:

```bash
pip install -e ".[dev,http,fastapi]"
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

with SPARQLSession() as session:
    session.put(odos)

    found = session.query(Person).where(Person.name == "Odos").first()
    team = session.query(Person).where(Person.works_for.name == "Acme Corp").all()
    full = session.get(Person, odos.id, depth=1)
```

## Session API

`SPARQLSession` is a context manager: on success it flushes any pending `put(..., flush=False)` writes; on error it rolls back the pending queue; it closes HTTP stores when the block ends.

| Method | Purpose |
|--------|---------|
| `add(model)` | Insert triples; does not remove existing data for the subject |
| `put(model)` | Upsert with cascade and orphan cleanup for embedded resources |
| `delete(model)` | Remove owned triples for the root and composition tree |
| `get(Model, iri, depth=0)` | Load one entity; `depth` eager-loads relationships (0–2) |
| `query(Model).where(...)` | Find entities; filters compile to SPARQL |
| `execute(sparql)` | Raw SPARQL SELECT |
| `flush()` / `rollback_pending()` | Apply or discard pending `put(..., flush=False)` writes |
| `close()` | Close the backing store when it supports `close()` |
| `expire(Model, iri)` | Evict cached instances for an IRI |

`put` treats nested `SPARQLModel` values as **composition** (cascade delete and orphan cleanup). Use `Relationship(..., cascade=False)` or an `IRI` reference when the linked resource is owned elsewhere.

## Query DSL

Filters compile to SPARQL against your store:

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
```

Supported operators include `==`, `!=`, `&`, `|`, ordering comparisons, `in_()`, and multi-hop paths through relationships.

## Stores

**In-memory** (default) — local `rdflib` graph, ideal for tests and prototypes:

```python
with SPARQLSession() as session:
    session.put(model)
```

**HTTP** — SPARQL 1.1 endpoint with a local mirror for cascade reads (`sparqlmodel[http]`):

```python
from sparqlmodel import HttpStore, SPARQLSession

with SPARQLSession(store=HttpStore("http://localhost:3030/ds/sparql")) as session:
    session.put(odos)
```

`query` / `execute` hit the remote endpoint; `get` and cascade logic use the mirror updated by this store’s writes. External changes visible only via SELECT are not visible to `get` until the mirror is updated.

## Known limitations

- **Multi-valued predicates** — first value per predicate on load; `add` can duplicate literals
- **`add` vs `put`** — `add` does not remove stale triples; prefer `put` for upserts
- **`HttpStore`** — mirror can lag behind the remote dataset (see above)
- **Shared embedded resources** — same nested object linked from multiple roots is not deduplicated in memory on load

## FastAPI

With `sparqlmodel[fastapi]`, session management mirrors SQLModel / SQLAlchemy: register a shared store on the app, inject a per-request session with `Depends`, and use `with SPARQLSession(...)` inside the dependency.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from sparqlmodel import IRI
from sparqlmodel.fastapi import SessionDep, http_store_lifespan, init_app, negotiated_response
from sparqlmodel.stores.memory import MemoryStore

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with http_store_lifespan(app, "http://localhost:3030/ds/sparql"):
        yield
    # Or for tests / in-process: init_app(app, MemoryStore()); yield

app = FastAPI(lifespan=lifespan)

@app.get("/person/{iri}")
def person(iri: str, request: Request, session: SessionDep) -> object:
    model = session.get(Person, IRI(iri))
    if model is None:
        raise HTTPException(status_code=404)
    return negotiated_response(request, model)
```

`SessionDep` is `Annotated[SPARQLSession, Depends(get_session)]`. Each request opens `with SPARQLSession(store=...) as session`, flushes on success, and rolls back pending writes on error — the same lifecycle as using a session outside FastAPI.

## Export

```python
from sparqlmodel.serializers import export_model

print(export_model(odos, format="turtle"))
```

## Documentation

- [ORM guide](docs/ORM.md) — lifecycle, cascade, hydration
- [Technical specification](docs/SPECS.md)
- [Roadmap](docs/ROADMAP.md)
- [Changelog](CHANGELOG.md)

## Ecosystem

SparqlModel installs **[TripleModel](https://github.com/eddiethedean/triplemodel)** (`triplemodel>=0.9`) as its RDF mapping engine: literals, terms, and file parse/serialize. Application code normally uses only `sparqlmodel`; reach for TripleModel directly when you need stateless Turtle/JSON-LD round-trips or library-style `to_graph` / `sync_to_graph` without a session.

See [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) for package boundaries and the integration roadmap (wiring session I/O through TripleModel in upcoming releases).

## License

MIT — see [LICENSE](LICENSE).
