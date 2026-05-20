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

## Stale data after `put`

**Symptom:** Old predicate values still appear in queries.

**Cause:** `add()` appends triples and does not remove stale predicates. Only `put()` runs orphan cleanup.

**Fix:** Use `put()` for upserts. Prefer `add()` only when you know the subject has no conflicting triples.

## Pending `put` not visible in `get`

**Symptom:** `put(model, flush=False)` then `get` returns old or missing data.

**Cause:** Pending queue is not flushed until `flush()` or context manager exit. The graph is unchanged until flush. The identity map is cleared for that subject when enqueueing a pending `put`, so `get` may return `None` or reload from the store rather than a stale instance.

**Fix:** Call `session.flush()` or exit the `with SPARQLSession()` block successfully. Do not call `close()` while pending writes remain — use `flush()` or `rollback_pending()` first.

## `QueryError` on `None` or wrong model class

**Symptom:** Filter raises {class}`~sparqlmodel.exceptions.QueryError`.

**Causes:**

- Comparing a field to `None` (unsupported in DSL)
- Filtering `Person.name` on a `query(Organization)` chain

**Fix:** Adjust filters; use raw `execute()` for OPTIONAL / absence patterns until **0.6**.

## `!=` behaves unexpectedly

**Symptom:** Resources with no value for a field still match or fail unexpectedly.

**Fix:** Try `.use_not_exists_for_ne()` or `.use_optional_for_comparisons()` on the query for NOT EXISTS semantics.

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
