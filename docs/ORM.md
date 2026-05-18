# SparqlModel ORM guide

**SparqlModel — the SQLModel of SPARQL:** typed models, a persistent session, and Python queries that compile to SPARQL.

SparqlModel is a **session-first SPARQL ORM** for building applications on RDF triple stores. If you think in terms of SQLModel or SQLAlchemy ORM — `session.add`, `session.query(Model).where(...)`, and unit-of-work semantics — you are in the right place.

For stateless Pydantic ↔ RDF mapping, file parse/serialize, and ETL, use **[TripleModel](https://github.com/eddiethedean/triplemodel)** directly. SparqlModel depends on TripleModel from 0.3 onward as an internal mapping substrate; you keep the SparqlModel public API (`SPARQLSession`, `Field`, `Relationship`).

Related docs: [SPECS.md](SPECS.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md)

---

## Choose your package

| I need… | Use |
|---------|-----|
| CRUD, queries, and persistence policy in an app | **SparqlModel** (`SPARQLSession`) |
| Python filters that compile to SPARQL (`Model.field == value`) | **SparqlModel** |
| Remote SPARQL endpoints, identity map, FastAPI (roadmap) | **SparqlModel** |
| Convert models to triples or load a Turtle file without a session | **[TripleModel](https://github.com/eddiethedean/triplemodel)** |
| ETL, libraries, tests, one-off serialization | **TripleModel** |

| | SparqlModel | TripleModel |
|---|-------------|-------------|
| **Metaphor** | SQLModel / SQLAlchemy ORM | SQLAlchemy Core / serde layer |
| **Entry point** | `SPARQLSession()` | `model.to_graph()` / `parse()` |
| **State** | Stateful session | Stateless |

---

## Stack

```text
Application code
    ↓
SPARQLSession · Query · Compiler · Stores     ← SparqlModel (ORM)
    ↓
TripleModel · terms · parse/serialize         ← triplemodel (mapping substrate, 0.3+)
    ↓
rdflib · pydantic
```

SparqlModel **0.1.x** still ships an interim local mapper in `graph.py` until 0.3 wires in `triplemodel`. The ORM surface (`SPARQLSession`, query DSL, cascade) is unchanged.

---

## What SparqlModel provides

- **`SPARQLSession`** — unit of work over a graph store (`add`, `put`, `delete`, `get`, `query`, `execute`)
- **`SPARQLModel`** — entity classes mapped to RDF (SQLModel-style `Field` / `Relationship`)
- **Query DSL** — `session.query(Person).where(Person.name == "Alice").all()`
- **SPARQL compiler** — Python comparisons and nested hops → SPARQL WHERE
- **Hydration** — `session.get(Person, iri, depth=1)` (eager-load relationships)
- **Persistence policy** — composition cascade and orphan cleanup on `put` / `delete`
- **Stores** — `MemoryStore` today; HTTP SPARQL store on the [roadmap](ROADMAP.md)

**Not SparqlModel:** ontology editing, built-in reasoning, or stateless file-only workflows (use TripleModel).

---

## ORM lifecycle

| Method | Semantics |
|--------|-----------|
| **`add(model)`** | Insert triples only; does not remove existing triples for the subject. Re-`add` can leave stale literals. |
| **`put(model)`** | Upsert: remove owned triples (root, embedded tree, orphans), then write current state. |
| **`delete(model)`** | Remove owned triples for the root and embedded composition targets. |
| **`get(Model, iri, depth=0)`** | Load one entity by IRI; optional relationship depth (0–2). |
| **`query(Model).where(...).all()`** | Find entities matching Python filter expressions (compiled to SPARQL). |
| **`execute(sparql)`** | Raw SPARQL SELECT; returns variable bindings. |

Always start application code with a session:

```python
session = SPARQLSession()
session.put(person)
found = session.query(Person).where(Person.name == "Odos").first()
```

---

## Composition and cascade (unit-of-work policy)

Relationships behave like ORM composition vs reference:

| Relationship value | On `put` / `delete` |
|--------------------|---------------------|
| Nested **`SPARQLModel`** (embedded object) | **Composition** — serialized recursively; owned triples removed on update/delete; orphans cleaned when a link changes |
| **`IRI` only** | **Reference** — link updated; target resource **not** cascade-deleted |

Shared entities referenced from multiple parents should use **`IRI` references**, not duplicate embeds.

This policy lives in SparqlModel (`session.py`, `graph.py`), not in TripleModel. TripleModel syncs owned triples for a single resource; SparqlModel orchestrates multi-resource cascade across a session graph.

---

## Query DSL

SQLModel-style filters over RDF:

```python
session.query(Person).where(Person.name == "Odos").all()
session.query(Person).where(Person.works_for.name == "Acme Corp").all()
session.query(Person).where(
    (Person.name == "Odos") & (Person.works_for.name == "Acme Corp")
).all()
```

- **`==`** — triple pattern match
- **`!=`** — subject has some value for the predicate that differs from the RHS (not SQL `NOT EXISTS` for absent values)
- **`None`** in filters raises `QueryError`
- Nested filters require the related resource’s `rdf:type` in the graph

Full compiler rules: [SPECS.md](SPECS.md#sparql-compilation).

---

## Hydration (eager load)

```python
person = session.get(Person, iri, depth=0)   # scalars only
person = session.get(Person, iri, depth=1)   # one hop of relationships
person = session.get(Person, iri, depth=2)   # two hops
```

`depth` is the ORM analogue of eager-loading related objects after a primary fetch. Query results support the same `depth` on `.all()` and `.first()`.

---

## Export (optional)

ORM usage does **not** require export helpers. For Turtle, JSON-LD, and other formats:

```python
from sparqlmodel.serializers import export_model
print(export_model(person, format="turtle"))
```

**0.1.x:** interim serializers in SparqlModel. **0.4+:** delegates to TripleModel `parse` / `serialize`.

---

## When not to use SparqlModel

Use **TripleModel** directly when:

- You have no `SPARQLSession` — scripts, ETL, libraries, tests
- You only need `to_graph()` / `from_graph()` or file parse/serialize
- You hand-write SPARQL and do not need the Python query compiler

Use **SparqlModel** when:

- You build a backend, API, or long-lived app over a triple store
- You want `put` / `delete` cascade semantics and Pythonic `where()` filters

---

## Roadmap (ORM features)

Planned ORM capabilities (see [ROADMAP.md](ROADMAP.md)):

- **0.2** — `HttpStore`, identity map, session cache, richer query compiler, optional FastAPI
- **0.3** — delegate mapping to TripleModel; **public ORM API unchanged**
- **0.4+** — delegate file I/O; SparqlModel stays session + SPARQL focused

Built on [TripleModel](https://github.com/eddiethedean/triplemodel).
