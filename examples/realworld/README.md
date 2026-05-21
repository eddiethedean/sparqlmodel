# Real-world SparqlModel examples

Runnable examples that use **real vocabularies, public datasets, and typical integration problems**—not synthetic `http://example.org/` toys. They mirror the [TripleModel real-world suite](https://github.com/eddiethedean/triplemodel/tree/main/examples/realworld) but use **`SPARQLSession`**, the **query DSL**, and **`session.get`**.

Scripts use :meth:`sparqlmodel.session.SPARQLSession.from_rdf_file` with ``Path(__file__).parent / "data"`` — no extra helper modules in this folder.

| Script | Real-world problem | Data file |
|--------|-------------------|-----------|
| [`nobel_laureates.py`](nobel_laureates.py) | Cultural heritage / biographical **linked open data** | [`data/nobel_laureates_1901.ttl`](data/nobel_laureates_1901.ttl) |
| [`dcat_data_catalog.py`](dcat_data_catalog.py) | **Open data portal** metadata (DCAT) | [`data/dcat_nobel_catalog.ttl`](data/dcat_nobel_catalog.ttl) |
| [`wikidata_capitals.py`](wikidata_capitals.py) | **Knowledge-graph** facts (Wikidata) | [`data/wikidata_capitals.ttl`](data/wikidata_capitals.ttl) |
| [`schema_org_ngos.py`](schema_org_ngos.py) | **Nonprofit / transparency** (Schema.org) | [`data/schema_org_ngos.ttl`](data/schema_org_ngos.ttl) |

Provenance and licenses: [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Run (offline)

From the repository root:

```bash
pip install sparqlmodel
PYTHONPATH=src python examples/realworld/nobel_laureates.py
PYTHONPATH=src python examples/realworld/dcat_data_catalog.py
PYTHONPATH=src python examples/realworld/wikidata_capitals.py
PYTHONPATH=src python examples/realworld/schema_org_ngos.py
```

## Documentation

Walkthrough (full scripts embedded via `literalinclude`): [Real-world examples](https://sparqlmodel.readthedocs.io/en/latest/guides/realworld.html) on Read the Docs.

## Live endpoints (optional)

Bundled `.ttl` files keep CI and tutorials offline. Production pipelines often use `HttpStore` against:

- Nobel Prize SPARQL: `http://data.nobelprize.org/sparql`
- Wikidata Query Service: `https://query.wikidata.org/`

See the [production guide](../../docs/PRODUCTION.md) for remote store semantics.
