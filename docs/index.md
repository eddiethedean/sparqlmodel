# SparqlModel documentation

**The SQLModel of SPARQL** — typed RDF models, a persistent session, and Python filters that compile to SPARQL.

SparqlModel is a session-first ORM for building applications on RDF triple stores. Define `SPARQLModel` classes, open a `SPARQLSession`, and use `put`, `get`, nested relationships, and a query builder that compiles to SPARQL — on in-memory graphs or remote SPARQL 1.1 endpoints.

Mapping (literals, terms, file I/O) is provided by the required dependency [TripleModel](https://github.com/eddiethedean/triplemodel).

```{toctree}
:maxdepth: 2
:caption: Get started

getting-started
```

```{toctree}
:maxdepth: 2
:caption: Guides

ORM
PRODUCTION
ECOSYSTEM
```

```{toctree}
:maxdepth: 2
:caption: Reference

SPECS
api/index
```

```{toctree}
:maxdepth: 1
:caption: Project

ROADMAP
PLAN
changelog
README
```

## Quick links

- [PyPI](https://pypi.org/project/sparqlmodel/)
- [GitHub](https://github.com/eddiethedean/sqarqlmodel)
- [Issue tracker](https://github.com/eddiethedean/sqarqlmodel/issues)
