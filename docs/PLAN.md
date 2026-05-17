# SparqlModel Project Plan

## Vision

SparqlModel is a Python-native SPARQL ORM and object graph mapper inspired by SQLModel, Pydantic, and FastAPI ergonomics.

The project aims to make RDF and SPARQL systems operationally usable for normal Python developers by hiding low-level triple manipulation behind typed Python models and a **stateful session** with Pythonic queries.

SparqlModel is the **application persistence and SPARQL layer**. Canonical Pydantic ↔ RDF mapping, term conversion, and file I/O belong in **[RDFModel](https://github.com/eddiethedean/rdfmodel)**. See [ECOSYSTEM.md](ECOSYSTEM.md) for boundaries and integration gates.

---

# Core Thesis

Traditional semantic web tooling is:
- RDF-centric
- ontology-centric
- academic
- difficult to operationalize

SparqlModel aims to provide:
- typed Python models (user-facing `SPARQLModel` API; implementation converges on RDFModel)
- object-oriented graph persistence via `SPARQLSession`
- Pythonic query building that compiles to SPARQL
- modern developer ergonomics
- FastAPI compatibility
- Pydantic validation
- SPARQL-native persistence against triple stores

---

# Product Positioning

SparqlModel is:
- SQLModel-like (session + query DSL)
- graph-native
- RDF-backed
- SPARQL-powered

SparqlModel is NOT:
- an ontology editor
- a Protégé replacement
- a reasoning engine
- an academic OWL framework
- a stateless mapping or file-format library (that is **RDFModel**)

| Metaphor | RDFModel | SparqlModel |
|----------|----------|-------------|
| Role | Schema + serialization library | Database session + query language |
| State | Stateless (`to_graph` / `from_graph`) | Stateful (`SPARQLSession`) |
| Killer feature | Correct triples from Pydantic | `where(Model.field == x)` |

---

# Primary Goals

- Typed SPARQL persistence (`add`, `put`, `delete`, `get`, `query`)
- Pythonic graph traversal and nested filters
- SPARQL query generation from expressions
- Store backends (in-memory today; HTTP SPARQL 1.1 on roadmap)
- Graph hydration with relationship depth
- FastAPI integration (optional extra)
- **Thin mapping layer** — delegate terms, sync, and file formats to RDFModel as it matures

---

# Target Users

- Knowledge graph engineers
- AI infrastructure teams
- Enterprise metadata systems
- Semantic web developers
- RDF/SPARQL platform teams
- FastAPI backend developers
- Research platforms
- Government interoperability systems

Developers who only need **stateless** model ↔ graph or file round-trip without a session should use **RDFModel** directly.

---

# Ecosystem Relationship

## RDFModel (required integration path)

**Repo:** [github.com/eddiethedean/rdfmodel](https://github.com/eddiethedean/rdfmodel) · PyPI: `rdfmodel`

RDFModel owns: `RdfModel`, field/predicate metadata, `python_to_term` / `term_to_python`, stateless `to_graph` / `from_graph`, and (roadmap) `parse` / `serialize`, Dataset/named graphs, optional SHACL.

SparqlModel owns: `SPARQLSession`, stores, query DSL, SPARQL compiler, hydration depth, cascade/orphan policy on `put`/`delete`, FastAPI, remote endpoints.

**Rules:**
1. SparqlModel **may** depend on `rdfmodel` once integration gates are met; it **must not** reimplement mapping logic that belongs upstream.
2. RDFModel **must not** import SparqlModel.
3. Term/graph mapping bugs → prefer RDFModel issues/PRs; compiler/session/cascade bugs → SparqlModel.

SparqlModel should get **thinner** as RDFModel matures, not wider. New datatype registries, Turtle parsers, or multi-valued round-trip logic go to RDFModel first.

Full maintainer guide: [ECOSYSTEM.md](ECOSYSTEM.md).

## semantic-sqlmodel

Operational SQLModel + semantic interoperability layer. SparqlModel should function as an optional RDF/SPARQL backend for semantic-sqlmodel once both stacks are stable.

---

# High-Level Architecture

```text
Application code
    ↓
SPARQLSession · Query · Compiler · Stores     ← SparqlModel
    ↓
Mapping · terms · parse/serialize (future)    ← RDFModel
    ↓
rdflib · pydantic
```

**Stay in SparqlModel:** `compiler.py`, `query.py`, `session.py`, cascade/orphan rules, `stores/*`, identity map, FastAPI.

**Converge on RDFModel:** `graph.py` serialization path, `fields.py` metadata adapter, `serializers.py` (delegate), term conversion in `types.py` where overlapping.

---

# Recommended Technology Stack

Core (today):
- Pydantic v2
- RDFLib
- typing-extensions

Core (after RDFModel integration gate):
- `rdfmodel` (version pinned per [ECOSYSTEM.md](ECOSYSTEM.md#rdfmodel-releases-to-wait-for-dependency-gate))

SparqlModel-owned optional:
- `httpx` — HTTP SPARQL store (`sparqlmodel[http]` or dev)
- `fastapi` — SparqlModel extra only

Do **not** bundle in SparqlModel core:
- `pyshacl` — use `rdfmodel[shacl]` if validation hooks are added on `put`
- SQLAlchemy / BerkeleyDB — RDFModel store extras if a `Store` needs them

Developer:
- pytest, ruff, ty
- local dev: `pip install -e ../rdfmodel` before runtime dependency is declared

---

# MVP Scope

Version 0.1 (shipped):
- `SPARQLModel`, `Field`, `Relationship`, `IRI`
- `SPARQLSession` CRUD and in-memory store
- Query builder and SPARQL compiler (scalar + single-hop nested)
- Hydration (`depth` 0–2)
- RDF export/import (implemented in SparqlModel; to delegate in 0.3+)

---

# Release Strategy (aligned with RDFModel)

| SparqlModel | Focus | RDFModel dependency |
|-------------|--------|---------------------|
| **0.1.x** | Session, compiler, cascade (shipped) | None (temporary overlap in `graph.py`) |
| **0.2** | `HttpStore`, richer compiler, identity map, FastAPI | Dev-only pin; no required PyPI dep |
| **0.3** | Integrate `rdfmodel`; thin `graph.py`; adapter for `SPARQLModel` | `rdfmodel>=0.2` (sync/remove, namespaces, nested embeds, multi-value) |
| **0.4** | Delegate file I/O to RDFModel; named graphs when upstream ready | `rdfmodel>=0.4` (parse/serialize); `0.5` for Dataset if needed |

See [ROADMAP.md](ROADMAP.md) for checklist detail.

---

# Long-Term Vision

SparqlModel becomes:
- the SQLModel of SPARQL — session, queries, and store backends
- a thin orchestration layer over RDFModel for mapping correctness
- a semantic AI / FastAPI infrastructure component for knowledge-graph apps

It does **not** aim to be the canonical RDF mapping library; that role is RDFModel’s.

---

# Major Risks

- Over-academic design
- RDF-first APIs exposed to app developers
- Excessive abstraction magic
- **Duplicating RDFModel** — slows both projects and diverges term semantics
- Depending on `rdfmodel` before sync/remove and nested models exist (adapter fights)
- Performance issues on large graphs without identity map / caching
- Trying to replace graph-native tooling or full reasoners

---

# Strategic Recommendations

- Keep APIs Pythonic; preserve `SPARQLModel` / `Field` / `session.put` UX for users
- Break duplicate **internal** graph code, not public field/session APIs
- Avoid growing `graph.py` with new parsers or datatype registries — add upstream
- Keep Pydantic central; raw triple APIs stay secondary
- Focus on operational use cases (CRUD, filters, HTTP stores)
- Treat reasoning and SHACL as optional hooks via RDFModel extras
- Optimize for FastAPI and AI ecosystems
- Open RDFModel issues for mapping bugs; fix compiler/session/cascade in SparqlModel
