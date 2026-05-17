# SparqlModel Technical Specification

## Overview

SparqlModel is a SPARQL-native object graph mapper and typed persistence framework for RDF triple stores.

It provides:
- Pydantic-native semantic models (`SPARQLModel`)
- Stateful persistence and queries (`SPARQLSession`)
- SPARQL query generation from Python expressions
- Graph hydration with relationship depth
- Store backends (in-memory today; HTTP SPARQL on roadmap)
- FastAPI interoperability (optional extra)

**Ecosystem:** Stateless Pydantic ↔ RDF mapping, term conversion, and canonical file I/O live in **[RDFModel](https://github.com/eddiethedean/rdfmodel)** (`rdfmodel`). SparqlModel integrates as a dependency once RDFModel reaches the milestones in [ECOSYSTEM.md](ECOSYSTEM.md). Maintainer boundaries: [PLAN.md](PLAN.md), [ROADMAP.md](ROADMAP.md).

| Layer | SparqlModel | RDFModel |
|-------|-------------|----------|
| Session CRUD, cascade policy | Yes | No |
| Query DSL + SPARQL compiler | Yes | No |
| Stores (`MemoryStore`, `HttpStore`) | Yes | No |
| `to_graph` / `from_graph`, terms, parse/serialize | Delegate (0.3+) | Yes |

---

# Ecosystem boundaries

**Heuristic:** if the fix would help code that never creates a `SPARQLSession`, implement it in **RDFModel**.

| Concern | Owner |
|---------|--------|
| Wrong XSD type on export, subject IRI prefix safety | RDFModel |
| `put` orphan / cascade after relationship change | SparqlModel (`graph.py` policy + `session.py`) |
| Stale triples on sync (declared predicates) | RDFModel sync + SparqlModel `put` orchestration |
| `!=` / nested filter semantics | SparqlModel (`compiler.py`) |
| Multi-valued predicate round-trip | RDFModel first; hydration consumes result |
| Turtle/JSON-LD parsers and format registry | RDFModel (0.4+); SparqlModel thin wrapper |
| Remote Fuseki / SPARQL endpoint | SparqlModel (`stores/`) |
| SHACL validation on save | `rdfmodel[shacl]` optional; hook from `put` |

**Anti-patterns:** new datatype registries or parsers only in `graph.py`; session/query code in RDFModel; `rdfmodel` dependency before sync/remove and nested models exist; circular imports.

Public API convergence (user-facing names stable, implementation thins):

| SparqlModel (keep) | RDFModel (target implementation) |
|--------------------|----------------------------------|
| `SPARQLModel`, `rdf_type`, `__prefixes__` | `RdfModel`, `Rdf.type_uri`, `Rdf.prefixes` |
| `Field("schema:name")` | `rdf_field` / `Predicate` + CURIE expand |
| `id: IRI` | Explicit IRI or `id_field` + namespace |
| `session.put(model)` | RDFModel sync + SparqlModel cascade |
| `session.get`, `query` | RDFModel load + compiler/hydration |
| `export_model(...)` | `to_graph().serialize(...)` after 0.4 |

---

# Core Components

## SPARQLModel

Base model class for RDF-backed entities.

Example:

```python
class Person(SPARQLModel):
    rdf_type = "schema:Person"

    id: IRI
    name: str = Field("schema:name")
```

---

## SPARQLSession

Primary persistence and query interface.

Responsibilities:
- add
- put
- delete
- query
- SPARQL execution
- graph synchronization

Example:

```python
session = SPARQLSession(endpoint)

session.put(person)
```

---

# Query Builder

## Goals

Provide SQLModel-like querying for RDF graphs.

Example:

```python
session.query(Person).where(Person.name == "Odos").all()
```

Nested graph traversal:

```python
session.query(Person).where(
    Person.works_for.name == "Acme"
)
```

---

# SPARQL Compilation

Python expressions compile into SPARQL query fragments.

Example:

```python
Person.name == "Odos"
```

Compiles to:

```sparql
?person schema:name "Odos" .
```

Filter semantics:

- `==` — triple pattern match.
- `!=` — subject must have some value for the predicate that differs from the right-hand side (not SQL `NOT EXISTS` for absent values).
- `None` as a filter value raises `QueryError`.
- String literals are escaped via RDFLib term serialization.
- String literals with colons (e.g. `"12:30"`) are not treated as compact IRIs unless they match `prefix:local` form and the prefix is known.

---

# RDF Persistence

## Implementation (0.1.x)

Persistence uses **RDFLib graph add/remove** via `MemoryStore.update_graph`, not generated SPARQL Update strings. HTTP backends may use SPARQL Update in a future release.

Serialization and load paths are implemented in `graph.py` today. **0.3+** routes model ↔ triple conversion through RDFModel while **cascade/orphan policy** remains SparqlModel-owned (`cascade_subjects_for_removal`, `owned_triples_for_subjects`, `session.put`/`delete` orchestration).

## Insert (`add`)

Objects serialize to RDF triples and are added to the store. `add` does not remove existing triples for the same subject.

## Update (`put`)

`put` removes owned triples for the model, embedded nested objects, and orphaned composition targets, then writes the current serialization (see Ownership).

## Delete

`delete` removes owned triples for the model’s subject and cascaded embedded resources (see Ownership).

## Ownership

When a relationship field holds a nested `SPARQLModel`, `put` and `delete` treat it as **composition**:

- Embedded objects are serialized recursively.
- On `put`, owned triples are cleared for the root, all nested models in the in-memory tree, and embedded relationship targets previously linked in the graph but no longer present (orphan cleanup), including orphans detected on **any** embedded model in the tree (not only the root).
- On `delete`, owned triples are cleared for the root and embedded models in the in-memory tree.

When a relationship stores an **`IRI` reference only** (not an embedded model), the target resource is **not** cascade-deleted—only the link triple on the parent is removed.

If the same resource IRI is embedded from multiple parents, deleting one parent will remove that resource’s triples; use `IRI` references for shared entities.

Orphan detection compares **expanded** IRIs so compact model ids and absolute graph URIs match consistently.

---

# Known limitations (0.1.x)

| Area | Behavior |
|------|----------|
| **Multi-valued predicates** | Load and query use the first object per predicate; `add` can accumulate duplicates; compound `!=` on multiple values follows RDF existential semantics |
| **Extension triples** | `put`/`delete` only remove declared field predicates plus `rdf:type` |
| **Nested query filters** | Require `rdf:type` on relationship targets in the graph |
| **JSON-LD** | Custom `model_dump_jsonld` path vs RDFLib `export_model(..., "json-ld")`; bare `@id` nodes deserialize to `IRI` when the field allows it |
| **Export** | `ensure_id()` may assign ids when serializing models with `id=None` |

---

# Hydration System

SPARQL query results hydrate into typed Python models.

Hydration modes:
- scalar-only
- eager relationship loading
- graph-depth traversal

Example:

```python
session.get(Person, iri, depth=2)
```

---

# Relationship System

Relationships map RDF predicates to typed Python references.

Example:

```python
works_for: Organization | None = Relationship(
    "schema:worksFor"
)
```

---

# JSON-LD Support

**0.1.x:** Custom `model_dump_jsonld` / `model_validate_jsonld` plus RDFLib-based `export_model(..., "json-ld")` — behaviors differ (see Known limitations).

**0.4+ (planned):** Prefer RDFModel parse/serialize and graph helpers; SparqlModel keeps session-scoped export convenience wrappers only.

---

# RDF Support

**0.1.x:** Turtle, JSON-LD, RDF/XML, N-Triples via `serializers.py` (RDFLib).

**0.4+ (planned):** Delegate to RDFModel `parse` / `serialize`; do not add new format parsers in SparqlModel core.

---

# FastAPI Integration

Optional FastAPI support includes:
- response classes
- content negotiation
- JSON-LD responses
- RDF responses

---

# Planned Optional Features

| Feature | Primary owner |
|---------|----------------|
| SHACL shapes generation | RDFModel |
| SHACL validate on `put` | SparqlModel hook + `rdfmodel[shacl]` |
| Named graphs / Dataset | RDFModel 0.5; SparqlModel field metadata if needed |
| OWL export | Low priority; either package |
| SPARQL endpoint federation | SparqlModel |
| Reasoning hooks | Optional; not a core reasoner |
| Neo4j / Oxigraph store experiments | SparqlModel `stores/` |
| AI extraction pipelines | Ecosystem; JSON-LD via RDFModel |

---

# Persistence Philosophy

SparqlModel is graph-native.

Unlike SQLModel:
- relationships are first-class
- graph traversal is native
- IRIs are primary identity objects
- schemas are flexible

---

# Design Principles

- Pythonic APIs first
- Typed models over raw triples
- Explicit behavior over magic
- Pydantic-native architecture
- FastAPI compatibility
- RDF interoperability
- Operational simplicity

---

# Recommended Package Structure

```text
sparqlmodel/
  model.py          # SPARQLModel; adapter to RdfModel (0.3+)
  fields.py         # Field/Relationship UX; metadata → RDFModel
  _rdf.py           # adapter (0.2 dev, 0.3 required)
  session.py
  query.py
  compiler.py       # SparqlModel-only
  hydration.py      # depth + relationships; load via RDFModel
  graph.py          # cascade/orphan policy; thin sync wrapper (0.3+)
  serializers.py    # delegate to RDFModel (0.4+)
  fastapi/
  stores/
```

---

# Dependency Strategy

**0.1.x (current):**
- `pydantic`, `rdflib`, `typing-extensions`

**0.2:** optional `httpx` for `HttpStore` (extra or dev); RDFModel pinned locally for adapter work only.

**0.3+:**
- `rdfmodel` required (minimum version per [ECOSYSTEM.md](ECOSYSTEM.md#rdfmodel-releases-to-wait-for-dependency-gate))

**SparqlModel optional extras:**
- `fastapi` — `sparqlmodel[fastapi]`
- `httpx` — `sparqlmodel[http]` or bundled with store extra

**Do not add to SparqlModel core:**
- `pyshacl` — use `rdfmodel[shacl]` for validation hooks
- SQLAlchemy / BerkeleyDB — RDFModel store extras if needed

**Testing:** SparqlModel owns session, cascade, compiler tests; RDFModel owns term/parse round-trip; optional CI job installs released `rdfmodel` against SparqlModel main.

---

# Future Ecosystem Integration

| Project | Relationship |
|---------|----------------|
| **RDFModel** | Required mapping layer (0.3+); primary upstream |
| **semantic-sqlmodel** | Optional SparqlModel backend |
| **FastAPI** | Optional extra |
| **PydanticAI / Instructor** | Consumers of session + models |
| **RDFLib** | Via RDFModel and stores |

See [ECOSYSTEM.md](ECOSYSTEM.md) for the full two-package maintainer guide.
