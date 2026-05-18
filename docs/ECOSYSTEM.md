# SparqlModel (ORM) and TripleModel (mapping)

How **SparqlModel** (`sparqlmodel`) — the **SPARQL ORM** — and **TripleModel** (`triplemodel`) — the **mapping substrate** — divide responsibility in the Python RDF stack.

User guide: [ORM.md](ORM.md) · Aligned docs: [PLAN.md](PLAN.md), [ROADMAP.md](ROADMAP.md), [SPECS.md](SPECS.md), [README.md](../README.md)

The two-sided maintainer guide also lives in the TripleModel repo:  
[docs/ECOSYSTEM.md](https://github.com/eddiethedean/triplemodel/blob/main/docs/ECOSYSTEM.md)

---

## Choose your package

| I need… | Use |
|---------|-----|
| CRUD, queries, cascade in an app | **SparqlModel** (`SPARQLSession`) |
| Python `where(Model.field == x)` → SPARQL | **SparqlModel** |
| Remote SPARQL, identity map, FastAPI (roadmap) | **SparqlModel** |
| Stateless `to_graph()` / `from_graph()` or file I/O | **[TripleModel](https://github.com/eddiethedean/triplemodel)** |
| ETL, libraries, tests without a session | **TripleModel** |

| | SparqlModel | TripleModel |
|---|-------------|-------------|
| **Metaphor** | SQLModel / SQLAlchemy ORM | SQLAlchemy Core / serde layer |
| **Question** | “How do I run an app on a graph?” | “How do I turn objects into correct triples?” |
| **Entry point** | `SPARQLSession()` | `model.to_graph()` / `parse()` |
| **State** | Stateful session | Stateless |

---

## Stack

```text
┌──────────────────────────────────────────┐
│  SparqlModel (ORM)                       │
│  Session · Query · Compiler · Stores       │
└────────────────────┬─────────────────────┘
                     │  triplemodel (from SparqlModel 0.3)
┌────────────────────▼─────────────────────┐
│  TripleModel (mapping substrate)         │
│  Terms · sync · parse/serialize          │
└────────────────────┬─────────────────────┘
                     │
┌────────────────────▼─────────────────────┐
│  rdflib · pydantic                       │
└──────────────────────────────────────────┘
```

**Rules for SparqlModel:**

1. **Depends on** `triplemodel` from 0.3 onward; **must not** reimplement mapping logic that belongs in TripleModel.
2. TripleModel **must not** import SparqlModel.
3. Term and graph mapping bugs → TripleModel; compiler, session, and cascade bugs → SparqlModel.

---

## SparqlModel (ORM)

**Tagline:** **SparqlModel — the SQLModel of SPARQL.**

**Question it answers:** “How do I run an app with CRUD, filters, and updates over RDF?”

| Layer | SparqlModel owns it |
|-------|---------------------|
| `SPARQLSession` | `add`, `put`, `delete`, `get`, `execute` |
| Stores | `MemoryStore`, `HttpStore` (roadmap) |
| Query DSL | `session.query(Model).where(...)` |
| SPARQL compiler | `==`, `!=`, `&`, nested hops → SPARQL |
| Hydration | `get(..., depth=0\|1\|2)` |
| Persistence policy | Owned triples, orphan cleanup, `add` vs `put` |
| App extras | FastAPI, HTTP SPARQL (roadmap) |

**Out of scope:** canonical literal/datatype conversion, subject-URI prefix safety, Turtle/JSON-LD format registry, or stateless file round-trip without a session.

---

## TripleModel (mapping substrate)

**Tagline:** Pydantic models ↔ RDF graphs (library-first, stateless).

**Repo:** [github.com/eddiethedean/triplemodel](https://github.com/eddiethedean/triplemodel) · PyPI: `triplemodel`

| Layer | TripleModel owns it |
|-------|---------------------|
| `TripleModel`, `rdf_field`, `Predicate` | Field ↔ predicate metadata |
| `RdfConfig` / `rdf_config()` | `namespace`, `type_uri`, `id_field` |
| `to_graph`, `sync_to_graph`, `from_graph` | Stateless round-trip |
| Terms | `python_to_term`, `term_to_python` |
| Files | `parse` / `serialize` |
| rdflib matrix | Namespaces, Dataset, etc. ([ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md)) |

**Users:** ETL, libraries, tests — and SparqlModel for model ↔ triple conversion from 0.3 onward.

```python
# TripleModel — use directly when you do not need a session
person = Person(slug="alice", name="Alice")
g = person.to_graph()
restored = Person.from_graph(g, person.subject_uri())
```

---

## Where to implement a change

| Symptom or feature | Repo | SparqlModel module (0.1.x) |
|--------------------|------|----------------------------|
| Wrong XSD type on export | **TripleModel** | `graph.py` (interim until 0.3) |
| Subject IRI prefix collision | **TripleModel** | — |
| `put` left stale `foaf:age` triple | **TripleModel** sync + **SparqlModel** `put` policy | `graph.py`, `session.py` |
| Orphan embedded IRI after relationship change | **SparqlModel** | `graph.py` (`cascade_subjects_for_removal`) |
| `!=` filter semantics | **SparqlModel** | `compiler.py` |
| Nested `Person.works_for.name` filter | **SparqlModel** | `compiler.py` |
| Multi-valued field round-trip | **TripleModel** | `hydration.py` consumes upstream |
| Turtle prefixes in export | **TripleModel** | `serializers.py` → thin wrapper (0.4+) |
| Remote Fuseki endpoint | **SparqlModel** | `stores/` |
| SHACL on save | **TripleModel** optional extra | optional hook on `session.put` |

### Maintainer heuristic

If the fix would help code that **never** creates a `SPARQLSession`, it belongs in **TripleModel**.

---

## Maintainer: interim 0.1.x mapper

SparqlModel **0.1.x** ships before the declared `triplemodel` dependency. Model ↔ triple conversion temporarily lives in `graph.py`, `fields.py`, and related modules. This is an **implementation detail** — SparqlModel is still an ORM; users start with `SPARQLSession`, not `model_to_graph`.

| SparqlModel module | TripleModel responsibility (from 0.3) | 0.3+ plan |
|--------------------|---------------------------------------|-----------|
| `graph.py` | `sync_to_graph`, triple sync | Delegate conversion; keep cascade/orphan policy |
| `fields.py` | `rdf_field`, predicate metadata | Adapter; keep `Field("curie")` UX |
| `types.py` (`IRI`, prefixes) | namespaces, subject IRIs | Keep `IRI`; expand via TripleModel |
| `serializers.py` | `parse` / `serialize` | Delegate (0.4+) |
| `hydration.py` | `from_graph` | Load via TripleModel; keep depth in ORM |
| `compiler.py` | — | SparqlModel only |
| `session.py`, `query.py`, `stores/*` | — | SparqlModel only |

Do **not** add new format parsers or datatype registries to `graph.py` — add them in TripleModel.

---

## Public API mapping

SparqlModel keeps a SQLModel-style ORM surface. Internally, 0.3+ calls TripleModel.

| SparqlModel (public ORM) | TripleModel (internal) |
|--------------------------|------------------------|
| `SPARQLModel` | Compose or subclass `TripleModel` |
| `rdf_type = "schema:Person"` | `type_uri` via `rdf_config()` |
| `Field("schema:name")` | `rdf_field` / `Predicate` |
| `id: IRI` | explicit IRI or `id_field` + namespace |
| `__prefixes__` | prefixes on `RdfConfig` |
| `session.put(model)` | TripleModel sync + SparqlModel cascade |
| `session.get`, `query` | TripleModel load + compiler/hydration |
| `export_model(...)` | `to_graph().serialize(...)` (0.4+) |

---

## TripleModel version gates

Declare `dependencies = ["triplemodel>=X"]` when TripleModel provides:

| TripleModel | SparqlModel milestone |
|-------------|----------------------|
| **0.2** | 0.3 — sync/remove, namespaces, nested embeds, multi-value |
| **0.3** | blank node / RDF list alignment for embedded resources |
| **0.4** | 0.4 — delegate `serializers.py`; parse/serialize in examples |
| **0.5** | named graphs / `@graph` if models need Dataset |

**Always SparqlModel (ORM):** `compiler.py`, `query.py`, cascade rules, `HttpStore`, FastAPI, identity map.

Track: [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md)

---

## Integration path (0.2 → 0.3)

1. **0.2 dev** — `pip install -e ../triplemodel`; prototype `sparqlmodel/_triple.py` (`SPARQLModel` ↔ `TripleModel`).
2. **0.3** — wire `model_to_graph` / load through TripleModel; keep `put`/`delete` cascade in `session.py`; **public ORM API unchanged**.
3. **Tests** — contract tests: TripleModel round-trip matches SparqlModel 0.1.x graph output for core models.
4. **Release** — `sparqlmodel` depends on `triplemodel>=0.2,<0.3` (adjust to actual releases).
5. **0.4** — thin `serializers.py`; delete interim term code from `graph.py`.

---

## Dependencies

| Package | SparqlModel |
|---------|-------------|
| `pydantic`, `rdflib`, `typing-extensions` | core (0.1.x+) |
| `triplemodel` | required from 0.3 |
| `httpx` | extra / dev (`sparqlmodel[http]`) |
| `fastapi` | extra only |
| `pyshacl` | **not** in core — `triplemodel[shacl]` if validation hooks are added |

SQLAlchemy / BerkeleyDB stay in TripleModel store extras, not SparqlModel core.

---

## Testing

| Concern | Owner |
|---------|--------|
| Literals, subject URI, parse round-trip | TripleModel |
| `put`, orphan, cascade | SparqlModel |
| Compiler, nested filters | SparqlModel |
| Session CRUD | SparqlModel |
| Cross-package contract | CI: released `triplemodel` + SparqlModel `main` |

---

## Documentation

| Document | Audience |
|----------|----------|
| [ORM.md](ORM.md) | App developers (ORM guide) |
| SparqlModel README | Quickstart and install |
| SparqlModel SPECS / ROADMAP / PLAN | Releases and architecture |
| TripleModel README | Mapping and files |
| TripleModel ECOSYSTEM | Both maintainers |
| **This file** | SparqlModel maintainers |

---

## Anti-patterns

- Copying `python_to_term` from TripleModel into `graph.py`
- Turtle/JSON-LD parsers only in SparqlModel
- Session or query-compiler code in TripleModel
- `triplemodel` dependency before TripleModel 0.2 sync/remove and nested models exist
- `triplemodel` importing `sparqlmodel`
- Positioning SparqlModel as “another mapper” instead of an ORM

---

## Summary

| | TripleModel | SparqlModel |
|---|-------------|-------------|
| **Metaphor** | SQLAlchemy Core / serde | SQLModel / SQLAlchemy ORM |
| **State** | Stateless | Stateful |
| **Killer feature** | Correct triples from Pydantic | `where(Model.field == x)` |
| **Grow here** | Terms, files, Dataset | Compiler, stores, cascade, FastAPI |

New rdflib mapping work goes in TripleModel. SparqlModel owns **application persistence and SPARQL ergonomics**.
