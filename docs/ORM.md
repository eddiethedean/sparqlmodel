# SparqlModel ORM guide

**SparqlModel — the SQLModel of SPARQL:** typed models, a persistent session, and Python queries that compile to SPARQL.

This guide is for **application developers**. SparqlModel is the ORM; **[TripleModel](https://github.com/eddiethedean/triplemodel)** (`triplemodel>=0.9`, installed automatically) is the mapping engine underneath.

Related: [SPECS.md](SPECS.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md)

---

## Two packages, one stack

| | SparqlModel | TripleModel |
|---|-------------|-------------|
| **Role** | ORM — run apps on graphs | Mapping — correct triples from Pydantic |
| **Metaphor** | SQLModel / SQLAlchemy ORM | SQLAlchemy Core / serde |
| **Entry point** | `with SPARQLSession() as session:` | `model.to_graph()` / `TripleModel.parse()` |
| **Dependency** | Requires `triplemodel>=0.9` | Standalone library |

```text
Your app
  → SPARQLSession.put / .query / .get
  → (today: interim graph.py; tomorrow: TripleModel sync/load APIs)
  → rdflib Graph in a Store
```

**Rule of thumb:** if your code never constructs a `SPARQLSession`, you probably want TripleModel only.

---

## Choose your package

| I need… | Use |
|---------|-----|
| CRUD, queries, cascade in a backend or API | **SparqlModel** |
| Python filters → SPARQL (`Person.name == "x"`) | **SparqlModel** |
| HTTP SPARQL store (`HttpStore`), identity map, flush queue | **SparqlModel** |
| Load a Turtle file into models without a session | **TripleModel** |
| ETL, tests, libraries, one-off `to_graph()` | **TripleModel** |

---

## What you import from SparqlModel

```python
from sparqlmodel import (
    SPARQLSession,   # start here
    SPARQLModel,
    Field,
    Relationship,
    IRI,
    HttpStore,       # optional: sparqlmodel[http]
)
```

- **`SPARQLSession`** — unit of work over a store
- **`SPARQLModel`** — entity class (SQLModel-style); not a standalone mapper
- **`Field` / `Relationship`** — ORM field API (backed by TripleModel predicate metadata as integration completes)

You generally **do not** import `triplemodel` in application code unless you are mixing stateless file I/O with session usage — e.g. bulk `TripleModel.parse()` then `session.put()` per row.

---

## ORM lifecycle

| Method | Semantics |
|--------|-----------|
| **`add(model)`** | Insert triples only; does not remove existing triples for the subject. |
| **`put(model)`** | Upsert: remove owned triples (root, embedded tree, orphans), then write current state. Uses mapping layer + SparqlModel cascade policy. |
| **`delete(model)`** | Remove owned triples for root and embedded composition targets. |
| **`get(Model, iri, depth=0)`** | Load one entity; `depth` eager-loads relationships (0–2). |
| **`query(Model).where(...)`** | Find entities; filters compile to SPARQL. |
| **`execute(sparql)`** | Raw SPARQL SELECT. |
| **`flush()`** / **`rollback_pending()`** | Apply or discard queued `put(..., flush=False)` writes. |
| **`close()`** | Close the backing store when it implements `close()` (e.g. `HttpStore`). |
| **`expire(Model, iri)`** | Evict cached instances for an IRI. |

```python
with SPARQLSession() as session:
    session.put(person)
    session.put(other, flush=False)
    # pending queue flushed on clean exit

with SPARQLSession(store=HttpStore("https://example.org/sparql")) as remote:
    hits = remote.query(Person).where(Person.name == "Alice").all()
```

On exception, the context manager calls `rollback_pending()` (discard the queue only — already-flushed writes stay). Set `rollback_on_error=False` to keep pending across errors, or `close_on_exit=False` when the store is managed elsewhere.

---

## Composition and cascade

SparqlModel-only **persistence policy** (TripleModel does not define multi-resource cascade):

| Value on a relationship | On `put` / `delete` |
|---------------------------|---------------------|
| Nested **`SPARQLModel`** | **Composition** — cascade owned triples; orphan cleanup when links change |
| Nested with **`Relationship(..., cascade=False)`** | **Reference** — link only; nested triples not written or removed by root `put` |
| **`IRI` only** | **Reference** — update link; do **not** delete the target resource |

TripleModel’s `sync_to_graph` syncs **one resource’s** owned triples. SparqlModel’s `put` decides **which subjects** to remove across the composition tree before calling into the mapper.

---

## Query DSL

```python
with SPARQLSession() as session:
    session.query(Person).where(Person.name == "Odos").all()
    session.query(Person).where(Person.works_for.name == "Acme Corp").all()
```

- **`==`** — triple pattern match
- **`!=`** — inequality filter; optional `.use_not_exists_for_ne()` for `NOT EXISTS` semantics
- **`&`** / **`|`** — `AndExpr` / `OrExpr`
- **`<`, `>`, `<=`, `>=`**, **`.in_(tuple)`** — ordering and membership filters
- **`None`** → `QueryError`
- Multi-hop paths (`Person.works_for.located_in.name`) require related `rdf:type` in the graph

Compiler detail: [SPECS.md](SPECS.md#sparql-compilation).

---

## Hydration

```python
with SPARQLSession() as session:
    session.get(Person, iri, depth=0)  # scalars
    session.get(Person, iri, depth=1)  # one relationship hop
```

ORM eager-load. Query `.all(depth=1)` and `.first(depth=1)` accept the same parameter.

Loading scalars and objects ultimately uses TripleModel `from_graph` (or equivalent) as integration replaces interim loaders in `hydration.py` / `graph.py`.

---

## HttpStore and the local mirror

`HttpStore` (`sparqlmodel[http]`) sends updates to a SPARQL 1.1 endpoint and keeps a **local rdflib mirror** for `session.graph`, `get`, cascade, and orphan logic.

| Operation | Reads / writes |
|-----------|----------------|
| `put` / `delete` / `update_graph` | Remote + mirror |
| `query` / `execute` | Remote only |
| `get` | Mirror only |

If another process changes the remote dataset, `execute` may return IRIs that `get` cannot load until this store instance has applied the same triples to its mirror. Use `MemoryStore` for single-process apps; treat each `HttpStore` as the single writer for its endpoint.

---

## Export and file I/O

**Preferred for files without a session:**

```python
from triplemodel import TripleModel  # example — use your TripleModel classes
# persons = Person.parse("data.ttl")
```

**From SparqlModel today (interim):**

```python
from sparqlmodel.serializers import export_model
export_model(person, format="turtle")
```

Roadmap: SparqlModel export becomes a thin wrapper over TripleModel `serialize`; new formats are added in TripleModel only.

---

## Current integration status

| Capability | Owner today | Direction |
|------------|-------------|-----------|
| Literals, XSD, subject IRIs | TripleModel (package dep) | SparqlModel stops reimplementing in `graph.py` |
| `session.put` graph writes | SparqlModel + interim `graph.py` | `sync_to_graph` + cascade orchestration |
| `session.get` / query hydrate | SparqlModel + interim loaders | `from_graph` + depth walker |
| Turtle / JSON-LD export | Interim `serializers.py` | TripleModel `serialize` |
| Query compiler | SparqlModel only | Stays in SparqlModel |

See [ROADMAP.md](ROADMAP.md) for milestones.

---

## When not to use SparqlModel

Use **TripleModel** alone when:

- There is no long-lived session
- You only need correct triples or file round-trip
- You are building a library that should not depend on ORM semantics

Use **SparqlModel** when:

- You are building an application or API over a triple store
- You need `put` / `delete` cascade and Pythonic `where()` filters

---

## Further reading

- [TripleModel docs](https://triplemodel.readthedocs.io/) — mapping, terms, files
- [ECOSYSTEM.md](ECOSYSTEM.md) — maintainer boundaries and module retirement
- [ROADMAP.md](ROADMAP.md) — ORM features and wiring schedule
