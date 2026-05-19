# SparqlModel Roadmap

SparqlModel is **the SQLModel of SPARQL** — a session-first ORM. **TripleModel** (`triplemodel>=0.9`, required) is the mapping engine. This roadmap covers **ORM features**, **Option A** (`SPARQLModel` subclasses `TripleModel`), and retiring interim integration code (`_triple.py`, duplicate serializers).

- [ORM guide](ORM.md) — application developers
- [SPECS.md](SPECS.md) — technical spec
- [ECOSYSTEM.md](ECOSYSTEM.md) — boundaries
- [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md) — upstream
- [ASYNC_RDF_RUST_PLAN.md](ASYNC_RDF_RUST_PLAN.md) — optional Rust async I/O package (companion to **0.5**)

---

## North star

**SparqlModel builds apps. TripleModel builds correct graphs.**

**Single model class (Option A):** `SPARQLModel` **subclasses** `TripleModel`. `Field` and `Relationship` are ORM sugar; session I/O calls `sync_to_graph` / `from_graph` on the **same** instances. The 0.3 `_triple.py` dynamic adapter is removed in **0.4**.

**1.2** = production SPARQL ORM GA (SQLModel of SPARQL) — [SPECS production checklist](SPECS.md#production-orm-checklist-12-ga-gate).

| Layer | Responsibility |
|-------|----------------|
| **SparqlModel** | `SPARQLSession`, query DSL, compiler, stores, cascade, hydration `depth` |
| **TripleModel** | Terms, `sync_to_graph`, `from_graph`, `parse`, `serialize`, Dataset |

**Dependency:** `triplemodel>=0.9.0,<2` is **shipped** in `pyproject.toml`.

**Integration debt:** `serializers.py` still duplicates some TripleModel file I/O — thin wrappers in **0.6**. Interim `_triple.py` adapter (0.3) is **superseded by 0.4** Option A. `graph.py` is cascade/orphan policy only.

**Current focus (next release):** **0.4 — unified model architecture (Option A)**. Async end-to-end follows in **0.5**.

---

## Design principle: Pydantic-first

SparqlModel and TripleModel are both **Pydantic v2** libraries. New ORM features should lean on that stack before inventing parallel validation.

| Principle | Implication |
|-----------|-------------|
| **Types on models** | Prefer annotations and `Field(..., ge=0, min_length=1)` over manual checks in session code |
| **`model_validate`** | Load paths use `SPARQLModel.model_validate` after `from_graph` (0.4+); avoid ad-hoc dict assembly |
| **SHACL (1.0)** | Graph-shape validation **complements** Pydantic; does not replace app-level types |
| **Non-persisted fields** | `computed_field` / extras that do not map to RDF stay out of `iter_sparql_fields` until a clear use case — defer by default |

Application guide: [guides/models.md](guides/models.md). Normative stack: [SPECS.md](SPECS.md#validation-architecture).

---

## Shipped (0.1.x)

### ORM

| Feature | Status |
|---------|--------|
| `SPARQLSession` — `add`, `put`, `delete`, `get`, `query`, `execute` | Done |
| `SPARQLModel`, `Field`, `Relationship`, `IRI` | Done |
| `MemoryStore` | Done |
| Query builder + compiler (`==`, `!=`, `&`, nested hop) | Done |
| Hydration `depth` 0–2 | Done |
| Cascade / orphan on `put`/`delete` | Done |
| CI (pytest 100% cov, ruff, ty) | Done |

### TripleModel

| Feature | Status |
|---------|--------|
| `triplemodel>=0.9.0,<2` required dependency | Done |
| Interim mapping in `graph.py` | **Removed 0.3.0** — cascade-only |
| Interim `serializers.py` (to retire) | Present — thin wrappers in **0.6** |

---

## Shipped (0.2.0)

### Stores (ORM)

| Feature | Status |
|---------|--------|
| `HttpStore` — SPARQL 1.1 over HTTP (`httpx`), local mirror | Done |
| `sparqlmodel[http]` optional extra | Done |
| Pluggable `Store` protocol; basic / bearer auth | Done |

### Session (ORM)

| Feature | Status |
|---------|--------|
| Identity map + hydration cache | Done |
| `flush()`, `rollback_pending()`, `put(..., flush=False)`, `autoflush` | Done |
| `expire(model_cls, iri)` | Done |

### Query compiler (ORM)

| Feature | Status |
|---------|--------|
| `OR`, `AndExpr` branches in OR | Done |
| Ordering (`<`, `>`, `<=`, `>=`), `IN` | Done |
| Multi-hop nested filters | Done |
| `Query.use_not_exists_for_ne()` for `!=` | Done |

### FastAPI (ORM)

| Feature | Status |
|---------|--------|
| `sparqlmodel[fastapi]` extra | Done |
| `turtle_response`, `jsonld_response`, `negotiated_response` | Done |

### TripleModel wiring (integration — interim)

| Feature | Status |
|---------|--------|
| `sparqlmodel/_triple.py` adapter (dynamic `TripleModel` classes) | Done — **interim; remove in 0.4** |
| Contract tests vs adapter `put` graphs | Done |
| `put` / `get` via `_triple.py` (`sync_to_graph` / `from_graph`) | Done — **superseded by 0.4** |

### Persistence polish

| Feature | Status |
|---------|--------|
| `StaleTripleWarning` on overlapping `add()` | Done |
| `Relationship(..., cascade=False)` | Done |

---

## 0.2 — Operational ORM + adapter foundation

**Status:** shipped as **0.2.0** (see above).

---

## 0.3 — Session I/O through TripleModel (interim adapter)

**Status:** shipped as **0.3.0** — **bridge until Option A (0.4)**.

**Goal:** wire session to TripleModel while keeping SQLModel-style `SPARQLModel` declarations. **Not** the long-term architecture (dynamic adapter).

### Wire session to TripleModel (interim)

- [x] `put` → cascade subjects in `graph.py`, then `sync_to_graph` per nested resource via `_triple.py`
- [x] `get` / query hydration → `sparql_from_graph` / `TripleModel.from_graph` via adapter
- [x] Field adapter: `Field` / `Relationship` → dynamic `rdf_field` TripleModel classes (internal) — **remove in 0.4**
- [x] Remove interim term conversion from `graph.py`
- [ ] Multi-valued `list[...]` fields via TripleModel — **deferred to 1.0**

### SparqlModel-only

- [x] `resolve_related_model` for unions / `ForwardRef`
- [ ] Optional `put` validation via `triplemodel[shacl]` — **deferred to 1.1**
- [x] Narrow `HydrationError` cases

### Consume from TripleModel (already in 0.9)

| Capability | SparqlModel use |
|------------|-----------------|
| `sync_to_graph` / `replace` / `patch` | `put` graph writes |
| `from_graph` / `all_from_graph` | load paths |
| Nested embeds, blanks, RDF lists | align cascade subject keys |
| `Rdf.prefixes`, CURIEs | namespace binding |

---

## 0.4 — Unified model (Option A)

**Status:** **next release** (after **0.3.0**).

**Goal:** one class, one mapping path — SQLModel pattern. **ORM public API unchanged** (`Field`, `Relationship`, `session.put`).

### Unified model layer

- [ ] `class SPARQLModel(TripleModel)` + merged metaclass (query `FieldRef` + TripleModel validation)
- [ ] `Field` / `Relationship` build `rdf_field` / `Predicate` + `Rdf` config at class creation (**no `exec`**)
- [ ] Map `rdf_type` / `__prefixes__` → nested `class Rdf` (`type_uri`, `prefixes`, `embed`, `IriId` for `id: IRI`)
- [ ] `session.put` / `get` call `sync_to_graph` / `from_graph` on the **same** instance type
- [ ] Use TripleModel nested embed for composition; SparqlModel-only `cascade` / `Relationship(..., cascade=False)`
- [ ] Delete `_triple.py`; migrate tests and contract tests
- [ ] CHANGELOG migration note (0.3 → 0.4; no public users yet)

**Write path (target):** validated `SPARQLModel` → cascade in `graph.py` → `sync_to_graph(model, store.graph, …)`.

**Read path (target):** `from_graph` on `SPARQLModel` subclass → optional depth hydration in SparqlModel → identity map.

**Exit criteria:** No dynamic shadow `TripleModel` classes; contract tests pass against direct `sync_to_graph` on `SPARQLModel` instances.

**Out of scope for 0.4:** async session, file I/O delegation, query pagination.

---

## 0.5 — Async end-to-end

**Status:** planned (after **0.4**).

**Goal:** first-class **async** ORM for FastAPI and asyncio apps — no blocking the event loop on `HttpStore` I/O. The **sync** API (`SPARQLSession`, `MemoryStore`, `HttpStore`, `SessionDep`) remains supported and unchanged.

### Store layer

- [ ] `AsyncStore` protocol — `async def query`, `async def update_graph`, `async def close` (mirror sync `Store`)
- [ ] `AsyncHttpStore` — `httpx.AsyncClient`, same mirror semantics as sync `HttpStore`
- [ ] `AsyncMemoryStore` — in-process graph; async methods (no network) for API symmetry and tests
- [ ] Optional extra `sparqlmodel[async]` or fold into `[http]` (document choice in SPECS)

### Session layer

- [ ] `AsyncSPARQLSession` — `async with`, `async def put` / `get` / `delete` / `add`, `async def flush` / `rollback_pending`, `async def execute`
- [ ] `async def query(Model)` → `AsyncQuery` with `async def all()` / `first()` (same expression DSL as sync)
- [ ] Identity map + hydration cache — same semantics as sync; **one session per asyncio task** (documented)
- [ ] Shared compiler + hydration; only I/O and session entry points are async

### FastAPI

- [ ] `AsyncSessionDep` — async generator dependency (`async with AsyncSPARQLSession(...) as session: yield session`)
- [ ] `async with http_store_lifespan(...)` wires `AsyncHttpStore` when app uses async session
- [ ] Guides: async routes with `await session.put` / `await session.query(...).all()`; when to keep sync session in `run_in_executor`

### Quality

- [ ] Contract tests: async session `put` / `get` / `query` parity with sync on `MemoryStore` and `AsyncHttpStore` (mock or testcontainers endpoint)
- [ ] [ORM.md](ORM.md) async section; [PRODUCTION.md](PRODUCTION.md) concurrency (async tasks vs threads)
- [ ] [SPECS.md](SPECS.md) async checklist — P0 for **0.5**, not deferred to 1.0+

**Exit criteria:** A FastAPI app can use `AsyncSessionDep` + `AsyncHttpStore` end-to-end without sync `httpx` on the hot path; SPECS async items checked.

**Out of scope for 0.5:** async TripleModel APIs (unified model stays sync; async session calls sync mapping on the event loop for in-memory work).

**Pydantic:** unchanged — `model_validate` on load paths; async does not change validation rules.

---

## 0.6 — File I/O delegated

**Goal:** no format logic in SparqlModel.

- [ ] `serializers.py` → thin wrappers over TripleModel `parse` / `serialize`
- [ ] Examples and docs use TripleModel for file round-trip
- [ ] Delete duplicate format tables and parsers from SparqlModel

**Exit criteria:** All format round-trips go through TripleModel; SparqlModel export helpers are thin wrappers only.

**Still SparqlModel:** session, compiler, stores, cascade, FastAPI.

**Pydantic:** keep `model_validate_jsonld` / `model_dump_jsonld` as the public parse API; delegate implementation to TripleModel.

---

## 0.7 — Query production

**Goal:** SQLModel-grade list APIs over SPARQL.

- [ ] `Query.offset(n)` → `OFFSET`
- [ ] `Query.order_by(FieldRef, *, desc=False)` → `ORDER BY`
- [ ] `Query.count()` → efficient count pattern
- [ ] OPTIONAL / absence filters for `Relationship | None` and existence checks
- [ ] Compiler tests + [ORM.md](ORM.md) pagination examples

**Exit criteria:** FastAPI list endpoints can paginate and sort without raw SPARQL; SPECS P0 query items checked.

**Pydantic:** filter values remain typed Python literals compiled to RDF; `FieldRef` unchanged.

---

## 0.8 — Session lifecycle

**Goal:** SQLAlchemy session parity for app code.

- [ ] `merge`, `refresh`, `expunge`, `expunge_all`
- [ ] Identity map rules documented (depth, materialized relationships)
- [ ] `scoped_session` helper or documented FastAPI `SessionDep` pattern
- [ ] Threading / concurrency guide

**Exit criteria:** SPECS session lifecycle table implemented; ORM guide covers detach/merge flows.

**Pydantic:** `merge` / `refresh` must produce validated `SPARQLModel` instances (`model_validate` after graph merge).

---

## 0.9 — HttpStore production

**Goal:** safe remote SPARQL for multi-instance apps (within documented constraints).

- [ ] Separate `read_endpoint` / `write_endpoint` (Fuseki-style)
- [ ] Mirror sync strategy (GSP GET, selective hydrate, or explicit remote-authoritative `get`)
- [ ] Batched UPDATE / size limits; retries and timeouts
- [ ] [PRODUCTION.md](PRODUCTION.md) deployment patterns

**Exit criteria:** Documented mirror contract; integration tests for read/write split; SPECS P0 HttpStore item checked.

---

## 1.0 — RDF modeling

**Goal:** SPARQLMojo-class field coverage via TripleModel.

- [ ] Multi-valued scalar and relationship fields (`list[...]`)
- [ ] Language-tagged literals (TripleModel `LangString` / equivalents)
- [ ] Polymorphic `session.query(Base)` with `rdf:type` branches
- [ ] Optional inverse / `back_populates` on `Relationship`

**Exit criteria:** Contract tests for multi-valued and lang fields; SPECS P1 modeling items checked.

**Owner split:** mapping in **TripleModel**; hydration, compiler, cascade in **SparqlModel**.

**Pydantic:** `list[str]`, `list[Organization]`, etc. with standard list validation; hydration returns typed lists.

---

## 1.1 — Ops and quality

**Goal:** production operability.

- [ ] Optional SHACL validation hook on `put` (`triplemodel[shacl]`) — runs after Pydantic validation passes
- [ ] Bulk `put` / `delete` helpers for large imports
- [ ] Structured query logging (SPARQL + timing)
- [ ] Performance guidelines (identity map, query shape, HttpStore batching)

**Exit criteria:** Operators can validate writes and observe queries in production.

---

## 1.2 — Production ORM GA

**Goal:** **SQLModel of SPARQL** for backend teams — feature-complete per [SPECS.md — Production checklist](SPECS.md#production-orm-checklist-12-ga-gate).

- [ ] All SPECS **P0** and **P1** items checked
- [ ] Document supported Pydantic features matrix (constraints, unions, `ForwardRef`, JSON Schema for OpenAPI)
- [ ] Security review on SPARQL generation
- [ ] Stable public API; migration guide from 0.3.x
- [ ] **P2** items remain optional follow-ups (ASK/CONSTRUCT helpers, named graphs, Oxigraph)

**Out of scope for 1.2:** OWL editor, built-in reasoner, mapping-only features in SparqlModel.

---

## Future (post-1.2)

| Theme | Owner |
|-------|--------|
| Named graphs in apps | TripleModel Dataset; SparqlModel session scope |
| semantic-sqlmodel backend | SparqlModel |
| SPARQL federation | SparqlModel |
| Oxigraph / other stores | SparqlModel `stores/` |
| Reasoning hooks | Optional; not core ORM |

---

## SQLModel parity checklist

Quick reference for application developers. Detail: [SPECS.md](SPECS.md).

| SQLModel / SQLAlchemy | SparqlModel | Status |
|-----------------------|-------------|--------|
| `Session.add` / `commit` | `add` / `put` + context `flush` | Shipped |
| `session.get(PK)` | `get(Model, iri)` | Shipped |
| `select().where()` | `query().where()` | Shipped |
| `limit` / `offset` | `limit` / `offset` | Partial (offset **0.7**) |
| `order_by` | `order_by` | **0.7** |
| `count` | `count()` | **0.7** |
| Relationships + eager load | `Relationship`, `depth` | Shipped (depth 0–2) |
| `merge` / `refresh` / `expunge` | same | **0.8** |
| Transactions | pending queue + store updates | Partial (**0.9** remote) |
| FastAPI `Depends(Session)` | `SessionDep` | Shipped |
| Async session / routes | `AsyncSPARQLSession`, `AsyncSessionDep` | **0.5** |
| Single model class (SQLModel pattern) | `SPARQLModel(TripleModel)` | **0.4** |

---

## SPARQLMojo comparison

[SPARQLMojo](https://pypi.org/project/sparqlmojo/) is the closest Python SPARQL ORM (beta, Python 3.12+). SparqlModel targets parity on app ergonomics while **requiring TripleModel** for mapping.

| Feature | SPARQLMojo | SparqlModel |
|---------|------------|-------------|
| Query compiler + session | Yes | Yes (0.2) |
| Identity map | Yes | Yes (0.2) |
| Lang / multi-lang literals | Yes | **1.0** (TripleModel) |
| Collection fields (`LiteralList`, …) | Yes | **1.0** (TripleModel) |
| Polymorphic queries | Yes | **1.0** |
| Property-path-style filters | Yes | Multi-hop `FieldRef` (0.2); extend **0.7** |
| Read/write endpoint split | Yes | **0.9** |
| Async ORM + HTTP store | No | **0.5** |
| FastAPI integration | No | Yes (0.2) |
| TripleModel mapping substrate | No | Yes (required) |
| Unified model (SQLModel pattern) | N/A | **0.4** (Option A) |
| Python 3.10+ | 3.12+ | 3.10+ |

**Differentiators:** cascade/orphan policy, `add` vs `put` semantics, FastAPI extras, TripleModel file I/O path, documented HttpStore mirror model.

---

## Priorities

1. **0.4 unified model (Option A)** — `SPARQLModel(TripleModel)`; delete `_triple.py`; direct `sync_to_graph` / `from_graph`.
2. **0.5 async end-to-end** — `AsyncSPARQLSession`, `AsyncHttpStore`, `AsyncSessionDep` (sync API unchanged).
3. **Do not expand** interim mapping — retire `serializers.py` in **0.6**.
4. **P0 query + HttpStore** for production APIs (**0.7–0.9**).
5. **P1 session lifecycle + RDF types** (**0.8–1.0**).
6. Keep sync `SPARQLSession` / `Field` / `session.put` stable; add async counterparts in parallel.
7. Contract tests on every integration PR; SPECS checklist drives **1.2** GA.
8. Document behavior in [ORM.md](ORM.md) and [PRODUCTION.md](PRODUCTION.md).

---

## Contributing

1. Read [ORM.md](ORM.md) and [ECOSYSTEM.md — Where to implement](ECOSYSTEM.md#where-to-implement-a-change)
2. Mapping bug? Open/fix in TripleModel, then wire SparqlModel.
3. ORM bug? Fix in SparqlModel.
4. Add CHANGELOG under `[Unreleased]`.
5. Remove SparqlModel tests that only duplicate a fixed TripleModel behavior.
