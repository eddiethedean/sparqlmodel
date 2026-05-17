# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-16

### Added

- `SPARQLModel` base class with Pydantic v2, `rdf_type`, `Field`, and `Relationship`
- `IRI` type with compact/absolute expansion via namespace prefixes
- `SPARQLSession` with `add`, `put`, `delete`, `get`, `query`, and `execute`
- In-memory `MemoryStore` backed by RDFLib
- Query builder with `.where()`, `.all()`, `.first()`, and `.limit()`
- SPARQL compiler for scalar equality and single-hop nested filters
- Graph hydration with configurable depth (0–2)
- RDF serializers (Turtle, N-Triples, RDF/XML, JSON-LD) and `model_dump_jsonld()`
- Test suite with pytest and CI (ruff, ty, coverage ≥85%)

[0.1.0]: https://github.com/odosmatthews/sparqlmodel/releases/tag/v0.1.0
