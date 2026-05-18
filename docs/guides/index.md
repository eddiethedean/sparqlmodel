# Guides

Task-oriented guides for building applications with SparqlModel. For normative API detail see {doc}`../SPECS`; for deployment see {doc}`../PRODUCTION`.

```{toctree}
:maxdepth: 1
:hidden:

sessions
queries
fastapi
```

| Guide | Description |
|-------|-------------|
| {doc}`sessions` | Lifecycle, flush queue, identity map, MemoryStore vs HttpStore |
| {doc}`queries` | Filters, boolean logic, multi-hop paths, limits, compiler behavior |
| {doc}`fastapi` | Per-request sessions, lifespan, content negotiation, testing |

## Related

- {doc}`../ORM` — full ORM guide (cascade, hydration, package choice)
- {doc}`../PRODUCTION` — operator guide (mirror model, threading, pagination roadmap)
- {doc}`../troubleshooting` — common errors and fixes
- {doc}`../api/index` — generated Python API reference
