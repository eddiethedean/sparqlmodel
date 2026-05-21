.PHONY: ci docs

# Local CI (matches .github/workflows/ci.yml test job)
ci:
	ruff check src tests
	ruff format --check src tests
	ty check
	pytest --cov=sparqlmodel --cov-fail-under=100 --cov-report=term-missing

# Sphinx HTML (matches .github/workflows/ci.yml docs job; -W = warnings are errors)
docs:
	$(MAKE) -C docs html SPHINXOPTS=-W
