# SparqlModel documentation

**The SQLModel of SPARQL** — version **{{ version }}**

SparqlModel is a session-first ORM for RDF triple stores: **Pydantic v2** `SPARQLModel` classes, `SPARQLSession` as the unit of work, and Python filters that compile to SPARQL. Run on in-memory graphs or remote SPARQL 1.1 endpoints.

Mapping (literals, terms, file I/O) is provided by the required dependency [TripleModel](https://github.com/eddiethedean/triplemodel) — also Pydantic-based.

## Start here

| | |
|---|---|
| {doc}`installation` | Python versions, extras (`http`, `fastapi`), dev setup |
| {doc}`getting-started` | First models, session, and query in minutes |
| {doc}`guides/index` | Pydantic models, sessions, query DSL, FastAPI — task-oriented how-tos |

## By role

| You are… | Start with |
|----------|------------|
| Application developer | {doc}`getting-started` → {doc}`guides/index` → {doc}`ORM` |
| API / platform engineer | {doc}`guides/fastapi` → {doc}`PRODUCTION` |
| Contributor / reviewer | {doc}`SPECS` → {doc}`ECOSYSTEM` → {doc}`api/index` |
| Operator | {doc}`PRODUCTION` → {doc}`troubleshooting` |

## Feature overview

| Area | Capabilities ({{ version }}) |
|------|------------------------------|
| Pydantic | `BaseModel` subclasses; validation on construct, `put`, and `get`; `Field` constraints; JSON Schema for APIs |
| Models | `SPARQLModel`, `Field`, `Relationship`, `IRI`, `rdf_type`, RDF predicates |
| Session | `add`, `put`, `delete`, `get`, identity map, flush queue |
| Queries | `==`, `!=`, `&`, `\|`, ordering, `in_`, multi-hop paths, `limit` |
| Stores | `MemoryStore`, `HttpStore` (mirror documented) |
| FastAPI | `SessionDep`, `http_store_lifespan`, Turtle / JSON-LD responses |

```{tip}
Production checklist and 0.3–1.0 milestones: {doc}`SPECS` and {doc}`ROADMAP`.
```

## External links

- [PyPI package](https://pypi.org/project/sparqlmodel/)
- [GitHub repository](https://github.com/eddiethedean/sqarqlmodel)
- [Issue tracker](https://github.com/eddiethedean/sqarqlmodel/issues)
- [TripleModel docs](https://triplemodel.readthedocs.io/)

```{toctree}
:maxdepth: 2
:caption: Get started

installation
getting-started
```

```{toctree}
:maxdepth: 2
:caption: Guides

guides/index
ORM
PRODUCTION
ECOSYSTEM
```

```{toctree}
:maxdepth: 2
:caption: Reference

SPECS
api/index
glossary
troubleshooting
```

```{toctree}
:maxdepth: 1
:caption: Project

ROADMAP
PLAN
changelog
README
```
