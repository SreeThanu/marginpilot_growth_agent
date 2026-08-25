"""Potential outcomes: completeness, coherence, and real heterogeneity.

CLAUDE.md invariant 8 makes these mandatory from the first world, because a
retrofit cannot produce worlds the agent has not already been tuned against.
"""

from __future__ import annotations

import numpy as np

from src.world.generator import generate, generate_world, treated_conversion_probability


def test_every_customer_has_both_outcomes_for_every_intervention() -> None:
    world, truth = generate(11)
    intervention_ids = {i.intervention_id for i in world.interventions}

    assert set(truth.outcomes) == {c.customer_id for c in world.customers}
    for customer in world.customers:
        per_intervention = truth.outcomes[customer.customer_id]
        assert set(per_intervention) == intervention_ids
        for pair in per_intervention.values():
            assert pair.y0 is not None
            assert pair.y1 is not None
            assert isinstance(pair.y0.converted, bool)
            assert isinstance(pair.y1.converted, bool)


def test_untreated_outcome_is_consistent_across_interventions() -> None:
    """There is only one untreated state.

    Y(0) is stored per intervention so the ground-truth record is complete and
    self-describing, but it must be the same outcome each time — otherwise the
    "control" arm would depend on which treatment the customer was not given.
    """
    world, truth = generate(12)
    for customer in world.customers:
        outcomes = list(truth.outcomes[customer.customer_id].values())
        assert len({(p.y0.converted, p.y0.contribution_inr) for p in outcomes}) == 1


def test_outcomes_use_common_random_numbers() -> None:
    """A customer who converts untreated must also convert under a treatment
    that only raises their conversion probability.

    Independent draws per arm would produce customers who buy at full price but
    not at a discount, which is noise masquerading as a negative individual
    effect and would corrupt every heterogeneity estimate downstream.
    """
    world, truth = generate(13)
    for customer in world.customers:
        for intervention in world.interventions:
            pair = truth.outcomes[customer.customer_id][intervention.intervention_id]
            p1 = treated_conversion_probability(
                customer, intervention, customer.expected_order_value_inr
            )
            if pair.y0.converted and p1 >= customer.baseline_purchase_prob:
                assert pair.y1.converted, (
                    f"{customer.customer_id} converts untreated but not under "
                    f"{intervention.intervention_id}"
                )


def test_treatment_effects_vary_across_customers_within_a_world() -> None:
    """Heterogeneity has to be real at the individual level.

    Without within-world variation, uplift modelling has nothing to model and
    any heterogeneity finding on Day 9 would be measuring sampling noise.
    """
    world = generate_world(14)
    intervention = world.interventions[1]  # percentage discount

    effects = np.array(
        [
            treated_conversion_probability(c, intervention, c.expected_order_value_inr)
            - c.baseline_purchase_prob
            for c in world.customers
        ]
    )

    assert effects.mean() > 0.0, "a discount should raise conversion on average"
    # Spread must be a meaningful fraction of the mean effect, not a rounding
    # artefact. The threshold is deliberately loose: the claim is "heterogeneous",
    # not a specific dispersion.
    assert effects.std() > 0.25 * abs(effects.mean())
    assert np.percentile(effects, 90) > 2.0 * np.percentile(effects, 10)


def test_ground_truth_round_trips_through_serialization() -> None:
    from src.world.schema import GroundTruth

    _, truth = generate(15)
    restored = GroundTruth.from_dict(truth.to_dict())
    assert restored.to_dict() == truth.to_dict()

    customer_id = next(iter(truth.outcomes))
    intervention_id = next(iter(truth.outcomes[customer_id]))
    assert (
        restored.outcomes[customer_id][intervention_id]
        == truth.outcomes[customer_id][intervention_id]
    )


def test_pull_forward_removes_contribution_from_some_incremental_orders() -> None:
    """Not every extra order is new demand.

    The cannibalization rate says a share of the lift is pull-forward: the
    customer would have bought later anyway, so the order adds no net
    contribution. If this never fires, the simulator is flattering promotions.
    """
    world, truth = generate(16)
    intervention_id = world.interventions[1].intervention_id

    incremental = 0
    zero_contribution = 0
    for customer in world.customers:
        pair = truth.outcomes[customer.customer_id][intervention_id]
        if pair.y1.converted and not pair.y0.converted:
            incremental += 1
            if pair.y1.contribution_inr == 0.0:
                zero_contribution += 1

    assert incremental > 0, "no incremental conversions to test against"
    assert zero_contribution > 0, "pull-forward never fires; cannibalization is inert"
    assert zero_contribution < incremental, "every incremental order was pulled forward"
