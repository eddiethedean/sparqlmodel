# SparqlModel Roadmap

SparqlModel is **the SQLModel of SPARQL** — a session-first ORM. **TripleModel** (`triplemodel>=0.9`, required) is the mapping engine. This roadmap covers **ORM features** and **wiring TripleModel into session I/O** (retiring interim `graph.py` / `serializers.py`).

- [ORM guide](ORM.md) — application developers
- [SPECS.md](SPECS.md) — technical spec
- [ECOSYSTEM.md](ECOSYSTEM.md) — boundaries
- [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md) — upstream

---

## North star

**SparqlModel builds apps. TripleModel builds correct graphs.**

| Layer | Responsibility |
|-------|----------------|
| **SparqlModel** | `SPARQLSession`, query DSL, compiler, stores, cascade, hydration `depth` |
| **TripleModel** | Terms, `sync_to_graph`, `from_graph`, `parse`, `serialize`, Dataset |

**Dependency:** `triplemodel>=0.9.0,<2` is **shipped** in `pyproject.toml`.

**Integration debt:** `graph.py` and `serializers.py` still duplicate some TripleModel behavior — scheduled for removal, not expansion.

---

## Shipped (0.1.x)

### ORM

| Feature | Status |
|---------|--------|
| `SPARQLSession` — `add`, `put`, `delete`, `get`, `query`, `execute` | Done |
| `SPARQLModel`, `Field`, `Relationship`, `IRI` | Done |
| `MemoryStore` | Done |
| Query builder + compiler (`==`, `!=`, `&`, nested hop) | Done |
| Hydration `depth` 0–2 | Done |
| Cascade / orphan on `put`/`delete` | Done |
| CI (pytest 100% cov, ruff, ty) | Done |

### TripleModel

| Feature | Status |
|---------|--------|
| `triplemodel>=0.9.0,<2` required dependency | Done |
| Interim mapping in `graph.py` (to retire) | Present — do not extend |
| Interim `serializers.py` (to retire) | Present — do not extend |

---

## Shipped (0.2.0)

### Stores (ORM)

| Feature | Status |
|---------|--------|
| `HttpStore` — SPARQL 1.1 over HTTP (`httpx`), local mirror | Done |
| `sparqlmodel[http]` optional extra | Done |
| Pluggable `Store` protocol; basic / bearer auth | Done |

### Session (ORM)

| Feature | Status |
|---------|--------|
| Identity map + hydration cache | Done |
| `flush()`, `rollback_pending()`, `put(..., flush=False)`, `autoflush` | Done |
| `expire(iri)` | Done |

### Query compiler (ORM)

| Feature | Status |
|---------|--------|
| `OR`, `AndExpr` branches in OR | Done |
| Ordering (`<`, `>`, `<=`, `>=`), `IN` | Done |
| Multi-hop nested filters | Done |
| `Query.use_not_exists_for_ne()` for `!=` | Done |

### FastAPI (ORM)

| Feature | Status |
|---------|--------|
| `sparqlmodel[fastapi]` extra | Done |
| `turtle_response`, `jsonld_response`, `negotiated_response` | Done |

### TripleModel wiring (integration)

| Feature | Status |
|---------|--------|
| `sparqlmodel/_triple.py` adapter | Done |
| Contract tests vs interim `put` graphs | Done |
| `put` still uses `graph.py` (0.3 switch) | Planned |

### Persistence polish

| Feature | Status |
|---------|--------|
| `StaleTripleWarning` on overlapping `add()` | Done |
| `Relationship(..., cascade=False)` | Done |

---

## 0.2 — Operational ORM + adapter foundation

**Status:** shipped as **0.2.0** (see above).

---

## 0.3 — Session I/O through TripleModel

**Goal:** one mapping path. **ORM public API unchanged.**

### Wire session to TripleModel

- [ ] `put` → compute cascade subjects, then `sync_to_graph` (or batch) per resource
- [ ] `get` / query hydration → `from_graph` / `graph_to_model` via adapter
- [ ] Field adapter: `Field("curie")` / `Relationship` → `rdf_field` / `Predicate`
- [ ] Remove interim term conversion from `graph.py`
- [ ] Multi-valued fields via TripleModel; update hydration + query as needed

### SparqlModel-only

- [ ] `resolve_related_model` for unions / `ForwardRef`
- [ ] Optional `put` validation via `triplemodel[shacl]`
- [ ] Narrow `HydrationError` cases

### Consume from TripleModel (already in 0.9)

| Capability | SparqlModel use |
|------------|-----------------|
| `sync_to_graph` / `replace` / `patch` | `put` graph writes |
| `from_graph` / `all_from_graph` | load paths |
| Nested embeds, blanks, RDF lists | align cascade subject keys |
| `Rdf.prefixes`, CURIEs | namespace binding |

---

## 0.4 — File I/O delegated

**Goal:** no format logic in SparqlModel.

- [ ] `serializers.py` → thin wrappers over TripleModel `parse` / `serialize`
- [ ] Examples and docs use TripleModel for file round-trip
- [ ] Delete duplicate format tables and parsers from SparqlModel

**Still SparqlModel:** session, compiler, stores, cascade, FastAPI.

---

## 0.5+ — Ecosystem

| Theme | Owner |
|-------|--------|
| Named graphs in apps | TripleModel Dataset; SparqlModel session if needed |
| semantic-sqlmodel backend | SparqlModel |
| SPARQL federation | SparqlModel |
| Oxigraph / other stores | SparqlModel `stores/` |
| Reasoning hooks | Optional; not core ORM |

**Out of scope:** OWL editor, built-in reasoner, mapping code only in SparqlModel.

---

## Priorities

1. **Do not expand** interim `graph.py` mapping — fix and use TripleModel.
2. Ship **ORM operational** features (HTTP store, identity map) in parallel with wiring.
3. Keep `SPARQLSession` / `Field` / `session.put` stable for users.
4. Contract tests on every integration PR.
5. Document behavior in [ORM.md](ORM.md).

---

## Contributing

1. Read [ORM.md](ORM.md) and [ECOSYSTEM.md — Where to implement](ECOSYSTEM.md#where-to-implement-a-change)
2. Mapping bug? Open/fix in TripleModel, then wire SparqlModel.
3. ORM bug? Fix in SparqlModel.
4. Add CHANGELOG under `[Unreleased]`.
5. Remove SparqlModel tests that only duplicate a fixed TripleModel behavior.
