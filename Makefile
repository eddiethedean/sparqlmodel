.PHONY: ci docs fuseki-up fuseki-down release-check

# Start Fuseki for integration tests (matches CI service image)
fuseki-up:
	docker run -d --rm --name sparqlmodel-fuseki -p 3030:3030 \
		-e FUSEKI_DATASET_1=sparqlmodel_test \
		stain/jena-fuseki:5.1.0

fuseki-down:
	docker stop sparqlmodel-fuseki 2>/dev/null || true

# Pre-release gate: lint, types, full pytest (600+ tests incl. Fuseki integration), docs
release-check: ci docs

# Local CI (matches .github/workflows/ci.yml test job; requires Fuseki on :3030)
ci:
	ruff check src tests
	ruff format --check src tests
	ty check
	FUSEKI_BASE_URL=$${FUSEKI_BASE_URL:-http://127.0.0.1:3030} \
		pytest --cov=sparqlmodel --cov-fail-under=100 --cov-report=term-missing

# Sphinx HTML (matches .github/workflows/ci.yml docs job; -W = warnings are errors)
docs:
	$(MAKE) -C docs html SPHINXOPTS=-W
