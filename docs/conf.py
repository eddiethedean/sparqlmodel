"""Sphinx configuration for SparqlModel documentation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Applied before intersphinx imports requests (RTD/CI do not use docs/Makefile).
os.environ.setdefault("PYTHONWARNINGS", "ignore::Warning")

# -- Path setup ----------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# -- Project information -------------------------------------------------------

project = "SparqlModel"
author = "SparqlModel Contributors"
copyright = "2026, SparqlModel Contributors"

try:
    from sparqlmodel import __version__ as release
except ImportError:  # pragma: no cover - docs build without install
    release = "0.9.1"

version = release

# -- General configuration -----------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

root_doc = "index"

# MyST
myst_heading_anchors = 4
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "substitution",
    "tasklist",
]
myst_substitutions = {
    "version": release,
    "pypi": "https://pypi.org/project/sparqlmodel/",
    "github": "https://github.com/eddiethedean/sqarqlmodel",
    "rtd": "https://sparqlmodel.readthedocs.io/en/latest/",
}

# Copy button
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_python = ("python", "pycon", "bash", "shell", "console")

# Autodoc
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented_params"
autosummary_generate = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_param = True

# Intersphinx (use canonical inventory URLs to avoid redirect noise in the build log).
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://pydantic.dev/docs/validation/latest/", None),
    "fastapi": ("https://fastapi.tiangolo.com/", None),
    "starlette": ("https://www.starlette.io/", None),
}

# CI and Read the Docs pass sphinx-build -W; suppress known-benign Sphinx warnings.
suppress_warnings = [
    "toc.not_included",
    "toc.no_title",
    "toc.excluded",
    "app.add_directive",
    "app.add_node",
    "app.add_role",
    "app.add_generic_role",
    "app.add_crossref_type",
    "ref.python",
]

# Fail on broken cross-refs (triplemodel has no published intersphinx inventory).
nitpicky = True
nitpick_ignore = [
    ("py:class", "triplemodel.*"),
    ("py:class", "triplemodel.store.graph.RdfGraph"),
    ("py:class", "triplemodel.Store"),
    ("py:class", "triplemodel.model.TripleModel"),
    ("py:class", "triplemodel.TripleModel"),
    ("py:class", "triplemodel.IriId"),
    ("py:class", "triplemodel.fields.metadata.IriId"),
    ("py:class", "IriId"),
    ("py:class", "ConfigDict"),
    ("py:class", "pydantic.ConfigDict"),
    ("py:class", "pydantic.fields.FieldInfo"),
    ("py:class", "FieldInfo"),
    ("py:class", "pydantic._internal._model_construction.ModelMetaclass"),
    ("py:class", "sparqlmodel.serializers.T"),
    ("py:class", "sparqlmodel.stores.base.Store"),
    ("py:class", "Response"),
    ("py:meth", "sparqlmodel.stores.http.HttpStore.close"),
    ("py:class", "typing_extensions.Self"),
    ("py:class", "Self"),
]

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_title = f"SparqlModel {release} documentation"
html_short_title = "SparqlModel"
html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
}
html_context = {
    "display_github": True,
    "github_user": "eddiethedean",
    "github_repo": "sqarqlmodel",
    "github_version": "main",
    "conf_py_path": "/docs/",
}
html_show_sphinx = True
html_show_copyright = True
