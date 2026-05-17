# SparqlModel Project Plan

## Vision

SparqlModel is a Python-native SPARQL ORM and object graph mapper inspired by SQLModel, Pydantic, and FastAPI ergonomics.

It sits on **[TripleModel](https://github.com/eddiethedean/triplemodel)** for Pydantic ↔ RDF mapping and, from 0.4 onward, file I/O. SparqlModel adds the **stateful session**, SPARQL query compiler, store backends, and cascade semantics application developers need.

See [ECOSYSTEM.md](ECOSYSTEM.md) for package boundaries.

---

# Core Thesis

Traditional semantic web tooling is RDF-centric, ontology-centric, and hard to operationalize.

This stack provides:
- **TripleModel** — correct, stateless mapping from typed models to triples
- **SparqlModel** — sessions, Pythonic queries, stores, and graph persistence policy

Together they hide low-level triple manipulation behind familiar Python APIs.

---

# Product Positioning

## SparqlModel

- SQLModel-like (session + query DSL)
- graph-native, RDF-backed, SPARQL-powered

**Not:** an ontology editor, reasoner, Protégé replacement, or stateless mapping library.

## TripleModel

- Pydantic ↔ RDF graphs, stateless
- terms, sync, parse/serialize (see TripleModel roadmap)

| | TripleModel | SparqlModel |
|---|-------------|-------------|
| **Role** | Schema + serialization | Session + query language |
| **State** | Stateless | Stateful (`SPARQLSession`) |
| **Killer feature** | Correct triples from Pydantic | `where(Model.field == x)` |

Developers who only need model ↔ graph or files without a session use **TripleModel** directly.

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

- Knowledge graph engineers
- AI infrastructure teams
- Enterprise metadata systems
- RDF/SPARQL platform teams
- FastAPI backend developers
- Research and government interoperability systems

---

# Ecosystem

## TripleModel

**Repo:** [github.com/eddiethedean/triplemodel](https://github.com/eddiethedean/triplemodel) · PyPI: `triplemodel`

Owns: `TripleModel`, `rdf_field`, `python_to_term` / `term_to_python`, `to_graph` / `sync_to_graph` / `from_graph`, parse/serialize, Dataset/named graphs (roadmap), optional SHACL.

## SparqlModel

Owns: `SPARQLSession`, stores, query DSL, SPARQL compiler, hydration depth, cascade/orphan on `put`/`delete`, FastAPI, remote endpoints.

**Rules:**
1. SparqlModel depends on `triplemodel` from 0.3; mapping logic stays upstream.
2. TripleModel does not import SparqlModel.
3. Mapping bugs → TripleModel; session/compiler/cascade → SparqlModel.

Maintainer guide: [ECOSYSTEM.md](ECOSYSTEM.md).

## semantic-sqlmodel

Optional RDF/SPARQL backend for semantic-sqlmodel once both stacks are stable.

---

# Architecture

```text
Application code
    ↓
SPARQLSession · Query · Compiler · Stores     ← SparqlModel
    ↓
TripleModel · terms · parse/serialize         ← triplemodel
    ↓
rdflib · pydantic
```

**SparqlModel only:** `compiler.py`, `query.py`, `session.py`, cascade/orphan, `stores/*`, identity map, FastAPI.

**TripleModel (from 0.3):** model ↔ triple conversion, terms, file formats (0.4+).

**0.1.x interim:** local `graph.py` / `fields.py` until 0.3 wires in `triplemodel`.

---

# Technology Stack

**SparqlModel core (0.1.x):** Pydantic v2, RDFLib, typing-extensions

**From SparqlModel 0.3:** `triplemodel` (pin per [ECOSYSTEM.md](ECOSYSTEM.md#triplemodel-version-gates))

**SparqlModel extras:** `httpx` (HTTP store), `fastapi`

**Not in SparqlModel core:** `pyshacl` — use `triplemodel[shacl]` for validation hooks

**Development:** `pip install -e ../triplemodel` alongside SparqlModel when working on the adapter.

---

# Releases

| SparqlModel | Focus | TripleModel |
|-------------|--------|-------------|
| **0.1.x** | Session, compiler, cascade; interim local mapper | used in dev; not a declared dep yet |
| **0.2** | `HttpStore`, richer compiler, identity map, FastAPI | dev pin + `_triple.py` prototype |
| **0.3** | `triplemodel` required; thin `graph.py` | `>=0.2` (sync, namespaces, nested embeds, multi-value) |
| **0.4** | Delegate serializers | `>=0.4` (parse/serialize); `0.5` for Dataset if needed |

Detail: [ROADMAP.md](ROADMAP.md).

---

# MVP (0.1.x, shipped)

- `SPARQLModel`, `Field`, `Relationship`, `IRI`
- `SPARQLSession` CRUD and in-memory store
- Query builder and SPARQL compiler
- Hydration (`depth` 0–2)
- RDF export via interim `graph.py` / `serializers.py`

---

# Long-Term Vision

- **SparqlModel** — the SQLModel of SPARQL: sessions, queries, store backends
- **TripleModel** — the canonical mapping layer underneath
- Together — practical knowledge-graph apps with FastAPI and AI tooling

---

# Risks

- Over-academic or RDF-first APIs for app developers
- Reimplementing TripleModel inside SparqlModel
- Declaring `triplemodel` before TripleModel 0.2 sync/remove and nested models
- Performance without identity map / caching on large graphs
- Scope creep into reasoning or ontology editing

---

# Strategy

- Preserve `SPARQLModel`, `Field`, and `session.put` UX
- Route mapping and formats to TripleModel; keep cascade and SPARQL in SparqlModel
- Document behavior explicitly (`put`, `!=`, `add`)
- Optional heavy deps as extras only
- FastAPI and operational RDF first
