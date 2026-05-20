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
    async with http_store_lifespan(app, "http://localhost:3030/ds/sparql"):
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

1. Dependency opens `with SPARQLSession(store=app.state.store, close_on_exit=False)`.
2. Route handler runs `put` / `query` / `get`.
3. On success: pending `put(..., flush=False)` is flushed.
4. On error: pending queue is rolled back (flushed data remains).

```{warning}
Do not share one `SPARQLSession` across concurrent requests. Inject `SessionDep` per handler.
```

## Content negotiation

`negotiated_response(request, model)` inspects `Accept` and returns Turtle or JSON-LD. For APIs that always return JSON-LD, call `jsonld_response(model)` directly.

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
