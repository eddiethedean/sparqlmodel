# Guides

Task-oriented guides for building applications with SparqlModel. For normative API detail see {doc}`../SPECS`; for deployment see {doc}`../PRODUCTION`.

```{toctree}
:maxdepth: 1
:hidden:

models
sessions
queries
fastapi
```

Real-world examples (Nobel, DCAT, Wikidata, Schema.org) live on {doc}`realworld` and in the site sidebar under **Guides**.

| Guide | Description |
|-------|-------------|
| {doc}`models` | Pydantic validation, `Field` constraints, read/write validation stack |
| {doc}`sessions` | Lifecycle, flush queue, identity map, MemoryStore vs HttpStore |
| {doc}`queries` | Filters, boolean logic, multi-hop paths, limits, compiler behavior |
| {doc}`fastapi` | Per-request sessions, lifespan, content negotiation, testing |
| {doc}`realworld` | Nobel, DCAT, Wikidata, Schema.org — bundled public datasets with `SPARQLSession` |

## Related

- {doc}`../ORM` — full ORM guide (cascade, hydration, package choice)
- {doc}`../PRODUCTION` — operator guide (mirror model, threading, pagination roadmap)
- {doc}`../troubleshooting` — common errors and fixes
- {doc}`../api/index` — generated Python API reference
