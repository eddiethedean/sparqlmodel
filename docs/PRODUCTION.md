# SparqlModel production guide

Operator and architect guide for running SparqlModel in production. Normative API detail: {doc}`SPECS`. Feature schedule: {doc}`ROADMAP`. Task guides: {doc}`guides/fastapi`, {doc}`guides/sessions`.

---

## When to use which store

| Store | Use case |
|-------|----------|
| **MemoryStore** | Unit tests, local prototypes, single-process tools |
| **HttpStore** | Remote Fuseki/Jena/compatible SPARQL 1.1 endpoint |

Do not use `HttpStore` as a shared cache across many writers without a [mirror sync strategy](SPECS.md#httpstore). Prefer one writer per endpoint. Since **0.9.1**, `get` can CONSTRUCT-pull individual subjects into the mirror when they are missing locally; since **0.9.2**, `refresh` does the same. Since **0.12.0**, `sync_mirror()` reloads the entire default graph into the mirror via Graph Store HTTP GET.

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

**Shipped (0.11.0):** Retries, batched UPDATE, optional SELECT GET — see [HTTP resilience (0.11+)](#http-resilience-011).

**Shipped (0.12.0):** GSP `sync_mirror()` when `graph_store_url` is set — see [Mirror sync (0.12+)](#mirror-sync-012).

---

## Mirror sync (0.12+)

When another process or admin UI changes the remote dataset, reconcile the local mirror with **`sync_mirror()`** (read-only on the server):

```python
from sparqlmodel import HttpStore, SPARQLSession

store = HttpStore(
    "http://localhost:3030/myds/sparql",
    read_endpoint="http://localhost:3030/myds/sparql",
    write_endpoint="http://localhost:3030/myds/update",
    graph_store_url="http://localhost:3030/myds/data",
)
with SPARQLSession(store=store) as session:
    store.sync_mirror()
    person = session.get(Person, IRI("http://example.org/p/1"))
```

| Mechanism | Scope | When to use |
|-----------|--------|-------------|
| `pull_subjects_into_mirror([iri, ...])` | Listed subjects (CONSTRUCT) | Targeted refresh after known IRIs changed |
| `mirror_mode="remote_authoritative"` | Per `get` / `refresh` | Every read must match remote for that IRI |
| **`sync_mirror()`** | **Entire default graph** (GSP GET) | Bulk external load, admin UI edits, startup warm-cache |

**Fuseki URLs (typical):**

| Service | Path |
|---------|------|
| SPARQL query | `http://host:3030/{dataset}/sparql` |
| SPARQL update | `http://host:3030/{dataset}/update` |
| Graph Store HTTP | `http://host:3030/{dataset}/data` |

`http_common.default_graph_store_url(sparql_endpoint)` guesses `.../sparql` → `.../data`; production apps should pass an explicit `graph_store_url`.

**CI / local integration tests:** `make fuseki-up` (sets `ADMIN_PASSWORD=testadmin` and `FUSEKI_DATASET_1=sparqlmodel_test`), export `FUSEKI_BASE_URL=http://127.0.0.1:3030` and `FUSEKI_ADMIN_PASSWORD=testadmin`, then run `pytest`.

---

## HTTP resilience (0.11+)

Configure on `HttpStore` / `AsyncHttpStore` (and via `http_store_lifespan` / `async_http_store_lifespan` — kwargs forward to the store constructor):

| Parameter | Default | Notes |
|-----------|---------|--------|
| `max_retries` | `2` | Up to **3** attempts total (`0..max_retries`) |
| `retry_backoff` | `0.5` | Seconds; exponential backoff per attempt (capped at 30s) |
| `max_triples_per_update` | `500` | Chunk size for `INSERT DATA` / `DELETE DATA` per HTTP request |
| `query_method` | `"post"` | `"get"` sends SELECT via query string ([SPARQL Protocol](https://www.w3.org/TR/sparql11-protocol/#query-operation)) |

**Retries apply to:** remote SELECT (`query`), CONSTRUCT pull (`pull_subjects_into_mirror`), Graph Store GET (`sync_mirror`), and each UPDATE chunk. Retried status codes: **502**, **503**, **504**, plus `httpx` connection/timeouts. **4xx** and other errors fail immediately (no retry).

**Batched UPDATE:** `update_graph` sends all DELETE chunks first, then all INSERT chunks. The local mirror is updated **only after every remote chunk succeeds**. If chunk *k* fails after earlier chunks succeeded, the remote dataset may be partially updated; the mirror is **not** changed — treat as an operator incident and reconcile manually.

**UPDATE retries:** Retries are safe for idempotent chunks only. If the server applies an UPDATE then returns **503**, a retry may send the same `INSERT DATA` / `DELETE DATA` again. Use `max_retries=0` for sensitive writes or design remote data so duplicate chunks are harmless.

**GET SELECT:** Useful behind caches or strict read-only proxies. Very long queries can exceed URL length limits on some servers; prefer POST for large SELECT text. CONSTRUCT pull always uses POST. When `read_endpoint` already includes query parameters (for example Fuseki `default-graph-uri`), GET merges `query=` with `&` rather than adding a second `?`.

**Compact IRIs:** Pass `prefixes=` on the HTTP store (or use absolute IRIs) so `pull_subjects_into_mirror` expands `schema:Person/1` consistently in CONSTRUCT `VALUES` and mirror removal.

Set `max_retries=0` in tests or when you need immediate failure without transport retries.

---

## Mirror modes (0.10+)

Configure on `HttpStore` / `AsyncHttpStore` (and via `http_store_lifespan(..., mirror_mode=...)`):

| `mirror_mode` | When `get` / `refresh` pull from remote | Typical use |
|---------------|------------------------------------------|-------------|
| **`writer`** (default) | Only when the subject has **no** triples in the mirror | This app is the primary writer for the endpoint |
| **`remote_authoritative`** | **Every** `get` / `refresh` (CONSTRUCT + replace-on-pull) | Read replicas, admin UIs, or multi-reader apps that must see remote truth |

Replace-on-pull applies to explicit `pull_subjects_into_mirror` in both modes: outgoing mirror triples `(subject, ?, ?)` for each requested IRI are removed before remote triples are merged. Triples where the IRI appears only as object are not removed by per-subject pull; use **`sync_mirror()`** for a full-graph refresh.

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
