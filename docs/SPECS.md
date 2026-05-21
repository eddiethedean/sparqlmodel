# SparqlModel Technical Specification

## Overview

This document specifies the **SparqlModel ORM layer**: session API, query compilation, hydration, cascade policy, and stores.

**SparqlModel — the SQLModel of SPARQL.**

**Mapping** (literals, terms, `to_graph`, `sync_to_graph`, `from_graph`, `parse`, `serialize`) is specified and implemented by **[TripleModel](https://github.com/eddiethedean/triplemodel)** `>=0.9`, a **required dependency** (Pydantic `TripleModel` classes). SparqlModel integrates TripleModel internally; application code uses `SPARQLSession` and **Pydantic v2** `SPARQLModel` unless doing stateless file I/O.

| Concern | SparqlModel | TripleModel |
|---------|-------------|-------------|
| `SPARQLSession` CRUD | Yes | No |
| Query DSL + compiler | Yes | No |
| Cascade / orphans on `put` | Yes | No |
| Hydration `depth` | Yes | No |
| Stores | Yes | No |
| Model ↔ triples, terms, files | `SPARQLModel(TripleModel)` (0.4+); thin `serializers` wrappers (0.7) | Yes |

[ORM.md](ORM.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md) · [PRODUCTION.md](PRODUCTION.md)

---

(production-orm-checklist-13-ga-gate)=

# Production ORM checklist (1.3 GA gate)

Normative checklist for declaring SparqlModel **production-ready** (version **1.3**). See [ROADMAP.md — Forward roadmap](ROADMAP.md#forward-roadmap-07--13) for milestone versions.

**Parity tiers:** **P0** = required for production HTTP/API apps; **P1** = SQLModel / [SPARQLMojo](https://pypi.org/project/sparqlmojo/) parity; **P2** = advanced RDF / ecosystem.

## P0 — Production APIs

- [x] `SPARQLModel`, `Field`, `Relationship`, `IRI`, Pydantic validation
- [x] `SPARQLSession` — `add`, `put`, `delete`, `get`, `query`, `execute`, context manager
- [x] Query filters: `==`, `!=`, `&`, `|`, ordering, `in_`, multi-hop paths; `(A & B) | C` precedence (0.2+)
- [x] `limit`, `first`, `all` with hydration `depth` 0–2
- [x] Identity map + `flush` / `rollback_pending` / `put(..., flush=False)`
- [x] `MemoryStore` and `HttpStore` (documented mirror semantics)
- [x] FastAPI `SessionDep`, `init_app`, `http_store_lifespan`
- [x] Session I/O via TripleModel (`put` / `get` / hydrate) — **0.3.0**
- [x] **Option A** — `SPARQLModel(TripleModel)`; `_triple.py` removed; `rdf_bridge` + direct `from_graph` — **0.4.0**
- [x] `AsyncSPARQLSession` — async CRUD, `async with`, `async def execute` — **0.6.0**
- [x] `AsyncStoreProtocol` + `AsyncHttpStore` (`httpx.AsyncClient`) + `AsyncMemoryStore` — **0.6.0**
- [x] `AsyncQuery` — `async def all()` / `first()`; same expression DSL as sync — **0.6.0**
- [x] FastAPI `AsyncSessionDep` + `async_http_store_lifespan` — **0.6.0**
- [x] Async/sync parity contract tests on memory and HTTP stores — **0.6.0**
- [x] `Query.offset(n)` — **0.8.0**
- [x] `Query.order_by(...)` — **0.8.0**
- [x] `Query.count()` — **0.8.0**
- [x] OPTIONAL / absence filters for nullable `Relationship | None` — **0.8.0**
- [ ] HttpStore mirror sync or remote-authoritative `get` contract — **1.0**
- [ ] Scoped session pattern documented (FastAPI + scripts) — **0.9**
- [x] Threading / asyncio concurrency model documented — **0.6** (async) + **0.9** (threads)

## P1 — SQLModel / SPARQLMojo parity

- [ ] `merge`, `refresh`, `expunge`, `expunge_all` on session — **0.9**
- [ ] Multi-valued scalar and relationship fields — **1.1** (TripleModel + SparqlModel hydrate)
- [ ] Language-tagged literals (`@lang`) — **1.1** (TripleModel)
- [ ] Polymorphic queries (`rdf:type` subclasses) — **1.1**
- [ ] HttpStore separate read/write endpoint URLs — **1.0**
- [ ] Optional SHACL validation on `put` — **1.2**
- [ ] Inverse / `back_populates` relationship navigation (where modeled) — **1.1**

## P2 — Advanced

- [ ] `session.ask(...)` or `Query.exists()` helper wrapping ASK — **1.2+**
- [ ] CONSTRUCT / DESCRIBE helpers — **1.2+**
- [ ] Named graph scope on session/store — **1.2+**
- [ ] Oxigraph or additional store backends — **1.2+**
- [ ] SPARQL federation in query layer — future

**Explicit non-goals:** OWL editor, built-in reasoner, duplicate TripleModel mapping in `graph.py`.

---

# SPARQLSession

ORM entry point. Binds a `Store` (default `MemoryStore`) and namespace registry.

```python
with SPARQLSession() as session:
    session.put(person)
    found = session.query(Person).where(Person.name == "Odos").first()
```

## Methods

| Method | Behavior |
|--------|----------|
| `add(model)` | Append triples; no removal of existing subject triples |
| `put(model, *, flush=True)` | Remove owned subjects (cascade), then write; queue when `flush=False` |
| `delete(model)` | Remove owned triples for root + embedded composition |
| `get(model_cls, iri, *, depth=0)` | Load one resource; optional relationship depth 0–2 |
| `query(model_cls)` | Return `Query` builder |
| `execute(sparql)` | Raw SELECT; auto-prefixes when configured |
| `flush()` / `rollback_pending()` | Apply or discard pending `put` queue |
| `close()` | Call `store.close()` when available |

## Context manager

On clean exit: `flush()` if the pending queue is non-empty. On exception: `rollback_pending()` when `rollback_on_error=True` (default). Always calls `close()` when `close_on_exit=True` (default). Does not undo already-flushed writes.

## Properties

- `store` — backing store
- `graph` — `triplemodel.Store` (`MemoryStore` graph, or `HttpStore` local mirror — not the remote dataset)
- `namespaces` — `NamespaceRegistry` for compiler and serialization

## Session lifecycle (target API)

**Current (0.2):** Context manager flushes pending `put` queue on success; `rollback_pending` on error; `expire(model_cls, iri)` evicts identity and hydration cache. No `merge`, `refresh`, or `expunge`. Not thread-safe.

**Target (1.2):**

| Method | Behavior |
|--------|----------|
| `merge(model)` | Attach detached/transient instance to session; reconcile with identity map |
| `refresh(model, *, depth=0)` | Reload from store; replace cached attributes |
| `expunge(model)` | Remove one instance from identity map |
| `expunge_all()` | Clear identity map and hydration cache |
| `scoped_session(...)` | Factory for request-scoped sessions (FastAPI pattern) |

**Object states (SQLAlchemy-aligned):**

```text
transient → (add|put) → pending (flush=False) → persistent (in store + identity map)
persistent → delete → (removed from store; expunge clears session)
persistent → expunge → detached (no session; may merge again)
```

**Threading:** One `SPARQLSession` per task/request unless documented otherwise; shared `HttpStore` requires external synchronization or single-writer discipline.

---

# Query builder

```python
with SPARQLSession() as session:
    session.query(Person).where(Person.name == "Odos").all()
    session.query(Person).where(Person.works_for.name == "Acme").limit(10).first()
```

- `.where(*expr)` — `CompareExpr`, `AndExpr`, or top-level `OrExpr`
- `.limit(n)` — non-negative integer
- `.offset(n)` — non-negative integer (**0.8**)
- `.order_by(field, *, desc=False)` — scalar field only; repeatable (**0.8**)
- `.count()` — returns `int`; ignores limit/offset/order_by (**0.8**)
- `.first()` — always uses `LIMIT 1`; ignores any prior `.limit()` or `.offset()` on the same query
- `.use_not_exists_for_ne()` — compile `!=` with `NOT EXISTS` (default since 0.5.2)
- `.use_inequality_for_ne()` — legacy inequality `!=` (pre-0.5.2 default)
- `.all(*, depth=0)` / `.first(*, depth=0)` — execute and hydrate

## Query builder (target API)

**Current (0.8):** `.offset(n)`, `.order_by(field, *, desc=False)`, `.count()` (ignores limit/offset/order_by). `.first()` always `LIMIT 1` and ignores `.limit()` / `.offset()`. Nullable relationship hops use `OPTIONAL`; `relationship.is_(None)` / `is_not(None)` for absence/presence. No `distinct` or field projection.

**Target (post-1.3):**

| Method | SPARQL |
|--------|--------|
| `.distinct()` | `DISTINCT` projection (if supported) |

**Precedence:** Python `&` binds tighter than `|`; `(A & B) | C` is two disjuncts (fixed 0.2).

---

# SPARQL compilation

`Person.name == "Odos"` → SPARQL triple patterns bound to `?person`.

| Operator | Semantics |
|----------|-----------|
| `==` | Pattern match |
| `!=` | `NOT EXISTS` by default (or `Query.use_inequality_for_ne()` for legacy inequality) |
| `&` | Conjoin patterns (`AndExpr` or multiple `.where`) |
| `\|` | Disjunction via `FILTER` + `EXISTS` branches (`OrExpr`) |
| `<`, `>`, `<=`, `>=` | Ordering on bound literal variables |
| `.in_(tuple)` / `.in_(list)` | `FILTER(?var IN (...))` — bare `str` raises `QueryError` (use `("value",)` or `["value"]`) |
| `None` | Raises `QueryError` |

Nested attribute paths (`Person.works_for.located_in.name`) support arbitrary hop length via join variables and related-type patterns.

Implementation: `compiler.py` — **SparqlModel only**; TripleModel does not compile Python filters.

---

# Hydration

```python
with SPARQLSession() as session:
    session.get(Person, iri, depth=2)
    session.query(Person).where(...).all(depth=1)
```

| `depth` | Loads |
|---------|--------|
| `0` | Scalars on root |
| `1` | One hop of `Relationship` fields |
| `2` | Two hops |

`validate_depth` rejects values outside 0–2.

**Integration note (0.3.x):** scalar and relationship loading uses `sparql_from_graph` → TripleModel `from_graph` via interim `_triple.py`. **0.4+:** `SPARQLModel.from_graph` on the unified subclass + SparqlModel depth hydration.

---

# SPARQLModel

ORM entity base class. SQLModel-style declaration:

```python
class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
```

- Metaclass enables `Person.name == "x"` in queries (`FieldRef`)
- `ensure_id()` assigns `urn:uuid:…` when `id` is unset
- JSON-LD helpers: `model_dump_jsonld` / `model_validate_jsonld` (ORM dict API; file JSON-LD via `serialize` — **0.7**)
- **Subclasses `TripleModel`** (Option A, **0.4+**); merged metaclass for query `FieldRef`
- `model_config` uses `extra="forbid"`
- `Field` / `Relationship` are ORM sugar over `rdf_field` / `Predicate` (built at class creation, no `exec`)

**Interim (0.3.x):** dynamic shadow `TripleModel` classes via `sparqlmodel._triple` — **removed in 0.4**.

See also {doc}`guides/models` for application patterns.

## Validation architecture

Three layers; all are complementary, not interchangeable.

| Layer | When | Mechanism |
|-------|------|-----------|
| **Application (Pydantic)** | `SPARQLModel(...)` / `model_validate` | Field types, `Field` constraints, `extra="forbid"` |
| **Mapping (TripleModel)** | `from_graph(..., validate_type=True)` | Expected `rdf:type` on subject; literal coercion per field |
| **Graph shapes (optional)** | `put` — **1.1** | SHACL via `triplemodel[shacl]`; after Pydantic passes |

**Write path (0.4+):** validated `SPARQLModel` → cascade in `graph.py` → `sync_to_graph(model, store.graph, …)`.

**Write path (0.3.x interim):** validated `SPARQLModel` → `to_triplemodel` → `TripleModel.model_validate` → `sync_to_graph`.

**Read path (0.4+):** graph → `SPARQLModel.from_graph` → optional depth hydration → identity map; Pydantic `ValidationError` surfaced as `HydrationError`.

**Planning rule:** new ORM features should extend Pydantic annotations and `Field` kwargs before adding ad-hoc validation in session or compiler code. See {doc}`ROADMAP` (Pydantic-first).

---

# Relationships

```python
works_for: Organization | None = Relationship("schema:worksFor", model=Organization)
```

| Value type | Semantics |
|------------|-----------|
| Embedded `SPARQLModel` | Composition — cascade on `put`/`delete` |
| `IRI` | Reference — no cascade delete of target |

## Relationships and hydration (target API)

**Current (0.2):** Single object per predicate on load; `depth` 0–2 eager-loads `Relationship` fields; composition cascade on `put`/`delete`.

**Target (1.0):**

- `list[T]` / collection fields for multi-valued literals and IRIs (via TripleModel) — **1.0**
- Language-tagged fields (`LangString`, multi-lang maps) — **1.0** (TripleModel)
- Polymorphic `session.query(Base).where(...)` matching subclasses — **1.0**
- Compiler emits `OPTIONAL` for nullable relationship paths in filters — **0.8.0**
- Optional `Relationship(..., back_populates=...)` for inverse navigation — **1.0**

---

# Persistence policy

SparqlModel-specific; orchestrates **which subjects** TripleModel (or interim `graph.py`) syncs.

## `put`

1. Compute `cascade_subjects_for_removal` (root, nested embeds, orphans on relationship change)
2. Remove `owned_triples_for_subjects` from store graph
3. Add current model graph (`model_to_graph` → future: TripleModel export + cascade)

## `delete`

Remove owned triples for cascade subject set (no re-add).

## Ownership rules

- Only **declared** predicates + `rdf:type` are owned
- Extension triples on a subject are not removed by `put`/`delete`
- Orphan keys use expanded IRIs and stable `_:bnode` keys

---

# Mapping integration (TripleModel)

**Dependencies (0.5+):** `triplemodel>=0.10.0,<2`, `pyoxigraph>=0.5,<0.6` in `pyproject.toml` (no core `rdflib`).

**Today (0.7+):** `SPARQLModel(TripleModel)`; session graphs are `triplemodel.Store`; `graph.py` holds cascade/orphan policy; `rdf_bridge` owns graph I/O. `serializers.py` is thin wrappers over TripleModel `infer_format`, `load_graph`, and `serialize`.

**Target wiring (0.4+):**

| SparqlModel surface | TripleModel API |
|---------------------|-----------------|
| `put` graph write | `sync_to_graph(model, graph, mode=...)` + cascade (same instance type) |
| `get` / query load | `SPARQLModel.from_graph` + depth hydration |
| `export_model` | `to_graph().serialize(...)` or `serialize()` |
| Predicate metadata | `rdf_field`, `Predicate`, nested `class Rdf` |

Cascade orchestration **remains in SparqlModel** after wiring.

---

# HttpStore

SPARQL 1.1 over HTTP (`httpx`) with a **local mirror** ([`stores/http.py`](../src/sparqlmodel/stores/http.py)).

| Method | Target |
|--------|--------|
| `update_graph` | Remote `INSERT DATA` / `DELETE DATA`, then mirror delta on success |
| `query` / `execute` (via session) | Remote SELECT |
| `graph`, `get`, cascade/orphan | Mirror only |

External writers or SELECT-only visibility without a matching mirror update can make `get` return `None` while `execute` returns bindings. Single-writer per endpoint is assumed. If both `auth` and `bearer_token` are set, Basic auth wins.

`put` may send `DELETE DATA` followed by `INSERT DATA` in one SPARQL Update request; whether that is atomic depends on the endpoint (not guaranteed in 0.2). After `HttpStore.close()`, `query` and `update_graph` raise `RuntimeError`.

## Store protocol (target API)

**Current (0.2):** [`Store`](../src/sparqlmodel/stores/base.py) — `graph`, `query(sparql)`, `update_graph(add=, remove=)`.

**Target (1.0):**

| Capability | Notes |
|------------|--------|
| `query` | SPARQL 1.1 SELECT (required) |
| `update` | Atomic SPARQL Update sequences where endpoint supports — **1.0** |
| `ask` / `construct` | Optional protocol methods for existence and graph-shaped reads — **1.2** (P2) |
| HttpStore `read_endpoint` / `write_endpoint` | Fuseki-style split URLs — **1.0** |
| Mirror sync | GSP GET, post-query hydrate, or documented remote-authoritative mode — **1.0** |
| Retries, timeouts, batch size limits | Production HttpStore — **1.0** |
| `OxigraphStore` / embedded backends | Optional — **1.2+** |

Protocols: [SPARQL 1.1 Query](https://www.w3.org/TR/sparql11-query/), [SPARQL 1.1 Update](https://www.w3.org/TR/sparql11-update/), [Graph Store HTTP](https://www.w3.org/TR/sparql11-http-rdf-update/).

---

# Security (SPARQL generation)

**Current (0.5+):** Filter values serialized via SparqlModel N3 helpers (`rdf_n3`) on pyoxigraph terms and string IRIs. IRIs with invalid characters raise `QueryError`. Predicates come from model metadata (trusted code).

**Target (1.3 GA):**

- No public API that concatenates untrusted strings into SPARQL text
- Predicates and class IRIs remain declaration-time only
- `LIMIT` / `OFFSET` remain integer-typed at API boundary
- Security review documented before 1.3 GA

---

# Async API (target 0.6)

Parallel to the sync stack; sync API remains supported.

| Component | Sync (shipped) | Async (0.6.0) |
|-----------|----------------|-------------|
| Session | `SPARQLSession` | `AsyncSPARQLSession` |
| Store | `Store`, `MemoryStore`, `HttpStore` | `AsyncStore`, `AsyncMemoryStore`, `AsyncHttpStore` |
| Query | `Query.all()` / `first()` | `AsyncQuery` — `await .all()` / `.first()` |
| FastAPI | `SessionDep`, sync `get_session` | `AsyncSessionDep`, async `get_async_session` |

**Semantics:** Same identity map, cascade, compiler, and hydration rules as sync. One session per asyncio task (not shared across concurrent tasks). `HttpStore` uses `httpx.Client`; `AsyncHttpStore` uses `httpx.AsyncClient` with the same mirror contract.

**Non-goals for 0.6:** Replacing sync session; async TripleModel mapping APIs (unified model stays sync; in-memory graph work stays on the event loop thread).

---

# Known limitations

## Until 0.4 (unified model)

| Area | Behavior |
|------|----------|
| Dual model types | 0.3 uses interim `_triple.py` dynamic adapter; **0.4** unifies on `SPARQLModel(TripleModel)` |

## Until 1.0 (HttpStore)

| Area | Behavior |
|------|----------|
| Mirror vs remote | `get` / cascade use mirror; `query` uses remote |
| Multi-writer endpoints | External updates invisible to mirror until sync |

## Until 1.1 (mapping)

| Area | Behavior |
|------|----------|
| Multi-valued predicates | First object per predicate on load |
| Language tags | Not in public field API |
| Polymorphic queries | Single `rdf_type` per model class |

## Permanent constraints

| Area | Behavior |
|------|----------|
| Composition vs reference | Embedded `SPARQLModel` cascades; `IRI` references do not |
| Owned triples | Only declared predicates + `rdf:type` removed on `put`/`delete` |
| `add` vs `put` | `add` does not remove stale triples |
| `put(..., flush=False)` | Pending models not visible in `get` until flush |
| `flush()` | Not a full remote transaction; partial failure re-queues remainder (0.2+) |
| Sessions | Not thread-safe; one session per task unless scoped externally |
| Closed session | After `close()`, all CRUD/query methods raise `RuntimeError`; share the store via a new session |
| Interim mapping | **0.3.0:** `_triple.py` adapter; **0.4** Option A removes it; `serializers.py` thin wrappers since **0.7** |

## Other (current)

| Area | Behavior |
|------|----------|
| Duplicate predicates | Two fields with the same expanded predicate on one model class → `ConfigurationError` at class definition |
| Write-path cycles | Cyclic embedded `SPARQLModel` graphs → `ConfigurationError` on `put` / `model_to_graph` |
| Shared composition | Orphan cleanup skips embedded targets still linked from subjects outside the current put cascade |
| Pending `put` | Identity for that subject evicted when queued; `close()` with pending writes raises `RuntimeError` |
| Nested query filters | Related resource must have expected `rdf:type` |
| AND filters, same path | Compiler reuses join variables per relationship path within one WHERE / EXISTS block |
| JSON-LD | `model_dump_jsonld` vs `export_model(..., "json-ld")` differ; non-cascade embeds omitted from `model_to_jsonld` |
| Export without `id` | `ensure_id()` may assign `urn:uuid:…` |

---

# Optional: export and files

ORM workflows do not require `sparqlmodel.serializers`.

Long term: all formats via TripleModel; SparqlModel may expose session-scoped helpers only.

---

# FastAPI (optional extra)

Install `sparqlmodel[fastapi]`. [`fastapi/deps.py`](../src/sparqlmodel/fastapi/deps.py) provides `init_app`, `get_session`, `SessionDep`, `http_store_lifespan`. [`fastapi/__init__.py`](../src/sparqlmodel/fastapi/__init__.py) provides `turtle_response`, `jsonld_response`, `negotiated_response`.

---

# Feature ownership

| Feature | Owner |
|---------|--------|
| SHACL shapes / validation engine | TripleModel `[shacl]` |
| SHACL on `session.put` | SparqlModel hook calling TripleModel |
| Named graphs / Dataset | TripleModel; SparqlModel consumes |
| SPARQL federation in apps | SparqlModel |
| Alternate store backends | SparqlModel `stores/` |
| OWL reasoner | Out of scope |

---

# Maintainer boundaries

For **end users**, use [ORM.md](ORM.md). This table is for **contributors**.

| Symptom | Fix in |
|---------|--------|
| Wrong XSD / literal on export | TripleModel |
| Subject IRI collision | TripleModel |
| Stale predicate after `put` | TripleModel sync + SparqlModel cascade |
| Orphan after relationship change | SparqlModel `graph.py` |
| `!=` / nested filter wrong | SparqlModel `compiler.py` |
| New RDF format | TripleModel |
| Fuseki / HTTP store | SparqlModel `stores/` |

**Anti-patterns:** new mapping code only in `graph.py`; session/compiler in TripleModel; `triplemodel` importing `sparqlmodel`.

---

# Package layout

```text
sparqlmodel/
  session.py       # ORM unit of work
  query.py         # query builder
  compiler.py      # ORM-only
  hydration.py     # depth; → TripleModel load
  model.py         # SPARQLModel(TripleModel) — 0.4+
  fields.py        # Field/Relationship sugar → rdf_field / Predicate
  graph.py         # cascade/orphan policy only
  serializers.py   # thin TripleModel parse/serialize wrappers (0.7)
  stores/
  rdf_bridge.py    # graph I/O (Option A; replaced _triple.py in 0.4)
```

---

# Dependencies

```
pydantic>=2.5,<3
pyoxigraph>=0.5,<0.6
triplemodel>=0.10.0,<2
typing-extensions>=4.8
```

Optional: `httpx`, `fastapi`

---

# Related projects

| Project | Role |
|---------|------|
| **TripleModel** | Required mapping engine |
| **Pyoxigraph / TripleModel** | In-process graphs and SPARQL execution (`Store`) |
| **semantic-sqlmodel** | Optional future backend |
