# MarginPilot
#
# Day 2: `worlds` and `test` are wired. The rest are declared now so the interface
# is fixed before the code exists, and echo their build day until implemented.

.PHONY: worlds demo eval audit adversarial test

PYTHON ?= python
WORLDS_DIR ?= worlds
AUDIT_DB ?= audit.db

## Generate 100 worlds — 80 dev, 20 sealed holdout — and print the sanity report
worlds:
	$(PYTHON) -m src.world --out $(WORLDS_DIR)

## Single world, full agent loop, dashboard on :8501 (Day 6 / Day 10)
demo:
	@echo "make demo: not implemented yet (Day 6 — src/agent/)"

## All strategies across the 20 holdout worlds -> results/ (Day 4 harness, Day 9 run)
eval:
	@echo "make eval: not implemented yet (Day 4 harness / Day 9 holdout run)"

## Print the full decision chain for one experiment: make audit EXPERIMENT=<id>
audit:
	$(PYTHON) -m src.audit $(EXPERIMENT) --db $(AUDIT_DB)

## Run the seven adversarial scenarios; each must produce a logged refusal
adversarial:
	$(PYTHON) -m src.eval.adversarial

## Run the test suite
test:
	$(PYTHON) -m pytest -q
