# Building documentation locally

## Prerequisites

```bash
pip install -e "..[docs]"
```

## HTML build

From the repository root (recommended — matches CI):

```bash
pip install -e ".[docs]"
make docs
open docs/_build/html/index.html
```

Or from this directory:

```bash
pip install -e "..[docs]"
make html
open _build/html/index.html
```

Builds run with **warnings as errors** (`SPHINXOPTS=-W` in `docs/Makefile`). A clean log should show no `WARNING:` lines from Sphinx; use `make docs` from the repo root (not bare `sphinx-build`) so `PYTHONWARNINGS` filters third-party import noise from intersphinx.

## Read the Docs

- Config: [`.readthedocs.yaml`](../.readthedocs.yaml)
- Import repo: `https://github.com/eddiethedean/sparqlmodel`
- Default version: **latest** (tracks `main`)
- `fail_on_warning: true` — must match local `make html`

## Site structure

| Section | Sources |
|---------|---------|
| Get started | `installation.md`, `getting-started.md` |
| Guides | `guides/`, `ORM.md`, `PRODUCTION.md`, `ECOSYSTEM.md` |
| Reference | `SPECS.md`, `api/`, `glossary.md`, `troubleshooting.md` |
| Project | `ROADMAP.md`, `PLAN.md`, `changelog.md` |
