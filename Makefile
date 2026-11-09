# Uses the repo-local virtualenv when present (.venv/bin on Linux/macOS, .venv/Scripts on Windows).
PY ?= $(firstword $(wildcard .venv/bin/python .venv/Scripts/python.exe) python)
SPLIT ?= dev

# Packages held to mypy --strict (FRD section 0). Only those that exist are checked.
STRICT_PACKAGES := $(wildcard backend/app/vision backend/app/coaching eval perf tools)

.PHONY: golden-report readme-check check lint lint-backend lint-frontend typecheck typecheck-backend typecheck-frontend test test-backend test-frontend eval golden-update bench

check: lint typecheck test

lint: lint-backend lint-frontend

lint-backend: readme-check
	$(PY) -m ruff check backend eval tools tests
	$(PY) -m ruff format --check backend eval tools tests

# The README's measured table must match the committed report it is generated from.
readme-check:
	$(PY) -m tools.golden_report check

lint-frontend:
	cd frontend && npm run lint

typecheck: typecheck-backend typecheck-frontend

typecheck-backend:
ifneq ($(strip $(STRICT_PACKAGES)),)
	$(PY) -m mypy --strict $(STRICT_PACKAGES)
else
	@echo "mypy: no strict packages yet (backend/app/vision, backend/app/coaching, eval, perf)"
endif

typecheck-frontend:
	cd frontend && npx tsc --noEmit

test: test-backend test-frontend

test-backend:
	$(PY) -m pytest --cov=backend/app --cov=eval --cov=tools --cov-report=term-missing:skip-covered

test-frontend:
	cd frontend && npx vitest run

eval:
	@echo "make eval SPLIT=$(SPLIT): not implemented until EVAL-04" && exit 1

golden-update:
	PYTHONPATH=backend $(PY) tests/golden/golden.py

# Re-measure the pipeline on the golden clip (downloads the pose model on first run),
# then regenerate the README table from the report.
golden-report:
	PYTHONPATH=backend $(PY) -m tools.golden_report run
	$(PY) -m tools.golden_report readme

bench:
	@echo "make bench: not implemented until PERF-01" && exit 1
