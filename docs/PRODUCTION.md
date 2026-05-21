# SparqlModel production guide

Operator and architect guide for running SparqlModel in production. Normative API detail: {doc}`SPECS`. Feature schedule: {doc}`ROADMAP`. Task guides: {doc}`guides/fastapi`, {doc}`guides/sessions`.

---

## When to use which store

| Store | Use case |
|-------|----------|
| **MemoryStore** | Unit tests, local prototypes, single-process tools |
| **HttpStore** | Remote Fuseki/Jena/compatible SPARQL 1.1 endpoint |

Do not use `HttpStore` as a shared cache across many writers without a [mirror sync strategy](SPECS.md#httpstore) (planned **1.0**). Prefer one writer per endpoint or accept that `get` / cascade only see triples this store instance has written.

---

## HttpStore mirror model (0.2)

| Operation | Reads / writes |
|-----------|----------------|
| `put`, `delete`, `update_graph` | Remote + local mirror |
| `query`, `execute` | **Remote only** |
| `get`, `session.graph`, cascade | **Mirror only** |

**Symptom:** `execute` returns IRIs that `get` cannot load — data exists on the server but not in the mirror. **Mitigation today:** `put` through the same session/store, or use `MemoryStore` for single-process apps.

**Planned (1.0):** Separate read/write URLs, mirror reconciliation, batched updates, retries.

---

## Session per request (FastAPI)

Use one `SPARQLSession` per HTTP request — same pattern as SQLAlchemy:

```python
from sparqlmodel.fastapi import SessionDep, http_store_lifespan, init_app

# Lifespan registers shared HttpStore on app.state
# Route handlers: def handler(session: SessionDep): ...
```

- Shared **store** on `app.state`; new **session** per request.
- `close_on_exit=False` on shared stores (default via `init_app`).
- Pending `put(..., flush=False)` is flushed on successful request end; rolled back on error.

**Threading:** Do not share one `SPARQLSession` across threads. See [SPECS — Session lifecycle](SPECS.md#session-lifecycle-target-api).

**Asyncio (0.6+):** Use `AsyncSPARQLSession` with `AsyncHttpStore` in async FastAPI routes. Do not share one async session across concurrent `asyncio` tasks (same rule as sync: one session per request/task). In-memory graph work (compiler, hydration, cascade) runs synchronously on the event loop thread; only HTTP store I/O is non-blocking. For CPU-heavy batch jobs in a sync codebase, `run_in_executor` with a sync session remains valid.

---

## Pagination and sorting (planned 0.6)

**Today:** Use `.limit(n)` only.

**Target:**

```python
session.query(Person).where(...).order_by(Person.name).offset(20).limit(10).all()
total = session.query(Person).where(...).count()
```

Until **0.6**, implement offset/sort in raw SPARQL via `session.execute` or fetch-and-slice in memory for small graphs only.

---

## Identity map and caching

- After `put`, `get(Model, iri, depth=0)` returns the same instance when relationships are not materialized on the in-memory object.
- `expire(Model, iri)` clears cache for that resource.
- `depth=0` vs `depth=1` may cache separate hydrated views.

**Planned (0.9):** `refresh`, `merge`, `expunge` for explicit cache control.

---

## Validation and quality

| Concern | Today | Planned |
|---------|-------|---------|
| Write validation | Pydantic on `SPARQLModel` at construct / `put` | SHACL on `put` (**1.0**, TripleModel) — complements Pydantic |
| Load validation | Pydantic via hydration (`HydrationError` on type mismatch) | Same; multi-valued fields **0.9** |
| Query logging | None | Structured SPARQL log (**1.0**) |
| Bulk import | Repeated `put` | Bulk helpers (**1.0**) |
| Async FastAPI routes | Sync `SessionDep` (blocking) | `AsyncSessionDep` + `AsyncHttpStore` (**0.5**) |

---

## Security

- Use HTTPS for remote endpoints; configure `bearer_token` or `auth` on `HttpStore`.
- Do not pass user-controlled strings into raw `execute()` without parameterization patterns supported by your endpoint.
- Filter values in the query DSL are serialized via SparqlModel N3 helpers (`rdf_n3`) for pyoxigraph-compatible SPARQL.

---

## Monitoring checklist

- Log SPARQL execution time and HTTP status from `HttpStore` (custom middleware until **1.0**).
- Alert on mirror divergence if you use both `execute` and `get` on the same dataset.
- Track pending-queue failures after `flush()` (partial writes possible; see [SPECS limitations](SPECS.md#known-limitations)).

---

## Further reading

- [ORM.md](ORM.md) — developer guide
- [SPECS.md — Production checklist](SPECS.md#production-orm-checklist-13-ga-gate)
- [ROADMAP.md — 0.4–1.2](ROADMAP.md)
