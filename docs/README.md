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

Builds run with **warnings as errors** (`SPHINXOPTS=-W` in the Makefile).

## Read the Docs

- Config: [`.readthedocs.yaml`](../.readthedocs.yaml)
- Import repo: `https://github.com/eddiethedean/sqarqlmodel` (note spelling: **sqarqlmodel**)
- Default version: **latest** (tracks `main`)
- `fail_on_warning: true` — must match local `make html`

## Site structure

| Section | Sources |
|---------|---------|
| Get started | `installation.md`, `getting-started.md` |
| Guides | `guides/`, `ORM.md`, `PRODUCTION.md`, `ECOSYSTEM.md` |
| Reference | `SPECS.md`, `api/`, `glossary.md`, `troubleshooting.md` |
| Project | `ROADMAP.md`, `PLAN.md`, `changelog.md` |
