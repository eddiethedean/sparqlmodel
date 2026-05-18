# Troubleshooting

Common issues when running SparqlModel in development or production.

## `execute` returns IRIs that `get` cannot load

**Symptom:** SPARQL SELECT finds a subject, but `session.get(Model, iri)` returns `None`.

**Cause:** With {class}`~sparqlmodel.stores.http.HttpStore`, `query` / `execute` read the **remote** endpoint; `get` and cascade read the **local mirror** updated only by this store instance’s writes.

**Mitigations:**

- `put` data through the same `HttpStore` session before `get`
- Use {class}`~sparqlmodel.stores.memory.MemoryStore` for single-process apps
- Treat each `HttpStore` as the primary writer for its endpoint until mirror sync ships (**0.7**)

See {doc}`PRODUCTION` — HttpStore mirror model.

## Stale data after `put`

**Symptom:** Old predicate values still appear in queries.

**Cause:** `add()` appends triples and does not remove stale predicates. Only `put()` runs orphan cleanup.

**Fix:** Use `put()` for upserts. Prefer `add()` only when you know the subject has no conflicting triples.

## Pending `put` not visible in `get`

**Symptom:** `put(model, flush=False)` then `get` returns old or missing data.

**Cause:** Pending queue is not flushed until `flush()` or context manager exit.

**Fix:** Call `session.flush()` or exit the `with SPARQLSession()` block successfully.

## `QueryError` on `None` or wrong model class

**Symptom:** Filter raises {class}`~sparqlmodel.exceptions.QueryError`.

**Causes:**

- Comparing a field to `None` (unsupported in DSL)
- Filtering `Person.name` on a `query(Organization)` chain

**Fix:** Adjust filters; use raw `execute()` for OPTIONAL / absence patterns until **0.5**.

## `!=` behaves unexpectedly

**Symptom:** Resources with no value for a field still match or fail unexpectedly.

**Fix:** Try `.use_not_exists_for_ne()` on the query for NOT EXISTS semantics.

## URL strings become IRIs

**Symptom:** Filter `Person.homepage == "https://example.org"` compiles as IRI not literal.

**Cause:** Field type is `IRI` or value matches IRI heuristics.

**Fix:** Use a `str` field for literal URLs (0.2+ compiles URL-shaped strings on `str` fields as literals).

## Thread safety / corrupted session state

**Symptom:** Intermittent wrong cache or flush behavior under concurrency.

**Cause:** Sharing one `SPARQLSession` across threads or async tasks.

**Fix:** One session per request/task; share the store only.

## Build / import errors

| Error | Fix |
|-------|-----|
| `No module named 'httpx'` | `pip install "sparqlmodel[http]"` |
| `No module named 'fastapi'` | `pip install "sparqlmodel[fastapi]"` |
| `triplemodel` version conflict | `pip install "triplemodel>=0.9.0,<2"` |

## Getting help

- [GitHub issues](https://github.com/eddiethedean/sqarqlmodel/issues)
- {doc}`SPECS` — normative behavior
- {doc}`changelog` — release notes
