# SparqlModel Roadmap

Shipped work, upcoming releases, and how they align with [TripleModel](https://github.com/eddiethedean/triplemodel).

- Implementation detail: [SPECS.md](SPECS.md)
- Vision and architecture: [PLAN.md](PLAN.md)
- Package boundaries: [ECOSYSTEM.md](ECOSYSTEM.md)

**Ecosystem rule:** mapping and file I/O live in TripleModel; session, SPARQL compilation, stores, and cascade policy live in SparqlModel.

---

## Shipped (0.1.x)

| Area | Status |
|------|--------|
| `SPARQLModel`, `Field`, `Relationship`, `IRI` | Done |
| `SPARQLSession` CRUD (`add`, `put`, `delete`, `get`) | Done |
| In-memory `MemoryStore` (RDFLib) | Done |
| Query builder (`where`, `all`, `first`, `limit`) | Done |
| SPARQL compiler (`==`, `!=`, `&`, single-hop nested filters) | Done |
| Hydration (`depth` 0–2) | Done |
| RDF serializers (Turtle, N-Triples, RDF/XML, JSON-LD) | Done (interim; delegate 0.4+) |
| Cascade ownership on `put`/`delete` | Done (0.1.2) |
| CI (pytest, ruff, ty, coverage ≥85%) | Done |
| Interim model ↔ triple mapping in `graph.py` | Done (replaced by TripleModel in 0.3) |

---

## 0.2 — Operational persistence

Real triple stores and API workloads. **`triplemodel` not yet a declared dependency** — develop against `pip install -e ../triplemodel`.

### Remote SPARQL store

- [ ] `HttpStore` — SPARQL 1.1 over HTTP (`httpx`)
- [ ] `SELECT` and `UPDATE` against remote endpoints
- [ ] `SPARQLSession` accepts any `Store` implementation
- [ ] Authentication (basic, bearer)

### Session & performance

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

## 0.3 — TripleModel integration

Single mapping path through TripleModel; public SparqlModel API unchanged.

**Requires:** `triplemodel>=0.2` when upstream ships sync/remove, namespace bind, nested embeds, and multi-value.

### Integration

- [ ] Declare `triplemodel` per [ECOSYSTEM.md](ECOSYSTEM.md#triplemodel-version-gates)
- [ ] Route `model_to_graph` / load through TripleModel; keep `put`/`delete` cascade in SparqlModel
- [ ] Field adapter: `Field("curie")` / `Relationship` over `rdf_field` / `Predicate`
- [ ] Contract tests vs SparqlModel 0.1.x graph output
- [ ] Remove interim term conversion from `graph.py`
- [ ] README + CHANGELOG

### In TripleModel (consume in SparqlModel)

| Feature | TripleModel | SparqlModel |
|---------|-------------|-------------|
| Multi-valued `list[T]` | implements | hydration + query |
| XSD / literals | implements | stop local converters |
| Subject IRI safety | implements | — |
| Duplicate predicate detection | implements | — |
| Blank nodes / RDF lists | 0.3 | align cascade keys |

### SparqlModel-only

- [ ] `resolve_related_model` for unions / `ForwardRef`
- [ ] Narrow `HydrationError` scope
- [ ] Optional strict `IRI` validation
- [ ] Optional `put` hook via `triplemodel[shacl]`

### Later (TripleModel 0.4+)

- [ ] Delegate `export_model` → `to_graph().serialize(...)`
- [ ] Named graphs when TripleModel 0.5 has `Dataset`
- [ ] SHACL shape generation in TripleModel; SparqlModel may validate on `put`

---

## 0.4 — File I/O via TripleModel

Thin `serializers.py`; SparqlModel focuses on session and SPARQL.

**Requires:** `triplemodel>=0.4` for `parse` / `serialize`.

- [ ] Delegate serializers to TripleModel
- [ ] Named graphs on fields when TripleModel 0.5 supports Dataset
- [ ] Blank node strategy aligned with TripleModel

**Still SparqlModel:** compiler, query, stores, cascade, FastAPI polish.

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

1. Operational features (HTTP store, FastAPI) before niche RDF tooling.
2. Mapping and files in TripleModel first.
3. Explicit, documented semantics for cascade and filters.
4. Stable `SPARQLModel` / `Field` / `session.put` public API.
5. Heavy deps as extras only.

---

## Contributing

1. [ECOSYSTEM.md — Where to implement](ECOSYSTEM.md#where-to-implement-a-change)
2. Match a roadmap section; add CHANGELOG under next release.
3. Discuss 0.5+ large items in an issue first.
4. Drop SparqlModel tests that only duplicate a TripleModel mapping fix.
