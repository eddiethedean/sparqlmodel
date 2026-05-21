# Troubleshooting

Common issues when running SparqlModel in development or production.

## `execute` returns IRIs that `get` cannot load

**Symptom:** SPARQL SELECT finds a subject, but `session.get(Model, iri)` returns `None`.

**Cause:** With {class}`~sparqlmodel.stores.http.HttpStore`, `query` / `execute` read the **remote** endpoint; `get` and cascade read the **local mirror** updated only by this store instance’s writes.

**Mitigations:**

- `put` data through the same `HttpStore` session before `get`
- Use {class}`~sparqlmodel.stores.memory.MemoryStore` for single-process apps
- Treat each `HttpStore` as the primary writer for its endpoint until mirror sync ships (**0.9**)

See {doc}`PRODUCTION` — HttpStore mirror model.

## `query().all()` returns fewer rows than the remote SELECT

**Symptom:** `session.query(Person).where(...).all()` is empty or shorter than the same filter run in a SPARQL client against the endpoint.

**Cause:** On {class}`~sparqlmodel.stores.http.HttpStore` / {class}`~sparqlmodel.stores.async_http.AsyncHttpStore`, the query compiler runs a remote SELECT, then each binding is hydrated with `get()`. `get()` reads the **local mirror**, not the remote dataset. Rows whose subject IRI was never written through this store instance are dropped silently.

**Mitigations:** Same as for `execute` + `get` above — `put` through the session first, use {class}`~sparqlmodel.stores.memory.MemoryStore` for single-process apps, or use raw `execute()` and handle bindings without `query().all()` until mirror sync ships (**1.0**).

## Stale data after `put`

**Symptom:** Old predicate values still appear in queries.

**Cause:** `add()` appends triples and does not remove stale predicates. Only `put()` runs orphan cleanup.

**Fix:** Use `put()` for upserts. Prefer `add()` only when you know the subject has no conflicting triples.

## Exception in `with` block leaves session open

**Symptom:** After an error inside `with SPARQLSession(...)`, the session still accepts calls or still has a pending queue.

**Cause:** With `rollback_on_error=False`, pending `put(..., flush=False)` entries are kept on error and `close()` is not called (so the original exception is not masked by a pending-queue `RuntimeError`).

**Fix:** Use `rollback_on_error=True` (default), call `rollback_pending()` before handling the error, or discard the session and open a new one.

## Pending `put` not visible in `get`

**Symptom:** `put(model, flush=False)` then `get` returns old or missing data.

**Cause:** Pending queue is not flushed until `flush()` or context manager exit. The graph is unchanged until flush. The identity map is cleared for that subject when enqueueing a pending `put`, so `get` may return `None` or reload from the store rather than a stale instance.

**Fix:** Call `session.flush()` or exit the `with SPARQLSession()` block successfully. Do not call `close()` while pending writes remain — use `flush()` or `rollback_pending()` first.

## `QueryError` on `None` or wrong model class

**Symptom:** Filter raises {class}`~sparqlmodel.exceptions.QueryError`.

**Causes:**

- Comparing a field to `None` (unsupported in DSL)
- Filtering `Person.name` on a `query(Organization)` chain
- Combining OR and AND with `&`, e.g. `((A | B) & C)` or `(C & (A | B))` — use `.where((A | B), C)` instead
- Passing a bare string to `.in_()` — use a one-element tuple or list, e.g. `.in_(("value",))`

**Fix:** Use nullable-hop `!=` (compiler emits `OPTIONAL` since **0.8**), or `Person.relationship.is_(None)` / `is_not(None)` for explicit absence. For complex patterns, raw `execute()` remains available.

## `QueryError: Cannot combine OR and AND`

**Symptom:** Building or running a filter like `((Person.name == "A") | (Person.name == "B")) & (Person.name != "C")` or `(Person.name != "C") & ((Person.name == "A") | (Person.name == "B"))` raises {class}`~sparqlmodel.exceptions.QueryError`.

**Cause:** Python `&` between an `OrExpr` and a comparison (in either order) would produce an invalid expression tree for the compiler.

**Fix:** Pass separate `.where()` arguments::

    session.query(Person).where(
        (Person.name == "A") | (Person.name == "B"),
        Person.name != "C",
    ).all()

Or use `(A & B) | C` when OR should bind less tightly than AND.

## Remote and mirror diverge after editing `session.graph`

**Symptom:** `query` / `execute` return data that `get` cannot load, or triples added via `session.graph.add` never appear on the remote endpoint.

**Cause:** On {class}`~sparqlmodel.stores.http.HttpStore`, `session.graph` is the **local mirror** only. Direct graph mutation does not send SPARQL Update to the server.

**Fix:** Use `session.put` / `delete` for persistence, or {class}`~sparqlmodel.stores.memory.MemoryStore` when tests need low-level graph edits.

## `!=` behaves unexpectedly

**Symptom:** Resources with no value for a field still match or fail unexpectedly.

**Fix:** Default ``!=`` uses NOT EXISTS since 0.5.2. For pre-0.5.2 inequality (excludes unbound), use `.use_inequality_for_ne()`.

## URL strings become IRIs

**Symptom:** Filter `Person.homepage == "https://example.org"` compiles as IRI not literal.

**Cause:** Field type is `IRI` or value matches IRI heuristics.

**Fix:** Use a `str` field for literal URLs (0.2+ compiles URL-shaped strings on `str` fields as literals).

## `RuntimeError: Cannot use a closed SPARQLSession`

**Symptom:** CRUD or `query` / `execute` fails after the session was closed.

**Cause:** `SPARQLSession.close()` (or exiting a `with` block when `close_on_exit=True`) marks the session closed. Further use of that session object is invalid.

**Fix:** Open a new session for the same store::

    with SPARQLSession(store=shared_store) as session:
        session.put(model)

Do not keep a session reference past request teardown when using FastAPI `SessionDep`.

## Thread safety / corrupted session state

**Symptom:** Intermittent wrong cache or flush behavior under concurrency.

**Cause:** Sharing one `SPARQLSession` across threads or async tasks.

**Fix:** One session per request/task; share the store only.

## Build / import errors

| Error | Fix |
|-------|-----|
| `No module named 'httpx'` | `pip install "sparqlmodel[http]"` |
| `No module named 'fastapi'` | `pip install "sparqlmodel[fastapi]"` |
| `triplemodel` version conflict | `pip install "triplemodel>=0.10.0,<2" "pyoxigraph>=0.5,<0.6"` |

## Getting help

- [GitHub issues](https://github.com/eddiethedean/sqarqlmodel/issues)
- {doc}`SPECS` — normative behavior
- {doc}`changelog` — release notes
