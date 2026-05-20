# SparqlModel ORM guide

**SparqlModel — the SQLModel of SPARQL:** typed models, a persistent session, and Python queries that compile to SPARQL.

This guide is for **application developers**. SparqlModel is the ORM; **[TripleModel](https://github.com/eddiethedean/triplemodel)** (`triplemodel>=0.10`, installed automatically) is the mapping engine underneath. In-process graphs use **pyoxigraph** via `triplemodel.Store`.

Related: {doc}`guides/index` · {doc}`SPECS` · {doc}`ECOSYSTEM` · {doc}`ROADMAP` · {doc}`troubleshooting`

---

## Two packages, one stack

| | SparqlModel | TripleModel |
|---|-------------|-------------|
| **Role** | ORM — run apps on graphs | Mapping — correct triples from Pydantic |
| **Metaphor** | SQLModel / SQLAlchemy ORM | SQLAlchemy Core / serde |
| **Entry point** | `with SPARQLSession() as session:` | `model.to_graph()` / `TripleModel.parse()` |
| **Dependency** | Requires `triplemodel>=0.10` and `pyoxigraph` | Standalone library |

```text
Your app
  → SPARQLModel(TripleModel) — one class (Option A; 0.4+)
  → SPARQLSession.put / .query / .get
  → sync_to_graph / from_graph + graph.py (cascade policy)
  → triplemodel.Store in a Store
```

**0.4.0+:** session I/O uses `sparqlmodel.rdf_bridge` on unified `SPARQLModel(TripleModel)` instances.

**Rule of thumb:** if your code never constructs a `SPARQLSession`, you probably want TripleModel only.

---

## Pydantic integration

`SPARQLModel` is a **Pydantic v2** model that **subclasses `TripleModel`** (Option A, target **0.4**) with a merged metaclass for the query DSL. That is the same positioning as SQLModel relative to SQLAlchemy: one class for mapping and ORM ergonomics.

| Layer | Validation |
|-------|------------|
| **Construct** | `Person(...)` and `Person.model_validate({...})` run Pydantic field validators |
| **Persist** | `session.put` → cascade in `graph.py` → `sync_to_graph` on the instance (**0.4+**; 0.3 uses interim `_triple.py`) |
| **Load** | `from_graph` on `SPARQLModel` + depth hydration → `model_validate` |
| **Config** | `extra="forbid"` rejects unknown fields on models |

`Field("schema:name", ...)` and `Relationship(...)` wrap `pydantic.Field` and forward keyword arguments (`min_length`, `ge`, `description`, defaults, and so on) for scalar and relationship annotations.

**FastAPI:** use the same `SPARQLModel` classes as request/response models; OpenAPI schema comes from Pydantic. See {doc}`guides/fastapi`.

**Errors:** Pydantic `ValidationError` on load is wrapped as `HydrationError` for a single ORM-facing exception; configuration problems (for example hydration cycles) stay as `ConfigurationError`.

Task-oriented examples: {doc}`guides/models`. Normative detail: {doc}`SPECS` (validation architecture).

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
    SPARQLSession,   # sync — start here
    AsyncSPARQLSession,  # asyncio / FastAPI async routes (0.6+)
    SPARQLModel,
    Field,
    Relationship,
    IRI,
    HttpStore,       # optional: sparqlmodel[http]
)
```

- **`SPARQLSession`** — unit of work over a store
- **`SPARQLModel`** — entity class (SQLModel-style); subclasses `TripleModel` (**0.4+**)
- **`Field` / `Relationship`** — ORM sugar over `rdf_field` / `Predicate`

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

## Async session (0.6+)

For FastAPI and other **asyncio** apps, use **`AsyncSPARQLSession`** with **`AsyncMemoryStore`** or **`AsyncHttpStore`** (`sparqlmodel[http]` — same `httpx` extra as sync). The sync session API is unchanged.

```python
from sparqlmodel import AsyncSPARQLSession, IRI
from sparqlmodel.stores.async_http import AsyncHttpStore

async with AsyncSPARQLSession(store=AsyncHttpStore("https://example.org/sparql")) as session:
    await session.put(person)
    results = await session.query(Person).where(Person.name == "Odos").all()
    one = await session.get(Person, person.id, depth=1)
```

| Topic | Guidance |
|-------|----------|
| **When to use async** | Remote SPARQL over the network in async routes; avoid blocking `httpx.Client` on the event loop |
| **When sync is fine** | Scripts, tests, `MemoryStore`, or sync FastAPI with `SessionDep` |
| **Concurrency** | One `AsyncSPARQLSession` per asyncio task — do not share across `asyncio.gather` workers |
| **FastAPI** | `AsyncSessionDep`, `init_async_app`, `async_http_store_lifespan` — see {doc}`guides/fastapi` |
| **Compiler / hydration** | Same rules as sync; only store I/O and session entry points are `async` |

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
- **`!=`** — default `NOT EXISTS` (0.5.2+); optional `.use_inequality_for_ne()` for legacy inequality
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

Loading scalars and relationships uses `hydration.py` over TripleModel `from_graph` on `SPARQLModel` instances (**0.4+**; 0.3 via interim `_triple.py`).

---

## HttpStore and the local mirror

`HttpStore` (`sparqlmodel[http]`) sends updates to a SPARQL 1.1 endpoint and keeps a **local `triplemodel.Store` mirror** for `session.graph`, `get`, cascade, and orphan logic.

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

**From SparqlModel today (serializers interim until 0.6):**

```python
from sparqlmodel.serializers import export_model
export_model(person, format="turtle")
```

Roadmap: SparqlModel export becomes a thin wrapper over TripleModel `serialize`; new formats are added in TripleModel only.

---

## Current integration status

| Capability | Owner today | Direction |
|------------|-------------|-----------|
| Literals, XSD, subject IRIs | TripleModel (package dep) | Via `SPARQLModel(TripleModel)` (**0.4**) |
| `session.put` graph writes | SparqlModel cascade + TripleModel `sync_to_graph` | Direct on instances (**0.4**) |
| `session.get` / query hydrate | SparqlModel depth + `from_graph` | Unified subclass (**0.4**) |
| Interim `_triple.py` adapter | Shipped 0.3 | **Remove 0.4** |
| Turtle / JSON-LD export | Interim `serializers.py` | TripleModel `serialize` (**0.6**) |
| Query compiler | SparqlModel only | Stays in SparqlModel |

See [ROADMAP.md](ROADMAP.md) for milestones.

---

## Production readiness

**Today (0.2.0):** Suitable for prototypes, tests, single-process apps (`MemoryStore`), and early FastAPI services. Remote `HttpStore` requires understanding the [mirror model](SPECS.md#httpstore) (query vs `get`).

**Target (1.2):** Production-grade SPARQL ORM with SQLModel-parity sessions and queries. Track progress:

- [Production checklist](SPECS.md#production-orm-checklist-12-ga-gate) — normative P0 / P1 / P2 gates
- [Roadmap](ROADMAP.md) — versions 0.4–1.2
- [SQLModel parity checklist](ROADMAP.md#sqlmodel-parity-checklist) — quick mapping from SQL habits
- [Production guide](PRODUCTION.md) — deployment and HttpStore operations

**Not yet available (planned):** `offset` / `order_by` / `count` on queries (**0.8**), `merge` / `refresh` / `expunge` (**0.9**), production HttpStore sync (**1.0**), multi-valued and language-tagged fields (**1.1**). **Async session and stores** shipped in **0.6.0**.

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
- [PRODUCTION.md](PRODUCTION.md) — deployment and HttpStore operations
- [PLAN.md](PLAN.md) — product vision and parity tiers
