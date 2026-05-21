# Data sources for real-world examples

Bundled `.ttl` files are **small excerpts** for offline demos. Provenance and licenses:

| File | Problem domain | Source | License / terms |
|------|----------------|--------|-----------------|
| `nobel_laureates_1901.ttl` | Biographical prizes & laureates | Structure and names from [Nobel Prize Linked Data](https://www.nobelprize.org/about/linked-data-examples/) (`data.nobelprize.org`, `nobel:` vocabulary). 1901 laureate names match public SPARQL examples on that page. | Nobel Prize Outreach — follow [nobelprize.org](https://www.nobelprize.org) terms for production use of their live endpoint. |
| `dcat_nobel_catalog.ttl` | Open data portal catalog (DCAT) | DCAT-AP shape inspired by the EU [DCAT-AP sample catalog](https://github.com/SEMICeu/dcat-ap_validator) describing the Nobel Media dataset; distribution points at the real SPARQL URL. | Sample metadata is documentary; DCAT is W3C. |
| `wikidata_capitals.ttl` | Knowledge graph / geographic facts | Facts for Q90 (Paris) and Q84 (London) from [Wikidata](https://www.wikidata.org/) via [Wikidata Query Service](https://query.wikidata.org/) (May 2026). Populations and country labels change over time. | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| `schema_org_ngos.ttl` | NGO / nonprofit registry (Schema.org) | Illustrative `schema:NGO` resources using Schema.org property URIs; organization names are public facts, URIs are under `https://example.org/org/`. | Schema.org terms; example URIs are not official entity IDs. |

## Refreshing Wikidata excerpt

```bash
PYTHONPATH=src python examples/realworld/refresh_wikidata_capitals.py
```

Re-runs the documented SPARQL query and overwrites `data/wikidata_capitals.ttl` (requires network).
