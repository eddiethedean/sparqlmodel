# SparqlModel Roadmap

SparqlModel is **the SQLModel of SPARQL** — a session-first ORM. **TripleModel** (`triplemodel>=0.10`, required) is the mapping engine on **pyoxigraph**. This roadmap covers **ORM features**, **Option A** (`SPARQLModel` subclasses `TripleModel`), and retiring interim integration code (duplicate serializers).

- [ORM guide](ORM.md) — application developers
- [SPECS.md](SPECS.md) — technical spec
- [ECOSYSTEM.md](ECOSYSTEM.md) — boundaries
- [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md) — upstream
- [ASYNC_RDF_RUST_PLAN.md](ASYNC_RDF_RUST_PLAN.md) — optional Rust async I/O package (companion to **0.6** async)
- [Pyoxigraph 0.5 docs](https://pyoxigraph.readthedocs.io/en/stable/) — RDF engine reference for this audit

---

## North star

**SparqlModel builds apps. TripleModel builds correct graphs.**

**Single model class (Option A, shipped 0.4.0):** `SPARQLModel` **subclasses** `TripleModel`. `Field` and `Relationship` are ORM sugar; session I/O uses `rdf_bridge` and `from_graph` on the **same** instances. The 0.3 `_triple.py` adapter was removed in **0.4**.

**0.15** = production SPARQL ORM GA (SQLModel of SPARQL) — [SPECS production checklist](SPECS.md#production-orm-checklist-13-ga-gate).

| Layer | Responsibility |
|-------|----------------|
| **SparqlModel** | `SPARQLSession`, query DSL, compiler, stores, cascade, hydration `depth` |
| **TripleModel** | Terms, `sync_to_graph`, `from_graph`, `parse`, `serialize`, Dataset |

**Dependency:** `triplemodel>=0.10.0,<2`, `pyoxigraph>=0.5,<0.6` — **shipped** in **0.5.0** (`pyproject.toml`). Core install has **no rdflib**.

**Integration debt:** `serializers.py` is thin wrappers over TripleModel I/O (**0.7** shipped). `graph.py` is cascade/orphan policy only.

**Current focus:** **[Production HttpStore](#production-httpstore)** — phase **[0.10 — Mirror semantics](#010--mirror-semantics)**. **0.9.2** shipped **2026-05-21**. Forward plan: [0.10 → 0.15](#forward-roadmap-07--015).

---

## Design principle: Pydantic-first

SparqlModel and TripleModel are both **Pydantic v2** libraries. New ORM features should lean on that stack before inventing parallel validation.

| Principle | Implication |
|-----------|-------------|
| **Types on models** | Prefer annotations and `Field(..., ge=0, min_length=1)` over manual checks in session code |
| **`model_validate`** | Load paths use `SPARQLModel.model_validate` after `from_graph` (0.4+); avoid ad-hoc dict assembly |
| **SHACL (0.14)** | Graph-shape validation **complements** Pydantic; does not replace app-level types |
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
| Interim `serializers.py` | Thin wrappers over TripleModel I/O — **0.7** shipped |

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
| `sparqlmodel/_triple.py` adapter (dynamic `TripleModel` classes) | **Removed 0.4.0** — replaced by `rdf_bridge` |
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
- [ ] Multi-valued `list[...]` fields via TripleModel — **deferred to 0.13**

### SparqlModel-only

- [x] `resolve_related_model` for unions / `ForwardRef`
- [ ] Optional `put` validation via `triplemodel[shacl]` — **deferred to 0.14**
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

**Status:** shipped as **0.4.0**.

**Goal:** one class, one mapping path — SQLModel pattern. **ORM public API unchanged** (`Field`, `Relationship`, `session.put`).

### Unified model layer

- [x] `class SPARQLModel(TripleModel)` + merged metaclass (query `FieldRef` + TripleModel validation)
- [x] `Field` / `Relationship` build `rdf_predicate` + `sparql` metadata at class creation (**no `exec`**)
- [x] Map `rdf_type` / `__prefixes__` → nested `class Rdf` (`type_uri`, `prefixes`, `embed`, `IriId` for `id`)
- [x] `session.put` / `get` call `rdf_bridge.model_to_graph` / `load_from_graph` on the **same** instance type
- [x] Per-subject graph sync for composition; SparqlModel-only `cascade` / `Relationship(..., cascade=False)` via `ref_field`
- [x] Delete `_triple.py`; migrate tests and contract tests
- [x] CHANGELOG migration note (0.3 → 0.4)

**Write path (target):** validated `SPARQLModel` → cascade in `graph.py` → `sync_to_graph(model, store.graph, …)`.

**Read path (target):** `from_graph` on `SPARQLModel` subclass → optional depth hydration in SparqlModel → identity map.

**Exit criteria:** No dynamic shadow `TripleModel` classes; contract tests pass against direct `sync_to_graph` on `SPARQLModel` instances.

**Out of scope for 0.4:** async session, file I/O delegation, query pagination.

---

## 0.5 — Pyoxigraph + TripleModel 0.10

**Status:** shipped as **0.5.0**.

**Goal:** one RDF engine for session graphs, cascade, mirror, and `rdf_bridge` — **pyoxigraph** via `triplemodel.Store`, not rdflib.

### Engine and stores

- [x] `pyoxigraph>=0.5,<0.6`, `triplemodel>=0.10.0,<2`; remove rdflib from core
- [x] `Store` protocol — `graph: triplemodel.Store`, `update_graph(add|remove: Store)`
- [x] `MemoryStore` / `HttpStore` mirror on `Store`; SPARQL JSON bindings without rdflib
- [x] `graph.py`, `rdf_bridge`, compiler N3 formatting on pyoxigraph terms
- [x] FastAPI responses via `export_graph` / TripleModel serialize
- [x] CHANGELOG breaking notes for `Store` / `session.graph` types

**Exit criteria:** No required rdflib in core; contract tests and full pytest suite green on TM 0.10.

**Out of scope for 0.5:** async session (**0.6**), disk-backed default store, `aio-rdf` crate.

### Pyoxigraph utilization (audit vs [0.5.8 docs](https://pyoxigraph.readthedocs.io/en/stable/))

SparqlModel does **not** import `pyoxigraph.Store` in application code. In-process graphs go through **`triplemodel.Store`** (pyoxigraph-backed). Direct `pyoxigraph` imports in this repo are limited to **term types** (`NamedNode`, `BlankNode`, `Literal`, `Triple`) and **N3 formatting** for SPARQL UPDATE bodies.

#### In use today (keep)

| Pyoxigraph area | SparqlModel use |
|-----------------|-----------------|
| [RDF model](https://pyoxigraph.readthedocs.io/en/stable/model.html) — `NamedNode`, `BlankNode`, `Literal`, `Triple` | `rdf_n3`, `graph.py`, `MemoryStore._term_value`, tests |
| [Store](https://pyoxigraph.readthedocs.io/en/stable/store.html) — in-memory `add` / `remove` / `query` | Via `triplemodel.Store` in `MemoryStore`, `HttpStore` mirror, `rdf_bridge` |
| RDF-star quoted triples in UPDATE | `term_to_n3` emits `<< s p o >>` |
| SPARQL SELECT | `MemoryStore.query` → `Store.query`; compiler + session `execute` |
| File parse/serialize (Turtle, JSON-LD, N-Triples, …) | Via TripleModel `load_graph` / `dump_graph` (`serializers.py` thin wrappers, **0.7**) |

#### Gaps — add to roadmap (by owner)

| Gap | Pyoxigraph API | Owner | Target |
|-----|----------------|-------|--------|
| SELECT-only `execute` / `MemoryStore.query` (ASK raises `QueryError`) | `QueryBoolean`, `bool(store.query("ASK …"))` | SparqlModel | **0.14** (see SPECS P2) |
| No CONSTRUCT / DESCRIBE on session | `QueryTriples`, `.serialize(RdfFormat.*)` | SparqlModel | **0.14** |
| ~~Hand-rolled SPARQL Results JSON parser~~ | [`parse_query_results`](https://pyoxigraph.readthedocs.io/en/stable/sparql.html#pyoxigraph.parse_query_results) — **shipped 0.9.1** | SparqlModel `stores/` | — |
| HttpStore mirror replace-on-pull / `mirror_mode` | CONSTRUCT per subject | SparqlModel `stores/` | **0.10** |
| HttpStore retries + batched UPDATE | `httpx` retry, chunked INSERT/DELETE | SparqlModel `stores/` | **0.11** |
| HttpStore GSP full mirror sync | Graph Store HTTP GET | SparqlModel `stores/` | **0.12** (Production HttpStore) |
| HttpStore UPDATE as string templates only | Remote endpoints need HTTP; local mirror could use `Store.update()` for dev tooling | SparqlModel | **0.12** (optional) or **0.14** |
| No disk-backed store | `Store(path)`, `backup`, `optimize`, `flush`, `read_only` | SparqlModel `stores/` | **0.14** (`OxigraphStore` backend) |
| Large imports iterate `add` per triple | `bulk_load`, `bulk_extend`, `extend` | SparqlModel session + TripleModel | **0.14** (bulk `put`) |
| Cascade / orphan scans graph broadly | `quads_for_pattern` | SparqlModel `graph.py` | **0.14** (perf) |
| Default graph only (no named graphs) | `Quad`, `Dataset`, `add_graph`, `named_graphs` | TripleModel Dataset + SparqlModel session scope | **post-0.15** |
| Blank-node merge on import | `parse(..., rename_blank_nodes=True)`, `Dataset.canonicalize` | TripleModel | **0.13** (document in **0.7**) |
| Directional literals | `Literal.direction` | TripleModel | **0.13** |
| Full RDF-star in models (not just UPDATE N3) | `RdfFormat.supports_rdf_star`, quoted triple fields | TripleModel + SparqlModel | **post-0.15** |
| Negotiated export uses string format names | `infer_format` on `Accept` | FastAPI extra | **0.7** shipped |
| `pyoxigraph.Variable` in compiler | `Variable` | SparqlModel (optional) | **post-0.15** |

**Intentionally delegated (not SparqlModel gaps):** `parse` / `serialize` / TriG / N-Quads / N3 parsers live in **TripleModel** per [ECOSYSTEM.md](ECOSYSTEM.md). SparqlModel **0.7** retires duplicate format tables; verify TripleModel passes through pyoxigraph `lenient`, `rename_blank_nodes`, and `without_named_graphs` where appropriate.

### 0.5.1 patch

**Status:** shipped as **0.5.1** (2026-05-19).

- [x] Query DSL — reject `((A | B) & C)` with `QueryError`; use `.where((A | B), C)` for OR + AND
- [x] Session — recursive `_depth_satisfied` for `get(..., depth=2)` with multiple relationships
- [x] `use_optional_for_comparisons(False)` restores default `!=` semantics
- [x] Docs — nitpicky Sphinx build, troubleshooting for OR/AND and session exit

### 0.5.2 patch

**Status:** shipped as **0.5.2** (2026-05-20).

- [x] `delete()` clears pending `put` queue for root and cascade subjects
- [x] Hydration cache — no negative cache; IRI-wide invalidation on session writes
- [x] Default `!=` → NOT EXISTS; `Query.use_inequality_for_ne()` for legacy semantics
- [x] `rdf_n3` / shared `sparql_escape` for UPDATE literal escaping
- [x] `load_from_graph` non-cascade embed coercion / `HydrationError`

---

## 0.6 — Async end-to-end

**Status:** shipped as **0.6.0** (2026-05-20).

**Goal:** first-class **async** ORM for FastAPI and asyncio apps — no blocking the event loop on `HttpStore` I/O. The **sync** API (`SPARQLSession`, `MemoryStore`, `HttpStore`, `SessionDep`) remains supported and unchanged.

### Store layer

- [x] `AsyncStoreProtocol` — `async def query`, `async def update_graph`, `async def aclose`
- [x] `AsyncHttpStore` — `httpx.AsyncClient`, same mirror semantics as sync `HttpStore`; shared `http_common` helpers
- [x] `AsyncMemoryStore` — in-process graph; async methods for API symmetry and tests
- [x] Async HTTP folded into **`sparqlmodel[http]`** (no separate `[async]` extra)

### Session layer

- [x] `AsyncSPARQLSession` — `async with`, async CRUD, `flush` / `rollback_pending`, `execute`
- [x] `AsyncQuery` — `await .all()` / `.first()`; same expression DSL as sync
- [x] `session_core` — shared identity map, cascade, hydration with sync session
- [x] **One session per asyncio task** — documented in ORM / PRODUCTION

### FastAPI

- [x] `AsyncSessionDep`, `init_async_app`, `get_async_session`, `async_http_store_lifespan`, `async_session_dependency`
- [x] [FastAPI guide](guides/fastapi.md) — async routes and lifespan

### Quality

- [x] Async store, session, query, and FastAPI contract tests
- [x] [ORM.md](ORM.md) async section; [PRODUCTION.md](PRODUCTION.md) concurrency notes
- [x] [SPECS.md](SPECS.md) async checklist marked for **0.6**

**Out of scope for 0.6:** async TripleModel APIs; **`aio-rdf`** Rust crate (optional later).

---

(forward-roadmap-07--015)=

## Forward roadmap (0.7 → 0.15)

**Shipped:** **0.9.2** (2026-05-21) — `refresh` mirror pull, `merge` partial-field fix, IRI ref hydration; **0.9.1** — partial HttpStore hardening; **0.9.0** — [session cache](#09--session-cache-control). **Next:** [Production HttpStore](#production-httpstore) — phase **0.10**.

Releases from **0.7** onward follow one rule: **finish integration debt before new ORM surface area**, then **list APIs → session cache → [Production HttpStore](#production-httpstore) (0.10–0.12) → modeling (0.13) → operations (0.14) → GA (0.15)**. Each **0.x** line is one theme; Production HttpStore is one milestone with ordered **phases** (0.10, 0.11, 0.12).

### At a glance

| Version | Track | Primary outcome |
|---------|-------|-----------------|
| **0.7** | Integration | All RDF **file** parse/serialize goes through TripleModel; SparqlModel has no format registry — **shipped** |
| **0.8** | Query | **Paginate, sort, and count** in the query DSL; nullable relationship filters — **shipped** |
| **0.9** | Session | **merge / refresh / expunge** and documented scoped-session patterns — **shipped** |
| **0.10–0.12** | Stores | **[Production HttpStore](#production-httpstore)** — mirror semantics → HTTP resilience → GSP sync & integration contract |
| **0.13** | Modeling | **Richer RDF fields** — multi-valued, `@lang`, polymorphic query, inverse nav |
| **0.14** | Operations | **SHACL, bulk I/O, ASK/CONSTRUCT, disk store**, performance and logging |
| **0.15** | GA | [SPECS P0 + P1](SPECS.md#production-orm-checklist-13-ga-gate) complete; stable public API |

### Tracks (what each line of work owns)

| Track | Versions | SparqlModel owns | TripleModel owns |
|-------|----------|------------------|------------------|
| **Integration** | 0.7 | Thin `serializers.py`, FastAPI `Accept` → format | `parse`, `serialize`, `infer_format`, parsers |
| **Query & API** | 0.8 | Compiler, `Query` / `AsyncQuery`, OPTIONAL for nullable hops | Literal/term encoding (unchanged) |
| **Session** | 0.9 | Identity map, merge/refresh/expunge, scoped session docs | `from_graph` / validation on reload |
| **Remote stores** | 0.10–0.12 ([Production HttpStore](#production-httpstore)) | `HttpStore` / `AsyncHttpStore`, mirror modes, transport, GSP sync | — |
| **Modeling** | 0.13 | Hydration, cascade, compiler for collections & polymorphism | Multi-valued, `LangString`, dispatch |
| **Operations** | 0.14 | SHACL hook on `put`, bulk helpers, `OxigraphStore`, logging | `triplemodel[shacl]` engine |
| **GA** | 0.15 | Checklist, security review, migration guide | Frozen mapping API for apps |

```text
0.7 File I/O → 0.8 Query lists → 0.9 Session cache
  → Production HttpStore (0.10 → 0.11 → 0.12)
  → 0.13 RDF fields → 0.14 Ops → 0.15 Production GA
```

**Why this order:** list endpoints (**0.8**) do not require remote-store work but unblock FastAPI apps; session cache (**0.9**) clarifies identity before HttpStore hardening; mirror correctness (**0.10**) precedes retries and large writes (**0.11**); GSP and operator contract (**0.12**) close the stores milestone; richer fields (**0.13**) depend on TripleModel mapping releases; ops (**0.14**) assume stable query/store/model APIs; **0.15** is checklist closure only (no new features).

---

### 0.7 — Delegated file I/O

**Status:** shipped as **0.7.0** (2026-05-20).

**Track:** Integration · **Depends on:** 0.6 (shipped)

**Goal:** Zero format logic in SparqlModel — only TripleModel (pyoxigraph) parses and serializes RDF documents.

- [x] `serializers.py` — thin wrappers calling `TripleModel.serialize` / `load_graph` / `infer_format`
- [x] Remove `SUPPORTED_FORMATS` and duplicate alias tables from SparqlModel
- [x] Docs and examples: file round-trip via `Model.parse` / `Model.serialize` or `triplemodel.io`
- [x] FastAPI `negotiated_response` uses `infer_format` (no local format registry)
- [x] `model_dump_jsonld` / `model_validate_jsonld` — public API kept; ORM dict semantics documented vs graph JSON-LD export

**Exit criteria:** Every Turtle/JSON-LD/NT file path goes through TripleModel; `make ci` green; no new format names added only in SparqlModel.

---

### 0.8 — Query lists

**Status:** shipped as **0.8.0** (2026-05-21).

**Track:** Query & API · **Depends on:** 0.7

**Goal:** SQLModel-grade **list** endpoints — paginate, sort, and count without hand-written SPARQL.

| Deliverable | Notes |
|-------------|--------|
| `Query.offset(n)` / `AsyncQuery.offset(n)` | `OFFSET` in compiled SELECT |
| `Query.order_by(FieldRef, *, desc=False)` | `ORDER BY` on bound variables |
| `Query.count()` | `COUNT(DISTINCT ?root)` |
| OPTIONAL / absence for `Relationship \| None` | Compiler `OPTIONAL` on nullable hops; `is_(None)` / `is_not(None)` |
| Tests + [guides/queries.md](guides/queries.md) pagination examples | Sync and async parity |

**Exit criteria:** FastAPI list routes can use `.limit().offset().order_by()` and `.count()`; SPECS **P0** query checklist items for **0.8** are checked.

**Out of scope:** `merge` / `refresh` (**0.9**); [Production HttpStore](#production-httpstore).

---

### 0.9 — Session cache control

**Status:** shipped as **0.9.0** (2026-05-21).

**Track:** Session · **Depends on:** 0.8 (shipped)

**Goal:** SQLAlchemy-style **identity map control** for long-lived processes and tests.

| Deliverable | Notes |
|-------------|--------|
| [x] `merge`, `refresh`, `expunge`, `expunge_all` on sync and async sessions | Validated field copy via `model_validate` after graph reload |
| [x] Document identity map + hydration cache rules | [ORM.md](ORM.md), [guides/sessions.md](guides/sessions.md) |
| [x] Scoped session pattern documented | [guides/fastapi.md](guides/fastapi.md) — `SessionDep` / `AsyncSessionDep`, `close_on_exit=False` |
| [x] Threading guide | [PRODUCTION.md](PRODUCTION.md), sessions guide — one session per thread/task |

**Exit criteria:** SPECS **P1** session lifecycle items for **0.9** checked; ORM guide covers detach/merge flows.

**Out of scope:** Remote mirror reconciliation ([Production HttpStore](#production-httpstore)); multi-valued fields (**0.13**).

### 0.9.1 patch

**Status:** shipped (2026-05-21).

- Hydration cache / `depth_satisfied` fixes for `get` and `refresh`
- Partial HttpStore hardening: `read_endpoint` / `write_endpoint`, `pull_subjects_into_mirror`, auto-pull on `get`, `parse_query_results`
- Compiler `!BOUND` guards for ordered comparisons on optional paths

### 0.9.2 patch

**Status:** shipped (2026-05-21).

- `refresh` auto-pulls remote subjects into the HttpStore mirror (sync and async), parity with `get`
- `merge` preserves unset relationship fields; invalidates hydration cache after reconcile
- `load_from_graph` keeps `IRI` refs when `Relationship | IRI` and target has no `rdf:type`
- CI smoke-run for `examples/realworld/`

---

(production-httpstore)=

### Production HttpStore

**Track:** Remote stores · **Depends on:** 0.9.2 · **Phases:** 0.10 → 0.11 → 0.12

**Goal:** Documented, testable **multi-instance** use of `HttpStore` / `AsyncHttpStore` (within stated constraints): correct mirror semantics, resilient HTTP, then full sync and operator contract.

**Already shipped (0.9.1 / 0.9.2):**

- [x] `read_endpoint` / `write_endpoint` (Fuseki-style split)
- [x] Partial mirror sync — `pull_subjects_into_mirror`, auto-pull on `get` / `refresh`
- [x] `pyoxigraph.parse_query_results` for remote SELECT

**Milestone exit criteria:** SPECS **P0** HttpStore items checked; operators know when `get` vs `execute` is authoritative; README/PRODUCTION state Production HttpStore guarantees vs **0.14** (ASK, disk store, multi-writer).

**Out of scope for this milestone:** Multi-valued / lang fields (**0.13**); disk-backed `OxigraphStore` (**0.14**).

#### Phase 0.10 — Mirror semantics

**Depends on:** 0.9.2

Per-subject mirror sync is **correct** and **configurable** before retries or full-graph sync.

| Deliverable | Notes |
|-------------|--------|
| Replace-on-pull | `pull_subjects_into_mirror` removes existing mirror triples per IRI before CONSTRUCT merge |
| `mirror_mode` | `writer` (default, 0.9.x) vs `remote_authoritative` on `HttpStore` / `AsyncHttpStore` |
| Docs | [PRODUCTION.md](PRODUCTION.md), [troubleshooting.md](troubleshooting.md) — query vs `get` authority |
| Tests | Stale predicate removed after remote CONSTRUCT; sync/async parity |

**Phase exit:** No stale predicates left for a subject after pull; operators can pick mirror mode per store.

#### Phase 0.11 — HTTP resilience

**Depends on:** phase 0.10

Safe large writes and transient failure handling — still single-writer per endpoint.

| Deliverable | Notes |
|-------------|--------|
| Shared HTTP transport | Retry policy in `http_common` (sync + async stores) |
| Retries | `max_retries`, `retry_backoff`; 502/503/504 and connection errors |
| Batched UPDATE | `max_triples_per_update`; chunk INSERT/DELETE; mirror only after all remote chunks succeed |
| Docs | [PRODUCTION.md](PRODUCTION.md) — batch sizes, retry defaults |

**Phase exit:** Large cascades do not send unbounded UPDATE strings; transient errors recover without app retry loops.

#### Phase 0.12 — Mirror contract

**Depends on:** phase 0.11

Full mirror option, integration coverage, stores-track sign-off.

| Deliverable | Notes |
|-------------|--------|
| Full mirror sync | `sync_mirror()` via Graph Store HTTP GET when `graph_store_url` configured |
| Integration tests | Read/write split + mirror contract (`tests/test_http_store_integration.py`) |
| Docs | README/PRODUCTION — milestone guarantees vs deferred **0.14** work |

**Phase exit:** Integration tests green; SPECS **P0** HttpStore row complete.

---

### 0.13 — Richer RDF models

**Track:** Modeling · **Depends on:** TripleModel releases for collections/lang · **Parallel with:** [Production HttpStore](#production-httpstore) phases if mapping lands upstream first

**Goal:** SPARQLMojo-class **field expressiveness** without duplicating TripleModel mapping.

| Deliverable | Owner |
|-------------|--------|
| Multi-valued scalar and relationship fields (`list[...]`) | TripleModel map + SparqlModel hydrate/compiler/cascade |
| Language-tagged literals (`LangString`, etc.) | TripleModel |
| Polymorphic `session.query(Base)` with `rdf:type` branches | SparqlModel compiler |
| `Relationship(..., back_populates=...)` (optional inverse) | SparqlModel + TripleModel metadata |

**Exit criteria:** Contract tests for multi-valued and lang fields; SPECS **P1** modeling items for **0.13** checked.

**Out of scope:** SHACL on `put` (**0.14**); named graphs (**post-0.15**).

---

### 0.14 — Production operations

**Track:** Operations · **Depends on:** [Production HttpStore](#production-httpstore) (0.12) and **0.13** feature APIs stable

**Goal:** Teams can **operate** SparqlModel in production (validate, import at scale, observe, tune).

| Deliverable | Notes |
|-------------|--------|
| Optional SHACL validation hook on `put` | `triplemodel[shacl]` after Pydantic passes |
| Bulk `put` / `delete` helpers | pyoxigraph `bulk_load` / `bulk_extend` where applicable |
| `session.execute` / stores: ASK and CONSTRUCT result types | Not SELECT-only |
| `OxigraphStore` backend | Disk `pyoxigraph.Store(path)`, backup/optimize |
| `graph.py` hot paths | `quads_for_pattern` where measurable |
| Structured SPARQL logging + performance guide | Identity map, query shape, HttpStore batching |

**Exit criteria:** Operators can validate writes and observe queries; SPECS **P2** items either shipped or explicitly deferred with owners.

**Out of scope:** GA checklist sign-off (**0.15**); OWL editor / reasoner.

---

### 0.15 — Production GA

**Track:** GA · **Depends on:** 0.14

**Goal:** Declare SparqlModel **production-ready** — the SQLModel of SPARQL for backend teams.

| Deliverable | Notes |
|-------------|--------|
| All SPECS **P0** and **P1** items checked | [Production checklist](SPECS.md#production-orm-checklist-13-ga-gate) |
| Pydantic features matrix for OpenAPI | Constraints, unions, `ForwardRef`, JSON Schema |
| Security review on SPARQL generation | Documented threat model for filter compilation |
| Stable public API + migration guide | 0.3.x → current |
| Pyoxigraph utilization table | P0/P1 rows closed; P2 deferred with targets |

**Exit criteria:** Version **0.15.0** tagged; README and ORM guide state production readiness; no open P0/P1 checklist items.

**Out of scope:** Named graphs, RDF-star entity fields, federation, alternate non-Oxigraph backends (**post-0.15**).

---

## Future (post-0.15)

| Theme | Owner |
|-------|--------|
| Named graphs in apps | TripleModel `Dataset` / `Quad`; SparqlModel session graph scope (`add_graph`, `named_graphs`) |
| RDF-star entity fields | TripleModel + SparqlModel compiler/hydration |
| `pyoxigraph.Variable` in query compiler | SparqlModel (optional; string SPARQL generation is sufficient today) |
| semantic-sqlmodel backend | SparqlModel |
| SPARQL federation | SparqlModel |
| Other store backends (Jena native, etc.) | SparqlModel `stores/` — Oxigraph disk covered in **0.14** |
| Reasoning hooks | Optional; not core ORM |

---

## SQLModel parity checklist

Quick reference for application developers. Detail: [SPECS.md](SPECS.md).

| SQLModel / SQLAlchemy | SparqlModel | Status |
|-----------------------|-------------|--------|
| `Session.add` / `commit` | `add` / `put` + context `flush` | Shipped |
| `session.get(PK)` | `get(Model, iri)` | Shipped |
| `select().where()` | `query().where()` | Shipped |
| `limit` / `offset` | `limit` / `offset` | Shipped (**0.8**) |
| `order_by` | `order_by` | Shipped (**0.8**) |
| `count` | `count()` | Shipped (**0.8**) |
| Relationships + eager load | `Relationship`, `depth` | Shipped (depth 0–2) |
| `merge` / `refresh` / `expunge` | same | Shipped (**0.9**) |
| Transactions | pending queue + store updates | Partial (remote txn **0.12**) |
| FastAPI `Depends(Session)` | `SessionDep` | Shipped |
| Async session / routes | `AsyncSPARQLSession`, `AsyncSessionDep` | Shipped (**0.6**) |
| Single model class (SQLModel pattern) | `SPARQLModel(TripleModel)` | **0.4** |

---

## SPARQLMojo comparison

[SPARQLMojo](https://pypi.org/project/sparqlmojo/) is the closest Python SPARQL ORM (beta, Python 3.12+). SparqlModel targets parity on app ergonomics while **requiring TripleModel** for mapping.

| Feature | SPARQLMojo | SparqlModel |
|---------|------------|-------------|
| Query compiler + session | Yes | Yes (0.2) |
| Identity map | Yes | Yes (0.2) |
| Lang / multi-lang literals | Yes | **0.13** (TripleModel) |
| Collection fields (`LiteralList`, …) | Yes | **0.13** (TripleModel) |
| Polymorphic queries | Yes | **0.13** |
| Property-path-style filters | Yes | Multi-hop `FieldRef` (0.2); OPTIONAL nullable hops (**0.8**) |
| Read/write endpoint split | Yes | Shipped (**0.9.1**); production contract **0.12** ([Production HttpStore](#production-httpstore)) |
| Async ORM + HTTP store | No | Shipped (**0.6**) |
| FastAPI integration | No | Yes (0.2) |
| TripleModel mapping substrate | No | Yes (required) |
| Unified model (SQLModel pattern) | N/A | **0.4** (Option A) |
| Python 3.10+ | 3.12+ | 3.10+ |

**Differentiators:** cascade/orphan policy, `add` vs `put` semantics, FastAPI extras, TripleModel file I/O path, documented HttpStore mirror model.

---

## Priorities (forward work)

1. **[Production HttpStore](#production-httpstore)** — phase **0.10** (mirror semantics), then **0.11** (HTTP resilience), then **0.12** (GSP `sync_mirror`, integration contract, SPECS P0 HttpStore).
2. **0.13** — RDF modeling via TripleModel (multi-valued, lang, polymorphic query) — no parallel mapping in SparqlModel.
3. **0.14** — Operations (SHACL hook, bulk, ASK/CONSTRUCT, `OxigraphStore`, logging/perf).
4. **0.15** — GA: SPECS P0+P1 checklist, security review, stable API — **no new features**.
5. Keep sync `SPARQLSession` / `Field` / `session.put` stable; mirror features on async APIs in the same release.
6. Contract tests on every integration PR; [SPECS](SPECS.md) checklist drives **0.15** GA.

---

## Contributing

1. Read [ORM.md](ORM.md) and [ECOSYSTEM.md — Where to implement](ECOSYSTEM.md#where-to-implement-a-change)
2. Mapping bug? Open/fix in TripleModel, then wire SparqlModel.
3. ORM bug? Fix in SparqlModel.
4. Add CHANGELOG under `[Unreleased]`.
5. Remove SparqlModel tests that only duplicate a fixed TripleModel behavior.
