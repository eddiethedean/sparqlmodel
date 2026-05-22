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
| `expire(Model, iri)` | Evict cache by IRI (also drops matching pending `put`) |
| `expunge(model)` | Detach one instance from identity / hydration cache (store unchanged) |
| `expunge_all()` | Clear all identity and hydration entries (pending queue kept) |
| `refresh(model, *, depth=0)` | Reload from the store into the cached instance when present |
| `merge(model)` | Attach or reconcile with the session identity map (no store write) |

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

After `put`, `get(Model, iri, depth=0)` returns the **same Python instance** when relationships are not materialized on the object. Different `depth` values may cache separate hydrated views.

### Cache control (0.9+)

| Method | When to use |
|--------|-------------|
| `expire(Model, iri)` | External graph change for one IRI; also removes a queued pending `put` for that subject |
| `expunge(model)` | Detach a specific instance (e.g. before long-lived work on a copy) |
| `expunge_all()` | Reset session caches between test cases; does **not** flush or clear the pending queue |
| `refresh(model, depth=...)` | Reload attributes from the store (updates the identity-map object in place when cached) |
| `merge(model)` | Re-attach a detached instance or copy field state onto the canonical session instance |

```text
transient → (add|put) → persistent (in store + identity map)
persistent → expunge → detached (may merge again)
persistent → refresh → persistent (reloaded from store)
```

`refresh` and `merge` do not write to the store — use `put` to persist changes. `merge` copies only fields you set on the detached instance (unset relationships are left unchanged on the cached object). `refresh(..., depth=0)` clears relationship attributes on the cached instance; a later `get(..., depth≥1)` reloads nested data from the store (0.9.1+). On {class}`~sparqlmodel.stores.http.HttpStore` / {class}`~sparqlmodel.stores.async_http.AsyncHttpStore`, `refresh` auto-pulls the subject into the mirror when missing, same as `get` (0.9.2+). Use `expunge` then `get` at the needed depth if you want a clean reload boundary.

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
