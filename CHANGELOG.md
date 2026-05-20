# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-05-18

### Added

- **Pyoxigraph engine** — `triplemodel>=0.10.0,<2`, `pyoxigraph>=0.5,<0.6`; session graphs are `triplemodel.Store`
- **`sparqlmodel.rdf_n3`** — N3 formatting for compiler filters and HTTP UPDATE bodies
- **`sparqlmodel.stores.sparql_json`** — SPARQL Results JSON parser (no rdflib)

### Changed

- **Breaking:** `Store.graph` and `SPARQLSession.graph` return `triplemodel.Store`, not `rdflib.Graph`
- **Breaking:** `Store.update_graph` accepts `Store` deltas; custom store implementations must migrate
- **`MemoryStore` / `HttpStore`** — pyoxigraph-backed mirror; SELECT bindings use term `.value` strings
- **`serializers`** — `export_graph` / `import_graph` delegate to TripleModel `dump_graph` / `load_graph`
- **`compiler`** — literal/IRI formatting via `rdf_n3` (not RDFLib `.n3()`)
- **FastAPI** — Turtle/JSON-LD responses via `export_graph`
- **ROADMAP** — async ORM milestone renumbered to **0.6**; file I/O delegation **0.7**

### Removed

- **rdflib** as a required dependency

### Fixed

- **Hydration DAGs** — `load_from_graph` no longer treats shared embedded resources as cycles
- **Session identity** — canonical identity per IRI with per-depth hydration cache
- **Query compiler** — absolute `urn:` / `http(s)://` strings on IRI-typed fields compile as IRIs; escaped newlines in string literals
- **Session** — pending `put` invalidates cascade caches; dedupes pending queue; `__exit__` exception handling
- `Query.use_optional_for_comparisons()`, `OrExpr` chaining, `FieldRef.in_` sequences, `Query.first()` limit behavior

## [0.4.0] - 2026-05-18

### Added

- **Unified model (Option A)** — `SPARQLModel` subclasses `TripleModel`; nested `Rdf` config injected from `rdf_type` / `__prefixes__`; `id` uses `IriId` for explicit subject IRIs
- **`sparqlmodel.rdf_bridge`** — `model_to_graph`, `load_from_graph` / `sparql_from_graph`, cycle detection, graph contract helpers (replaces interim adapter)
- **Dual field metadata** — `Field` / `Relationship` set both `sparql` (ORM/compiler) and `rdf_predicate` (TripleModel) in `json_schema_extra`
- **`Relationship(..., cascade=False)`** — uses TripleModel `ref_field` for URI FK without nested embed on put

### Changed

- **Session / hydration / serializers / FastAPI** — import graph I/O from `rdf_bridge` instead of `_triple`
- **`get_prefixes()`** — merges built-in RDF prefixes (`rdf`, `rdfs`, `xsd`, `schema`) with model `__prefixes__`
- **Removed `sparqlmodel._triple`** — no `exec`-generated shadow `TripleModel` classes

### Fixed

- Subclasses that redeclare `id: IRI` without `IriId` get `IriId` metadata applied at class creation so `from_graph` populates subject IRIs

### Migration (0.3 → 0.4)

No public API changes for `SPARQLModel`, `Field`, `Relationship`, or `SPARQLSession.put` / `get` / `query`. Internal adapter module removed; tests and apps should import `sparqlmodel.rdf_bridge` only if they used private `_triple` helpers.

## [0.3.0] - 2026-05-18

### Added

- **Session I/O via TripleModel** — `put` / `add` / `get` / hydration use `sparqlmodel._triple` (`sync_to_graph`, `TripleModel.from_graph`) as the single mapping path
- **`sparql_from_graph`** — load `SPARQLModel` instances from an rdflib graph with relationship depth (0–2)
- **`resolve_related_model`** — resolves `typing.ForwardRef` on relationship annotations (Python 3.10–3.13)

### Changed

- **`graph.py`** — cascade/orphan orchestration only; interim `model_to_triples`, `load_scalars`, and `graph_to_model` removed
- **`model_to_graph`** (internal) — implemented via TripleModel `sync_to_graph`; normalizes `xsd:string` literals for SPARQL query compatibility
- **`HydrationError`** — raised only for validation / value errors during `from_graph` hydration (`ConfigurationError` for cycles propagates unchanged)
- **Contract tests** — `assert_put_graph_contract` and `test_session_put_matches_contract` assert adapter graphs only (no interim branch)

### Fixed

- **`SPARQLSession`** — raise `RuntimeError` on use after `close()` (CRUD, `query`, `execute`, `flush`, `expire`, `rollback_pending`); raise when `close()` is called with a non-empty pending `put` queue
- **`HttpStore`** — raise `RuntimeError` on `query` / `update_graph` after `close()`
- **`execute()`** — inject session `PREFIX` declarations only when the query prologue has no `PREFIX` line (not when the word appears in a string literal)
- **`negotiated_response`** — respect `Accept` quality values (`;q=`) when choosing Turtle vs JSON-LD
- **`SPARQLModel`** — reject duplicate RDF predicates on the same class at definition time (`ConfigurationError`)
- **`put` / `model_to_graph`** — detect cyclic embedded models on write (same as `to_triplemodel`)
- **Orphan cleanup** — do not delete embedded resources still referenced from another subject in the graph (shared composition)
- **`put(..., flush=False)`** — evict identity-map entry for that subject so `get` does not return a stale pre-pending instance
- **`expire()`** — drop matching entries from the pending `put` queue
- **Query compiler** — reuse join variables for the same relationship path within AND / single EXISTS blocks (fixes false positives with multiple values per predicate)
- **JSON-LD** — unwrap scalar `IRI` fields from `{"@id": ...}` on import; omit non-cascade embedded nodes from `model_to_jsonld`

### Documentation

- ROADMAP / SPECS / ORM / ECOSYSTEM — mark **0.3.0** session I/O milestone shipped; multi-valued `list[...]` fields remain **0.8**
- Sessions / troubleshooting — pending `put` vs identity map and `close()` with pending queue
- Queries guide — Python `&` / `|` precedence matches the compiler
- README / SPECS — duplicate predicates, write-path cycles, shared composition, compiler join reuse

## [0.2.0] - 2026-05-18

### Added

- **`HttpStore`** — SPARQL 1.1 over HTTP (`httpx`), local graph mirror, optional `sparqlmodel[http]` extra
- **Session identity map** and hydration cache; `flush()`, `rollback_pending()`, `expire(model_cls, iri)`, `put(..., flush=False)`, `autoflush`
- **Query compiler:** `OR`, ordering (`<`, `>`, `<=`, `>=`), `IN` (`FieldRef.in_`), multi-hop paths, optional `Query.use_not_exists_for_ne()` for `!=`
- **`sparqlmodel/_triple.py`** — dynamic `TripleModel` adapter and contract tests vs interim `put` graphs
- **`Relationship(..., cascade=False)`** for non-owned embeds
- **`StaleTripleWarning`** on overlapping `add()` for the same subject
- **`sparqlmodel[fastapi]`** — `init_app`, `SessionDep`, `http_store_lifespan`, `turtle_response`, `jsonld_response`, `negotiated_response`

### Changed

- `SPARQLSession` accepts any `Store` implementation (not only `MemoryStore`)
- Pluggable `Store` protocol documented in [SPECS](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/SPECS.md)

### Fixed

- **`AndExpr.__or__`** — `(A & B) | C` compiles as (A AND B) OR C, not three flat disjuncts
- **`use_not_exists_for_ne`** — unique variables per `!=` inside AND branches of OR
- **Compiler** — URL-shaped strings on `str` fields compile as literals, not IRIs
- **`SPARQLSession.get`** — identity map used at `depth=0` when relationships are not materialized
- **`put(..., flush=False)`** — no longer registers identity before flush; hydration invalidated on queue
- **`flush()`** — re-queues pending models if a mid-flush `put` fails

### Documentation

- [ROADMAP](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ROADMAP.md) — **Shipped (0.2.0)**; milestones 0.3–1.0 and SQLModel / SPARQLMojo parity tables
- [ORM](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ORM.md), [SPECS](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/SPECS.md), [README](https://github.com/eddiethedean/sqarqlmodel/blob/main/README.md) — HttpStore mirror, session flush/identity map, compiler ops, FastAPI extra, known limitations
- [PLAN](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/PLAN.md), [PRODUCTION](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/PRODUCTION.md) — production ORM vision, checklist (P0/P1/P2), operator guide
- `expire(Model, iri)` signature; repository URLs in `pyproject.toml`

## [0.1.4] - 2026-05-16

### Added

- **`triplemodel>=0.9.0,<2`** as a required dependency (mapping substrate)

### Changed

- Align `pydantic` and `rdflib` pins with TripleModel (`>=2.5,<3`, `>=7.0,<8`)

### Documentation

- Reposition SparqlModel as a **session-first SPARQL ORM** (the SQLModel of SPARQL) across README and docs
- Add [ORM](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ORM.md) — ORM guide (lifecycle, cascade, query DSL, hydration, package choice)
- Reframe [PLAN](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/PLAN.md), [SPECS](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/SPECS.md), [ECOSYSTEM](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ECOSYSTEM.md), and [ROADMAP](https://github.com/eddiethedean/sqarqlmodel/blob/main/docs/ROADMAP.md) with ORM-first structure; TripleModel as mapping substrate
- Rewrite all docs for **`triplemodel>=0.9` as required mapping engine**; integration roadmap focuses on wiring, not adding the dependency
- Update package metadata and module docstrings for ORM framing

### Fixed

- `put` orphan cleanup when a relationship changes from embedded model to `IRI` reference (old embedded triples removed)
- SPARQL compiler: unique join variables for parallel nested filters; reject filters on wrong model class
- BNode relationship targets removed correctly on `put` orphan cleanup
- Cascade/orphan subject keys use expanded IRIs and stable `_:id` BNode keys consistently
- `iter_nested_models` dedupes shared embedded resources; serialization still rejects true cycles
- Query filters: string literals no longer coerced to IRIs unless field type is `IRI`; unknown compact prefixes stay literals
- Typed numeric filter literals use XSD datatypes (match graph serialization)
- `resolve_related_model` prefers `SPARQLModel` over `IRI` in union annotations
- JSON-LD: empty `@type` list error; relationship arrays; scalar `IRI` fields export as `@id` nodes
- SPARQL `PREFIX` declarations validate prefix names and namespace URIs
- IRI values in filters serialized via RDFLib `URIRef.n3()`
- `compile_where` rejects negative `limit`

## [0.1.3] - 2026-05-16

### Fixed

- `put` orphan cleanup now runs for embedded models (e.g. changing `Organization.located_in` removes the old `Location`)
- Canonical expanded IRIs used for orphan detection and cycle/visited keys (compact vs absolute mismatch)
- JSON-LD: `IRI` relationship references round-trip; `ensure_id` on export; cycle-safe serialization via `@id` references
- `hydrate_from_bindings` and nested `graph_to_model` respect `rdf:type` (wrong-type bindings skipped)
- Query compiler: RDFLib literal escaping, IRI validation, `None` filter rejection, nested `AndExpr` flattening, invalid `where()` raises `QueryError`
- `Query.limit()` rejects negative values
- Per-subclass `__prefixes__` copy (no shared mutable class dict)

### Documented

- Known limitations in README (shared embeds, `add`, multi-valued predicates, JSON-LD paths, export side effects)

## [0.1.2] - 2026-05-16

### Changed

- `put` and `delete` cascade owned-triple removal to embedded `SPARQLModel` values and former relationship targets (orphan cleanup); `IRI`-only references are not cascade-deleted

## [0.1.1] - 2026-05-16

### Fixed

- Query compiler: strings with colons are only treated as IRIs when they match compact `prefix:local` form; `IRI` values always serialize as IRIs
- `CompareExpr.__and__` for combining filters with `&`
- `Query.first()` restores `_limit` if execution fails
- Hydration `depth` validated consistently on `get`, `query`, and `hydrate_from_bindings`
- `!=` filters use unique SPARQL variables per expression (no collision)
- `hydrate_one` accepts any matching `rdf:type` when a resource has multiple types
- `model_to_triples` detects cyclic nested models
- JSON-LD import: `@type` validation; nested objects no longer inherit parent keys

### Documented

- `add` insert-only semantics and `!=` filter behavior

## [0.1.0] - 2026-05-16

### Added

- `SPARQLModel` base class with Pydantic v2, `rdf_type`, `Field`, and `Relationship`
- `IRI` type with compact/absolute expansion via namespace prefixes
- `SPARQLSession` with `add`, `put`, `delete`, `get`, `query`, and `execute`
- In-memory `MemoryStore` backed by RDFLib
- Query builder with `.where()`, `.all()`, `.first()`, and `.limit()`
- SPARQL compiler for scalar equality and single-hop nested filters
- Graph hydration with configurable depth (0–2)
- RDF serializers (Turtle, N-Triples, RDF/XML, JSON-LD) and `model_dump_jsonld()`
- Test suite with pytest and CI (ruff, ty, coverage ≥85%)

[0.2.0]: https://github.com/eddiethedean/sqarqlmodel/releases/tag/v0.2.0
[0.1.4]: https://github.com/eddiethedean/sqarqlmodel/releases/tag/v0.1.4
[0.1.3]: https://github.com/eddiethedean/sqarqlmodel/releases/tag/v0.1.3
[0.1.2]: https://github.com/eddiethedean/sqarqlmodel/releases/tag/v0.1.2
[0.1.1]: https://github.com/eddiethedean/sqarqlmodel/releases/tag/v0.1.1
[0.1.0]: https://github.com/eddiethedean/sqarqlmodel/releases/tag/v0.1.0
