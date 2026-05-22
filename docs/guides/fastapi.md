# FastAPI integration

Install the optional extra:

```bash
pip install "sparqlmodel[fastapi]"
```

Pattern: **one shared store** on the application, **one session per request** — same as SQLAlchemy.

## HttpStore + lifespan

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from sparqlmodel import IRI, SPARQLModel, Field
from sparqlmodel.fastapi import SessionDep, http_store_lifespan, negotiated_response

class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}
    id: IRI
    name: str = Field("schema:name")

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with http_store_lifespan(
        app,
        "http://localhost:3030/ds/sparql",
        max_retries=2,
        query_method="get",
    ):
        yield

app = FastAPI(lifespan=lifespan)

@app.get("/people/{iri:path}")
def get_person(iri: str, request: Request, session: SessionDep):
    model = session.get(Person, IRI(iri), depth=0)
    if model is None:
        raise HTTPException(status_code=404)
    return negotiated_response(request, model)
```

| Symbol | Role |
|--------|------|
| `http_store_lifespan` | Creates shared `HttpStore`, registers on `app.state`, closes on shutdown |
| `SessionDep` | `Annotated[SPARQLSession, Depends(get_session)]` — opens session per request |
| `negotiated_response` | Turtle / JSON-LD from `Accept` header |
| `turtle_response` / `jsonld_response` | Fixed-format helpers |

## In-memory store (tests)

```python
from sparqlmodel.fastapi import init_app
from sparqlmodel.stores.memory import MemoryStore

app = FastAPI()
init_app(app, MemoryStore())

@app.get("/health")
def health(session: SessionDep):
    return {"ok": True}
```

`init_app` sets `close_on_exit=False` so the shared store outlives each request.

## Request lifecycle

1. Dependency opens `with SPARQLSession(store=app.state.sparql_store, close_on_exit=False)` (or `sparql_async_store` for async apps).
2. Route handler runs `put` / `query` / `get`.
3. On success: pending `put(..., flush=False)` is flushed.
4. On error: pending queue is rolled back (flushed data remains).

```{warning}
Do not share one `SPARQLSession` across concurrent requests. Inject `SessionDep` per handler.

With `init_app` / `http_store_lifespan`, prefer `SessionDep` or `get_session` (they keep `close_on_exit=False` on the shared store). Do not override with `session_dependency(close_on_exit=True)` when using a shared `HttpStore` — that would close the HTTP client after the first request.
```

## Scoped session pattern (0.9+)

SparqlModel does not ship a `scoped_session()` factory. Use the same pattern as SQLAlchemy + FastAPI:

| Piece | Role |
|-------|------|
| `app.state.sparql_store` | One `HttpStore` / `MemoryStore` for the process (via `init_app` or `http_store_lifespan`) |
| `SessionDep` / `AsyncSessionDep` | One session per request; `close_on_exit=False` on the shared store |
| `merge` / `refresh` / `expunge` | Optional cache control inside a long handler or background job (see {doc}`sessions`) |

Scripts can use `with SPARQLSession(store=shared_store, close_on_exit=False) as session:` per unit of work, or open a new session per thread when sharing a store across threads (sessions are not thread-safe).

## Content negotiation

`negotiated_response(request, model)` inspects `Accept` and returns Turtle or JSON-LD. For APIs that always return JSON-LD, call `jsonld_response(model)` directly.

The optional `formats` argument is a map of **media type strings to negotiate** (dict keys only). Values are reserved for future use and are ignored today; serialization format is resolved from the winning media type via TripleModel `infer_format`.

## Testing

Use `MemoryStore` + `TestClient`:

```python
from fastapi.testclient import TestClient

init_app(app, MemoryStore())
client = TestClient(app)
```

Seed data with `session.put` inside routes or a fixture that uses `SessionDep` override (standard FastAPI dependency overrides).

## Async routes (0.6+)

Install `sparqlmodel[http]` for `AsyncHttpStore` (uses `httpx.AsyncClient`). Async HTTP shares the **`[http]`** extra — there is no separate `[async]` package.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sparqlmodel import IRI, SPARQLModel, Field
from sparqlmodel.fastapi import AsyncSessionDep, async_http_store_lifespan

class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}
    id: IRI
    name: str = Field("schema:name")

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_http_store_lifespan(app, "http://localhost:3030/ds/sparql"):
        yield

app = FastAPI(lifespan=lifespan)

@app.get("/people/{iri:path}")
async def get_person(iri: str, session: AsyncSessionDep):
    return await session.get(Person, IRI(iri), depth=0)
```

| Symbol | Role |
|--------|------|
| `async_http_store_lifespan` | Shared `AsyncHttpStore` on `app.state`, `aclose` on shutdown |
| `init_async_app` | Register async store for tests / in-memory apps |
| `AsyncSessionDep` | One `AsyncSPARQLSession` per request (`close_on_exit=False` when store is shared) |
| `async_session_dependency` | Custom `get_async_session` for dependency overrides |

```{warning}
Use `async def` route handlers with `AsyncSessionDep`. Keep sync `SessionDep` for sync routes only — mixing blocking `httpx.Client` I/O on the event loop will block other requests.
```

In-memory async tests:

```python
from sparqlmodel.fastapi import init_async_app
from sparqlmodel.stores.async_memory import AsyncMemoryStore

app = FastAPI()
init_async_app(app, AsyncMemoryStore())

@app.get("/health")
async def health(session: AsyncSessionDep):
    await session.put(Person(id=IRI("urn:p:1"), name="OK"))
    return {"ok": True}
```

## Next

- {doc}`sessions` — flush queue and identity map
- {doc}`../PRODUCTION` — deployment and HttpStore mirror
- {doc}`../api/fastapi` — `deps` module reference
