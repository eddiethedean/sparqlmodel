# SparqlModel (ORM) + TripleModel (mapping engine)

SparqlModel is a **SPARQL ORM**. TripleModel is its **required mapping engine** (`triplemodel>=0.9.0,<2`). This document defines boundaries for contributors and maintainers of both packages.

**Users:** start with [ORM.md](ORM.md) and the [README](https://github.com/eddiethedean/sqarqlmodel/blob/main/README.md).

TripleModel’s mirror of this contract:  
[github.com/eddiethedean/triplemodel/docs/ECOSYSTEM.md](https://github.com/eddiethedean/triplemodel/blob/main/docs/ECOSYSTEM.md)

Also: [PLAN.md](PLAN.md) · [ROADMAP.md](ROADMAP.md) · [SPECS.md](SPECS.md) · [PRODUCTION.md](PRODUCTION.md)

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

```text
┌──────────────────────────────────────────┐
│  SparqlModel                             │
│  Session · Query · Compiler · Stores     │
└────────────────────┬─────────────────────┘
                     │  triplemodel>=0.9.0,<2  (required)
┌────────────────────▼─────────────────────┐
│  TripleModel                             │
│  sync_to_graph · from_graph · parse · …  │
└────────────────────┬─────────────────────┘
                     │
┌────────────────────▼─────────────────────┐
│  rdflib · pydantic                       │
└──────────────────────────────────────────┘
```

### Rules

1. SparqlModel **must** depend on `triplemodel>=0.9`; **must not** grow parallel mapping implementations.
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
| FastAPI (roadmap) | optional extra |

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

SparqlModel **calls** these APIs as integration replaces interim code.

```python
# TripleModel — no session required
person = Person(slug="alice", name="Alice")
g = person.to_graph()
sync_to_graph(person, g, mode="replace")
restored = Person.from_graph(g, person.subject_uri())
```

---

## Where to implement a change

| Symptom | Repo | SparqlModel module (until wired) |
|---------|------|--------------------------------|
| Wrong XSD / datatype | **TripleModel** | stop fixing in `graph.py` |
| Subject IRI safety | **TripleModel** | — |
| Stale literal after `put` | **TripleModel** `sync_to_graph` + **SparqlModel** cascade | `session.py`, `graph.py` |
| Orphan embedded resource | **SparqlModel** | `cascade_subjects_for_removal` |
| `!=` / nested filter | **SparqlModel** | `compiler.py` |
| Multi-valued round-trip | **TripleModel** (target **0.8**) | `hydration.py` + query compiler consume |
| Language-tagged literals | **TripleModel** (target **0.8**) | `Field` / adapter; not SparqlModel-only |
| New RDF format | **TripleModel** | thin wrapper in `serializers.py` |
| Remote Fuseki | **SparqlModel** | `stores/` |
| SHACL validation | **TripleModel** | optional `put` hook |

### Heuristic

If the fix helps code that **never** uses `SPARQLSession`, it belongs in **TripleModel**.

---

## Interim code (retiring)

SparqlModel **depends on TripleModel** but **0.1.x** still ships duplicate logic:

| Module | Status | Action |
|--------|--------|--------|
| `graph.py` | Cascade / orphan policy | **Keep** orchestration; mapping in `_triple.py` (0.3.0) |
| `fields.py` | Interim predicate metadata | Adapter to `rdf_field` / `Predicate` |
| `serializers.py` | Interim formats | Replace with TripleModel `parse` / `serialize` |
| `hydration.py` | Depth walker | Keep depth; load via TripleModel |

**Do not** add new parsers, datatype tables, or term converters to SparqlModel.

---

## Public ORM API vs TripleModel internals

SparqlModel keeps a stable SQLModel-style surface:

| SparqlModel (public) | TripleModel (internal target) |
|----------------------|-------------------------------|
| `SPARQLModel`, `rdf_type`, `__prefixes__` | `TripleModel`, `class Rdf`, `rdf_config()` |
| `Field("schema:name")` | `rdf_field` / `Predicate` |
| `id: IRI` | explicit IRI or `id_field` + `namespace` |
| `session.put` | `sync_to_graph` + SparqlModel cascade |
| `session.get`, `query` | `from_graph` + compiler + depth |
| `export_model` | `serialize` |

---

## Dependency pin

```text
# pyproject.toml (SparqlModel)
dependencies = [
    "triplemodel>=0.9.0,<2",
]
```

Recommended by TripleModel ecosystem docs for API stability through 1.0.

**Optional SparqlModel extras:** `httpx`, `fastapi`  
**Optional TripleModel extras (not in SparqlModel core):** `shacl`, `sqlalchemy`, `berkeleydb`

---

## Integration milestones

| Milestone | SparqlModel | TripleModel usage |
|-----------|-------------|-------------------|
| **Done** | `triplemodel>=0.9` on PyPI install | Package available to all installs |
| **0.2** | `_triple.py` adapter, contract tests | `sync_to_graph`, namespaces, nested embeds |
| **0.3** | Shipped — interim convert removed from `graph.py` | `put`/`get` wired to `_triple.py` |
| **0.4** | Delete interim `serializers.py` | `parse` / `serialize` only upstream |
| **0.5+** | Named graphs in apps if needed | Dataset APIs from TripleModel |

Track upstream: [TripleModel ROADMAP](https://github.com/eddiethedean/triplemodel/blob/main/ROADMAP.md)

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

**New mapping work → TripleModel. New app persistence / SPARQL ergonomics → SparqlModel.**
