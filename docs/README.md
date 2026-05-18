# Building documentation locally

## Prerequisites

```bash
pip install -e "..[docs]"
```

## HTML build

```bash
cd docs
make html
open _build/html/index.html
```

Or without make:

```bash
sphinx-build -W -b html docs docs/_build/html
```

## Read the Docs

Configuration: [`.readthedocs.yaml`](../.readthedocs.yaml)

Import the project on [Read the Docs](https://readthedocs.org/) and point it at this repository. The default Sphinx config path `docs/conf.py` is detected automatically.

Suggested settings:

- **Documentation type:** Sphinx HTML
- **Python version:** 3.12
- **Canonical URL:** `https://sparqlmodel.readthedocs.io/`

After the first successful build, set the **Documentation** URL in `pyproject.toml` to your RTD site.
