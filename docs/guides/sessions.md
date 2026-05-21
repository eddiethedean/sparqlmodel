# Sessions and stores

`SPARQLSession` is the unit of work: all reads and writes go through a session bound to a store ({class}`~sparqlmodel.stores.memory.MemoryStore` or {class}`~sparqlmodel.stores.http.HttpStore`).

## Context manager (recommended)

```python
from sparqlmodel import SPARQLSession

with SPARQLSession() as session:
    session.put(model)
    found = session.get(Person, model.id)
# flush pending writes on success; rollback pending queue on error; close store
```

| Exit path | Behavior |
|-----------|----------|
| Normal | `flush()` pending `put(..., flush=False)` queue, then `close()` store |
| Exception | `rollback_pending()` (discard queue only; flushed data remains), then `close()` |
| `rollback_on_error=False` | Keep pending queue after errors |
| `close_on_exit=False` | Leave store open (shared `HttpStore` on FastAPI `app.state`) |

## Session API at a glance

| Method | Use when |
|--------|----------|
| `add(model)` | Append triples; never delete existing subject data |
| `put(model)` | Upsert with cascade and orphan cleanup (default for apps) |
| `delete(model)` | Remove owned triples for root + composition tree |
| `get(Model, iri, depth=0)` | Load one resource; `depth` 0–2 eager-loads relationships |
| `query(Model).where(...)` | Fluent SELECT compiled to SPARQL |
| `execute(sparql)` | Raw SPARQL SELECT |
| `flush()` / `rollback_pending()` | Control `put(..., flush=False)` queue |
| `expire(Model, iri)` | Evict identity map / hydration cache |

## Pending flush queue

Defer writes until commit:

```python
with SPARQLSession() as session:
    session.put(a, flush=False)
    session.put(b, flush=False)
    session.flush()  # or rely on context manager exit
```

```{warning}
Pending models are not written to the store until `flush()` (or successful context-manager exit). `get` does not return the pending instance; identity for that subject is evicted when the pending `put` is queued. A failed `flush()` re-queues remaining models (0.2+). Calling `close()` with a non-empty pending queue raises `RuntimeError`.
```

## Identity map

After `put`, `get(Model, iri, depth=0)` returns the **same Python instance** when relationships are not materialized on the object. Use `expire(Model, iri)` after external graph changes.

Different `depth` values may cache separate hydrated views.

## Choosing a store

| Store | When to use |
|-------|-------------|
| {class}`~sparqlmodel.stores.memory.MemoryStore` | Tests, notebooks, single-process tools (default) |
| {class}`~sparqlmodel.stores.http.HttpStore` | Fuseki, Jena, or any SPARQL 1.1 endpoint (`sparqlmodel[http]`) |

Load an existing RDF file into a session with {meth}`~sparqlmodel.session.SPARQLSession.from_rdf_file` (see {doc}`realworld` for full examples).

```python
from sparqlmodel import HttpStore, SPARQLSession

with SPARQLSession(store=HttpStore("http://localhost:3030/ds/sparql")) as session:
    session.put(model)
```

```{seealso}
{doc}`../PRODUCTION` — HttpStore mirror semantics (query vs `get`).
{doc}`../troubleshooting` — “execute finds IRI but get fails”.
```

## Composition vs reference

| Relationship value | `put` / `delete` |
|--------------------|------------------|
| Nested `SPARQLModel` | Composition — cascade + orphan cleanup |
| `Relationship(..., cascade=False)` | Reference — link only |
| `IRI` | Reference — update link; do not delete target resource |

## Threading

Sessions are **not thread-safe**. Use one session per request, task, or thread. Share the **store** (e.g. on `app.state`), not the session.

## Next

- {doc}`queries` — filter and compile queries
- {doc}`fastapi` — wire sessions into ASGI apps
- {doc}`../ORM` — cascade and hydration in depth
