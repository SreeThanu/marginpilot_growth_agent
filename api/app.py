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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
    allow_methods=["GET"],
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


@app.get("/api/scenarios/{scenario_id}/audit")
def audit(scenario_id: str) -> dict[str, Any]:
    return _guard(service.audit_trail, scenario_id.upper())


@app.get("/api/safety")
def safety() -> dict[str, Any]:
    return _guard(service.safety_report)


@app.get("/api/reproducibility")
def reproducibility() -> dict[str, Any]:
    return _guard(service.reproducibility)
