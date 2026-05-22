# SparqlModel production guide

Operator and architect guide for running SparqlModel in production. Normative API detail: {doc}`SPECS`. Feature schedule: {doc}`ROADMAP`. Task guides: {doc}`guides/fastapi`, {doc}`guides/sessions`.

---

## When to use which store

| Store | Use case |
|-------|----------|
| **MemoryStore** | Unit tests, local prototypes, single-process tools |
| **HttpStore** | Remote Fuseki/Jena/compatible SPARQL 1.1 endpoint |

Do not use `HttpStore` as a shared cache across many writers without a [mirror sync strategy](SPECS.md#httpstore) (full reconciliation planned **1.0**). Prefer one writer per endpoint. Since **0.9.1**, `get` can CONSTRUCT-pull individual subjects into the mirror when they are missing locally; since **0.9.2**, `refresh` does the same.

---

## HttpStore mirror model (0.2)

| Operation | Reads / writes |
|-----------|----------------|
| `put`, `delete`, `update_graph` | Remote + local mirror |
| `query`, `execute` | **Remote only** |
| `get`, `session.graph`, cascade | **Mirror only** |

**Symptom:** `execute` returns IRIs that `get` cannot load — data exists on the server but not in the mirror. **Mitigation (0.9.1+):** `get` and `refresh` (0.9.2+) attempt `pull_subjects_into_mirror` automatically; you can also call `pull_subjects_into_mirror` explicitly, `put` through the same session/store, or use `MemoryStore` for single-process apps.

**Do not mutate `session.graph` directly on `HttpStore` / `AsyncHttpStore`.** `session.graph` is the local mirror only; `add`/`remove` on it do not update the remote endpoint. `query` and `execute` still read the server, so the mirror and remote can diverge permanently. Use `session.put` / `delete` or `MemoryStore` for tests that need direct graph edits.

**Shipped (0.9.1):** Optional `read_endpoint` / `write_endpoint`, `pull_subjects_into_mirror`, auto-pull on `get`, `pyoxigraph.parse_query_results` for SELECT JSON.

**Shipped (0.9.2):** Auto-pull on `refresh`; `merge` partial-field semantics and hydration invalidation.

**Shipped (0.10.0):** Replace-on-pull (no stale predicates per IRI after pull); `mirror_mode` on HTTP stores.

**Planned (0.11–0.12):** Retries, batched UPDATE, GSP `sync_mirror()`. **Planned (1.0):** Full mirror reconciliation.

---

## Mirror modes (0.10+)

Configure on `HttpStore` / `AsyncHttpStore` (and via `http_store_lifespan(..., mirror_mode=...)`):

| `mirror_mode` | When `get` / `refresh` pull from remote | Typical use |
|---------------|------------------------------------------|-------------|
| **`writer`** (default) | Only when the subject has **no** triples in the mirror | This app is the primary writer for the endpoint |
| **`remote_authoritative`** | **Every** `get` / `refresh` (CONSTRUCT + replace-on-pull) | Read replicas, admin UIs, or multi-reader apps that must see remote truth |

Replace-on-pull applies to explicit `pull_subjects_into_mirror` in both modes: mirror triples for each requested IRI are removed before remote triples are merged.

**Authority:**

| API | Source of truth |
|-----|-----------------|
| `query`, `execute`, `Query.count()` | **Remote** endpoint |
| `get`, `refresh`, cascade, `session.graph` | **Mirror** (after any pull for that read) |

With **`writer`**, a subject already in the mirror may be stale until you call `pull_subjects_into_mirror` or the subject was never written locally (then `get` pulls once). With **`remote_authoritative`**, each `get`/`refresh` re-syncs that IRI from remote.

**Caution:** `remote_authoritative` does not flush pending `put(..., flush=False)`; avoid reading the same IRI with unflushed local writes.

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

## Pagination and sorting (0.8+)

```python
session.query(Person).where(...).order_by(Person.name).offset(20).limit(10).all()
total = session.query(Person).where(...).count()
```

`count()` hits the store with a `COUNT(DISTINCT ?root)` query and does not hydrate rows. On `HttpStore`, it uses the remote endpoint only (no mirror hydration). For list routes, prefer `.all()` with `.offset()` / `.limit()` and a separate `.count()` with the same `.where()` filters.

---

## Identity map and caching

- After `put`, `get(Model, iri, depth=0)` returns the same instance when relationships are not materialized on the in-memory object.
- `expire(Model, iri)` clears cache for that resource (and drops a pending `put` for that IRI).
- `expunge(model)` / `expunge_all()` detach instances from the session without changing the store.
- `refresh(model, *, depth=0)` reloads from the store; `merge(model)` reconciles a detached instance with the identity map (no store write).
- `depth=0` vs `depth=1` may cache separate hydrated views.

---

## Validation and quality

| Concern | Today | Planned |
|---------|-------|---------|
| Write validation | Pydantic on `SPARQLModel` at construct / `put` | SHACL on `put` (**1.0**, TripleModel) — complements Pydantic |
| Load validation | Pydantic via hydration (`HydrationError` on type mismatch) | Same; multi-valued fields **1.1** |
| Query logging | None | Structured SPARQL log (**1.0**) |
| Bulk import | Repeated `put` | Bulk helpers (**1.0**) |
| Async FastAPI routes | Sync `SessionDep` (blocking) | `AsyncSessionDep` + `AsyncHttpStore` (**0.6+**) |

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
- [ROADMAP.md — Forward roadmap](ROADMAP.md#forward-roadmap-07--015)
