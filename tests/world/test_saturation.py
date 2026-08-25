"""The demand-saturation curve must bound the tail without flattening it.

The earlier hard cap, ``min(x, 3.0)``, bounded response by assigning every
customer past the threshold an identical multiplier — erasing exactly the
individual variation uplift modelling exists to find, in the tail where it is
largest. The smooth form has to hold the same asymptote while keeping distinct
customers distinct.
"""

from __future__ import annotations

import numpy as np

from src.world.generator import (
    RESPONSE_ASYMPTOTE,
    generate_world,
    intervention_affinity,
    response_multiplier,
    treated_conversion_probability,
)


def test_curve_starts_at_one_with_unit_slope() -> None:
    """Weak promotions must behave exactly as the unsaturated model says.

    Otherwise the elasticity ranges taken from the literature would no longer
    mean what those papers measured.
    """
    assert response_multiplier(0.0) == 1.0
    for x in (1e-4, 1e-3, 1e-2):
        assert abs(response_multiplier(x) - (1.0 + x)) < x * 0.01


def test_curve_approaches_but_never_reaches_the_asymptote() -> None:
    """Analytically the curve never reaches 3.0.

    In IEEE-754 doubles it becomes indistinguishable from 3.0 once
    ``exp(-x/2) < eps``, i.e. beyond roughly x = 71. That is a float-resolution
    artefact rather than a modelling ceiling, and it affects a handful of the
    most extreme cells in the corpus (measured: 85 of 1,286,456, 0.007%). It is
    recorded here rather than papered over.
    """
    for x in (0.5, 1.0, 5.0, 20.0, 60.0):
        assert response_multiplier(x) < RESPONSE_ASYMPTOTE
    assert response_multiplier(1e3) == RESPONSE_ASYMPTOTE


def test_curve_is_strictly_increasing_across_the_corpus_range() -> None:
    """Two customers who differ in response must still differ after saturation."""
    xs = np.linspace(0.0, 30.0, 4000)
    ms = np.array([response_multiplier(float(x)) for x in xs])
    assert np.all(np.diff(ms) > 0.0)


def test_nothing_clips_in_the_generated_corpus() -> None:
    """No customer sits exactly at a ceiling, in response or in probability."""
    for seed in (2, 19, 47, 73):
        world = generate_world(seed)
        for intervention in world.interventions:
            affinity = intervention_affinity(world.params, intervention)
            p1 = np.array(
                [
                    treated_conversion_probability(
                        c, intervention, c.expected_order_value_inr, affinity
                    )
                    for c in world.customers
                ]
            )
            assert np.all(p1 < 1.0)
            assert not np.any(np.isclose(p1, 0.98)), "the old probability clip is gone"
            # Ratio to baseline must stay under the asymptote for every customer.
            p0 = np.array([c.baseline_purchase_prob for c in world.customers])
            assert np.all(p1 <= 1.0 - (1.0 - p0) ** RESPONSE_ASYMPTOTE + 1e-12)


def test_tail_heterogeneity_survives_saturation() -> None:
    """The point of the change: the most responsive customers must not all be
    assigned the same effect."""
    world = generate_world(73)  # the world that clipped worst under the hard cap
    intervention = world.interventions[0]
    affinity = intervention_affinity(world.params, intervention)
    p0 = np.array([c.baseline_purchase_prob for c in world.customers])
    p1 = np.array(
        [
            treated_conversion_probability(c, intervention, c.expected_order_value_inr, affinity)
            for c in world.customers
        ]
    )
    effects = p1 - p0
    top = effects[effects >= np.percentile(effects, 90)]
    # Under a hard cap this decile collapsed toward a single value.
    assert len(np.unique(np.round(top, 6))) > len(top) * 0.5
    assert top.std() > 0.0
