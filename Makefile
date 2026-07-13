## Phony targets
.PHONY: install install-api install-ui dev-api dev-ui dev-all test test-py test-ui lint

## ── Setup ────────────────────────────────────────────────────────────────────

install: install-api install-ui   ## install all dependencies

install-api:                      ## pip-install the Python engine + API + dev extras
	pip install -e ".[api,dev]"

install-ui:                       ## npm-install the Next.js frontend
	cd frontend && npm install

## ── Development servers ───────────────────────────────────────────────────────

dev-api:                          ## start the FastAPI service on :8000
	python -m report_aggregator.api

dev-ui:                           ## start the Next.js dev server on :3000
	cd frontend && npm run dev

dev-all:                          ## start both services together (via frontend/scripts/dev.sh)
	cd frontend && npm run dev:all

## ── Testing ───────────────────────────────────────────────────────────────────

test: test-py test-ui             ## run all tests

test-py:                          ## run Python pytest suite
	pytest tests/ -v

test-ui:                          ## run frontend vitest suite
	cd frontend && npm test

## ── Linting ───────────────────────────────────────────────────────────────────

lint:                             ## lint Python and JavaScript
	ruff check src/ tests/
	cd frontend && npm run lint
