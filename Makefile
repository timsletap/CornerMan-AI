# Uses the repo-local virtualenv when present (.venv/bin on Linux/macOS, .venv/Scripts on Windows).
PY ?= $(firstword $(wildcard .venv/bin/python .venv/Scripts/python.exe) python)
SPLIT ?= dev

# Packages held to mypy --strict (FRD section 0). Only those that exist are checked.
STRICT_PACKAGES := $(wildcard backend/app/vision backend/app/coaching eval perf)

.PHONY: check lint lint-backend lint-frontend typecheck typecheck-backend typecheck-frontend test test-backend test-frontend eval golden-update bench

check: lint typecheck test

lint: lint-backend lint-frontend

lint-backend:
	$(PY) -m ruff check backend tests
	$(PY) -m ruff format --check backend tests

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
	$(PY) -m pytest --cov=backend/app --cov-report=term-missing:skip-covered

test-frontend:
	cd frontend && npx vitest run

eval:
	@echo "make eval SPLIT=$(SPLIT): not implemented until EVAL-04" && exit 1

golden-update:
	@echo "make golden-update: not implemented until QA-02" && exit 1

bench:
	@echo "make bench: not implemented until PERF-01" && exit 1
