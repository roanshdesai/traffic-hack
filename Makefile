# Overcrowding early warning (main) + journey planner (secondary): developer commands.
# Everything runs locally. Nothing here registers, submits or deploys anything.

PY      ?= python3
VENV    := .venv
BIN     := $(VENV)/bin
DATASET ?= data/processed/synthetic
WARN_DATASET ?= data/processed/earlywarning-synthetic
TICKETS ?= data/raw/2026-10/October-Delhi.csv
REAL_WARN_DATASET ?= data/processed/earlywarning-tickets-2026-10

.PHONY: help setup setup-backend setup-frontend fixtures data data-real-tickets test test-backend test-frontend lint \
        api api-real ui build-ui demo clean

help:
	@echo "make setup      install backend (.venv) and frontend (node_modules) dependencies"
	@echo "make data       build both datasets from the SIMULATED fixtures"
	@echo "make data-real-tickets  build the early-warning dataset from the real Oct 2026 ticket file (needs $(TICKETS))"
	@echo "make api-real   serve the API on the real-ticket early-warning dataset"
	@echo "make test       run backend and frontend tests"
	@echo "make lint       ruff + TypeScript typecheck"
	@echo "make api        run the API on http://127.0.0.1:8000 (auto-reload)"
	@echo "make ui         run the Vite dev server on http://localhost:5173 (proxies /api)"
	@echo "make demo       build data + UI and serve both on http://127.0.0.1:8000"
	@echo "make fixtures   regenerate the SIMULATED fixtures (deterministic)"

setup: setup-backend setup-frontend

setup-backend:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e "backend[dev]"

setup-frontend:
	cd frontend && npm ci

fixtures:
	$(BIN)/busplanner generate-fixtures
	$(BIN)/busplanner warn-generate-fixtures

data:
	$(BIN)/busplanner warn-build-synthetic --out $(WARN_DATASET)
	$(BIN)/busplanner build-synthetic --out $(DATASET)

data-real-tickets:
	$(BIN)/busplanner warn-build-tickets --tickets $(TICKETS) \
	  --mapping config/ticket_mappings/ondc_2026_10.json --origin real \
	  --baseline-end 2026-10-21 --holiday 2026-10-02 \
	  --label "Delhi ONDC e-ticket boardings, Oct 2026 (sample)" --out $(REAL_WARN_DATASET)

test: test-backend test-frontend

test-backend:
	cd backend && ../$(BIN)/python -m pytest

test-frontend:
	cd frontend && npm test

lint:
	$(BIN)/ruff check backend
	$(BIN)/ruff format --check backend
	cd frontend && npm run typecheck

api:
	$(BIN)/busplanner serve --dataset $(DATASET) --warning-dataset $(WARN_DATASET) --reload

api-real:
	$(BIN)/busplanner serve --dataset $(DATASET) --warning-dataset $(REAL_WARN_DATASET)

ui:
	cd frontend && npm run dev

build-ui:
	cd frontend && npm run build

demo: data build-ui
	$(BIN)/busplanner serve --dataset $(DATASET) --warning-dataset $(WARN_DATASET)

clean:
	rm -rf data/processed frontend/dist backend/.pytest_cache backend/.ruff_cache
