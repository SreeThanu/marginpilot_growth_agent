"""The scenario-independent merchant promotion evaluator."""

from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import app
from api import evaluate as evaluate_module
from api.evaluate import (
    PROPOSER_ENV,
    EvaluationInadmissible,
    EvaluationInput,
    evaluate,
)
from api import service
from demo.fixtures import FIXTURES


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches a model unless it says so.

    The adapter now falls back to a Gemini REST transport when the vendor client
    is absent, and this machine has a working key — so without this the suite
    would start making live calls, which is both slow and a way to have a rate
    limit fail a test. Tests that want a proposer opt in through
    :func:`_with_reasoner`, which sets the variable back and patches the
    transport.
    """
    monkeypatch.setenv(PROPOSER_ENV, "none")
BASE_REQUEST = {
    "offer_kind": "flat_discount",
    "flat_discount_inr": 50.0,
    "discount_pct": None,
    "shipping_fee_waived_inr": None,
    "bundle_added_value_inr": None,
    "cohort_id": "ALL",
    "population": 500,
    "aov_inr": 600.0,
    "margin": 0.30,
    "observed_conversion": 0.10,
    "budget_inr": 100_000.0,
}


def request(**overrides) -> EvaluationInput:
    return EvaluationInput.model_validate(BASE_REQUEST | overrides)


def test_recorded_case_page_does_not_mount_the_merchant_request() -> None:
    source = (ROOT / "frontend/src/app/page.tsx").read_text("utf-8")
    assert "MerchantRequestPanel" not in source


def test_evaluate_page_mounts_the_merchant_request() -> None:
    source = (ROOT / "frontend/src/app/evaluate/page.tsx").read_text("utf-8")
    assert "MerchantRequestPanel" in source
    assert "EVALUATE A PROMOTION" in source


def test_evaluation_has_no_scenario_input_or_scenario_response() -> None:
    assert tuple(inspect.signature(evaluate).parameters) == ("request", "limits")
    result = evaluate(request())
    assert "scenario" not in result


def test_post_evaluate_accepts_a_generic_request() -> None:
    response = TestClient(app).post("/api/evaluate", json=BASE_REQUEST)
    assert response.status_code == 200
    assert response.json()["offer"]["kind"] == "flat_discount"


@pytest.mark.parametrize(
    ("overrides", "expected_kind", "expected_cost"),
    [
        ({}, "flat_discount", 50.0),
        (
            {
                "offer_kind": "percentage_discount",
                "flat_discount_inr": None,
                "discount_pct": 0.10,
            },
            "percentage_discount",
            60.0,
        ),
        (
            {
                "offer_kind": "free_shipping",
                "flat_discount_inr": None,
                "shipping_fee_waived_inr": 45.0,
            },
            "free_shipping",
            45.0,
        ),
    ],
)
def test_explicit_offer_types_reach_the_existing_intervention_path(
    overrides, expected_kind: str, expected_cost: float
) -> None:
    result = evaluate(request(**overrides))
    assert result["offer"]["kind"] == expected_kind
    assert result["offer"]["incentive_cost_per_order_inr"] == pytest.approx(
        expected_cost
    )
    assert result["recommendation"]["decision"] == "INSUFFICIENT_EVIDENCE"


def test_bundle_fails_closed_when_its_added_value_cannot_be_priced() -> None:
    with pytest.raises(EvaluationInadmissible, match="bundle-added order value"):
        evaluate(
            request(
                offer_kind="bundle",
                flat_discount_inr=None,
                discount_pct=0.10,
                bundle_added_value_inr=150.0,
            )
        )


def test_offer_magnitude_is_not_inherited_from_scenario_a() -> None:
    result = evaluate(request(flat_discount_inr=37.0))
    assert result["offer"]["incentive_cost_per_order_inr"] == pytest.approx(37.0)
    assert result["offer"]["incentive_cost_per_order_inr"] != 120.0


def test_no_fixture_proposal_or_lift_is_used_for_a_generic_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Checked against the code with docstrings stripped: the module explains in
    # prose why it borrows neither the recorded proposals nor the heuristic's
    # fixed 0.03, so a raw substring search would fail on that justification.
    code = _proposer_code()
    assert "proposal_payload" not in code
    assert "SCENARIO_A" not in code
    # HeuristicReasoner returns a hardcoded 0.03 that its own docstring says is
    # not reasoning. It must not be reachable as a hypothesis source.
    assert "HeuristicReasoner" not in code

    monkeypatch.setenv(PROPOSER_ENV, "none")
    result = evaluate(request())
    assert result["status"] == "ASSESSMENT_UNAVAILABLE"
    assert result["assessment"]["status"] == "UNAVAILABLE"
    assert result["assessment"]["expected_lift_absolute"] is None
    assert result["assessment"]["evidence_basis"] == "NONE"
    assert result["assessment"]["hypothesis"] is None
    assert result["recommendation"]["decision"] == "INSUFFICIENT_EVIDENCE"
    # The offer economics are still real, because they come from the brief.
    assert result["offer"]["contribution_per_order_inr"] == pytest.approx(180.0)


def _proposer_code() -> str:
    """The executable part of the adapter, with the docstrings stripped.

    The module docstring names ``HeuristicReasoner`` in order to explain why it
    is excluded, so a plain substring search over the file would fail on its own
    justification.
    """
    import ast

    tree = ast.parse((ROOT / "api/evaluate.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(
                body[0].value, ast.Constant
            ) and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _reply(**overrides) -> dict:
    """A well-formed model reply for the merchant's own offer."""
    return {
        "intervention_id": "merchant_requested_offer",
        "cohort_id": "ALL",
        "expected_lift_absolute": 0.04,
        "evidence_basis": "PRIOR",
        "hypothesis": "The offer lifts conversion among price-sensitive buyers.",
        "mechanism": "A lower effective price converts hesitant baskets.",
        "citations": ["interventions", "context"],
        "requested_decision": "PROMOTE",
    } | overrides


def _with_reasoner(monkeypatch: pytest.MonkeyPatch, ask) -> None:
    """Wire a canned ``ask`` into the existing reasoner slot.

    Patched at :func:`api.evaluate._reasoner_ask` rather than at the proposer,
    so the production path — ``LLMProposer`` formatting the brief into
    ``PROPOSAL_PROMPT``, and the reply reaching ``recommend_from_raw`` — is the
    one under test. Only the network call is replaced.
    """
    monkeypatch.setenv(PROPOSER_ENV, "auto")
    monkeypatch.setattr(
        evaluate_module, "_reasoner_ask", lambda choice: (ask, "marginpilot_gemini")
    )


def test_the_brief_for_this_offer_is_what_reaches_the_proposer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def ask(prompt: str) -> dict:
        seen["prompt"] = prompt
        return _reply()

    _with_reasoner(monkeypatch, ask)
    evaluate(request(flat_discount_inr=37.0, aov_inr=600.0))

    prompt = seen["prompt"]
    assert "merchant_requested_offer" in prompt
    # The merchant's own conditions, not a recorded merchant's.
    assert "600" in prompt
    assert "demo_scenario_A" not in prompt
    assert "demo_flat_discount" not in prompt


def test_a_validated_proposal_becomes_the_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_reasoner(monkeypatch, lambda prompt: _reply(expected_lift_absolute=0.055))
    result = evaluate(request())

    assessment = result["assessment"]
    assert result["status"] == "EVALUATED"
    assert assessment["status"] == "AVAILABLE"
    assert assessment["expected_lift_absolute"] == pytest.approx(0.055)
    assert assessment["evidence_basis"] == "PRIOR"
    assert assessment["hypothesis"]
    assert assessment["mechanism"]
    assert assessment["citations"]
    assert assessment["source"] == "marginpilot_gemini"
    assert result["recommendation"]["decision"] in {
        "DO_NOT_PROMOTE",
        "RUN_EXPERIMENT_FIRST",
    }


def test_the_offer_the_merchant_chose_changes_the_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same hypothesis, priced against two different offers."""
    _with_reasoner(monkeypatch, lambda prompt: _reply())
    conditions = dict(
        population=30_000, aov_inr=600.0, margin=0.22,
        observed_conversion=0.10, budget_inr=400_000.0,
    )

    deep = evaluate(request(flat_discount_inr=120.0, **conditions))
    shallow = evaluate(request(flat_discount_inr=37.0, **conditions))

    assert deep["recommendation"]["decision"] == "DO_NOT_PROMOTE"
    assert deep["recommendation"]["expected_net_contribution_inr"] == pytest.approx(
        -345_600.0
    )
    assert shallow["recommendation"]["decision"] == "RUN_EXPERIMENT_FIRST"
    assert shallow["recommendation"]["expected_net_contribution_inr"] == pytest.approx(
        3_000.0
    )
    # The hypothesis did not move; the offer did.
    assert (
        deep["assessment"]["expected_lift_absolute"]
        == shallow["assessment"]["expected_lift_absolute"]
    )


@pytest.mark.parametrize(
    "overrides, depth, incentive",
    [
        ({"offer_kind": "flat_discount", "flat_discount_inr": 120.0}, 0.20, 120.0),
        (
            {
                "offer_kind": "percentage_discount",
                "flat_discount_inr": None,
                "discount_pct": 0.10,
            },
            0.10,
            60.0,
        ),
        (
            {
                "offer_kind": "free_shipping",
                "flat_discount_inr": None,
                "shipping_fee_waived_inr": 60.0,
            },
            0.10,
            60.0,
        ),
    ],
)
def test_every_supported_offer_kind_reaches_the_policy(
    monkeypatch: pytest.MonkeyPatch, overrides: dict, depth: float, incentive: float
) -> None:
    _with_reasoner(monkeypatch, lambda prompt: _reply())
    result = evaluate(request(aov_inr=600.0, **overrides))

    assert result["offer"]["depth_at_observed_aov"] == pytest.approx(depth)
    assert result["offer"]["incentive_cost_per_order_inr"] == pytest.approx(incentive)
    assert result["assessment"]["status"] == "AVAILABLE"
    assert result["recommendation"]["decision"] != "INSUFFICIENT_EVIDENCE"


def test_a_reply_naming_another_merchants_intervention_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_reasoner(
        monkeypatch, lambda prompt: _reply(intervention_id="demo_flat_discount")
    )
    result = evaluate(request())
    assert result["recommendation"]["decision"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize(
    "bad",
    [
        {"expected_lift_absolute": "not a number"},
        {"citations": []},
        {"evidence_basis": "EXPERIMENT"},
        {"hypothesis": ""},
    ],
)
def test_an_unusable_reply_claims_nothing(
    monkeypatch: pytest.MonkeyPatch, bad: dict
) -> None:
    _with_reasoner(monkeypatch, lambda prompt: _reply(**bad))
    result = evaluate(request())

    assert result["status"] == "ASSESSMENT_UNAVAILABLE"
    assert result["assessment"]["expected_lift_absolute"] is None
    assert result["assessment"]["evidence_basis"] == "NONE"
    assert result["recommendation"]["decision"] in {
        "INSUFFICIENT_EVIDENCE",
        "DO_NOT_PROMOTE",
    }


def test_a_reasoner_that_raises_does_not_produce_an_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ask(prompt: str) -> dict:
        raise RuntimeError("rate limited")

    _with_reasoner(monkeypatch, ask)
    result = evaluate(request())

    assert result["assessment"]["status"] == "UNAVAILABLE"
    assert result["assessment"]["expected_lift_absolute"] is None
    assert "RuntimeError" in result["assessment"]["reason"]
    assert result["recommendation"]["decision"] == "INSUFFICIENT_EVIDENCE"


def test_a_custom_evaluation_can_never_return_promote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No pre-experiment path constructs PROMOTE, however good the hypothesis."""
    decisions = set()
    for lift in (0.0, 0.05, 0.2, 0.6, 1.0):
        _with_reasoner(monkeypatch, lambda prompt, l=lift: _reply(
            expected_lift_absolute=l
        ))
        for discount in (1.0, 37.0, 120.0):
            decisions.add(
                evaluate(request(flat_discount_inr=discount))["recommendation"][
                    "decision"
                ]
            )
    assert "PROMOTE" not in decisions


def test_merchant_cannot_supply_lift_or_evidence() -> None:
    for forbidden in (
        "expected_lift_absolute",
        "expected_lift",
        "evidence_basis",
        "evidence",
    ):
        with pytest.raises(ValidationError):
            EvaluationInput.model_validate(BASE_REQUEST | {forbidden: 0.04})


def test_malformed_and_unsupported_offers_fail_closed() -> None:
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(BASE_REQUEST | {"offer_kind": "cashback"})
    with pytest.raises(EvaluationInadmissible, match="required"):
        evaluate(request(flat_discount_inr=None))
    with pytest.raises(EvaluationInadmissible, match="standing policy ceiling"):
        evaluate(
            request(
                offer_kind="percentage_discount",
                flat_discount_inr=None,
                discount_pct=0.30,
            )
        )


def test_evaluation_does_not_mutate_recorded_fixtures_or_cases() -> None:
    fingerprints = {key: spec.fingerprint() for key, spec in FIXTURES.items()}
    before = {key: service.scenario_detail(key) for key in ("A", "B", "C")}

    evaluate(request())

    assert {key: spec.fingerprint() for key, spec in FIXTURES.items()} == fingerprints
    assert {key: service.scenario_detail(key) for key in ("A", "B", "C")} == before


def test_frozen_and_audit_paths_are_absent_from_the_worktree_diff() -> None:
    changed = subprocess.run(
        ["git", "diff", "--name-only", "ac56601"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    frozen = (
        "src/world/",
        "src/eval/",
        "src/economics/",
        "src/experiment/",
        "src/policy/",
        "results/",
        "docs/simulator.md",
        "requirements.txt",
        "src/audit/",
    )
    assert not [path for path in changed if path.startswith(frozen)]


class _StubResponse:
    """The parts of an ``httpx.Response`` this transport reads."""

    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=None, response=None  # type: ignore[arg-type]
            )

    def json(self) -> dict:
        return self._payload


def _openrouter_call(monkeypatch: pytest.MonkeyPatch, response: _StubResponse) -> dict:
    """Select the explicit OpenRouter route and capture the request it builds.

    Patched at ``httpx.post`` rather than at ``_openrouter_ask``, so the real
    dispatch, credential read, model selection, reply parsing and the shared
    ``_extract_json`` are all under test. Only the socket is replaced, so no
    test reaches the network.
    """
    monkeypatch.setenv(PROPOSER_ENV, "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-not-a-real-key")
    monkeypatch.delenv("MARGINPILOT_OPENROUTER_MODEL", raising=False)
    sent: dict = {}

    def post(url: str, **kwargs) -> _StubResponse:
        sent["url"] = url
        sent.update(kwargs)
        return response

    monkeypatch.setattr(evaluate_module.httpx, "post", post)
    return sent


def _as_openrouter_reply(payload: dict) -> _StubResponse:
    return _StubResponse({"choices": [{"message": {"content": json.dumps(payload)}}]})


def test_the_explicit_openrouter_route_produces_a_nemotron_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _openrouter_call(monkeypatch, _as_openrouter_reply(_reply()))
    result = evaluate(request())

    # The request is the documented chat-completions shape, against the default
    # Nemotron build, asking for a JSON object.
    assert sent["url"] == "https://openrouter.ai/api/v1/chat/completions"
    body = sent["json"]
    assert body["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.0
    assert [message["role"] for message in body["messages"]] == ["system", "user"]
    # The shared prompts, not a restatement of them.
    from src.agent.proposer import PROPOSAL_PROMPT
    from src.agent.reasoner import SYSTEM_PROMPT

    assert body["messages"][0]["content"] == SYSTEM_PROMPT
    assert PROPOSAL_PROMPT.split("{brief}")[0].strip() in body["messages"][1]["content"]
    assert sent["headers"]["Authorization"].startswith("Bearer ")

    # And the reply travels the ordinary validation path to become an assessment.
    assert result["status"] == "EVALUATED"
    assert result["assessment"]["status"] == "AVAILABLE"
    assert result["assessment"]["source"] == "marginpilot_openrouter_nemotron"
    assert result["assessment"]["expected_lift_absolute"] == pytest.approx(0.04)


def test_the_openrouter_model_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _openrouter_call(monkeypatch, _as_openrouter_reply(_reply()))
    monkeypatch.setenv("MARGINPILOT_OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
    evaluate(request())

    assert sent["json"]["model"] == "nvidia/nemotron-3-ultra-550b-a55b"


def test_openrouter_is_not_reachable_from_the_auto_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``auto`` must behave exactly as it did before this transport existed."""
    monkeypatch.setenv(PROPOSER_ENV, "auto")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-not-a-real-key")
    called = False

    def _never() -> None:
        nonlocal called
        called = True
        raise AssertionError("auto reached the OpenRouter transport")

    monkeypatch.setattr(evaluate_module, "_openrouter_ask", _never)
    monkeypatch.setattr(evaluate_module, "_gemini_rest_ask", lambda: None)
    from src.agent import reasoner as reasoners

    monkeypatch.setattr(
        reasoners.GeminiReasoner, "__init__",
        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("no key")),
    )
    monkeypatch.setattr(
        reasoners.ClaudeReasoner, "__init__",
        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("no key")),
    )

    assert evaluate_module._reasoner_ask("auto") is None
    assert called is False


@pytest.mark.parametrize(
    "response",
    [
        _StubResponse({}, status=429),
        _StubResponse({}, status=500),
        _StubResponse({"choices": []}),
        _StubResponse({"choices": [{"message": {"content": "not json at all"}}]}),
    ],
    ids=["rate_limited", "server_error", "no_choices", "unparseable"],
)
def test_a_failed_openrouter_call_claims_nothing(
    monkeypatch: pytest.MonkeyPatch, response: _StubResponse,
) -> None:
    """Fail closed: no lift, no evidence, and the offer economics still real."""
    _openrouter_call(monkeypatch, response)
    result = evaluate(request())

    assert result["status"] == "ASSESSMENT_UNAVAILABLE"
    assert result["assessment"]["status"] == "UNAVAILABLE"
    assert result["assessment"]["expected_lift_absolute"] is None
    assert result["assessment"]["evidence_basis"] == "NONE"
    assert result["assessment"]["hypothesis"] is None
    assert result["recommendation"]["decision"] == "INSUFFICIENT_EVIDENCE"
    assert result["offer"]["contribution_per_order_inr"] == pytest.approx(180.0)


def test_no_openrouter_credential_claims_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PROPOSER_ENV, "openrouter")
    monkeypatch.setattr(evaluate_module, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def _no_network(*args, **kwargs):
        raise AssertionError("a missing credential must not reach the network")

    monkeypatch.setattr(evaluate_module.httpx, "post", _no_network)

    assert evaluate_module._reasoner_ask("openrouter") is None
    assert evaluate(request())["status"] == "ASSESSMENT_UNAVAILABLE"
