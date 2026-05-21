# SparqlModel (ORM) + TripleModel (mapping engine)

SparqlModel is a **SPARQL ORM**. TripleModel is its **required mapping engine** (`triplemodel>=0.10.0,<2`); in-process graphs use **pyoxigraph** via `triplemodel.Store`. This document defines boundaries for contributors and maintainers of both packages.

**Architecture (Option A, shipped 0.4.0):** `SPARQLModel` **subclasses** `TripleModel` — one class, one mapping path. Session I/O uses `rdf_bridge` (`model_to_graph`, `load_from_graph`) on the same instances. The 0.3 `_triple.py` adapter was **removed in 0.4**.

**Users:** start with [ORM.md](ORM.md) and the [README](https://github.com/eddiethedean/sqarqlmodel/blob/main/README.md).

TripleModel’s mirror of this contract:  
[github.com/eddiethedean/triplemodel/docs/ECOSYSTEM.md](https://github.com/eddiethedean/triplemodel/blob/main/docs/ECOSYSTEM.md)

Also: [PLAN.md](PLAN.md) · [ROADMAP.md](ROADMAP.md) · [SPECS.md](SPECS.md) · [PRODUCTION.md](PRODUCTION.md) · [ASYNC_RDF_RUST_PLAN.md](ASYNC_RDF_RUST_PLAN.md) (proposed async Rust I/O package)

---

## Choose your package

| I need… | Package |
|---------|---------|
| `SPARQLSession`, CRUD, cascade, query DSL | **SparqlModel** |
| `where(Model.field == x)` → SPARQL | **SparqlModel** |
| Correct triples, `parse` / `serialize`, no session | **TripleModel** |
| ETL, library, test fixtures without ORM | **TripleModel** |

| | SparqlModel | TripleModel |
|---|-------------|-------------|
| **Metaphor** | SQLModel / SQLAlchemy ORM | SQLAlchemy Core |
| **PyPI** | `sparqlmodel` | `triplemodel` (required by SparqlModel) |
| **Imports in apps** | `SPARQLSession`, `SPARQLModel` | Usually transitive; direct for file-only tools |

---

## Stack (required dependency)

Both SparqlModel and TripleModel are **Pydantic v2** stacks: validated Python objects in app code, RDF terms in graphs. SparqlModel adds session lifecycle, SPARQL compilation, stores, and cascade policy; TripleModel adds term mapping and file I/O.

```text
┌──────────────────────────────────────────┐
│  SparqlModel                             │
│  SPARQLModel(TripleModel) · Session · … │
└────────────────────┬─────────────────────┘
                     │  triplemodel>=0.10.0,<2  (required)
┌────────────────────▼─────────────────────┐
│  TripleModel (Pydantic)                  │
│  sync_to_graph · from_graph · parse · …  │
└────────────────────┬─────────────────────┘
                     │
┌────────────────────▼─────────────────────┐
│  pyoxigraph · triplemodel · pydantic     │
└──────────────────────────────────────────┘
```

### Rules

1. SparqlModel **must** depend on `triplemodel>=0.10`; **must not** grow parallel mapping implementations or dynamic shadow `TripleModel` classes.
2. TripleModel **must not** import SparqlModel.
3. Mapping / literal / format bugs → **TripleModel** first, then wire SparqlModel.
4. Session / compiler / cascade bugs → **SparqlModel**.

---

## SparqlModel owns (ORM)

| Area | Modules |
|------|---------|
| Session API | `session.py` |
| Query DSL + SPARQL compiler | `query.py`, `compiler.py`, `expressions.py` |
| Hydration depth | `hydration.py` |
| Cascade / orphan policy | `graph.py` (orchestration), `session.py` |
| Stores | `stores/*` |
| FastAPI (optional extra) | `fastapi/` |

**Out of scope:** XSD registries, `python_to_term`, Turtle parsers, stateless `parse()` without a session.

---

## TripleModel owns (mapping engine)

| Area | Examples |
|------|----------|
| `TripleModel`, `rdf_field`, `Predicate` | Field metadata |
| `RdfConfig` | `namespace`, `type_uri`, `id_field`, prefixes |
| Graph I/O | `to_graph`, `sync_to_graph`, `from_graph`, `all_from_graph` |
| Terms | Literals, `LangString`, registries |
| Files | `parse`, `serialize`, Dataset, N-Quads |
| SHACL | `triplemodel[shacl]` |

`SPARQLModel` **is a** `TripleModel` subclass (0.4+); session code calls these APIs on app instances directly.

```python
# TripleModel — no session required
person = Person(slug="alice", name="Alice")
g = person.to_graph()
sync_to_graph(person, g, mode="replace")
restored = Person.from_graph(g, person.subject_uri())
```

---

## Where to implement a change

| Symptom | Repo | SparqlModel module |
|---------|------|-------------------|
| Wrong XSD / datatype | **TripleModel** | — |
| Subject IRI safety | **TripleModel** | — |
| Stale literal after `put` | **TripleModel** `sync_to_graph` + **SparqlModel** cascade | `session.py`, `graph.py` |
| Orphan embedded resource | **SparqlModel** | `cascade_subjects_for_removal` |
| `!=` / nested filter | **SparqlModel** | `compiler.py` |
| Multi-valued round-trip | **TripleModel** (target **1.0**) | `hydration.py` + query compiler consume |
| Language-tagged literals | **TripleModel** (target **1.0**) | `Field` sugar; not SparqlModel-only |
| New RDF format | **TripleModel** | thin wrapper in `serializers.py` until **0.7** |
| Remote Fuseki | **SparqlModel** | `stores/` |
| SHACL validation | **TripleModel** | optional `put` hook (**1.1**) |

### Heuristic

If the fix helps code that **never** uses `SPARQLSession`, it belongs in **TripleModel**.

---

## Interim code (retiring)

| Module | Status | Action |
|--------|--------|--------|
| `_triple.py` | Interim adapter (0.3) | **Remove in 0.4** (Option A) |
| `graph.py` | Cascade / orphan policy | **Keep** orchestration only |
| `fields.py` | Predicate sugar | Thin wrapper over `rdf_field` / `Predicate` at class creation |
| `serializers.py` | Interim formats | Thin TripleModel wrappers only (**0.7**) |
| `hydration.py` | Depth walker | Keep depth; load via `from_graph` on `SPARQLModel` |

**Do not** add new parsers, datatype tables, term converters, or `exec`-generated shadow model classes to SparqlModel.

---

## Public ORM API vs TripleModel

SparqlModel keeps a stable SQLModel-style surface on a unified base class:

| SparqlModel (public) | TripleModel (implementation) |
|----------------------|-------------------------------|
| `SPARQLModel(TripleModel)`, `rdf_type`, `__prefixes__` | nested `class Rdf`, `rdf_config()` |
| `Field("schema:name")` | `rdf_field` / `Predicate` |
| `id: IRI` | `IriId` / explicit IRI id |
| `session.put` | `sync_to_graph` + SparqlModel cascade |
| `session.get`, `query` | `from_graph` + compiler + depth |
| `export_model` | `serialize` |

---

## Dependency pin

```text
# pyproject.toml (SparqlModel)
dependencies = [
    "triplemodel>=0.10.0,<2",
    "pyoxigraph>=0.5,<0.6",
]
```

Recommended by TripleModel ecosystem docs for API stability through 1.0.

**Optional SparqlModel extras:** `httpx`, `fastapi`  
**Optional TripleModel extras (not in SparqlModel core):** `shacl`, `sqlalchemy`, `berkeleydb`

---

## Integration milestones

| Milestone | SparqlModel | TripleModel usage |
|-----------|-------------|-------------------|
| **Done** | `triplemodel>=0.10` + pyoxigraph on PyPI install | Package available to all installs |
| **0.2** | `_triple.py` adapter (interim), contract tests | `sync_to_graph`, namespaces, nested embeds |
| **0.3** | Shipped — session I/O via interim adapter | `put`/`get` via `_triple.py` |
| **0.4** | **Option A** — `SPARQLModel(TripleModel)`; delete `_triple.py` | Direct `sync_to_graph` / `from_graph` on app instances |
| **0.5** | Pyoxigraph engine (`triplemodel.Store`, no core rdflib) | — |
| **0.6** | Async ORM (`AsyncSPARQLSession`, async stores, FastAPI) | — |
| **0.7** | Thin `serializers.py` only | All file `parse` / `serialize` upstream |
| **0.8** | Query lists (`offset`, `order_by`, `count`) | — |
| **0.9** | Session cache (`merge`, `refresh`, `expunge`) | — |
| **1.0** | Production HttpStore | Mirror sync, read/write URLs |
| **1.1** | Multi-valued / lang / polymorphic query | TripleModel mapping first |
| **1.2** | SHACL hook, bulk, ASK/CONSTRUCT | `triplemodel[shacl]` |
| **1.3** | Production GA (SPECS P0+P1) | — |
| **post-1.3** | Named graphs in apps if needed | Dataset APIs from TripleModel |

Track upstream: [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md) · **SM-6** (SparqlModel 0.4 unified model)

---

## Testing split

| Concern | Owner |
|---------|--------|
| Literals, parse round-trip, subject URI | TripleModel |
| `put`, orphan, cascade | SparqlModel |
| Compiler, nested filters | SparqlModel |
| Session CRUD | SparqlModel |
| Cross-package contract | CI: pinned `triplemodel` + SparqlModel `main` |

---

## Anti-patterns

- Adding `python_to_term` (or similar) only in SparqlModel `graph.py`
- Implementing Turtle/JSON-LD parsers only in SparqlModel
- Dynamic shadow `TripleModel` classes via `exec` (0.3 adapter — remove in 0.4)
- Putting `SPARQLSession` or the query compiler in TripleModel
- `triplemodel` importing `sparqlmodel`
- Treating SparqlModel as a second mapping library instead of an ORM on top of TripleModel

---

## Summary

| | TripleModel | SparqlModel |
|---|-------------|-------------|
| **Role** | Mapping engine | ORM |
| **Dependency** | Standalone | Requires TripleModel |
| **Killer API** | `sync_to_graph` / `from_graph` | `session.put` / `session.query().where()` |
| **Model type** | `TripleModel` | `SPARQLModel(TripleModel)` |

**New mapping work → TripleModel. New app persistence / SPARQL ergonomics → SparqlModel.**
