# Minimal Makefile for Sphinx documentation
#
# Usage:
#   make html     # build HTML under docs/_build/html
#   make clean

SPHINXOPTS    ?= -W
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build
# Intersphinx imports requests before conf.py runs; do not treat that as a failed build.
PYTHONWARNINGS ?= ignore::Warning

.PHONY: help html clean

help:
	@PYTHONWARNINGS="$(PYTHONWARNINGS)" $(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

html:
	@PYTHONWARNINGS="$(PYTHONWARNINGS)" $(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

clean:
	@PYTHONWARNINGS="$(PYTHONWARNINGS)" $(SPHINXBUILD) -M clean "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)
