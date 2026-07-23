# Noema — the handover interface. `make help` lists everything.
# Backend commands assume the venv exists (make setup-backend once).

PY := backend/.venv/bin/python

help:            ## this list
	@grep -E '^[a-z-]+:.*##' Makefile | awk -F':.*## ' '{printf "  make %-22s %s\n", $$1, $$2}'

setup-backend:   ## one-time: venv + pinned deps (needs python3.12)
	cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
	@test -f backend/.env || (cp backend/.env.example backend/.env && echo ">> put your OPENAI_API_KEY in backend/.env")

setup-frontend:  ## one-time: npm install
	cd frontend && npm install

backend:         ## run the API (port 8000; --reload kills in-flight bench runs on edits)
	cd backend && .venv/bin/uvicorn app.main:app --reload

backend-stable:  ## run the API without --reload (campaign days: safe to edit files)
	cd backend && .venv/bin/uvicorn app.main:app

frontend:        ## run the UI dev server (port 5173)
	cd frontend && npm run dev

test:            ## all free test suites (~1 min, $0, offline)
	$(PY) tests/run_all.py

sync:            ## pull the code AND the bench-data repo (benchdata/)
	git pull
	@if [ -d benchdata/.git ]; then git -C benchdata pull; \
	elif [ -d ../noema-bench-data/.git ]; then git -C ../noema-bench-data pull; \
	else echo ">> no bench-data clone — run: git clone https://github.com/Anassdd/noema-bench-data.git benchdata"; fi

build:           ## production frontend build -> frontend/dist/
	cd frontend && npm run build

migrate-state:   ## PREVIEW moving all state under backend/var (see STORAGE.md §3)
	$(PY) scripts/migrate_state.py --state-dir backend/var

migrate-state-apply: ## actually move state (STOP the backend first)
	$(PY) scripts/migrate_state.py --state-dir backend/var --apply

.PHONY: help setup-backend setup-frontend backend backend-stable frontend test build migrate-state migrate-state-apply
