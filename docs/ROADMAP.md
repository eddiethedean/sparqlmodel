# SparqlModel Roadmap

ORM-focused releases and TripleModel integration. SparqlModel is **the SQLModel of SPARQL** — sessions, queries, stores, and persistence policy. Mapping and file I/O delegate to [TripleModel](https://github.com/eddiethedean/triplemodel).

- [ORM guide](ORM.md) — user-facing
- [SPECS.md](SPECS.md) — technical spec
- [PLAN.md](PLAN.md) — vision
- [ECOSYSTEM.md](ECOSYSTEM.md) — package boundaries

**Ecosystem rule:** mapping and file I/O live in TripleModel; session, SPARQL compilation, stores, and cascade policy live in SparqlModel.

---

## ORM north star

**Shipped (0.1.x):** session CRUD, query DSL, SPARQL compiler, hydration depth, cascade on `put`/`delete`, in-memory store.

**Planned ORM (0.2+):** HTTP SPARQL store, identity map, session cache, richer query compiler, FastAPI extra.

**Integration (0.3+):** delegate mapping to TripleModel; **public ORM API unchanged** (`SPARQLSession`, `Field`, `Relationship`, query DSL).

---

## Shipped (0.1.x)

| ORM area | Status |
|----------|--------|
| `SPARQLSession` CRUD (`add`, `put`, `delete`, `get`, `query`) | Done |
| `SPARQLModel`, `Field`, `Relationship`, `IRI` | Done |
| In-memory `MemoryStore` (RDFLib) | Done |
| Query builder (`where`, `all`, `first`, `limit`) | Done |
| SPARQL compiler (`==`, `!=`, `&`, single-hop nested filters) | Done |
| Hydration (`depth` 0–2) | Done |
| Cascade ownership on `put`/`delete` | Done (0.1.2) |
| Optional RDF export (interim serializers) | Done (delegate 0.4+) |
| CI (pytest, ruff, ty, coverage ≥85%) | Done |
| Interim mapper in `graph.py` | Done (delegate TripleModel 0.3) |

---

## 0.2 — Operational ORM

Real triple stores and API workloads. **`triplemodel` not yet a declared dependency** — develop against `pip install -e ../triplemodel`.

### Stores

- [ ] `HttpStore` — SPARQL 1.1 over HTTP (`httpx`)
- [ ] `SELECT` and `UPDATE` against remote endpoints
- [ ] `SPARQLSession` accepts any `Store` implementation
- [ ] Authentication (basic, bearer)

### Session and performance

- [ ] Identity map (one instance per IRI per session)
- [ ] Session cache for `get` / query hydration
- [ ] Optional `flush` / unit-of-work for batched `put`s

### Query compiler

- [ ] `OR` and grouped expressions
- [ ] Ordering comparisons (`<`, `>`, `<=`, `>=`) for numeric and date literals
- [ ] Multi-hop nested filters
- [ ] Configurable `!=` semantics (optional SQL-style `NOT EXISTS`)
- [ ] `IN` / membership filters

### API integration

- [ ] Optional FastAPI extra (`sparqlmodel[fastapi]`)
- [ ] Response classes for Turtle, JSON-LD, RDF/XML
- [ ] Content negotiation

### Persistence polish

- [ ] `add` vs `put` — merge mode or stale-literal warnings on re-`add`
- [ ] `cascade=False` on `Relationship` for shared embedded IRIs
- [ ] Align with TripleModel 0.2 sync/remove before 0.3 integration

### TripleModel adapter (dev)

- [ ] `sparqlmodel/_triple.py` — `SPARQLModel` ↔ `TripleModel` for one model
- [ ] Track [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md) for 0.2 gate

---

## 0.3 — Delegate mapping; ORM surface unchanged

Single mapping path through TripleModel. **Public SparqlModel ORM API unchanged** — same `SPARQLSession`, `Field`, `Relationship`, query DSL.

**Requires:** `triplemodel>=0.2` when upstream ships sync/remove, namespace bind, nested embeds, and multi-value.

### Integration

- [ ] Declare `triplemodel` per [ECOSYSTEM.md](ECOSYSTEM.md#triplemodel-version-gates)
- [ ] Route `model_to_graph` / load through TripleModel; keep `put`/`delete` cascade in SparqlModel
- [ ] Field adapter: `Field("curie")` / `Relationship` over `rdf_field` / `Predicate`
- [ ] Contract tests vs SparqlModel 0.1.x graph output
- [ ] Remove interim term conversion from `graph.py`
- [ ] README + CHANGELOG (ORM positioning)

### Consume from TripleModel

| Feature | TripleModel | SparqlModel ORM |
|---------|-------------|-----------------|
| Multi-valued `list[T]` | implements | hydration + query |
| XSD / literals | implements | stop local converters |
| Subject IRI safety | implements | — |
| Blank nodes / RDF lists | 0.3 | align cascade keys |

### SparqlModel-only (ORM)

- [ ] `resolve_related_model` for unions / `ForwardRef`
- [ ] Narrow `HydrationError` scope
- [ ] Optional strict `IRI` validation
- [ ] Optional `put` hook via `triplemodel[shacl]`

---

## 0.4 — File I/O via TripleModel

Delegate serializers; SparqlModel stays **session + SPARQL ORM**.

**Requires:** `triplemodel>=0.4` for `parse` / `serialize`.

- [ ] Delegate serializers to TripleModel
- [ ] Named graphs on fields when TripleModel 0.5 supports Dataset
- [ ] Blank node strategy aligned with TripleModel

**Still SparqlModel:** compiler, query, stores, cascade, FastAPI.

---

## 0.5+ — Ecosystem

| Theme | Owner |
|-------|--------|
| semantic-sqlmodel backend | SparqlModel |
| SPARQL federation | SparqlModel |
| Reasoning hooks (not a full reasoner) | optional |
| Oxigraph / other store backends | SparqlModel `stores/` |
| AI / JSON-LD pipelines | both |
| MkDocs and tutorials | SparqlModel |

**Out of scope:** ontology editing, built-in OWL reasoner, parsers only in SparqlModel, session code in TripleModel.

---

## TripleModel tracker

| TripleModel | SparqlModel |
|-------------|-------------|
| **0.2** | 0.3 integration |
| **0.3** | blank node / RDF list alignment |
| **0.4** | delegate serializers |
| **0.5** | named graphs if needed |

[TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md)

---

## Priorities

1. ORM operational features (HTTP store, identity map, FastAPI) before niche RDF tooling.
2. Mapping and files in TripleModel first.
3. Explicit, documented ORM semantics for cascade and filters ([ORM.md](ORM.md)).
4. Stable `SPARQLModel` / `Field` / `session.put` public API.
5. Heavy deps as extras only.

---

## Contributing

1. [ORM.md](ORM.md) — what belongs in the ORM
2. [ECOSYSTEM.md — Where to implement](ECOSYSTEM.md#where-to-implement-a-change)
3. Match a roadmap section; add CHANGELOG under next release.
4. Discuss 0.5+ large items in an issue first.
5. Drop SparqlModel tests that only duplicate a TripleModel mapping fix.
