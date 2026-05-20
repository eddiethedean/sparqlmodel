# Installation

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10, 3.11, 3.12, or 3.13 |
| SparqlModel | {{ version }} (current release) |
| TripleModel | `>=0.10.0,<2` (installed automatically) |
| Pyoxigraph | `>=0.5,<0.6` (installed automatically) |

## PyPI

```bash
pip install sparqlmodel
```

Verify:

```bash
python -c "import sparqlmodel; print(sparqlmodel.__version__)"
```

## Optional extras

| Extra | Install | Provides |
|-------|---------|----------|
| *(core)* | `pip install sparqlmodel` | `MemoryStore`, `SPARQLSession`, query compiler |
| `http` | `pip install "sparqlmodel[http]"` | `HttpStore`, `AsyncHttpStore` (requires `httpx`) |
| `fastapi` | `pip install "sparqlmodel[fastapi]"` | `SessionDep`, `AsyncSessionDep`, lifespan helpers, RDF responses |
| Combined | `pip install "sparqlmodel[http,fastapi]"` | Remote store + FastAPI integration |

```{note}
`fastapi` extra includes `httpx` because `HttpStore` and lifespan helpers depend on it.
```

## Development install

From a clone of [sqarqlmodel](https://github.com/eddiethedean/sqarqlmodel):

```bash
git clone https://github.com/eddiethedean/sqarqlmodel.git
cd sqarqlmodel
pip install -e ".[dev,http,fastapi,docs]"
pytest
```

If you see many `PytestRemovedIn9Warning` messages about `ensure_greenlet_context`, uninstall the unrelated `pytest-green-light` plugin from your environment (this repo already disables it via `-p no:green-light` in `pyproject.toml`).

Build documentation locally:

```bash
cd docs && make html
# open _build/html/index.html
```

See {doc}`README` for Read the Docs and CI details.

## Version pinning

For reproducible deployments:

```text
sparqlmodel=={{ version }}
triplemodel>=0.10.0,<2
pyoxigraph>=0.5,<0.6
```

Track releases on [PyPI](https://pypi.org/project/sparqlmodel/#history) and the {doc}`changelog`.
