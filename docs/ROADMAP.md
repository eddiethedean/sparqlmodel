# SparqlModel Roadmap

This document tracks what is shipped, what is planned next, and longer-term direction. For implementation detail, see [SPECS.md](SPECS.md). For product vision and ecosystem boundaries, see [PLAN.md](PLAN.md) and [ECOSYSTEM.md](ECOSYSTEM.md).

**Ecosystem rule:** SparqlModel gets thinner as [RDFModel](https://github.com/eddiethedean/rdfmodel) matures. Features that help a script with no `SPARQLSession` belong in RDFModel; session, SPARQL compilation, stores, and cascade policy stay here.

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
| RDF serializers (Turtle, N-Triples, RDF/XML, JSON-LD) | Done (to delegate in 0.3+) |
| Cascade ownership for embedded models on `put`/`delete` | Done (0.1.2) |
| CI (pytest, ruff, ty, coverage ≥85%) | Done |

**Technical debt:** `graph.py`, `fields.py`, `types.py`, `serializers.py`, and parts of `hydration.py` overlap RDFModel until integration (see [ECOSYSTEM.md — Current overlap](ECOSYSTEM.md#current-overlap-technical-debt)).

---

## 0.2 — Operational persistence & ergonomics

Target: real triple stores and typical API workloads. **No required `rdfmodel` PyPI dependency** — pin RDFModel in dev only (`pip install -e ../rdfmodel`) and prototype adapters.

### Remote SPARQL store

- [ ] `HttpStore` — SPARQL 1.1 Protocol over HTTP (`httpx`)
- [ ] `SELECT` and `UPDATE` (INSERT/DELETE) against remote endpoints
- [ ] `SPARQLSession` accepts any `Store` implementation (not only `MemoryStore`)
- [ ] Authentication hooks (basic auth, bearer token)

### Session & performance

- [ ] Identity map — one in-memory instance per IRI per session
- [ ] Session-level cache for repeated `get` / query hydration
- [ ] Optional `flush` / unit-of-work batching for multiple `put`s

### Query compiler

- [ ] `OR` and grouped expressions
- [ ] Ordering comparisons (`<`, `>`, `<=`, `>=`) for numeric and date literals
- [ ] Multi-hop nested filters (beyond one relationship hop)
- [ ] Optional SQL-style `NOT EXISTS` semantics for `!=` (configurable; current behavior documented)
- [ ] `IN` / membership filters

### API integration

- [ ] Optional FastAPI extra (`sparqlmodel[fastapi]`)
- [ ] Response classes for Turtle, JSON-LD, RDF/XML
- [ ] Content negotiation on read endpoints

### Persistence polish (SparqlModel-owned)

- [ ] `add` vs `put` clarity — optional `merge` mode or stale-literal warnings on re-`add`
- [ ] Reference counting or explicit `cascade=False` on `Relationship` for shared embedded IRIs
- [ ] Coordinate with RDFModel 0.2 sync/remove when integrating (avoid divergent stale-triple behavior)

### RDFModel prep (dev-only)

- [ ] `_rdf.py` adapter proof of concept: one `SPARQLModel` ↔ `RdfModel` config
- [ ] Track [RDFModel ROADMAP](https://github.com/eddiethedean/rdfmodel/blob/main/ROADMAP.md) for 0.2 gate (sync/remove, namespaces, nested embeds, multi-value)

---

## 0.3 — RDFModel integration & graph modeling

Target: single mapping code path through RDFModel; public SparqlModel API unchanged for typical apps.

**Dependency gate:** declare `rdfmodel>=0.2,<0.3` (adjust to actual RDFModel releases) when upstream provides sync/remove, namespace bind, nested embedded models, and multi-valued fields.

### Integration (required for 0.3 release)

- [ ] Runtime dependency on `rdfmodel` per gate in [ECOSYSTEM.md](ECOSYSTEM.md#rdfmodel-releases-to-wait-for-dependency-gate)
- [ ] Replace `model_to_graph` / primary load path via RDFModel; keep `put`/`delete` orchestration and cascade in `session.py` + `graph.py` policy helpers
- [ ] Field metadata adapter: preserve `Field("curie")` / `Relationship` UX over `rdf_field` / `Predicate`
- [ ] Contract tests: RDFModel round-trip matches legacy graph output for core models
- [ ] Remove duplicated term conversion from `graph.py` once coverage is green
- [ ] Document integration in README and CHANGELOG

### Upstream-first (implement in RDFModel; consume in SparqlModel)

| Feature | Owner | SparqlModel action |
|---------|--------|-------------------|
| Multi-valued fields (`list[T]`) | **RDFModel** | Hydration/query consume RDFModel load |
| XSD / literal correctness | **RDFModel** | Stop extending local converters |
| Subject IRI prefix safety | **RDFModel** | — |
| Duplicate predicate detection on load | **RDFModel** | — |
| Blank nodes / RDF lists (if still embedding BNodes) | **RDFModel** 0.3 | Align cascade keys with upstream |

### SparqlModel-only (0.3)

- [ ] `resolve_related_model` improvements for unions and `ForwardRef`
- [ ] Narrow `HydrationError` to validation/config failures
- [ ] Optional stricter `IRI` validation mode
- [ ] Optional `session.put` validation hook via `rdfmodel[shacl]` (do not bundle `pyshacl` in core)

### Deferred until RDFModel 0.4+

- [ ] Delegate `export_model` / file formats to `model.to_graph().serialize(...)` ([ECOSYSTEM.md](ECOSYSTEM.md))
- [ ] Named graphs / `Dataset` — after RDFModel 0.5
- [ ] SHACL shapes **generation** — RDFModel; SparqlModel may only hook validation on `put`

---

## 0.4 — File I/O delegation & advanced persistence

Target: thin `serializers.py`; SparqlModel focuses on session and SPARQL.

**Dependency gate:** `rdfmodel>=0.4` for `parse` / `serialize` and base URI handling.

- [ ] Replace most of `serializers.py` with RDFModel parse/serialize
- [ ] Named graphs on `Field` / `Relationship` when RDFModel 0.5 `Dataset` support lands
- [ ] Blank node strategy documented and configurable (`_:id` vs stable skolem) — align with RDFModel

### Stay in SparqlModel (0.4+)

- `compiler.py`, `query.py`, `HttpStore` hardening, identity map refinements
- Cascade/orphan rules on `put`/`delete`
- FastAPI extras and content negotiation polish

---

## 0.5+ — Ecosystem & advanced RDF

Longer-term, optional capabilities. Not committed to a release date.

| Theme | Owner | Notes |
|-------|--------|--------|
| **semantic-sqlmodel** | SparqlModel adapter | Optional RDF/SPARQL backend |
| **Federation** | SparqlModel | SPARQL endpoint federation |
| **Reasoning** | Optional hooks | Not a full reasoner; materialization hooks only |
| **Engines** | SparqlModel `stores/` | pyoxigraph / Oxigraph backend experiments |
| **AI** | Both | JSON-LD pipelines; PydanticAI-friendly helpers |
| **Docs** | SparqlModel | MkDocs, tutorials, deployment guides |
| **OWL export** | Low priority | From model metadata; not core ORM |

Explicitly **out of scope** for SparqlModel core:

- Ontology editing (Protégé replacement)
- Built-in OWL reasoning engine
- Copy-pasting `python_to_term` or Turtle parsers from RDFModel into `graph.py`
- Pushing session or query-compiler code into RDFModel

---

## RDFModel milestone tracker

Track [RDFModel ROADMAP](https://github.com/eddiethedean/rdfmodel/blob/main/ROADMAP.md) before bumping SparqlModel’s `rdfmodel` pin.

| RDFModel release | Unblocks in SparqlModel |
|------------------|-------------------------|
| **0.2** | Required dep; replace graph sync path; multi-value; namespaces |
| **0.3** | Blank node / RDF list alignment for embedded resources |
| **0.4** | Delegate `serializers.py`; parse/serialize in docs/examples |
| **0.5** | Named graphs / `@graph` on models if pursued |

---

## How priorities are chosen

1. **Operational first** — remote stores and FastAPI beat niche RDF features.
2. **Upstream mapping** — term, file, and multi-value work goes to RDFModel before growing SparqlModel.
3. **Explicit over magic** — cascade, `!=`, and `add` vs `put` stay documented and predictable.
4. **Stable public API** — `SPARQLModel`, `Field`, `session.put` remain familiar; internal duplication is what shrinks.
5. **Optional extras** — FastAPI, HTTP store, SHACL via RDFModel extras — not heavy deps in core.

---

## Contributing

When picking up work:

1. Check [ECOSYSTEM.md — Where to implement](ECOSYSTEM.md#where-to-implement-a-change) before opening a PR.
2. Align with a roadmap section and add a CHANGELOG entry under the next unreleased version.
3. Open an issue to discuss 0.5+ items before large implementations.
4. If RDFModel already fixes a mapping bug, drop duplicate SparqlModel tests that only asserted the same behavior.
