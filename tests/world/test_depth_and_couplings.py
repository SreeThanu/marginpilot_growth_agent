"""Depth anchoring and the semantic couplings.

Two properties this file exists to protect:

* Depth is a multiple of **margin**, never of break-even. Break-even depth
  contains the true treatment effect, so anchoring to it would make ``d/margin``
  an observable readout of ``incremental/treated`` and let a baseline rank
  interventions by profitability without running an experiment.
* Semantic signals are emitted from hidden latents at partial fidelity. Perfect
  fidelity would make the text a lookup table and the LLM ablation meaningless;
  zero fidelity would make it decoration.
"""

from __future__ import annotations

import numpy as np

from src.world import vocabulary as vocab
from src.world.generator import (
    _AFFINITY_SIGNAL_THRESHOLD,
    DEPTH_MULTIPLE_OF_MARGIN,
    generate_world,
    intervention_affinity,
)


def test_depth_is_the_documented_multiple_of_margin() -> None:
    for seed in range(1, 41):
        world = generate_world(seed)
        margin = world.params.margin_mean
        mean_basket = world.params.aov_median_inr * float(
            np.exp(world.params.aov_sigma**2 / 2.0)
        )
        for intervention in world.interventions:
            low, high = DEPTH_MULTIPLE_OF_MARGIN[intervention.kind]
            depth = intervention.effective_depth(mean_basket)
            j = depth / margin
            # Rupee amounts are rounded to the nearest 10, so allow slack.
            assert low - 0.03 <= j <= high + 0.03, (
                f"{world.world_id} {intervention.intervention_id}: j={j:.3f} "
                f"outside [{low}, {high}]"
            )


def test_every_intervention_kind_has_a_hidden_affinity() -> None:
    """If depth alone decided the winner, a baseline could rank the four
    interventions without experimenting. The affinity is what it cannot see."""
    world = generate_world(5)
    affinities = {i.kind: intervention_affinity(world.params, i) for i in world.interventions}
    assert len(affinities) == 4
    assert all(0.5 <= a <= 2.2 for a in affinities.values())


def test_affinities_vary_across_worlds() -> None:
    worlds = [generate_world(s) for s in range(1, 31)]
    for field in ("shipping_affinity", "clearance_affinity", "pct_affinity", "bundle_affinity"):
        values = {getattr(w.params, field) for w in worlds}
        assert len(values) > 20, f"{field} barely varies"


def _fidelity(signal_present: list[bool], latent_high: list[bool]) -> tuple[float, float]:
    tp = [s for s, h in zip(signal_present, latent_high) if h]
    fp = [s for s, h in zip(signal_present, latent_high) if not h]
    return (sum(tp) / len(tp) if tp else 0.0, sum(fp) / len(fp) if fp else 0.0)


def test_signals_are_informative_but_not_decisive() -> None:
    """~78% true-positive / ~18% false-positive, measured over 300 worlds.

    Both bounds matter. A signal that always fired would let the agent read the
    latent off the text and skip the experiment. One that fired at random would
    make the context decoration, and an LLM reading it could not beat a baseline
    that ignores it.
    """
    # 150 worlds: enough for the fidelity bounds below, and worlds now carry
    # ~20k customers each, so generation cost is no longer negligible.
    worlds = [generate_world(s) for s in range(1, 151)]

    ship_signal = [vocab.SIGNAL_SHIPPING_THRESHOLD in w.semantic.customer_service_themes for w in worlds]
    ship_latent = [w.params.shipping_affinity > _AFFINITY_SIGNAL_THRESHOLD for w in worlds]
    tp, fp = _fidelity(ship_signal, ship_latent)
    assert 0.65 <= tp <= 0.90, f"shipping signal true-positive rate {tp:.2f}"
    assert 0.08 <= fp <= 0.30, f"shipping signal false-positive rate {fp:.2f}"

    war_signal = [vocab.SIGNAL_COMPETITOR_PRICE_WAR in w.semantic.competitor_events for w in worlds]
    war_latent = [w.params.competitive_pressure for w in worlds]
    tp, fp = _fidelity(war_signal, war_latent)
    assert 0.65 <= tp <= 0.90, f"price-war signal true-positive rate {tp:.2f}"
    assert 0.08 <= fp <= 0.30, f"price-war signal false-positive rate {fp:.2f}"


def test_price_war_signal_tracks_a_real_elasticity_shift() -> None:
    """The coupling has to be causal, not cosmetic."""
    worlds = [generate_world(s) for s in range(1, 121)]
    under_pressure = [w.params.elasticity_mean for w in worlds if w.params.competitive_pressure]
    calm = [w.params.elasticity_mean for w in worlds if not w.params.competitive_pressure]
    assert np.mean(under_pressure) < np.mean(calm), "price war must raise price sensitivity"


def test_coupled_signals_are_not_also_drawn_as_distractors() -> None:
    """A false positive must be uninformative, not a near-duplicate of the signal."""
    assert vocab.SIGNAL_COMPETITOR_PRICE_WAR not in vocab.COMPETITOR_EVENTS
    assert vocab.SIGNAL_SHIPPING_THRESHOLD not in vocab.CUSTOMER_SERVICE_THEMES
    assert vocab.SIGNAL_CONVERSION_DRIFT not in vocab.TRADING_NOTES


def test_clearance_signal_is_decided_once_per_world() -> None:
    """Per-note emission would compound to ~100%/58% effective fidelity.

    With four ageing SKUs, a per-note draw at 0.78/0.18 gives a world-level rate
    of 1-(1-p)^4 — handing the latent over outright on high worlds and flooding
    the low ones with false positives. Caught by measurement, not by review.
    """
    # 150 worlds: enough for the fidelity bounds below, and worlds now carry
    # ~20k customers each, so generation cost is no longer negligible.
    worlds = [generate_world(s) for s in range(1, 151)]
    signal = [
        any(vocab.SIGNAL_CLEARS_WHEN_DISCOUNTED in note for note in w.semantic.inventory_notes)
        for w in worlds
    ]
    latent = [w.params.clearance_affinity > _AFFINITY_SIGNAL_THRESHOLD for w in worlds]
    tp, fp = _fidelity(signal, latent)
    assert 0.65 <= tp <= 0.90, f"clearance signal true-positive rate {tp:.2f}"
    assert 0.08 <= fp <= 0.30, f"clearance signal false-positive rate {fp:.2f}"

    # And it appears at most once, so its presence is one bit, not a count.
    for world in worlds[:40]:
        hits = sum(
            vocab.SIGNAL_CLEARS_WHEN_DISCOUNTED in note for note in world.semantic.inventory_notes
        )
        assert hits <= 1
