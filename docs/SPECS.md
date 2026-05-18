# SparqlModel Technical Specification

## Overview

This document specifies the **SparqlModel ORM layer**: session API, query compilation, hydration, cascade policy, and stores.

**SparqlModel — the SQLModel of SPARQL.**

**Mapping** (literals, terms, `to_graph`, `sync_to_graph`, `from_graph`, `parse`, `serialize`) is specified and implemented by **[TripleModel](https://github.com/eddiethedean/triplemodel)** `>=0.9`, a **required dependency**. SparqlModel integrates TripleModel internally; application code uses `SPARQLSession` and `SPARQLModel` unless doing stateless file I/O.

| Concern | SparqlModel | TripleModel |
|---------|-------------|-------------|
| `SPARQLSession` CRUD | Yes | No |
| Query DSL + compiler | Yes | No |
| Cascade / orphans on `put` | Yes | No |
| Hydration `depth` | Yes | No |
| Stores | Yes | No |
| Model ↔ triples, terms, files | Integrates (retiring interim code) | Yes |

[ORM.md](ORM.md) · [ECOSYSTEM.md](ECOSYSTEM.md) · [ROADMAP.md](ROADMAP.md)

---

# SPARQLSession

ORM entry point. Binds a `Store` (default `MemoryStore`) and namespace registry.

```python
with SPARQLSession() as session:
    session.put(person)
    found = session.query(Person).where(Person.name == "Odos").first()
```

## Methods

| Method | Behavior |
|--------|----------|
| `add(model)` | Append triples; no removal of existing subject triples |
| `put(model, *, flush=True)` | Remove owned subjects (cascade), then write; queue when `flush=False` |
| `delete(model)` | Remove owned triples for root + embedded composition |
| `get(model_cls, iri, *, depth=0)` | Load one resource; optional relationship depth 0–2 |
| `query(model_cls)` | Return `Query` builder |
| `execute(sparql)` | Raw SELECT; auto-prefixes when configured |
| `flush()` / `rollback_pending()` | Apply or discard pending `put` queue |
| `close()` | Call `store.close()` when available |

## Context manager

On clean exit: `flush()` if the pending queue is non-empty. On exception: `rollback_pending()` when `rollback_on_error=True` (default). Always calls `close()` when `close_on_exit=True` (default). Does not undo already-flushed writes.

## Properties

- `store` — backing store
- `graph` — rdflib `Graph` (`MemoryStore` graph, or `HttpStore` local mirror — not the remote dataset)
- `namespaces` — `NamespaceRegistry` for compiler and serialization

---

# Query builder

```python
with SPARQLSession() as session:
    session.query(Person).where(Person.name == "Odos").all()
    session.query(Person).where(Person.works_for.name == "Acme").limit(10).first()
```

- `.where(*expr)` — `CompareExpr` or `AndExpr`
- `.limit(n)` — non-negative integer
- `.all(*, depth=0)` / `.first(*, depth=0)` — execute and hydrate

---

# SPARQL compilation

`Person.name == "Odos"` → SPARQL triple patterns bound to `?person`.

| Operator | Semantics |
|----------|-----------|
| `==` | Pattern match |
| `!=` | Inequality filter (or `Query.use_not_exists_for_ne()` for `NOT EXISTS`) |
| `&` | Conjoin patterns (`AndExpr` or multiple `.where`) |
| `\|` | Disjunction via `FILTER` + `EXISTS` branches (`OrExpr`) |
| `<`, `>`, `<=`, `>=` | Ordering on bound literal variables |
| `.in_(tuple)` | `FILTER(?var IN (...))` |
| `None` | Raises `QueryError` |

Nested attribute paths (`Person.works_for.located_in.name`) support arbitrary hop length via join variables and related-type patterns.

Implementation: `compiler.py` — **SparqlModel only**; TripleModel does not compile Python filters.

---

# Hydration

```python
with SPARQLSession() as session:
    session.get(Person, iri, depth=2)
    session.query(Person).where(...).all(depth=1)
```

| `depth` | Loads |
|---------|--------|
| `0` | Scalars on root |
| `1` | One hop of `Relationship` fields |
| `2` | Two hops |

`validate_depth` rejects values outside 0–2.

**Integration note:** scalar and object loading will call TripleModel `from_graph` (or batch helpers) as interim `graph_to_model` is retired.

---

# SPARQLModel

ORM entity base class. SQLModel-style declaration:

```python
class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
```

- Metaclass enables `Person.name == "x"` in queries (`FieldRef`)
- `ensure_id()` assigns `urn:uuid:…` when `id` is unset
- JSON-LD helpers: `model_dump_jsonld` / `model_validate_jsonld` (interim; prefer TripleModel JSON-LD long term)

**Adapter target (internal):** map to `TripleModel` + `RdfConfig` / `rdf_field` without changing public field syntax.

---

# Relationships

```python
works_for: Organization | None = Relationship("schema:worksFor", model=Organization)
```

| Value type | Semantics |
|------------|-----------|
| Embedded `SPARQLModel` | Composition — cascade on `put`/`delete` |
| `IRI` | Reference — no cascade delete of target |

---

# Persistence policy

SparqlModel-specific; orchestrates **which subjects** TripleModel (or interim `graph.py`) syncs.

## `put`

1. Compute `cascade_subjects_for_removal` (root, nested embeds, orphans on relationship change)
2. Remove `owned_triples_for_subjects` from store graph
3. Add current model graph (`model_to_graph` → future: TripleModel export + cascade)

## `delete`

Remove owned triples for cascade subject set (no re-add).

## Ownership rules

- Only **declared** predicates + `rdf:type` are owned
- Extension triples on a subject are not removed by `put`/`delete`
- Orphan keys use expanded IRIs and stable `_:bnode` keys

---

# Mapping integration (TripleModel)

**Dependency:** `triplemodel>=0.9.0,<2` in `pyproject.toml`.

**Today (0.1.x):** `graph.py`, `fields.py`, and `serializers.py` contain interim logic. **Do not extend** interim parsers or datatype tables — fix upstream in TripleModel, then wire SparqlModel.

**Target wiring:**

| SparqlModel surface | TripleModel API |
|---------------------|-----------------|
| `put` graph write | `sync_to_graph(model, graph, mode=...)` + cascade |
| `get` / query load | `from_graph` / `graph_to_model` |
| `export_model` | `to_graph().serialize(...)` or `serialize()` |
| Predicate metadata | `rdf_field`, `Predicate`, `RdfConfig` |

Cascade orchestration **remains in SparqlModel** after wiring.

---

# HttpStore

SPARQL 1.1 over HTTP (`httpx`) with a **local mirror** ([`stores/http.py`](../src/sparqlmodel/stores/http.py)).

| Method | Target |
|--------|--------|
| `update_graph` | Remote `INSERT DATA` / `DELETE DATA`, then mirror delta on success |
| `query` / `execute` (via session) | Remote SELECT |
| `graph`, `get`, cascade/orphan | Mirror only |

External writers or SELECT-only visibility without a matching mirror update can make `get` return `None` while `execute` returns bindings. Single-writer per endpoint is assumed. If both `auth` and `bearer_token` are set, Basic auth wins.

---

# Known limitations (0.2.x)

| Area | Behavior |
|------|----------|
| `HttpStore` mirror | `get` / cascade use mirror; `query` uses remote — see above |
| Multi-valued predicates | First object per predicate on load; `add` can duplicate |
| `put(..., flush=False)` | Pending models not visible in `get` until flush |
| `flush()` | Not transactional across multiple pending models; partial failure re-queues remainder |
| Interim vs TripleModel paths | Some round-trips differ until integration completes |
| Nested query filters | Related resource must have expected `rdf:type` |
| JSON-LD | `model_dump_jsonld` vs `export_model(..., "json-ld")` differ |
| Export without `id` | `ensure_id()` may assign `urn:uuid:…` |
| Sessions | Not thread-safe; one session per task |

---

# Optional: export and files

ORM workflows do not require `sparqlmodel.serializers`.

Long term: all formats via TripleModel; SparqlModel may expose session-scoped helpers only.

---

# FastAPI (optional extra)

Install `sparqlmodel[fastapi]`. [`fastapi/deps.py`](../src/sparqlmodel/fastapi/deps.py) provides `init_app`, `get_session`, `SessionDep`, `http_store_lifespan`. [`fastapi/__init__.py`](../src/sparqlmodel/fastapi/__init__.py) provides `turtle_response`, `jsonld_response`, `negotiated_response`.

---

# Feature ownership

| Feature | Owner |
|---------|--------|
| SHACL shapes / validation engine | TripleModel `[shacl]` |
| SHACL on `session.put` | SparqlModel hook calling TripleModel |
| Named graphs / Dataset | TripleModel; SparqlModel consumes |
| SPARQL federation in apps | SparqlModel |
| Alternate store backends | SparqlModel `stores/` |
| OWL reasoner | Out of scope |

---

# Maintainer boundaries

For **end users**, use [ORM.md](ORM.md). This table is for **contributors**.

| Symptom | Fix in |
|---------|--------|
| Wrong XSD / literal on export | TripleModel |
| Subject IRI collision | TripleModel |
| Stale predicate after `put` | TripleModel sync + SparqlModel cascade |
| Orphan after relationship change | SparqlModel `graph.py` |
| `!=` / nested filter wrong | SparqlModel `compiler.py` |
| New RDF format | TripleModel |
| Fuseki / HTTP store | SparqlModel `stores/` |

**Anti-patterns:** new mapping code only in `graph.py`; session/compiler in TripleModel; `triplemodel` importing `sparqlmodel`.

---

# Package layout

```text
sparqlmodel/
  session.py       # ORM unit of work
  query.py         # query builder
  compiler.py      # ORM-only
  hydration.py     # depth; → TripleModel load
  model.py         # SPARQLModel; → TripleModel adapter
  fields.py        # Field/Relationship; → Predicate metadata
  graph.py         # cascade; → sync_to_graph (retiring local convert)
  serializers.py   # → TripleModel parse/serialize (retiring)
  stores/
  _triple.py       # adapter (planned)
```

---

# Dependencies

```
pydantic>=2.5,<3
rdflib>=7.0,<8
triplemodel>=0.9.0,<2
typing-extensions>=4.8
```

Optional: `httpx`, `fastapi`

---

# Related projects

| Project | Role |
|---------|------|
| **TripleModel** | Required mapping engine |
| **RDFLib** | Graphs and SPARQL execution |
| **semantic-sqlmodel** | Optional future backend |
