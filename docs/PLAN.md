# SparqlModel Project Plan

## Vision

**SparqlModel — the SQLModel of SPARQL.**

SparqlModel is a **SPARQL ORM** for application developers. It requires **[TripleModel](https://github.com/eddiethedean/triplemodel)** `>=0.9` and focuses exclusively on what TripleModel does not provide: **sessions**, a **query compiler**, **store backends**, **cascade persistence policy**, and **hydration depth**.

TripleModel is the **mapping substrate** — literals, terms, `sync_to_graph`, `from_graph`, and file parse/serialize. SparqlModel does not compete with it; it **consumes** it.

Guides: [ORM.md](ORM.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md)

---

# Product positioning

## SparqlModel (ORM)

- Entry point: `SPARQLSession()`
- SQLModel-style models: `SPARQLModel`, `Field`, `Relationship`
- Python queries → SPARQL: `session.query(Person).where(Person.name == x)`
- Unit-of-work semantics: `add`, `put`, `delete`, cascade, orphans
- Stores: in-memory today; HTTP SPARQL and identity map on the roadmap

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
| **Now (0.1.x)** | ORM shipped; interim `graph.py` | Dependency declared; selective API adoption starting |
| **0.2** | `HttpStore`, identity map, `_triple` adapter | Contract tests against released TripleModel |
| **0.3** | `put`/`get` through `sync_to_graph` / `from_graph` | Delete interim term conversion in `graph.py` |
| **0.4** | Thin `serializers.py` | `parse` / `serialize` only in TripleModel |

---

# Primary goals

- Typed SPARQL persistence with explicit `add` / `put` / `delete` semantics
- Pythonic filters compiled to SPARQL
- Relationship hydration with `depth`
- Operational stores (memory + remote SPARQL)
- **Lean on TripleModel** for all mapping and file I/O
- Stable `SPARQLModel` / `Field` / `session.put` developer experience

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

| SparqlModel | ORM | TripleModel wiring |
|-------------|-----|-------------------|
| **0.1.x** | Session, query, cascade | `triplemodel>=0.9` required; interim `graph.py` |
| **0.2** | Remote store, identity map | Adapter + contract tests |
| **0.3** | Frozen ORM surface | Session I/O via TripleModel sync/load |
| **0.4** | ORM + SPARQL only | Delegated file I/O |

Detail: [ROADMAP.md](ROADMAP.md)

---

# Risks

- Reimplementing TripleModel in `graph.py` instead of deleting it
- ORM scope creep (reasoning, ontology editing)
- Performance without identity map on large graphs
- Diverging `Field` UX from TripleModel predicate metadata during adapter work

---

# Strategy

1. **TripleModel first** for any mapping, literal, or format bug
2. **SparqlModel first** for session, compiler, cascade, stores
3. Preserve ORM public API; change internals via adapter layer
4. Document semantics in [ORM.md](ORM.md) and [SPECS.md](SPECS.md)
5. Contract tests: SparqlModel `put` triple sets align with TripleModel `sync_to_graph` + cascade rules
