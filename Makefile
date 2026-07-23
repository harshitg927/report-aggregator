## Phony targets
.PHONY: install install-api install-ui dev-api dev-ui dev-all test test-py test-ui lint \
	docker-build docker-up docker-down

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

## ── Docker ────────────────────────────────────────────────────────────────────

docker-build:                     ## build API and frontend images
	docker compose build

docker-up:                        ## start full stack (API :8000, UI :3000)
	docker compose up --build -d

docker-down:                      ## stop compose services
	docker compose down

# CLI example (same Python image, override the command):
#   docker run --rm -v "$$PWD:/work" -w /work report-aggregator:latest \
#     report-aggregator merge a.json b.json -o merged.json

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
