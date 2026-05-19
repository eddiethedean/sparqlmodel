# SparqlModel Technical Specification

## Overview

This document specifies the **SparqlModel ORM layer**: session API, query compilation, hydration, cascade policy, and stores.

**SparqlModel — the SQLModel of SPARQL.**

**Mapping** (literals, terms, `to_graph`, `sync_to_graph`, `from_graph`, `parse`, `serialize`) is specified and implemented by **[TripleModel](https://github.com/eddiethedean/triplemodel)** `>=0.9`, a **required dependency**. SparqlModel integrates TripleModel internally; application code uses `SPARQLSession` and `SPARQLModel` unless doing stateless file I/O.

| Concern | SparqlModel | TripleModel |
|---------|-------------|-------------|
| `SPARQLSession` CRUD | Yes | No |
| Query DSL + compiler | Yes | No |
| Cascade / orphans on `put` | Yes | No |
| Hydration `depth` | Yes | No |
| Stores | Yes | No |
| Model ↔ triples, terms, files | Integrates (retiring interim code) | Yes |

[ORM.md](ORM.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md) · [PRODUCTION.md](PRODUCTION.md)

---

# Production ORM checklist (1.0 GA gate)

Normative checklist for declaring SparqlModel **production-ready** (version **1.0**). See [ROADMAP.md](ROADMAP.md) for milestone versions.

**Parity tiers:** **P0** = required for production HTTP/API apps; **P1** = SQLModel / [SPARQLMojo](https://pypi.org/project/sparqlmojo/) parity; **P2** = advanced RDF / ecosystem.

## P0 — Production APIs

- [x] `SPARQLModel`, `Field`, `Relationship`, `IRI`, Pydantic validation
- [x] `SPARQLSession` — `add`, `put`, `delete`, `get`, `query`, `execute`, context manager
- [x] Query filters: `==`, `!=`, `&`, `|`, ordering, `in_`, multi-hop paths; `(A & B) | C` precedence (0.2+)
- [x] `limit`, `first`, `all` with hydration `depth` 0–2
- [x] Identity map + `flush` / `rollback_pending` / `put(..., flush=False)`
- [x] `MemoryStore` and `HttpStore` (documented mirror semantics)
- [x] FastAPI `SessionDep`, `init_app`, `http_store_lifespan`
- [x] Session I/O via TripleModel only (`put` / `get` / hydrate) — **0.3.0**
- [ ] `Query.offset(n)` — **0.5**
- [ ] `Query.order_by(...)` — **0.5**
- [ ] `Query.count()` — **0.5**
- [ ] OPTIONAL / absence filters for nullable `Relationship | None` — **0.5**
- [ ] HttpStore mirror sync or remote-authoritative `get` contract — **0.7**
- [ ] Scoped session pattern documented (FastAPI + scripts) — **0.6**
- [ ] Threading / concurrency model documented — **0.6**

## P1 — SQLModel / SPARQLMojo parity

- [ ] `merge`, `refresh`, `expunge`, `expunge_all` on session — **0.6**
- [ ] Multi-valued scalar and relationship fields — **0.8** (TripleModel + SparqlModel hydrate)
- [ ] Language-tagged literals (`@lang`) — **0.8** (TripleModel)
- [ ] Polymorphic queries (`rdf:type` subclasses) — **0.8**
- [ ] HttpStore separate read/write endpoint URLs — **0.7**
- [ ] Optional SHACL validation on `put` — **0.9**
- [ ] Inverse / `back_populates` relationship navigation (where modeled) — **0.8**

## P2 — Advanced

- [ ] `session.ask(...)` or `Query.exists()` helper wrapping ASK — **1.0+**
- [ ] CONSTRUCT / DESCRIBE helpers — **1.0+**
- [ ] Named graph scope on session/store — **1.0+**
- [ ] Optional async session extra — **1.0+**
- [ ] Oxigraph or additional store backends — **1.0+**
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
- `graph` — rdflib `Graph` (`MemoryStore` graph, or `HttpStore` local mirror — not the remote dataset)
- `namespaces` — `NamespaceRegistry` for compiler and serialization

## Session lifecycle (target API)

**Current (0.2):** Context manager flushes pending `put` queue on success; `rollback_pending` on error; `expire(model_cls, iri)` evicts identity and hydration cache. No `merge`, `refresh`, or `expunge`. Not thread-safe.

**Target (1.0):**

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
- `.use_not_exists_for_ne()` — compile `!=` with `NOT EXISTS`
- `.all(*, depth=0)` / `.first(*, depth=0)` — execute and hydrate

## Query builder (target API)

**Current (0.2):** As above. No `offset`, `order_by`, `count`, `distinct`, or field projection. Nested filters require related `rdf:type` in the graph.

**Target (1.0):**

| Method | SPARQL |
|--------|--------|
| `.offset(n)` | `OFFSET n` |
| `.order_by(field, *, desc=False)` | `ORDER BY` on bound variable |
| `.count()` | Subselect or `COUNT` pattern; returns `int` |
| `.where(Relationship.is_(None))` / absence | `OPTIONAL` + `FILTER(!BOUND(?var))` or `NOT EXISTS` |
| `.distinct()` | `DISTINCT` (if supported) |

**Precedence:** Python `&` binds tighter than `|`; `(A & B) | C` is two disjuncts (fixed 0.2).

---

# SPARQL compilation

`Person.name == "Odos"` → SPARQL triple patterns bound to `?person`.

| Operator | Semantics |
|----------|-----------|
| `==` | Pattern match |
| `!=` | Inequality filter (or `Query.use_not_exists_for_ne()` for `NOT EXISTS`) |
| `&` | Conjoin patterns (`AndExpr` or multiple `.where`) |
| `\|` | Disjunction via `FILTER` + `EXISTS` branches (`OrExpr`) |
| `<`, `>`, `<=`, `>=` | Ordering on bound literal variables |
| `.in_(tuple)` | `FILTER(?var IN (...))` |
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

**Integration note:** scalar and relationship loading uses `sparql_from_graph` → TripleModel `from_graph` (see `sparqlmodel._triple`).

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
- JSON-LD helpers: `model_dump_jsonld` / `model_validate_jsonld` (interim; prefer TripleModel JSON-LD long term)

**Adapter target (internal):** map to `TripleModel` + `RdfConfig` / `rdf_field` without changing public field syntax.

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

- `list[T]` / collection fields for multi-valued literals and IRIs (via TripleModel) — **0.8**
- Language-tagged fields (`LangString`, multi-lang maps) — **0.8** (TripleModel)
- Polymorphic `session.query(Base).where(...)` matching subclasses — **0.8**
- Compiler emits `OPTIONAL` for nullable relationship paths in filters — **0.5**
- Optional `Relationship(..., back_populates=...)` for inverse navigation — **0.8**

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

**Dependency:** `triplemodel>=0.9.0,<2` in `pyproject.toml`.

**Today (0.3.x):** `graph.py` holds cascade/orphan policy only; mapping is in `_triple.py`. `serializers.py` remains interim until **0.4**. **Do not extend** interim serializers — fix upstream in TripleModel.

**Target wiring:**

| SparqlModel surface | TripleModel API |
|---------------------|-----------------|
| `put` graph write | `sync_to_graph(model, graph, mode=...)` + cascade |
| `get` / query load | `sparql_from_graph` → `TripleModel.from_graph` |
| `export_model` | `to_graph().serialize(...)` or `serialize()` |
| Predicate metadata | `rdf_field`, `Predicate`, `RdfConfig` |

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
| `update` | Atomic SPARQL Update sequences where endpoint supports — **0.7** |
| `ask` / `construct` | Optional protocol methods for existence and graph-shaped reads — **P2** |
| HttpStore `read_endpoint` / `write_endpoint` | Fuseki-style split URLs — **0.7** |
| Mirror sync | GSP GET, post-query hydrate, or documented remote-authoritative mode — **0.7** |
| Retries, timeouts, batch size limits | Production HttpStore — **0.7** |
| `OxigraphStore` / embedded backends | Optional — **1.0+** |

Protocols: [SPARQL 1.1 Query](https://www.w3.org/TR/sparql11-query/), [SPARQL 1.1 Update](https://www.w3.org/TR/sparql11-update/), [Graph Store HTTP](https://www.w3.org/TR/sparql11-http-rdf-update/).

---

# Security (SPARQL generation)

**Current (0.2):** Filter values serialized via RDFLib `Literal(...).n3()` and `URIRef(...).n3()`. IRIs with invalid characters raise `QueryError`. Predicates come from model metadata (trusted code).

**Target (1.0):**

- No public API that concatenates untrusted strings into SPARQL text
- Predicates and class IRIs remain declaration-time only
- `LIMIT` / `OFFSET` remain integer-typed at API boundary
- Security review documented before 1.0 GA

---

# Known limitations

## Until 0.5 (query)

| Area | Behavior |
|------|----------|
| Pagination | `limit` only; no `offset` or `order_by` |
| Absence / null filters | No `OPTIONAL` for nullable relationships in DSL |
| Aggregates | No `count()` on `Query` |

## Until 0.7 (HttpStore)

| Area | Behavior |
|------|----------|
| Mirror vs remote | `get` / cascade use mirror; `query` uses remote |
| Multi-writer endpoints | External updates invisible to mirror until sync |

## Until 0.8 (mapping)

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
| Interim mapping | **0.3.0:** session I/O uses `_triple.py`; `serializers.py` interim until 0.4 |

## Other (current)

| Area | Behavior |
|------|----------|
| Nested query filters | Related resource must have expected `rdf:type` |
| JSON-LD | `model_dump_jsonld` vs `export_model(..., "json-ld")` differ |
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
  model.py         # SPARQLModel; → TripleModel adapter
  fields.py        # Field/Relationship; → Predicate metadata
  graph.py         # cascade; → sync_to_graph (retiring local convert)
  serializers.py   # → TripleModel parse/serialize (retiring)
  stores/
  _triple.py       # TripleModel adapter (session put/get/hydrate — 0.3.0)
```

---

# Dependencies

```
pydantic>=2.5,<3
rdflib>=7.0,<8
triplemodel>=0.9.0,<2
typing-extensions>=4.8
```

Optional: `httpx`, `fastapi`

---

# Related projects

| Project | Role |
|---------|------|
| **TripleModel** | Required mapping engine |
| **RDFLib** | Graphs and SPARQL execution |
| **semantic-sqlmodel** | Optional future backend |
