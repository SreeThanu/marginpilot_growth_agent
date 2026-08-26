"""The tool surface, and what it structurally cannot do.

CLAUDE.md caps the agent at ten tools and forbids it from touching arm
assignment, horizons, budgets or ground truth. Those are enforced here against
the actual signatures, so adding a tool that violates one fails the build rather
than passing review.
"""

from __future__ import annotations

import dataclasses
import inspect
import typing

import pytest

from src.agent import tools
from src.agent.hypothesis import AgentHypothesis, ContextCitation
from src.agent.tools import TOOLS, ToolContext
from src.eval.contracts import merchant_view
from src.eval.executor import GroundTruthExecutor
from src.experiment.registry import ExperimentRegistry
from src.world.generator import generate

#: Types that carry latent parameters or potential outcomes. No tool may accept
#: one, and no tool context may hold one.
FORBIDDEN_TYPES = {
    "World", "GroundTruth", "WorldParams", "Customer", "PotentialOutcome",
    "PotentialOutcomePair", "Segment", "Product",
}


@pytest.fixture()
def ctx():
    world, truth = generate(3)
    view = merchant_view(world)
    return ToolContext(
        view=view,
        registry=ExperimentRegistry(),
        executor=GroundTruthExecutor(world, truth, view.observed_margin),
        budget_remaining_inr=view.budget_inr,
        max_experiments=1,
    )


def test_exactly_ten_tools() -> None:
    """CLAUDE.md's list is closed. Tool sprawl is how the boundary erodes."""
    assert len(TOOLS) == 10
    assert {t.__name__ for t in TOOLS} == {
        "get_merchant_metrics", "get_customer_segments", "get_product_context",
        "propose_experiment", "validate_experiment", "launch_experiment",
        "get_experiment_results", "evaluate_experiment", "scale_experiment",
        "stop_experiment",
    }


def test_no_tool_can_receive_ground_truth_or_latent_parameters() -> None:
    """The type-level assertion: check every annotated parameter."""
    violations = []
    for tool in TOOLS:
        hints = typing.get_type_hints(tool)
        for name, annotation in hints.items():
            rendered = str(annotation)
            for forbidden in FORBIDDEN_TYPES:
                if f".{forbidden}'" in rendered or rendered.endswith(f".{forbidden}"):
                    violations.append(f"{tool.__name__}({name}: {rendered})")
    assert not violations, (
        "no agent tool may accept ground truth or latent world parameters "
        f"(CLAUDE.md invariant 8): {violations}"
    )


def test_tool_context_cannot_hold_a_world_or_ground_truth() -> None:
    fields = {f.name: str(f.type) for f in dataclasses.fields(ToolContext)}
    # Pinned deliberately: any new field on the context has to be justified here
    # before it can carry data to a tool. `limits` and `power_level` are the
    # merchant's policy configuration, not world state.
    assert set(fields) == {
        "view", "registry", "executor", "budget_remaining_inr", "max_experiments",
        "launched", "limits", "power_level",
    }
    for name, annotation in fields.items():
        for forbidden in FORBIDDEN_TYPES:
            assert forbidden not in annotation, f"ToolContext.{name} exposes {forbidden}"


def test_no_tool_accepts_an_arm_a_horizon_or_a_budget() -> None:
    """Invariants 1, 2 and 3, enforced by the absence of a parameter."""
    forbidden_params = {
        "arm", "arms", "assignment", "seed", "horizon", "horizon_per_arm",
        "n_per_arm", "sample_size", "budget", "budget_inr", "discount_ceiling", "alpha",
    }
    for tool in TOOLS:
        found = forbidden_params & set(inspect.signature(tool).parameters)
        assert not found, f"{tool.__name__} exposes {found}, which would hand the agent authority"


def test_observation_tools_expose_context_but_not_latents(ctx) -> None:
    metrics = tools.get_merchant_metrics(ctx)
    segments = tools.get_customer_segments(ctx)
    products = tools.get_product_context(ctx)

    blob = repr(metrics) + repr(segments) + repr(products)
    for latent in (
        "promo_response_scale", "affinity", "elasticity", "baseline_purchase_prob",
        "responsiveness", "cannibalization", "y0", "y1",
    ):
        assert latent not in blob, f"tool output leaks {latent}"

    # And the qualitative context the agent is meant to reason from is present.
    assert segments[0]["notes"]
    assert products["customer_service_themes"]
    assert products["trading_notes"]


def test_validate_does_not_execute(ctx) -> None:
    """CLAUDE.md invariant 2: validate returns a verdict, never an execution."""
    hypothesis = _hypothesis(ctx)
    design = tools.propose_experiment(ctx, hypothesis)
    verdict = tools.validate_experiment(ctx, design)

    assert set(verdict) >= {"approved", "rejections", "experiment_id"}
    assert len(ctx.launched) == 0, "validation must not have launched anything"


def test_launch_refuses_an_unvalidated_design(ctx) -> None:
    world, truth = generate(3)
    view = merchant_view(world)
    broke = ToolContext(
        view=view,
        registry=ExperimentRegistry(),
        executor=GroundTruthExecutor(world, truth, view.observed_margin),
        budget_remaining_inr=0.0,   # nothing can be funded
        max_experiments=1,
    )
    with pytest.raises(PermissionError):
        tools.launch_experiment(broke, tools.propose_experiment(broke, _hypothesis(broke)))


def test_scale_refuses_when_the_rule_says_no(ctx) -> None:
    from src.experiment.evaluator import ScaleDecision

    refused = ScaleDecision(
        scale=False, probability_net_positive=0.4, projected_net_inr=-1.0,
        projected_downside_inr=-100.0, tolerable_loss_inr=50.0, min_probability=0.8,
        reason="hold: not enough evidence",
    )
    hypothesis = _hypothesis(ctx)
    design = tools.propose_experiment(ctx, hypothesis)
    experiment = tools.launch_experiment(ctx, design)
    with pytest.raises(PermissionError):
        tools.scale_experiment(ctx, experiment, refused)


def _hypothesis(ctx) -> AgentHypothesis:
    contribution = ctx.view.observed_aov_inr * ctx.view.observed_margin
    return AgentHypothesis(
        hypothesis_id="hyp_test",
        intervention_id=ctx.view.interventions[0].intervention_id,
        prediction="Conversion rises by three points.",
        reasoning="Support tickets mention shipping cost repeatedly.",
        citations=(ContextCitation("customer_service_themes", "shipping", "shipping-sensitive"),),
        expected_effect_absolute=0.03,
        mde_contribution_per_customer_inr=contribution * 0.02,
        success_condition="P(net>0) >= 0.80.",
        failure_condition="P(net>0) < 0.80.",
        selection_rationale="Cheapest incentive per unit of contribution.",
    )
