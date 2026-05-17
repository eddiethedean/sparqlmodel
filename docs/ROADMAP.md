# SparqlModel Roadmap

This document tracks what is shipped, what is planned next, and longer-term direction. For implementation detail, see [SPECS.md](SPECS.md). For product vision, see [PLAN.md](PLAN.md).

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
| RDF serializers (Turtle, N-Triples, RDF/XML, JSON-LD) | Done |
| Cascade ownership for embedded models on `put`/`delete` | Done (0.1.2) |
| CI (pytest, ruff, ty, coverage ≥85%) | Done |

---

## 0.2 — Operational persistence & ergonomics

Target: make SparqlModel usable against real triple stores and typical API workloads.

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

### Persistence polish

- [ ] `add` vs `put` clarity — optional `merge` mode or stale-literal warnings on re-`add`
- [ ] Reference counting or explicit `cascade=False` on `Relationship` for shared embedded IRIs
- [ ] SPARQL literal escaping via RDFLib term serialization

---

## 0.3 — Graph modeling & data quality

Target: safer RDF modeling and production data constraints.

### Cardinality & validation

- [ ] Multi-valued fields (`list[T]` ↔ multiple objects per predicate)
- [ ] Detect ambiguous duplicate predicates on load (two fields → one predicate)
- [ ] Validate unique expanded predicates per model at class definition

### Graph features

- [ ] Named graphs / contexts on `Field` and `Relationship`
- [ ] Blank node strategy documented and configurable (`_:id` vs stable skolem)

### SHACL & schemas

- [ ] Optional SHACL shapes generation from models
- [ ] Validate instances on `put` when `pyshacl` extra is installed

### Hydration & types

- [ ] Narrow `HydrationError` to validation/config failures (avoid masking bugs)
- [ ] Stricter `IRI` validation mode (optional RFC 3987 checks)
- [ ] `resolve_related_model` improvements for unions and `ForwardRef`

---

## 0.4+ — Ecosystem & advanced RDF

Longer-term, optional capabilities. Not committed to a release date.

| Theme | Ideas |
|-------|--------|
| **Interop** | semantic-sqlmodel backend adapter; SPARQL endpoint federation |
| **Reasoning** | Optional OWL/RDFS materialization hooks (not a full reasoner) |
| **Export** | OWL ontology export from model metadata |
| **Engines** | pyoxigraph / Oxigraph store backend; Neo4j bridge experiments |
| **AI** | JSON-LD round-trip for extraction pipelines; PydanticAI-friendly helpers |
| **Docs** | MkDocs site, tutorials, deployment guides |

Explicitly **out of scope** for SparqlModel core:

- Ontology editing (Protégé replacement)
- Built-in OWL reasoning engine
- Full academic OWL tooling surface

---

## How priorities are chosen

1. **Operational first** — remote stores and FastAPI beat niche RDF features.
2. **Explicit over magic** — behavior (cascade, `!=`, `add`) stays documented and predictable.
3. **Pydantic-native** — models and validation remain central; raw triple APIs stay secondary.
4. **Optional extras** — heavy dependencies (SHACL, pyld, FastAPI) ship as optional install groups.

---

## Contributing

When picking up work, align PRs with a roadmap section and add a CHANGELOG entry under the next unreleased version. Open an issue to discuss items marked 0.4+ before large implementations.
