# Delhi bus crowding-aware journey planner: developer commands.
# Everything runs locally. Nothing here registers, submits or deploys anything.

PY      ?= python3
VENV    := .venv
BIN     := $(VENV)/bin
DATASET ?= data/processed/synthetic

.PHONY: help setup setup-backend setup-frontend fixtures data test test-backend test-frontend lint \
        api ui build-ui demo clean

help:
	@echo "make setup      install backend (.venv) and frontend (node_modules) dependencies"
	@echo "make data       build the dataset from the SIMULATED fixtures into $(DATASET)"
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

data:
	$(BIN)/busplanner build-synthetic --out $(DATASET)

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
	$(BIN)/busplanner serve --dataset $(DATASET) --reload

ui:
	cd frontend && npm run dev

build-ui:
	cd frontend && npm run build

demo: data build-ui
	$(BIN)/busplanner serve --dataset $(DATASET)

clean:
	rm -rf data/processed frontend/dist backend/.pytest_cache backend/.ruff_cache
