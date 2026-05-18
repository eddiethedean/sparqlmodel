# Glossary

| Term | Definition |
|------|------------|
| **SPARQLModel** | Pydantic-based entity class with `rdf_type`, `Field`, and `Relationship` metadata. |
| **SPARQLSession** | Unit of work over a `Store`; entry point for `put`, `get`, `query`. |
| **Store** | Backend abstraction (`MemoryStore`, `HttpStore`) holding or proxying an RDF graph. |
| **Composition** | Nested `SPARQLModel` owned by a root; cascade delete and orphan cleanup on `put`. |
| **Reference** | `IRI` or `Relationship(cascade=False)`; root does not own target triples. |
| **Identity map** | Session cache returning the same Python instance for an IRI at `depth=0`. |
| **Flush queue** | Pending `put(..., flush=False)` writes applied on `flush()` or context exit. |
| **Hydration** | Loading fields and relationships from the graph into model instances (`depth` 0–2). |
| **Mirror** | Local `rdflib` graph inside `HttpStore` used for `get` and cascade. |
| **TripleModel** | Required mapping library (`triplemodel`); literals, terms, file parse/serialize. |
| **Orphan cleanup** | Removing stale owned triples when relationships or values change on `put`. |

See also {doc}`ECOSYSTEM` for package boundaries.
