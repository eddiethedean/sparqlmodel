# SparqlModel Technical Specification

## Overview

SparqlModel is a SPARQL-native object graph mapper and typed persistence framework for RDF triple stores.

It provides:
- Pydantic-native semantic models
- SPARQL query generation
- RDF graph persistence
- JSON-LD serialization
- Graph hydration
- FastAPI interoperability

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

Features:
- automatic @context generation
- @id support
- @type support
- compact IRIs
- graph serialization

---

# RDF Support

Supported serializations:
- Turtle
- JSON-LD
- RDF/XML
- N-Triples

Implemented via RDFLib.

---

# FastAPI Integration

Optional FastAPI support includes:
- response classes
- content negotiation
- JSON-LD responses
- RDF responses

---

# Planned Optional Features

- SHACL generation
- OWL export
- Named graph support
- SPARQL endpoint federation
- Reasoning integration
- Neo4j adapters
- AI extraction pipelines

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
  model.py
  fields.py
  session.py
  query.py
  compiler.py
  hydration.py
  graph.py
  serializers.py
  fastapi/
  stores/
  integrations/
```

---

# Dependency Strategy

Core dependencies:
- pydantic
- rdflib
- httpx
- typing-extensions

Optional extras:
- fastapi
- pyld
- pyshacl
- pyoxigraph
- SPARQLWrapper

---

# Future Ecosystem Integration

SparqlModel should integrate cleanly with:
- semantic-sqlmodel
- FastAPI
- PydanticAI
- Instructor
- RDFLib
- graph databases
- AI extraction systems
