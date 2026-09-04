# MarginPilot
#
# Day 2: `worlds` and `test` are wired. The rest are declared now so the interface
# is fixed before the code exists, and echo their build day until implemented.

.PHONY: worlds demo snapshot eval audit adversarial test api web

PYTHON ?= python
WORLDS_DIR ?= worlds
AUDIT_DB ?= data/audit.db
EVAL_ARGS ?=

## Generate 100 worlds — 80 dev, 20 sealed holdout — and print the sanity report
worlds:
	$(PYTHON) -m src.world --out $(WORLDS_DIR)

## Rebuild the dashboard snapshot from dev worlds, then serve the dashboard
demo: snapshot
	$(PYTHON) -m streamlit run src/ui/app.py

## Rebuild data/dashboard_snapshot.json (dev worlds only; ~9s)
snapshot:
	$(PYTHON) -m src.ui.snapshot

## Open the sealed holdout once and evaluate every strategy -> results/
## EVAL_ARGS=--with-agent also runs MarginPilot (needs GEMINI_API_KEY, one call per world)
eval:
	$(PYTHON) -m src.eval $(EVAL_ARGS)

## Print the full decision chain for one experiment: make audit EXPERIMENT=<id>
audit:
	$(PYTHON) -m src.audit $(EXPERIMENT) --db $(AUDIT_DB)

## Run the seven adversarial scenarios; each must produce a logged refusal
adversarial:
	$(PYTHON) -m src.eval.adversarial

## Serve the read-only JSON adapter the web frontend reads (http://127.0.0.1:8000)
api:
	$(PYTHON) -m api

## Run the judge-facing web frontend in development (needs `make api` in another shell)
web:
	cd frontend && npm run dev

## Run the test suite
test:
	$(PYTHON) -m pytest -q
