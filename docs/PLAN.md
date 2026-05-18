# SparqlModel Project Plan

## Vision

**SparqlModel — the SQLModel of SPARQL:** typed models, a persistent session, and Python queries that compile to SPARQL.

SparqlModel is a Python-native **SPARQL ORM** inspired by SQLModel, Pydantic, and FastAPI ergonomics. It sits on **[TripleModel](https://github.com/eddiethedean/triplemodel)** as a stateless mapping substrate (from 0.3 onward) and adds what application developers need: **stateful sessions**, a query compiler, store backends, and cascade persistence policy.

User guide: [ORM.md](ORM.md) · Package boundaries: [ECOSYSTEM.md](ECOSYSTEM.md)

---

# Product Positioning

## SparqlModel (ORM)

- Session-first: `SPARQLSession` is the main entry point
- SQLModel-like query DSL: `session.query(Model).where(Model.field == x)`
- Graph-native persistence: `put`, `delete`, cascade, hydration depth
- Store backends (in-memory today; HTTP SPARQL on roadmap)

**Not:** an ontology editor, reasoner, Protégé replacement, or stateless mapping library — **that is [TripleModel](https://github.com/eddiethedean/triplemodel)**.

## TripleModel (mapping substrate)

- Pydantic ↔ RDF graphs, stateless
- Terms, sync, parse/serialize (see TripleModel roadmap)

| | TripleModel | SparqlModel |
|---|-------------|-------------|
| **Metaphor** | SQLAlchemy Core / serde layer | SQLModel / SQLAlchemy ORM |
| **Role** | Correct triples from Pydantic | Session + query language |
| **State** | Stateless | Stateful (`SPARQLSession`) |
| **Killer feature** | `to_graph()` / `from_graph()` | `where(Model.field == x)` |

Developers who only need model ↔ graph or files **without a session** use **TripleModel** directly.

---

# ORM thesis

SparqlModel exists to answer: **“How do I run an application on a graph?”**

Core ORM capabilities (now and planned):

- **`SPARQLSession`** — unit of work over a store (`add`, `put`, `delete`, `get`, `query`)
- **Query compiler** — Python expressions → SPARQL WHERE
- **Persistence policy** — composition cascade, orphan cleanup, `add` vs `put` semantics
- **Hydration** — relationship depth on `get` and query results
- **Stores** — `MemoryStore`; `HttpStore`, identity map, session cache (roadmap 0.2)
- **FastAPI** — optional extra for RDF APIs (roadmap)

Mapping and file formats delegate to TripleModel from 0.3 / 0.4; the **public ORM surface stays stable**.

---

# Core Thesis

Traditional semantic web tooling is RDF-centric, ontology-centric, and hard to operationalize.

This stack provides:

- **TripleModel** — correct, stateless mapping from typed models to triples
- **SparqlModel** — sessions, Pythonic queries, stores, and graph persistence policy

Together they hide low-level triple manipulation behind familiar Python APIs — with SparqlModel as the application ORM layer.

---

# Primary Goals

- Typed SPARQL persistence (`add`, `put`, `delete`, `get`, `query`)
- Pythonic graph traversal and nested filters
- SPARQL generation from Python expressions
- Store backends (in-memory today; HTTP SPARQL 1.1 on roadmap)
- Graph hydration with relationship depth
- FastAPI integration (optional extra)
- Delegation of mapping and file I/O to TripleModel per [ROADMAP.md](ROADMAP.md)

---

# Target Users

- FastAPI and backend developers
- Knowledge graph engineers building operational systems
- AI infrastructure and enterprise metadata teams
- RDF/SPARQL platform teams
- Research and government interoperability systems

---

# Ecosystem

## TripleModel

**Repo:** [github.com/eddiethedean/triplemodel](https://github.com/eddiethedean/triplemodel) · PyPI: `triplemodel`

Owns: `TripleModel`, `rdf_field`, term conversion, `to_graph` / `sync_to_graph` / `from_graph`, parse/serialize, Dataset/named graphs, optional SHACL.

## SparqlModel

Owns: `SPARQLSession`, stores, query DSL, SPARQL compiler, hydration depth, cascade/orphan on `put`/`delete`, FastAPI, remote endpoints.

**Rules:**

1. SparqlModel depends on `triplemodel` from 0.3; mapping logic stays upstream.
2. TripleModel does not import SparqlModel.
3. Mapping bugs → TripleModel; session/compiler/cascade → SparqlModel.

Maintainer guide: [ECOSYSTEM.md](ECOSYSTEM.md)

## semantic-sqlmodel

Optional RDF/SPARQL backend for semantic-sqlmodel once both stacks are stable.

---

# Architecture

```text
Application code
    ↓
SPARQLSession · Query · Compiler · Stores     ← SparqlModel (ORM)
    ↓
TripleModel · terms · parse/serialize         ← triplemodel (substrate)
    ↓
rdflib · pydantic
```

**SparqlModel only:** `compiler.py`, `query.py`, `session.py`, cascade/orphan, `stores/*`, identity map, FastAPI.

**TripleModel (from 0.3):** model ↔ triple conversion, terms, file formats (0.4+).

**0.1.x interim:** local `graph.py` / `fields.py` until 0.3 wires in `triplemodel` (implementation detail; ORM API unchanged).

---

# Technology Stack

**SparqlModel core (0.1.x):** Pydantic v2, RDFLib, typing-extensions

**From SparqlModel 0.3:** `triplemodel` (pin per [ECOSYSTEM.md](ECOSYSTEM.md#triplemodel-version-gates))

**SparqlModel extras:** `httpx` (HTTP store), `fastapi`

**Not in SparqlModel core:** `pyshacl` — use `triplemodel[shacl]` for validation hooks

**Development:** `pip install -e ../triplemodel` alongside SparqlModel when working on the adapter.

---

# Releases

| SparqlModel | ORM focus | TripleModel integration |
|-------------|-----------|-------------------------|
| **0.1.x** | Session, compiler, cascade | interim local mapper |
| **0.2** | `HttpStore`, identity map, FastAPI | dev pin + adapter prototype |
| **0.3** | Public ORM API unchanged | `triplemodel` required |
| **0.4** | Session + SPARQL | delegate serializers |

Detail: [ROADMAP.md](ROADMAP.md)

---

# MVP (0.1.x, shipped)

- `SPARQLModel`, `Field`, `Relationship`, `IRI`
- `SPARQLSession` CRUD and in-memory store
- Query builder and SPARQL compiler
- Hydration (`depth` 0–2)
- Optional RDF export via interim serializers

---

# Long-Term Vision

- **SparqlModel** — the SQLModel of SPARQL: sessions, queries, store backends
- **TripleModel** — the canonical mapping substrate underneath
- Together — practical knowledge-graph apps with FastAPI and AI tooling

---

# Risks

- Over-academic or RDF-first APIs for app developers
- Reimplementing TripleModel inside SparqlModel (weakens ORM vs mapper positioning)
- Declaring `triplemodel` before TripleModel 0.2 sync/remove and nested models
- Performance without identity map / caching on large graphs
- Scope creep into reasoning or ontology editing

---

# Strategy

- Preserve `SPARQLModel`, `Field`, and `session.put` UX
- Route mapping and formats to TripleModel; keep cascade and SPARQL in SparqlModel
- Document ORM behavior explicitly ([ORM.md](ORM.md), `put`, `!=`, `add`)
- Optional heavy deps as extras only
- FastAPI and operational RDF first
