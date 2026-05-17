# SparqlModel Technical Specification

## Overview

SparqlModel is a SPARQL-native object graph mapper for RDF triple stores. It is the **session and query layer** in a two-package stack with **[TripleModel](https://github.com/eddiethedean/triplemodel)** (`triplemodel`), which owns stateless Pydantic ↔ RDF mapping.

SparqlModel provides:

- `SPARQLModel` — typed models (public API; maps to TripleModel from 0.3)
- `SPARQLSession` — `add`, `put`, `delete`, `get`, `query`, `execute`
- SPARQL query generation from Python expressions
- Graph hydration with relationship depth
- Store backends (`MemoryStore` today; `HttpStore` on roadmap)
- FastAPI interoperability (optional extra)

| Layer | SparqlModel | TripleModel |
|-------|-------------|-------------|
| Session CRUD, cascade policy | Yes | No |
| Query DSL + SPARQL compiler | Yes | No |
| Stores | Yes | No |
| Model ↔ triples, terms, parse/serialize | 0.1.x interim / 0.3+ delegate | Yes |

Boundaries: [ECOSYSTEM.md](ECOSYSTEM.md) · [PLAN.md](PLAN.md) · [ROADMAP.md](ROADMAP.md)

---

# Ecosystem boundaries

**Heuristic:** code that never uses `SPARQLSession` belongs in **TripleModel**.

| Concern | Owner |
|---------|--------|
| XSD types, subject IRI prefix safety | TripleModel |
| `put` orphan / cascade | SparqlModel (`graph.py`, `session.py`) |
| Stale triples on declared predicates | TripleModel sync + SparqlModel `put` |
| `!=` / nested filters | SparqlModel (`compiler.py`) |
| Multi-valued predicates | TripleModel; SparqlModel hydration consumes |
| Turtle/JSON-LD parsers | TripleModel (0.4+); SparqlModel thin wrapper |
| Remote SPARQL endpoint | SparqlModel (`stores/`) |
| SHACL on `put` | `triplemodel[shacl]` + optional SparqlModel hook |

**Anti-patterns:** parsers or datatype registries only in `graph.py`; session/query code in TripleModel; early `triplemodel` pin before TripleModel 0.2 gates; circular imports.

| SparqlModel (public) | TripleModel (internal, 0.3+) |
|----------------------|------------------------------|
| `SPARQLModel`, `rdf_type`, `__prefixes__` | `TripleModel`, `RdfConfig` / `rdf_config()` |
| `Field("schema:name")` | `rdf_field` / `Predicate` |
| `id: IRI` | explicit IRI or `id_field` + namespace |
| `session.put` | TripleModel sync + SparqlModel cascade |
| `session.get`, `query` | TripleModel load + compiler/hydration |
| `export_model` | `to_graph().serialize(...)` (0.4+) |

---

# Core Components

## SPARQLModel

Base class for RDF-backed entities (SQLModel-style; backed by TripleModel from 0.3).

```python
class Person(SPARQLModel):
    rdf_type = "schema:Person"

    id: IRI
    name: str = Field("schema:name")
```

## SPARQLSession

Primary persistence and query interface.

```python
session = SPARQLSession()
session.put(person)
found = session.query(Person).where(Person.name == "Odos").first()
```

Responsibilities: `add`, `put`, `delete`, `get`, `query`, raw SPARQL `execute`, graph sync with the store.

---

# Query Builder

SQLModel-like queries over RDF:

```python
session.query(Person).where(Person.name == "Odos").all()

session.query(Person).where(Person.works_for.name == "Acme").all()
```

---

# SPARQL Compilation

Expressions compile to SPARQL patterns.

```python
Person.name == "Odos"  # → ?person schema:name "Odos" .
```

- `==` — triple pattern match
- `!=` — subject has some value for the predicate that differs from the RHS (not SQL `NOT EXISTS` for absent values)
- `None` filter values raise `QueryError`
- Literals escaped via RDFLib; colon strings (e.g. `"12:30"`) are not compact IRIs unless prefix is known

---

# RDF Persistence

## 0.1.x

- RDFLib graph add/remove via `MemoryStore.update_graph` (not SPARQL Update strings; HTTP stores may use UPDATE later)
- Interim serialization in `graph.py` (replaced by TripleModel in 0.3)
- Cascade/orphan policy stays in SparqlModel after integration

## `add`

Insert triples; does not remove existing triples for the subject.

## `put`

Remove owned triples (root, embedded tree, orphans), then write current state.

## `delete`

Remove owned triples for root and embedded composition targets.

## Ownership

- Nested `SPARQLModel` in a relationship → **composition** (recursive serialize, cascade on `put`/`delete`, orphan cleanup on any node in the tree)
- `IRI` only → external reference (link removed; target not cascade-deleted)
- Same IRI embedded from multiple parents → use `IRI` references for shared entities
- Orphan detection uses expanded IRIs

---

# Known limitations (0.1.x)

| Area | Behavior |
|------|----------|
| Multi-valued predicates | First object per predicate on load; `add` can duplicate |
| Extension triples | `put`/`delete` only mapped predicates + `rdf:type` |
| Nested query filters | Related resource must have expected `rdf:type` |
| JSON-LD | Custom vs `export_model(..., "json-ld")` paths differ |
| Export | `ensure_id()` may assign `urn:uuid:…` when `id` is unset |

---

# Hydration

```python
session.get(Person, iri, depth=2)
```

Modes: scalars only, relationship loading, depth-limited traversal. Load path uses TripleModel from 0.3.

---

# Relationships

```python
works_for: Organization | None = Relationship("schema:worksFor")
```

---

# JSON-LD and RDF formats

**0.1.x:** `model_dump_jsonld` / `model_validate_jsonld` and `export_model` via interim modules.

**0.4+:** TripleModel `parse` / `serialize`; SparqlModel may keep thin session-scoped helpers.

Formats: Turtle, JSON-LD, RDF/XML, N-Triples.

---

# FastAPI (planned)

Optional extra: response classes, content negotiation, RDF/JSON-LD responses.

---

# Optional features

| Feature | Owner |
|---------|--------|
| SHACL generation | TripleModel |
| SHACL on `put` | SparqlModel hook + `triplemodel[shacl]` |
| Named graphs / Dataset | TripleModel 0.5 |
| SPARQL federation | SparqlModel |
| Store experiments (Oxigraph, etc.) | SparqlModel |
| Reasoning hooks | optional, not core |

---

# Design principles

- Pythonic session/query APIs first
- Typed models over raw triples
- Explicit cascade and filter semantics
- TripleModel for mapping; SparqlModel for persistence and SPARQL

---

# Package layout

```text
sparqlmodel/
  model.py          # SPARQLModel; TripleModel adapter (0.3+)
  fields.py         # Field/Relationship → TripleModel metadata
  _triple.py        # adapter (0.2 dev, 0.3+)
  session.py
  query.py
  compiler.py       # SparqlModel only
  hydration.py
  graph.py          # cascade policy; delegates sync (0.3+)
  serializers.py    # delegates to TripleModel (0.4+)
  stores/
  fastapi/          # optional
```

---

# Dependencies

| Version | Packages |
|---------|----------|
| 0.1.x | `pydantic`, `rdflib`, `typing-extensions` |
| 0.2 | + `httpx` (optional); TripleModel in dev for adapter |
| 0.3+ | + `triplemodel` (see [ECOSYSTEM.md](ECOSYSTEM.md#triplemodel-version-gates)) |

**Extras:** `sparqlmodel[fastapi]`, `sparqlmodel[http]`

**Not in core:** `pyshacl` — use `triplemodel[shacl]`

**Tests:** TripleModel — terms and parse; SparqlModel — session, cascade, compiler; optional cross-package CI.

---

# Related projects

| Project | Role |
|---------|------|
| **TripleModel** | Mapping layer under SparqlModel |
| **semantic-sqlmodel** | Optional backend |
| **FastAPI** | Optional extra |
| **RDFLib** | Graphs and stores |

Full guide: [ECOSYSTEM.md](ECOSYSTEM.md).
