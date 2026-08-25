"""Determinism and variety: the two properties a world corpus must have.

Determinism, because an evaluation that cannot be regenerated cannot be checked
by anyone else. Variety, because 100 copies of one world would make the holdout
protocol theatre.
"""

from __future__ import annotations

import pytest

from src.world.generator import generate, generate_world
from src.world.persistence import serialize_world


def test_same_seed_produces_a_byte_identical_world() -> None:
    first = generate_world(4242)
    second = generate_world(4242)

    assert first == second
    # Object equality is not enough: the corpus is consumed from disk, so the
    # serialized bytes are what actually has to be stable.
    assert serialize_world(first) == serialize_world(second)


def test_same_seed_produces_identical_ground_truth() -> None:
    _, first = generate(77)
    _, second = generate(77)
    assert first.to_dict() == second.to_dict()


def test_ground_truth_is_reproducible_from_the_world_alone() -> None:
    """Truth is a function of the world's seed, not of call order.

    Without this, regenerating truth for an existing world could silently
    produce different outcomes than the ones the world was evaluated against.
    """
    from src.world.generator import generate_ground_truth

    world = generate_world(31)
    assert generate_ground_truth(world).to_dict() == generate_ground_truth(world).to_dict()


def test_different_seeds_produce_materially_different_worlds() -> None:
    worlds = [generate_world(seed) for seed in (1, 2, 3, 4, 5, 6, 7, 8)]

    # Structural parameters must differ, not just IDs.
    assert len({w.params.baseline_conversion for w in worlds}) == len(worlds)
    assert len({w.params.elasticity_mean for w in worlds}) == len(worlds)
    assert len({w.params.aov_median_inr for w in worlds}) == len(worlds)
    assert len({w.params.cannibalization_rate for w in worlds}) == len(worlds)

    # And the customer bases must differ in size, not merely in draw.
    assert len({w.params.n_customers for w in worlds}) > 1

    # Two worlds should not share a serialized form.
    serialized = {serialize_world(w) for w in worlds}
    assert len(serialized) == len(worlds)


def test_parameters_stay_inside_the_documented_ranges() -> None:
    """Ranges come from docs/simulator.md; drifting out of them silently would
    make that document a work of fiction."""
    for seed in range(1, 26):
        params = generate_world(seed).params
        assert 0.06 <= params.baseline_conversion <= 0.20
        # Lower bound is -5.0, not -3.5: a world under competitive pressure has
        # its elasticity multiplied by 1.35, which is the coupling that makes the
        # competitor event in the semantic context mean something.
        assert -5.0 <= params.elasticity_mean <= -1.2
        assert 0.30 <= params.elasticity_sd <= 0.90
        assert 0.25 <= params.responsiveness_sigma <= 0.60
        assert 0.9 <= params.promo_response_scale <= 2.1
        for affinity in (
            params.shipping_affinity,
            params.clearance_affinity,
            params.pct_affinity,
            params.bundle_affinity,
        ):
            assert 0.5 <= affinity <= 2.2
        assert 500.0 <= params.aov_median_inr <= 2500.0
        assert 0.15 <= params.cannibalization_rate <= 0.45
        assert 0.85 <= params.seasonality_index <= 1.35
        assert 12_000 <= params.n_customers <= 28_000
        assert 0.05 <= params.budget_share_of_revenue <= 0.15
        # Budget is a share of the world's own revenue, not a flat figure.
        assert params.promotion_budget_inr == pytest.approx(
            round(params.projected_revenue_inr * params.budget_share_of_revenue, -3), abs=1.0
        )


def test_exactly_four_intervention_kinds() -> None:
    """CLAUDE.md's locked list caps intervention types at ~4."""
    world = generate_world(9)
    kinds = {i.kind for i in world.interventions}
    assert len(world.interventions) == 4
    assert len(kinds) == 4


def test_stated_parameters_describe_the_catalogue_they_produced() -> None:
    """A world's numbers must not contradict its own products.

    Sampling catalogue prices and margins independently of the world's stated
    AOV and margin parameters would put a lie in every world file, and the
    sanity report would then be describing something the simulator does not use.
    """
    import numpy as np

    for seed in (2, 17, 44, 63):
        world = generate_world(seed)
        margins = np.array([p.contribution_margin for p in world.products])
        prices = np.array([p.unit_price_inr for p in world.products])

        assert abs(float(margins.mean()) - world.params.margin_mean) < 0.06
        # Unit prices sit below AOV — a basket is one to two items.
        assert 0.3 * world.params.aov_median_inr < float(np.median(prices)) < 1.6 * world.params.aov_median_inr


def test_budget_is_a_share_of_the_worlds_own_revenue() -> None:
    """A flat budget is either trivial for a large merchant or ruinous for a
    small one — and, worse, unrelated to whether it can fund an experiment big
    enough to resolve the contribution question it is meant to answer."""
    import numpy as np

    budgets, shares = [], []
    for seed in range(1, 61):
        params = generate_world(seed).params
        budgets.append(params.promotion_budget_inr)
        shares.append(params.promotion_budget_inr / params.projected_revenue_inr)

    # Typical budgets in the intended band.
    assert 250_000 <= float(np.median(budgets)) <= 650_000
    # And every world's budget is a plausible share of its own revenue.
    assert all(0.04 < s < 0.16 for s in shares)


def test_worlds_are_large_enough_to_run_a_contribution_powered_experiment() -> None:
    """The population has to supply the sample the decision rule requires.

    Without this the agent cannot resolve a typical effect at any budget, and
    MarginPilot degenerates into Baseline 1 for a reason that has nothing to do
    with its reasoning.
    """
    from src.experiment.power import required_sample_size_for_contribution

    for seed in (4, 22, 57):
        world = generate_world(seed)
        contribution_per_order = world.params.aov_median_inr * world.params.margin_mean
        needed = required_sample_size_for_contribution(
            world.params.baseline_conversion,
            0.03,
            contribution_per_incremental_order_inr=contribution_per_order,
            incentive_cost_per_treated_order_inr=contribution_per_order * 0.3,
            mde_contribution_per_customer_inr=contribution_per_order * 0.02,
        )
        assert needed * 2 <= world.params.n_customers, (
            f"{world.world_id} cannot seat a 2-arm experiment needing {needed}/arm"
        )
