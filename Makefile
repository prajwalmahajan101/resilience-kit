# Developer shortcuts for resilience-kit. Every target mirrors a CI job so
# `make gate` locally is the same surface CI enforces on a PR. Uses `uv`.

.DEFAULT_GOAL := help
.PHONY: help install lint format types imports test cov audit lock-check dead-symbols gate clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Sync all extras + dev group and install the test fixture
	uv sync --all-extras --group dev
	uv pip install -e tests/fixtures/fake_third_party

lint: ## ruff check
	uv run ruff check .

format: ## ruff format (in place)
	uv run ruff format .

types: ## mypy --strict on src
	uv run mypy --strict src

imports: ## import-linter (layered architecture, LLD §1)
	uv run lint-imports

test: ## Unit + contract suite (no integration)
	uv run pytest tests -q -m "not integration"

cov: ## Unit + contract with the coverage gate (matches CI)
	uv run pytest tests -q -m "not integration" \
		--cov=resilience_kit --cov-report=term --cov-fail-under=68

audit: ## pip-audit (OSV) on the locked runtime deps
	uv export --frozen --all-extras --no-dev --no-emit-project \
		--format requirements-txt -o requirements-audit.txt
	uvx pip-audit@2.7.3 -r requirements-audit.txt

lock-check: ## Fail if uv.lock drifts from pyproject.toml
	uv lock --check

dead-symbols: ## Flag public symbols with no caller and no __all__ re-export
	uv run --no-project python scripts/check_dead_symbols.py

gate: lint types imports cov audit lock-check dead-symbols ## Run the full local CI gate
	@echo "All gate checks passed."

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build coverage.xml requirements-audit.txt
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
