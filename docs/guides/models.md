# Models and Pydantic validation

SparqlModel entities are **Pydantic v2 models** with RDF metadata. This guide covers validation on write and read, `Field` constraints, and how that relates to [TripleModel](https://github.com/eddiethedean/triplemodel) underneath.

For session and persistence semantics see {doc}`sessions`. For the full ORM picture see {doc}`../ORM`.

---

## Why Pydantic

If you use FastAPI or SQLModel, you already know the pattern: define a class with typed fields, let Pydantic validate input, and work with ordinary Python objects in application code.

SparqlModel applies that to RDF:

- Catch `name=123` or missing required fields **before** `session.put`.
- Catch graph data that does not match your annotations when hydrating from a store.
- Generate JSON Schema from models for OpenAPI when using {doc}`fastapi`.

TripleModel (required dependency) is also Pydantic-based. **`SPARQLModel` subclasses `TripleModel`** (Option A, **0.4+**) — one class for app code, mapping, and queries. You rarely import `triplemodel` in app code unless you need stateless file I/O without a session.

---

## Define a model

```python
from sparqlmodel import Field, IRI, Relationship, SPARQLModel

class Organization(SPARQLModel):
    rdf_type = "schema:Organization"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")

class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
    works_for: Organization | None = Relationship(
        "schema:worksFor", model=Organization
    )
```

| Piece | Role |
|-------|------|
| `rdf_type` | RDF class IRI (compact or absolute); maps to TripleModel `Rdf.type_uri` at class creation (**0.4+**) |
| `__prefixes__` | CURIE → namespace map for predicates and types |
| `Field("schema:…")` | Scalar mapped to a predicate (`rdf_field` sugar) |
| `Relationship(...)` | Link to another `SPARQLModel` or `IRI` |

`SPARQLModel` uses `model_config = ConfigDict(extra="forbid")`, so extra keys in input data are rejected.

---

## Validation on write

Validation runs when you construct an instance:

```python
Person(id=IRI("urn:p:1"), name="Ada")   # ok
Person(id=IRI("urn:p:2"), name=123)     # pydantic.ValidationError
```

When you `session.put(person)`, the session serializes an already-validated instance:

- **0.4+:** `sync_to_graph(person, …)` on the `SPARQLModel` instance (a `TripleModel`).
- **0.4.0+:** `session.put` → `rdf_bridge.model_to_graph` on `SPARQLModel` instances (subclass `TripleModel`).

---

## Validation on read

`session.get` and query hydration load from the store graph via TripleModel `from_graph`, then `SPARQLModel.model_validate` (with SparqlModel depth for relationships).

If stored triples do not match your field types (for example a literal where you declared `int`), hydration raises `HydrationError` wrapping Pydantic’s `ValidationError`.

Configuration mistakes (for example hydration cycles) raise `ConfigurationError` instead. See {doc}`../troubleshooting`.

TripleModel’s `from_graph(..., validate_type=True)` also checks that subjects have the expected `rdf:type` before scalars are applied.

---

## Pydantic `Field` kwargs

`sparqlmodel.Field` and `Relationship` forward extra keyword arguments to `pydantic.Field`:

```python
class Product(SPARQLModel):
    rdf_type = "schema:Product"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name", min_length=1, description="Display name")
    stock: int = Field("schema:inventoryLevel", ge=0)
```

Use standard Pydantic constraints on scalar fields. Relationship fields support the same kwargs where they apply to the declared annotation (for example optional defaults).

---

## What Pydantic does not cover (yet)

| Concern | Today | Planned |
|---------|-------|---------|
| App-level types and constraints | Pydantic on `SPARQLModel` | — |
| RDF type of subject on load | TripleModel `validate_type` | — |
| Multi-valued predicates (`list[...]`) | First value per predicate on load | **1.0** |
| Graph shape rules (cardinality, domains) | Not enforced | SHACL on `put` (**1.1**, TripleModel) |

Pydantic validates **Python values** against your model. It does not replace SHACL or OWL reasoning for graph-level rules.

---

## TripleModel integration (Option A)

**Target (0.4+):** `SPARQLModel` **is** a `TripleModel`. `Field` / `Relationship` build `rdf_field` / `Predicate` and nested `class Rdf` at class creation — no dynamic shadow classes.

1. **Write:** `session.put` → cascade policy → `sync_to_graph` on your instance.
2. **Read:** `from_graph` on your class → depth hydration → identity map.

**0.4.0+:** one model class; no `_triple.py` adapter.

Application code should stay on `SPARQLModel`, `Field`, and `Relationship`. For stateless file parse/serialize or ETL without a session, you may import TripleModel directly — see {doc}`../ORM`.

---

## Related

- {doc}`../getting-started` — install and first query
- {doc}`fastapi` — Pydantic models in HTTP handlers
- {doc}`../SPECS` — validation architecture (normative)
- [Pydantic documentation](https://docs.pydantic.dev/latest/)
