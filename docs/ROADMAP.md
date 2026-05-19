# SparqlModel Roadmap

SparqlModel is **the SQLModel of SPARQL** — a session-first ORM. **TripleModel** (`triplemodel>=0.9`, required) is the mapping engine. This roadmap covers **ORM features** and **wiring TripleModel into session I/O** (retiring interim `graph.py` / `serializers.py`).

- [ORM guide](ORM.md) — application developers
- [SPECS.md](SPECS.md) — technical spec
- [ECOSYSTEM.md](ECOSYSTEM.md) — boundaries
- [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md) — upstream

---

## North star

**SparqlModel builds apps. TripleModel builds correct graphs.**

**1.0** = production SPARQL ORM (SQLModel of SPARQL) — [SPECS production checklist](SPECS.md#production-orm-checklist-10-ga-gate).

| Layer | Responsibility |
|-------|----------------|
| **SparqlModel** | `SPARQLSession`, query DSL, compiler, stores, cascade, hydration `depth` |
| **TripleModel** | Terms, `sync_to_graph`, `from_graph`, `parse`, `serialize`, Dataset |

**Dependency:** `triplemodel>=0.9.0,<2` is **shipped** in `pyproject.toml`.

**Integration debt:** `graph.py` and `serializers.py` still duplicate some TripleModel behavior — scheduled for removal, not expansion.

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
| Interim mapping in `graph.py` (to retire) | Present — do not extend |
| Interim `serializers.py` (to retire) | Present — do not extend |

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

### TripleModel wiring (integration)

| Feature | Status |
|---------|--------|
| `sparqlmodel/_triple.py` adapter | Done |
| Contract tests vs adapter `put` graphs | Done |
| `put` / `get` via `_triple.py` (`sync_to_graph` / `from_graph`) | Done |

### Persistence polish

| Feature | Status |
|---------|--------|
| `StaleTripleWarning` on overlapping `add()` | Done |
| `Relationship(..., cascade=False)` | Done |

---

## 0.2 — Operational ORM + adapter foundation

**Status:** shipped as **0.2.0** (see above).

---

## 0.3 — Session I/O through TripleModel

**Status:** shipped as **0.3.0**.

**Goal:** one mapping path. **ORM public API unchanged.**

### Wire session to TripleModel

- [x] `put` → cascade subjects in `graph.py`, then `sync_to_graph` per nested resource via `_triple.py`
- [x] `get` / query hydration → `sparql_from_graph` / `TripleModel.from_graph` via adapter
- [x] Field adapter: `Field` / `Relationship` → dynamic `rdf_field` TripleModel classes (internal)
- [x] Remove interim term conversion from `graph.py`
- [ ] Multi-valued `list[...]` fields via TripleModel — **deferred to 0.8**

### SparqlModel-only

- [x] `resolve_related_model` for unions / `ForwardRef`
- [ ] Optional `put` validation via `triplemodel[shacl]` — **deferred to 0.9**
- [x] Narrow `HydrationError` cases

### Consume from TripleModel (already in 0.9)

| Capability | SparqlModel use |
|------------|-----------------|
| `sync_to_graph` / `replace` / `patch` | `put` graph writes |
| `from_graph` / `all_from_graph` | load paths |
| Nested embeds, blanks, RDF lists | align cascade subject keys |
| `Rdf.prefixes`, CURIEs | namespace binding |

---

## 0.4 — File I/O delegated

**Goal:** no format logic in SparqlModel.

- [ ] `serializers.py` → thin wrappers over TripleModel `parse` / `serialize`
- [ ] Examples and docs use TripleModel for file round-trip
- [ ] Delete duplicate format tables and parsers from SparqlModel

**Exit criteria:** All format round-trips go through TripleModel; SparqlModel export helpers are thin wrappers only.

**Still SparqlModel:** session, compiler, stores, cascade, FastAPI.

---

## 0.5 — Query production

**Goal:** SQLModel-grade list APIs over SPARQL.

- [ ] `Query.offset(n)` → `OFFSET`
- [ ] `Query.order_by(FieldRef, *, desc=False)` → `ORDER BY`
- [ ] `Query.count()` → efficient count pattern
- [ ] OPTIONAL / absence filters for `Relationship | None` and existence checks
- [ ] Compiler tests + [ORM.md](ORM.md) pagination examples

**Exit criteria:** FastAPI list endpoints can paginate and sort without raw SPARQL; SPECS P0 query items checked.

---

## 0.6 — Session lifecycle

**Goal:** SQLAlchemy session parity for app code.

- [ ] `merge`, `refresh`, `expunge`, `expunge_all`
- [ ] Identity map rules documented (depth, materialized relationships)
- [ ] `scoped_session` helper or documented FastAPI `SessionDep` pattern
- [ ] Threading / concurrency guide

**Exit criteria:** SPECS session lifecycle table implemented; ORM guide covers detach/merge flows.

---

## 0.7 — HttpStore production

**Goal:** safe remote SPARQL for multi-instance apps (within documented constraints).

- [ ] Separate `read_endpoint` / `write_endpoint` (Fuseki-style)
- [ ] Mirror sync strategy (GSP GET, selective hydrate, or explicit remote-authoritative `get`)
- [ ] Batched UPDATE / size limits; retries and timeouts
- [ ] [PRODUCTION.md](PRODUCTION.md) deployment patterns

**Exit criteria:** Documented mirror contract; integration tests for read/write split; SPECS P0 HttpStore item checked.

---

## 0.8 — RDF modeling

**Goal:** SPARQLMojo-class field coverage via TripleModel.

- [ ] Multi-valued scalar and relationship fields (`list[...]`)
- [ ] Language-tagged literals (TripleModel `LangString` / equivalents)
- [ ] Polymorphic `session.query(Base)` with `rdf:type` branches
- [ ] Optional inverse / `back_populates` on `Relationship`

**Exit criteria:** Contract tests for multi-valued and lang fields; SPECS P1 modeling items checked.

**Owner split:** mapping in **TripleModel**; hydration, compiler, cascade in **SparqlModel**.

---

## 0.9 — Ops and quality

**Goal:** production operability.

- [ ] Optional SHACL validation hook on `put` (`triplemodel[shacl]`)
- [ ] Bulk `put` / `delete` helpers for large imports
- [ ] Structured query logging (SPARQL + timing)
- [ ] Performance guidelines (identity map, query shape, HttpStore batching)

**Exit criteria:** Operators can validate writes and observe queries in production.

---

## 1.0 — Production ORM GA

**Goal:** **SQLModel of SPARQL** for backend teams — feature-complete per [SPECS.md — Production checklist](SPECS.md#production-orm-checklist-10-ga-gate).

- [ ] All SPECS **P0** and **P1** items checked
- [ ] Security review on SPARQL generation
- [ ] Stable public API; migration guide from 0.2.x
- [ ] **P2** items remain optional follow-ups (ASK/CONSTRUCT helpers, named graphs, async extra, Oxigraph)

**Out of scope for 1.0:** OWL editor, built-in reasoner, mapping-only features in SparqlModel.

---

## Future (post-1.0)

| Theme | Owner |
|-------|--------|
| Named graphs in apps | TripleModel Dataset; SparqlModel session scope |
| semantic-sqlmodel backend | SparqlModel |
| SPARQL federation | SparqlModel |
| Oxigraph / other stores | SparqlModel `stores/` |
| Async session extra | SparqlModel |
| Reasoning hooks | Optional; not core ORM |

---

## SQLModel parity checklist

Quick reference for application developers. Detail: [SPECS.md](SPECS.md).

| SQLModel / SQLAlchemy | SparqlModel | Status |
|-----------------------|-------------|--------|
| `Session.add` / `commit` | `add` / `put` + context `flush` | Shipped |
| `session.get(PK)` | `get(Model, iri)` | Shipped |
| `select().where()` | `query().where()` | Shipped |
| `limit` / `offset` | `limit` / `offset` | Partial (offset **0.5**) |
| `order_by` | `order_by` | **0.5** |
| `count` | `count()` | **0.5** |
| Relationships + eager load | `Relationship`, `depth` | Shipped (depth 0–2) |
| `merge` / `refresh` / `expunge` | same | **0.6** |
| Transactions | pending queue + store updates | Partial (**0.7** remote) |
| FastAPI `Depends(Session)` | `SessionDep` | Shipped |

---

## SPARQLMojo comparison

[SPARQLMojo](https://pypi.org/project/sparqlmojo/) is the closest Python SPARQL ORM (beta, Python 3.12+). SparqlModel targets parity on app ergonomics while **requiring TripleModel** for mapping.

| Feature | SPARQLMojo | SparqlModel |
|---------|------------|-------------|
| Query compiler + session | Yes | Yes (0.2) |
| Identity map | Yes | Yes (0.2) |
| Lang / multi-lang literals | Yes | **0.8** (TripleModel) |
| Collection fields (`LiteralList`, …) | Yes | **0.8** (TripleModel) |
| Polymorphic queries | Yes | **0.8** |
| Property-path-style filters | Yes | Multi-hop `FieldRef` (0.2); extend **0.5** |
| Read/write endpoint split | Yes | **0.7** |
| FastAPI integration | No | Yes (0.2) |
| TripleModel mapping substrate | No | Yes (required) |
| Python 3.10+ | 3.12+ | 3.10+ |

**Differentiators:** cascade/orphan policy, `add` vs `put` semantics, FastAPI extras, TripleModel file I/O path, documented HttpStore mirror model.

---

## Priorities

1. **Do not expand** interim `graph.py` mapping — wire TripleModel (**0.3–0.4**).
2. **P0 query + HttpStore** for production APIs (**0.5–0.7**).
3. **P1 session lifecycle + RDF types** (**0.6–0.8**).
4. Keep `SPARQLSession` / `Field` / `session.put` stable; extend via new methods.
5. Contract tests on every integration PR; SPECS checklist drives 1.0.
6. Document behavior in [ORM.md](ORM.md) and [PRODUCTION.md](PRODUCTION.md).

---

## Contributing

1. Read [ORM.md](ORM.md) and [ECOSYSTEM.md — Where to implement](ECOSYSTEM.md#where-to-implement-a-change)
2. Mapping bug? Open/fix in TripleModel, then wire SparqlModel.
3. ORM bug? Fix in SparqlModel.
4. Add CHANGELOG under `[Unreleased]`.
5. Remove SparqlModel tests that only duplicate a fixed TripleModel behavior.
