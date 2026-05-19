# SparqlModel Project Plan

## Vision

**SparqlModel — the SQLModel of SPARQL.**

SparqlModel is a **SPARQL ORM** for application developers. It requires **[TripleModel](https://github.com/eddiethedean/triplemodel)** `>=0.9` and focuses exclusively on what TripleModel does not provide: **sessions**, a **query compiler**, **store backends**, **cascade persistence policy**, and **hydration depth**.

TripleModel is the **mapping substrate** — literals, terms, `sync_to_graph`, `from_graph`, and file parse/serialize. SparqlModel does not compete with it; it **consumes** it.

Guides: [ORM.md](ORM.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md) · [SPECS.md](SPECS.md) · [PRODUCTION.md](PRODUCTION.md)

---

# Production ORM definition (1.1 GA north star)

SparqlModel **1.1** means a **fully featured production SPARQL ORM** — the [SQLModel](https://sqlmodel.tiangolo.com/) of SPARQL for backend and FastAPI teams:

1. **Correctness** — One mapping path via TripleModel; cascade/orphan rules covered by contract tests.
2. **Session parity** — Identity map, pending flush, `expire` / `refresh` / `merge` / `expunge`, scoped session for FastAPI, documented threading.
3. **Query parity** — Pagination (`offset` + `limit`), sorting, `count()`, filters including null/absence on relationships.
4. **RDF fidelity** — Multi-valued fields, language tags (TripleModel), polymorphic `rdf:type` queries where modeled.
5. **Operational stores** — Production `HttpStore` (read/write URLs, mirror contract, retries); `MemoryStore` for tests.
6. **Production hooks** — Optional SHACL on `put`, query logging, bulk operations.

**Explicit non-goals:** OWL editor, built-in reasoner, reimplementing TripleModel in `graph.py`.

GA gate: [SPECS.md — Production checklist](SPECS.md#production-orm-checklist-11-ga-gate).

---

# Parity tiers

| Tier | Meaning | Examples |
|------|---------|----------|
| **P0** | Required for production HTTP/API apps | TripleModel wiring, `offset` / `order_by` / `count`, OPTIONAL filters, HttpStore mirror strategy |
| **P1** | SQLModel / SPARQLMojo parity | `merge` / `refresh` / `expunge`, multi-valued + lang fields, polymorphic query, read/write endpoints |
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

SparqlModel wins on **integrated mapping (TripleModel)**, **FastAPI**, **composition semantics**, and **documented store contracts**. SPARQLMojo leads on **lang/collection fields** until **0.9** (planned via TripleModel).

---

# Product positioning

## SparqlModel (ORM)

- Entry point: `with SPARQLSession() as session:`
- SQLModel-style models: `SPARQLModel`, `Field`, `Relationship`
- Python queries → SPARQL: `session.query(Person).where(Person.name == x)`
- Unit-of-work semantics: `add`, `put`, `delete`, cascade, orphans
- Stores: `MemoryStore`, `HttpStore` (`sparqlmodel[http]`)

**Not SparqlModel:** mapping correctness, XSD registries, Turtle parsers, or stateless ETL — **that is TripleModel**.

## TripleModel (required dependency)

- PyPI: `triplemodel` · pinned in SparqlModel as `>=0.9.0,<2`
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

**Owned by TripleModel (SparqlModel delegates):**

1. Model ↔ triple conversion
2. Literal and IRI term handling
3. `sync_to_graph` / `from_graph` / `parse` / `serialize`
4. Multi-valued fields, nested embeds, blank nodes (per TripleModel roadmap)

**Public ORM API stays stable** while interim `graph.py` / `serializers.py` are retired in favor of TripleModel calls.

---

# Architecture

```text
Application
    ↓
SPARQLSession · Query · Compiler · Stores     ← SparqlModel
    ↓
triplemodel>=0.9 (sync, load, terms, files)   ← TripleModel
    ↓
rdflib · pydantic
```

**Never in SparqlModel:** duplicate `python_to_term`, new RDF format parsers, or session-free mapping APIs.

**Never in TripleModel:** `SPARQLSession`, query compiler, cascade `put`, or HTTP store plugins.

---

# Integration strategy

SparqlModel **already depends** on `triplemodel>=0.9`. The remaining work is **wiring**, not packaging:

| Phase | SparqlModel | TripleModel usage |
|-------|-------------|-------------------|
| **0.1.x** | ORM shipped; interim `graph.py` | Dependency declared |
| **0.2** | `HttpStore`, identity map, `_triple` adapter | Contract tests |
| **0.3** | Session I/O via adapter | `sync_to_graph` / `from_graph`; retire interim mapping |
| **0.4** | **Async end-to-end** (`AsyncSPARQLSession`, `AsyncHttpStore`, FastAPI) | — |
| **0.5** | Thin `serializers.py` | `parse` / `serialize` only |
| **0.6** | Query production (`offset`, `order_by`, `count`, OPTIONAL) | — |
| **0.7** | Session lifecycle (`merge`, `refresh`, `expunge`, scoped session) | — |
| **0.8** | HttpStore production (read/write URLs, mirror sync) | — |
| **0.9** | RDF modeling in ORM layer | Multi-valued, lang tags, polymorphic query |
| **1.0** | Ops (SHACL hook, bulk, logging) | SHACL validation |
| **1.1** | Production GA (SPECS P0+P1 complete) | Stable mapping substrate |

---

# Primary goals

**P0 (production APIs):**

- **Async ORM** — `AsyncSPARQLSession`, async stores, FastAPI `AsyncSessionDep` (**0.4**)
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

**Required:** `pydantic>=2.5,<3`, `rdflib>=7.0,<8`, **`triplemodel>=0.9.0,<2`**, `typing-extensions`

**Optional extras:** `httpx` (HTTP store), `fastapi`

**SHACL:** `triplemodel[shacl]` — optional hook on `session.put`, not in SparqlModel core

**Development:** `pip install -e ".[dev]"` and optionally `pip install -e ../triplemodel`

---

# Releases (summary)

| Version | Theme |
|---------|--------|
| **0.1.x** | Core ORM + cascade |
| **0.2** | HttpStore, identity map, compiler 0.2, FastAPI |
| **0.3** | TripleModel session I/O (shipped) |
| **0.4** | Async end-to-end |
| **0.5** | Delegated file I/O |
| **0.6–0.8** | Production query + session + HttpStore |
| **0.9–1.0** | RDF modeling + ops |
| **1.1** | Production GA |

Detail: [ROADMAP.md](ROADMAP.md)

---

# Risks

- Reimplementing TripleModel in `graph.py` instead of deleting it
- ORM scope creep (reasoning, ontology editing)
- Performance without identity map on large graphs
- Diverging `Field` UX from TripleModel predicate metadata during adapter work
- Documenting features as shipped when only planned (keep ROADMAP / SPECS in sync)
- **HttpStore mirror** in multi-tenant or multi-writer deployments without sync strategy

---

# Strategy

1. **TripleModel first** for any mapping, literal, or format bug
2. **SparqlModel first** for session, compiler, cascade, stores
3. **P0 before P2** — async (**0.4**), then pagination and HttpStore, before federation/reasoning
4. Preserve ORM public API; add methods; change internals via adapter layer
5. Document semantics in [ORM.md](ORM.md), [SPECS.md](SPECS.md), [PRODUCTION.md](PRODUCTION.md)
6. Contract tests: SparqlModel `put` triple sets align with TripleModel `sync_to_graph` + cascade rules
7. **SPECS Production checklist** is the **1.1** GA gate
