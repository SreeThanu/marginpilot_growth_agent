"""The FastAPI application. Routes only.

Every route is a GET. Nothing in this service mutates state, launches a
campaign, spends a rupee or writes to a durable audit log — the decision path is
already complete before the first HTTP request arrives, and this surface exists
to read it out. Making that structural rather than promised is why there is no
POST here.

Errors are surfaced, not swallowed. A collector that raises returns a 500 with
its exception text so the frontend can print "unavailable" beside the thing that
failed instead of an invented value in place of it.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api import evaluate as evaluate_module
from api import reprice as reprice_module
from api import service
from demo.fixtures import FIXTURE_LABEL, FIXTURES

logger = logging.getLogger("marginpilot.api")

#: The dev frontend. Deliberately explicit rather than ``*`` — this service
#: reads a merchant's decision record, and a wildcard origin on something that
#: will one day hold real merchant data is a habit worth not forming.
ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
)

app = FastAPI(
    title="MarginPilot API",
    version="1.0.0",
    description=(
        "Read-only HTTP boundary over the MarginPilot decision engine. "
        "Serves what the engine produced; computes nothing."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _guard(fn, *args: Any) -> Any:
    """Run a collector, turning a failure into a 500 that names it."""
    try:
        return fn(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown scenario {exc}") from exc
    except Exception as exc:  # surfaced, never replaced with a default
        logger.exception("collector %s failed", getattr(fn, "__name__", fn))
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Whether the engine imports and which fixtures it can decide."""
    return {
        "status": "ok",
        "label": FIXTURE_LABEL,
        "scenarios": list(service.SCENARIO_ORDER),
        "fixture_count": len(FIXTURES),
    }


@app.get("/api/scenarios")
def scenarios() -> dict[str, Any]:
    return {"label": FIXTURE_LABEL, "scenarios": _guard(service.scenario_index)}


@app.get("/api/scenarios/{scenario_id}")
def scenario(scenario_id: str) -> dict[str, Any]:
    return _guard(service.scenario_detail, scenario_id.upper())


@app.get("/api/scenarios/{scenario_id}/reprice")
def reprice(
    scenario_id: str,
    incentive_inr: float = Query(
        ...,
        description="What the merchant wants the incentive to cost, in rupees.",
    ),
    population: int | None = Query(None, description="Eligible customers."),
    aov_inr: float | None = Query(None, description="Average order value."),
    margin: float | None = Query(None, description="Contribution margin, 0-1."),
    observed_conversion: float | None = Query(
        None, description="Baseline conversion rate, 0-1."
    ),
    budget_inr: float | None = Query(None, description="Budget for this promotion."),
) -> dict[str, Any]:
    """Price this merchant's promotion under stated conditions, and decide.

    Every parameter is a business condition the merchant knows about their own
    shop. Conspicuously absent, and absent by design: the expected lift and the
    evidence basis. Those are MarginPilot's hypothesis about customer response,
    they are read from the existing proposal, and there is no query parameter
    that can move them — a merchant able to state the expected lift would be
    supplying the answer, not the question.

    Omitting a condition uses the merchant record's own figure, so the
    single-parameter call remains exactly what it was.

    A GET, like everything else here, and for the same reason: asking what an
    offer would be worth is a read. Nothing is launched, nothing is spent and
    nothing is written to the audit chain — the pre-experiment path has no
    branch that can return PROMOTE, so this route cannot authorise a rollout
    even in principle.

    Uncached. The incentive is user-supplied, and keying a cache on it would let
    a dragged control grow one without bound for no benefit at ~3ms a call.

    A request the policy will not price returns 422 rather than a decision. An
    inadmissible *request* and a policy refusal are different events, and
    collapsing them would let a refused ceiling breach read as an economic
    verdict.
    """
    key = scenario_id.upper()
    if key not in FIXTURES:
        raise HTTPException(status_code=404, detail=f"unknown scenario '{scenario_id}'")
    try:
        return reprice_module.reprice(
            key,
            incentive_inr,
            population=population,
            aov_inr=aov_inr,
            margin=margin,
            observed_conversion=observed_conversion,
            budget_inr=budget_inr,
        )
    except reprice_module.RequestInadmissible as exc:
        raise HTTPException(
            status_code=422,
            detail=reprice_module.inadmissible_payload(key, incentive_inr, exc),
        ) from exc


@app.post("/api/evaluate")
def evaluate(request: evaluate_module.EvaluationInput) -> dict[str, Any]:
    """Evaluate one merchant-stated promotion without a recorded scenario."""
    try:
        return evaluate_module.evaluate(request)
    except evaluate_module.EvaluationInadmissible as exc:
        raise HTTPException(
            status_code=422,
            detail=evaluate_module.inadmissible_payload(exc),
        ) from exc


@app.get("/api/scenarios/{scenario_id}/audit")
def audit(scenario_id: str) -> dict[str, Any]:
    return _guard(service.audit_trail, scenario_id.upper())


@app.get("/api/safety")
def safety() -> dict[str, Any]:
    return _guard(service.safety_report)


@app.get("/api/reproducibility")
def reproducibility() -> dict[str, Any]:
    return _guard(service.reproducibility)
