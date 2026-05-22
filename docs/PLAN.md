# SparqlModel Project Plan

## Vision

**SparqlModel — the SQLModel of SPARQL.**

SparqlModel is a **SPARQL ORM** for application developers. It requires **[TripleModel](https://github.com/eddiethedean/triplemodel)** `>=0.10` and focuses exclusively on what TripleModel does not provide: **sessions**, a **query compiler**, **store backends**, **cascade persistence policy**, and **hydration depth**.

TripleModel is the **mapping substrate** — literals, terms, `sync_to_graph`, `from_graph`, and file parse/serialize. SparqlModel does not compete with it; **`SPARQLModel` subclasses `TripleModel`** (Option A) so there is one class and one mapping path.

Guides: [ORM.md](ORM.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md) · [SPECS.md](SPECS.md) · [PRODUCTION.md](PRODUCTION.md)

---

# Production ORM definition (1.3 GA north star)

SparqlModel **1.2** means a **fully featured production SPARQL ORM** — the [SQLModel](https://sqlmodel.tiangolo.com/) of SPARQL for backend and FastAPI teams:

1. **Correctness** — One mapping path via `SPARQLModel(TripleModel)`; cascade/orphan rules covered by contract tests.
2. **Session parity** — Identity map, pending flush, `expire` / `refresh` / `merge` / `expunge`, scoped session for FastAPI, documented threading.
3. **Query parity** — Pagination (`offset` + `limit`), sorting, `count()`, filters including null/absence on relationships.
4. **RDF fidelity** — Multi-valued fields, language tags (TripleModel), polymorphic `rdf:type` queries where modeled.
5. **Operational stores** — Production `HttpStore` (read/write URLs, mirror contract, retries); `MemoryStore` for tests.
6. **Production hooks** — Optional SHACL on `put`, query logging, bulk operations.

**Explicit non-goals:** OWL editor, built-in reasoner, reimplementing TripleModel in `graph.py`.

GA gate: [SPECS.md — Production checklist](SPECS.md#production-orm-checklist-13-ga-gate).

---

# Parity tiers

| Tier | Meaning | Examples |
|------|---------|----------|
| **P0** | Required for production HTTP/API apps | Unified `SPARQLModel(TripleModel)`, `offset` / `order_by` / `count`, OPTIONAL filters, HttpStore mirror strategy |
| **P1** | SQLModel / SPARQLMojo parity | Full [ROADMAP parity backlog](ROADMAP.md#sparqlmojo-parity-backlog): modeling **0.13**, ops **0.14** |
| **P2** | Advanced / ecosystem | Named graphs, federation, CONSTRUCT/ASK helpers, Oxigraph store |

---

# Competitive positioning

| | SparqlModel | [SPARQLMojo](https://pypi.org/project/sparqlmojo/) | Raw rdflib |
|---|-------------|-------------------|------------|
| Session + query DSL | Yes | Yes | Manual |
| TripleModel mapping | Required | No | N/A |
| FastAPI `SessionDep` | Yes | No | Manual |
| Cascade `put` / orphans | Yes | Partial | Manual |
| Python 3.10+ | Yes | 3.12+ | Yes |

SparqlModel wins on **integrated mapping (TripleModel)**, **FastAPI**, **async HTTP**, **composition semantics**, and **documented store contracts**. SPARQLMojo leads on **lang/collections, property paths, ontology-aware queries** until **0.13** (see [parity backlog](ROADMAP.md#sparqlmojo-parity-backlog)).

---

# Product positioning

## SparqlModel (ORM)

- Entry point: `with SPARQLSession() as session:`
- SQLModel-style models: `SPARQLModel` (subclasses `TripleModel`), `Field`, `Relationship`
- Python queries → SPARQL: `session.query(Person).where(Person.name == x)`
- Unit-of-work semantics: `add`, `put`, `delete`, cascade, orphans
- Stores: `MemoryStore`, `HttpStore` (`sparqlmodel[http]`)

**Not SparqlModel:** mapping correctness, XSD registries, Turtle parsers, or stateless ETL — **that is TripleModel**.

## TripleModel (required dependency)

- PyPI: `triplemodel` · pinned in SparqlModel as `>=0.10.0,<2` (with `pyoxigraph>=0.5,<0.6`)
- Stateless Pydantic ↔ RDF; API frozen from TripleModel 0.9 until 1.0
- SparqlModel routes new mapping features through TripleModel first

| | TripleModel | SparqlModel |
|---|-------------|-------------|
| **Question** | “Are these triples correct?” | “How do I run my app on a graph?” |
| **State** | Stateless | Stateful session |
| **Grow here** | Terms, files, Dataset, SHACL | Compiler, stores, cascade, FastAPI |

---

# ORM thesis

SparqlModel exists to answer: **“How do I build and operate an application on RDF?”**

**Owned by SparqlModel (now and always):**

1. `SPARQLSession` — CRUD and graph sync with a store
2. Query DSL and SPARQL compiler
3. Cascade and orphan policy on `put` / `delete`
4. Hydration depth on `get` and query results
5. Pluggable stores (`MemoryStore`, `HttpStore`, …)
6. Optional FastAPI integration

**Owned by TripleModel (SparqlModel delegates via subclass):**

1. Model ↔ triple conversion
2. Literal and IRI term handling
3. `sync_to_graph` / `from_graph` / `parse` / `serialize`
4. Multi-valued fields, nested embeds, blank nodes (per TripleModel roadmap)

**Public ORM API stays stable** (`Field`, `Relationship`, `session.put`) while internals move to **Option A** (delete `_triple.py` adapter in **0.4**) and `serializers.py` is retired in **0.6**.

---

# Architecture (Option A)

```text
Application
    ↓
SPARQLModel(TripleModel) · Field/Relationship sugar · Query metaclass
    ↓
SPARQLSession · Compiler · Stores · graph.py (cascade only)   ← SparqlModel
    ↓
sync_to_graph · from_graph · terms · files                    ← TripleModel (same instance type)
    ↓
pyoxigraph · triplemodel · pydantic
```

**Never in SparqlModel:** duplicate `python_to_term`, new RDF format parsers, dynamic shadow `TripleModel` classes (`exec` adapter), or session-free mapping APIs.

**Never in TripleModel:** `SPARQLSession`, query compiler, cascade `put`, or HTTP store plugins.

---

# Integration strategy

SparqlModel **depends** on `triplemodel>=0.10` and **pyoxigraph** (0.5+). Remaining work: async sessions, file I/O consolidation, and production features.

| Phase | SparqlModel | TripleModel usage |
|-------|-------------|-------------------|
| **0.1.x** | ORM shipped; interim `graph.py` mapping | Dependency declared |
| **0.2** | `HttpStore`, identity map, `_triple` adapter (interim) | Contract tests |
| **0.3** | Session I/O via adapter (interim bridge) | `sync_to_graph` / `from_graph`; cascade-only `graph.py` |
| **0.4** | **Unified model (Option A)** — `SPARQLModel(TripleModel)`; delete `_triple.py` | Direct `sync_to_graph` / `from_graph` on app instances |
| **0.5** | **Pyoxigraph + TM 0.10** (`triplemodel.Store`, no core rdflib) | — |
| **0.6** | **Async end-to-end** (`AsyncSPARQLSession`, `AsyncHttpStore`, FastAPI) | — |
| **0.7** | Delegated file I/O | Thin `serializers.py`; TripleModel `parse` / `serialize` only |
| **0.8** | Query lists | `offset`, `order_by`, `count`, OPTIONAL nullable hops |
| **0.9** | Session cache | `merge`, `refresh`, `expunge`, scoped session docs |
| **0.10–0.12** | [Production HttpStore](ROADMAP.md#production-httpstore) | Mirror semantics, HTTP resilience, GSP sync |
| **0.13** | SPARQLMojo modeling parity | Multi-valued, lang, polymorphic query, property paths, inverse/VALUES |
| **0.14** | Production operations | SHACL hook, bulk, ASK/CONSTRUCT, `OxigraphStore`, logging |
| **0.15** | Production GA | SPECS P0+P1 complete; stable public API |

---

# Primary goals

**P0 (production APIs):**

- **Unified model (Option A)** — `SPARQLModel(TripleModel)`; one mapping path (**0.4**)
- **Pyoxigraph engine** — `triplemodel.Store` for session graphs (**0.5**, shipped)
- **Async ORM** — `AsyncSPARQLSession`, async stores, FastAPI `AsyncSessionDep` (**0.6**)
- Typed SPARQL persistence with explicit `add` / `put` / `delete` semantics
- Pythonic filters compiled to SPARQL (including pagination and sorting)
- Relationship hydration with `depth`; nullable relationship filters
- Operational stores with documented HttpStore mirror semantics
- **Lean on TripleModel** for all mapping and file I/O

**P1 (parity):**

- Session lifecycle aligned with SQLAlchemy (`merge`, `refresh`, `expunge`)
- Multi-valued and language-tagged fields via TripleModel
- Polymorphic queries and optional inverse relationships

**Cross-cutting:**

- Stable `SPARQLModel` / `Field` / `session.put` developer experience
- FastAPI session injection and content negotiation

---

# Target users

- FastAPI and backend teams
- Knowledge-graph product engineers
- Enterprise metadata and AI infrastructure
- Anyone who would reach for SQLModel if the database were RDF

---

# Technology stack

**Required:** `pydantic>=2.5,<3`, `pyoxigraph>=0.5,<0.6`, **`triplemodel>=0.10.0,<2`**, `typing-extensions`

**Optional extras:** `httpx` (HTTP store), `fastapi`

**SHACL:** `triplemodel[shacl]` — optional hook on `session.put`, not in SparqlModel core

**Development:** `pip install -e ".[dev]"` and optionally `pip install -e ../triplemodel`

---

# Releases (summary)

| Version | Theme |
|---------|--------|
| **0.1.x** | Core ORM + cascade |
| **0.2** | HttpStore, identity map, compiler 0.2, FastAPI |
| **0.3** | TripleModel session I/O via interim adapter (shipped) |
| **0.4** | Unified model (Option A) |
| **0.5** | Pyoxigraph + TripleModel 0.10 |
| **0.6** | Async end-to-end |
| **0.7** | Delegated file I/O |
| **0.8** | Query lists |
| **0.9** | Session cache |
| **0.10–0.12** | Production HttpStore |
| **0.13** | SPARQLMojo modeling parity |
| **0.14** | Production operations |
| **0.15** | Production GA |

Detail: [ROADMAP.md](ROADMAP.md)

---

# Risks

- Reimplementing TripleModel in `graph.py` instead of keeping cascade-only policy
- ORM scope creep (reasoning, ontology editing)
- Performance without identity map on large graphs
- **Metaclass + `TripleModel.__pydantic_init_subclass__` ordering** when merging query DSL with mapping validation
- Diverging `Field` sugar from TripleModel `rdf_field` / `Predicate` metadata
- Documenting features as shipped when only planned (keep ROADMAP / SPECS in sync)
- **HttpStore mirror** in multi-tenant or multi-writer deployments without sync strategy

---

# Strategy

1. **TripleModel first** for any mapping, literal, or format bug
2. **SparqlModel first** for session, compiler, cascade, stores
3. **Option A before async** — unified model (**0.4**), pyoxigraph engine (**0.5**), then async (**0.6**), then pagination and HttpStore
4. Preserve ORM public API (`Field`, `Relationship`, `session.put`); change internals on unified `SPARQLModel(TripleModel)` base
5. Document semantics in [ORM.md](ORM.md), [SPECS.md](SPECS.md), [PRODUCTION.md](PRODUCTION.md)
6. Contract tests: SparqlModel `put` triple sets align with TripleModel `sync_to_graph` + cascade rules
7. **SPECS Production checklist** is the **1.3** GA gate
