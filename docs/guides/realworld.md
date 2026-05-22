# Real-world examples

These examples use **real vocabularies, public datasets, and typical integration problems**—not synthetic `http://example.org/` toys. They are adapted from the [TripleModel real-world suite](https://github.com/eddiethedean/triplemodel/tree/main/examples/realworld) to show **SparqlModel** patterns: load bundled Turtle into a `MemoryStore`, then use `SPARQLSession` for **queries**, **`get`**, and **`execute`**.

Source tree: [`examples/realworld/`](https://github.com/eddiethedean/sparqlmodel/tree/main/examples/realworld) (scripts below are included from that directory at doc build time).

## Overview

| Example | Script | Data |
|---------|--------|------|
| [Nobel laureates](#nobel-prize-linked-data-1901) | `nobel_laureates.py` | `data/nobel_laureates_1901.ttl` |
| [DCAT catalog](#dcat-open-data-catalog) | `dcat_data_catalog.py` | `data/dcat_nobel_catalog.ttl` |
| [Wikidata capitals](#wikidata-capital-cities) | `wikidata_capitals.py` | `data/wikidata_capitals.ttl` |
| [Schema.org NGOs](#schemaorg-ngo-registry) | `schema_org_ngos.py` | `data/schema_org_ngos.ttl` |

Provenance and licenses: [DATA_SOURCES.md](https://github.com/eddiethedean/sparqlmodel/blob/main/examples/realworld/DATA_SOURCES.md).

## Run locally

```bash
pip install sparqlmodel
```

From the SparqlModel repository root:

```bash
PYTHONPATH=src python examples/realworld/nobel_laureates.py
PYTHONPATH=src python examples/realworld/dcat_data_catalog.py
PYTHONPATH=src python examples/realworld/wikidata_capitals.py
PYTHONPATH=src python examples/realworld/schema_org_ngos.py
```

## Load bundled Turtle

Each script opens data with the public API :meth:`~sparqlmodel.session.SPARQLSession.from_rdf_file` (in-memory :class:`~sparqlmodel.stores.memory.MemoryStore`):

```python
from pathlib import Path

from sparqlmodel import SPARQLSession

DATA_DIR = Path(__file__).resolve().parent / "data"

with SPARQLSession.from_rdf_file(
    DATA_DIR / "nobel_laureates_1901.ttl",
    prefixes=PREFIXES,
) as session:
    ...
```

Pass a :class:`~pathlib.Path` (or path string), not file **contents**—TripleModel treats long strings as path-like sources.

For production, swap the default in-memory store for `HttpStore` (see {doc}`../PRODUCTION`) and keep the same session API.

---

## Nobel Prize linked data (1901)

**Problem:** Cultural heritage and science datasets publish stable URIs and a shared ontology; you need typed models and filters over an existing graph.

**Data:** [`nobel_laureates_1901.ttl`](../../examples/realworld/data/nobel_laureates_1901.ttl) — excerpt aligned with [Nobel Prize linked data examples](https://www.nobelprize.org/about/linked-data-examples/).

```{literalinclude} ../../examples/realworld/nobel_laureates.py
:language: python
:end-before: if __name__
```

```{note}
`rdfs:label` values in the bundle include language tags (`@en`). Equality filters on `name` must match the stored literal form; this example filters on `gender` and uses `session.get` by IRI for round-trip checks.
```

---

## DCAT open data catalog

**Problem:** Governments and EU portals publish [DCAT](https://www.w3.org/TR/vocab-dcat/) metadata so users can discover datasets and SPARQL endpoints before downloading data.

**Data:** [`dcat_nobel_catalog.ttl`](../../examples/realworld/data/dcat_nobel_catalog.ttl).

Use `IRI` for object fields that are resources in the graph (e.g. `dcat:accessURL`). Multi-valued `dcat:keyword` in the bundle hydrates as the **first** value only (see {doc}`../troubleshooting`).

```{literalinclude} ../../examples/realworld/dcat_data_catalog.py
:language: python
:end-before: if __name__
```

---

## Wikidata capital cities

**Problem:** Wikidata (and similar KGs) often assert types with `wdt:P31` rather than `rdf:type`, so the default `session.query` type pattern (`?s a <Class>`) may not match.

**Data:** [`wikidata_capitals.ttl`](../../examples/realworld/data/wikidata_capitals.ttl) — Paris and London with population and country (CC0).

**Approach:** `session.execute` with Wikidata property patterns, then `from_graph(..., validate_type=False)`. `session.execute` on `MemoryStore` supports **SELECT** (not `ASK`).

```{literalinclude} ../../examples/realworld/wikidata_capitals.py
:language: python
:end-before: if __name__
```

---

## Schema.org NGO registry

**Problem:** Transparency and search pipelines expose `schema:NGO` records; you want Pydantic validation and session APIs over that graph.

**Data:** [`schema_org_ngos.ttl`](../../examples/realworld/data/schema_org_ngos.ttl).

```{literalinclude} ../../examples/realworld/schema_org_ngos.py
:language: python
:end-before: if __name__
```

---

## TripleModel vs SparqlModel in these examples

| Task | TripleModel (upstream) | SparqlModel (here) |
|------|------------------------|-------------------|
| Parse bundled TTL | `load_models`, `parse_file` | `load_graph` + `MemoryStore` + `SPARQLSession` |
| Filter rows | Python list comprehensions | `session.query(Model).where(...)` |
| Load one resource | `Model.from_graph` | `session.get(Model, IRI(...), depth=...)` |
| Wikidata P31 typing | `instance_of` / `validate_type=False` | `execute` + `from_graph(..., validate_type=False)` |
| Remote SPARQL | `load_sparql`, `construct_from_sparql` | `HttpStore` + same session (see {doc}`../PRODUCTION`) |

Mapping details (literals, `serialize`, `parse`) remain in **TripleModel**; SparqlModel adds the session and query layer on top of `SPARQLModel(TripleModel)`.

## What's next

- {doc}`sessions` — flush queue, identity map, stores
- {doc}`queries` — boolean filters, multi-hop paths, raw SPARQL
- {doc}`../PRODUCTION` — `HttpStore` and Nobel / Wikidata live endpoints
- {doc}`../ECOSYSTEM` — package boundaries with TripleModel
