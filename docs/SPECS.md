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

---

# RDF Persistence

## Insert

Objects serialize into RDF triples and generate INSERT DATA queries.

## Update

Updates use DELETE/INSERT SPARQL operations.

## Delete

Deletes remove owned triples for model predicates.

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
