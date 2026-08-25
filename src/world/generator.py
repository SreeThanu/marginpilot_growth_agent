"""Sample a merchant world, and its sealed potential outcomes, from a seed.

``generate_world(seed)`` is a pure function: the same seed produces a
byte-identical world, semantic text included. Randomness comes from
``numpy.random.default_rng`` with independent child streams spawned from a
``SeedSequence``, so adding a sampling step to one section cannot shift the
draws of another. Python's built-in ``hash()`` is never used for anything
generative — string hashing is salted per process and would break reproducibility
across runs.

Parameter ranges and their sourcing live in ``docs/simulator.md``. That document
was written before this module, deliberately: it is the defence against "you
built the world to win", and it is worth nothing if it is written afterwards to
describe whatever the code happened to do.

Response model
--------------
A customer ``i`` offered intervention ``j`` converts with probability::

    lift  = (1 - d_ij) ** eps_i - 1          # constant-elasticity demand
    p1_ij = clip(p0_i * (1 + s_i * lift), 0, 0.98)

``s_i`` scales the *lift* rather than the level, so a zero-depth intervention
leaves the customer exactly at baseline. ``s_i`` and ``eps_i`` both vary across
customers within a world: treatment-effect heterogeneity has to be real at the
individual level or uplift modelling and every heterogeneity finding downstream
is measuring noise.

Both potential outcomes are drawn under **common random numbers** — one uniform
per customer decides ``Y(0)`` and ``Y(1)`` alike — so the individual effect is
well defined and monotone rather than an artefact of two independent coin flips.

Simplification, stated openly: one basket-level contribution margin (the
catalogue mean) is used for both arms rather than re-weighting the basket toward
promoted SKUs. Margin-mix shift is a real effect, but modelling it here would
make measured incremental contribution differ from the hand-computed arithmetic
in the README and in ``src/economics/``, and those hand-checks are worth more to
this project than the extra realism.
"""

from __future__ import annotations

import numpy as np

from src.world import vocabulary as vocab
from src.world.schema import (
    SCHEMA_VERSION,
    Customer,
    GroundTruth,
    Intervention,
    InterventionKind,
    PotentialOutcome,
    PotentialOutcomePair,
    Product,
    Segment,
    SemanticContext,
    World,
    WorldParams,
)

#: Bumped when sampling logic changes in a way that alters worlds for a fixed
#: seed. Recorded in every world so a stale file is detectable.
GENERATOR_VERSION = "3.0.0"

# Child-stream indices. Fixed positions, never reordered: reordering would
# silently change every world ever generated from a given seed.
_STREAM_PARAMS = 0
_STREAM_SEMANTIC = 1
_STREAM_CATALOGUE = 2
_STREAM_SEGMENTS = 3
_STREAM_CUSTOMERS = 4
_STREAM_INTERVENTIONS = 5
_STREAM_OUTCOMES = 6
_N_STREAMS = 7


def _streams(seed: int) -> list[np.random.Generator]:
    return [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(_N_STREAMS)]


def _round(value: float, places: int = 6) -> float:
    """Round before storing.

    Serialization must be byte-stable, and rounding keeps the JSON free of
    17-digit float tails that make diffs between worlds unreadable.
    """
    return float(np.round(value, places))


# --------------------------------------------------------------------------- #
# Structural parameters — ranges from docs/simulator.md
# --------------------------------------------------------------------------- #


#: Probability the price-war latent is set.
_LATENT_PREVALENCE = 0.35

#: Per-intervention affinities are lognormal around 1.0. Sigma sets how strongly
#: worlds differ in which promotion suits them; the clip keeps the tail from
#: pushing customers into the saturation cap en masse.
_AFFINITY_SIGMA = 0.45
_AFFINITY_CLIP = (0.5, 2.2)

#: A signal is emitted for an affinity above this. Below it the world has no
#: particular preference and there is nothing to hint at.
_AFFINITY_SIGNAL_THRESHOLD = 1.25

#: Fidelity of the semantic signal emitted from a hidden latent: the chance the
#: signal appears when the latent is high, and the chance it appears anyway when
#: it is not. Context that shifts the prior without settling the question.
_SIGNAL_TRUE_POSITIVE = 0.78
_SIGNAL_FALSE_POSITIVE = 0.18


def _affinity(rng: np.random.Generator) -> float:
    """One world's hidden response multiplier for one intervention kind."""
    return _round(float(np.clip(rng.lognormal(0.0, _AFFINITY_SIGMA), *_AFFINITY_CLIP)))


def _sample_params(rng: np.random.Generator, seasonality_index: float) -> WorldParams:
    margin_mean = _round(rng.uniform(0.22, 0.38))

    # Hidden latents. Drawn before the observable parameters they modify so that
    # the semantic emission and the behaviour both descend from one draw.
    competitive_pressure = bool(rng.random() < _LATENT_PREVALENCE)
    elasticity_mean = rng.uniform(-3.5, -1.2)
    if competitive_pressure:
        # A price war really does make the market more price-sensitive. This is
        # the coupling: the competitor event in the semantic context is emitted
        # from this same flag, at partial fidelity.
        elasticity_mean *= 1.35

    baseline_conversion = _round(rng.uniform(0.06, 0.20))
    aov_median = _round(rng.uniform(500.0, 2500.0), 2)
    aov_sigma = _round(rng.uniform(0.35, 0.75))
    n_customers = int(rng.integers(12_000, 28_001))

    # Budget is a share of the revenue this world actually turns over in one
    # experiment window, not a fixed rupee figure. A flat budget is either
    # trivial for a large merchant or ruinous for a small one, and — more
    # importantly — a budget unrelated to world scale cannot fund an experiment
    # large enough to resolve the contribution question it is meant to answer.
    mean_basket = aov_median * float(np.exp(aov_sigma**2 / 2.0))
    projected_revenue = n_customers * baseline_conversion * seasonality_index * mean_basket
    budget_share = _round(rng.uniform(0.05, 0.15))

    return WorldParams(
        baseline_conversion=baseline_conversion,
        elasticity_mean=_round(max(elasticity_mean, -5.0)),
        elasticity_sd=_round(rng.uniform(0.30, 0.90)),
        responsiveness_sigma=_round(rng.uniform(0.25, 0.60)),
        promo_response_scale=_round(rng.uniform(0.9, 2.1)),
        competitive_pressure=competitive_pressure,
        shipping_affinity=_affinity(rng),
        clearance_affinity=_affinity(rng),
        pct_affinity=_affinity(rng),
        bundle_affinity=_affinity(rng),
        aov_median_inr=aov_median,
        aov_sigma=aov_sigma,
        margin_mean=margin_mean,
        margin_sd=_round(rng.uniform(0.03, 0.08)),
        cannibalization_rate=_round(rng.uniform(0.15, 0.45)),
        seasonality_index=_round(seasonality_index),
        projected_revenue_inr=_round(projected_revenue, 2),
        budget_share_of_revenue=budget_share,
        promotion_budget_inr=_round(round(projected_revenue * budget_share, -3), 2),
        n_customers=n_customers,
        experiment_window_days=int(rng.integers(14, 43)),
    )


# --------------------------------------------------------------------------- #
# Semantic context
# --------------------------------------------------------------------------- #


def _choose(rng: np.random.Generator, items: tuple, size: int, replace: bool = False) -> list:
    """Choose ``size`` items by index.

    Indices rather than ``rng.choice(items)`` because NumPy would coerce tuples
    of strings into an array and, for the nested tables here, into something
    with a surprising dtype.
    """
    idx = rng.choice(len(items), size=min(size, len(items)), replace=replace)
    return [items[int(i)] for i in idx]


def _sample_catalogue(
    rng: np.random.Generator, vertical: str, params: WorldParams
) -> tuple[Product, ...]:
    """Sample the catalogue *from the world's own parameters*.

    Prices are centred on the world's AOV and margins on its margin mean, so a
    world's stated structural parameters describe the catalogue it actually has.
    Sampling the two independently would put a lie in every world file.
    """
    table = vocab.VERTICALS[vertical]
    n_products = int(rng.integers(12, 31))
    products: list[Product] = []
    for index in range(n_products):
        noun = table["nouns"][int(rng.integers(0, len(table["nouns"])))]
        category = table["categories"][int(rng.integers(0, len(table["categories"])))]
        variant = _choose(rng, ("Classic", "Everyday", "Premium", "Mini", "Pro", "Gift"), 1)[0]
        name = f"{variant} {noun}".strip()

        # A basket holds one to two items on average, so unit prices sit below AOV.
        price = float(np.round(rng.lognormal(mean=np.log(params.aov_median_inr * 0.75), sigma=0.5), 2))
        price = float(min(max(price, 99.0), 20_000.0))
        margin = float(min(max(rng.normal(params.margin_mean, params.margin_sd), 0.15), 0.50))
        cost = float(np.round(price * (1.0 - margin), 2))

        age_days = int(rng.integers(3, 420))
        if age_days < 30:
            status = "fresh"
        elif age_days < 90:
            status = "steady"
        elif age_days < 180:
            status = "aging"
        elif age_days < 300:
            status = "overstocked"
        else:
            status = "clearance"

        detail = _choose(rng, vocab.PRODUCT_DETAILS, 1)[0]
        movement = _choose(rng, vocab.STOCK_STATUS_NOTES[status], 1)[0]
        template = _choose(rng, vocab.PRODUCT_DESCRIPTION_TEMPLATES, 1)[0]
        description = template.format(
            name=name,
            detail=detail,
            movement=movement[0].upper() + movement[1:],
            movement_lower=movement,
            age_phrase=f"{age_days} days ago",
        )

        products.append(
            Product(
                product_id=f"sku_{index:03d}",
                name=name,
                category=category,
                description=description,
                unit_price_inr=price,
                unit_cost_inr=cost,
                inventory_units=int(rng.integers(20, 2400)),
                inventory_age_days=age_days,
                stock_status=status,
            )
        )
    return tuple(products)


def _sample_calendar(rng: np.random.Generator) -> tuple[tuple[str, ...], float]:
    """Choose the trading calendar and the seasonality index it implies.

    The index is derived from the events actually chosen rather than sampled
    independently, so a world that says "Diwali gifting season" also *behaves*
    like one. Context that contradicted the simulator would make the reasoning
    task unlearnable rather than hard.

    Drawn before the catalogue because the world's structural parameters depend
    on it, and the catalogue depends on those.
    """
    events = _choose(rng, vocab.SEASONAL_EVENTS, int(rng.integers(1, 4)))
    index = float(min(max(np.mean([mult for _, mult in events]), 0.85), 1.35))
    return tuple(text for text, _ in events), index


def _emit_signal(rng: np.random.Generator, latent_is_high: bool) -> bool:
    """Should the semantic signal for this latent appear?

    Partial fidelity on purpose. A signal that appeared exactly when its latent
    was high would let the agent read the latent off the text and skip the
    experiment; a signal uncorrelated with it would be decoration. Emitting at
    ~78% true-positive / ~18% false-positive shifts the prior without settling
    the question, which is the only regime where running the experiment is still
    the rational move.
    """
    threshold = _SIGNAL_TRUE_POSITIVE if latent_is_high else _SIGNAL_FALSE_POSITIVE
    return bool(rng.random() < threshold)


def _sample_semantic(
    rng: np.random.Generator,
    vertical: str,
    products: tuple[Product, ...],
    seasonal_events: tuple[str, ...],
    params: WorldParams,
) -> SemanticContext:
    """Assemble the human-readable business context from templates.

    Four strings are emitted from hidden latents rather than drawn at random —
    see :func:`_emit_signal`. Each points at something the agent-facing view does
    not expose (market elasticity, per-intervention response affinity, true
    baseline conversion) rather than at an observable like margin or AOV, which
    structural features already carry and which text would merely restate.
    """
    table = vocab.VERTICALS[vertical]
    brand = table["brand_words"][int(rng.integers(0, len(table["brand_words"])))]
    suffix = _choose(rng, vocab.MERCHANT_SUFFIXES, 1)[0]
    merchant_name = f"{brand}{suffix}"

    categories = sorted({p.category for p in products})
    top_category = _choose(rng, tuple(categories), 1)[0]
    thin_category = _choose(rng, tuple(categories), 1)[0]
    description = _choose(rng, vocab.MERCHANT_DESCRIPTION_TEMPLATES, 1)[0].format(
        name=merchant_name,
        age=int(rng.integers(2, 12)),
        vertical_phrase=vocab.VERTICAL_PHRASES[vertical],
        n_products=len(products),
        top_category=top_category,
        thin_category=thin_category,
        skew_phrase=_choose(rng, vocab.SKEW_PHRASES, 1)[0],
    )

    aging = [p for p in products if p.stock_status in ("aging", "overstocked", "clearance")]
    flagged = _choose(rng, tuple(aging), min(4, len(aging))) if aging else []
    # Decided ONCE per world, then attached to a single note. Emitting per note
    # would compound: with four ageing SKUs, a per-note draw at 0.78/0.18 yields
    # an effective world-level fidelity of 1-(1-p)^4, i.e. ~100%/58% — which
    # would hand the agent the latent outright on high worlds and flood the low
    # ones with false positives.
    emit_clearance = _emit_signal(rng, params.clearance_affinity > _AFFINITY_SIGNAL_THRESHOLD)
    signal_index = int(rng.integers(0, len(flagged))) if flagged else -1

    notes: list[str] = []
    for position, product in enumerate(flagged):
        status_note = _choose(rng, vocab.STOCK_STATUS_NOTES[product.stock_status], 1)[0]
        # Coupled to clearance affinity: a hidden multiplier on flat-discount
        # response. Ageing stock is visible to everyone; whether discounting it
        # actually moves it is not.
        if emit_clearance and position == signal_index:
            status_note = f"{status_note}, and {vocab.SIGNAL_CLEARS_WHEN_DISCOUNTED}"
        notes.append(
            _choose(rng, vocab.INVENTORY_NOTE_TEMPLATES, 1)[0].format(
                product=product.name,
                age=product.inventory_age_days,
                status_note=status_note,
            )
        )
    inventory_notes = tuple(notes) or ("No SKU is currently flagged for stock age.",)

    # Coupled signals first, then distractors drawn from pools the signals were
    # held out of — so a false positive is genuinely uninformative rather than a
    # near-duplicate of the real thing.
    competitor_events = _choose(rng, vocab.COMPETITOR_EVENTS, int(rng.integers(1, 3)))
    if _emit_signal(rng, params.competitive_pressure):
        competitor_events.insert(0, vocab.SIGNAL_COMPETITOR_PRICE_WAR)

    service_themes = _choose(rng, vocab.CUSTOMER_SERVICE_THEMES, int(rng.integers(2, 4)))
    if _emit_signal(rng, params.shipping_affinity > _AFFINITY_SIGNAL_THRESHOLD):
        service_themes.insert(0, vocab.SIGNAL_SHIPPING_THRESHOLD)

    trading = _choose(rng, vocab.TRADING_NOTES, int(rng.integers(2, 4)))
    # Coupled to true baseline conversion, which the agent never sees directly.
    if _emit_signal(rng, params.baseline_conversion < 0.11):
        trading.insert(0, vocab.SIGNAL_CONVERSION_DRIFT)

    return SemanticContext(
        merchant_name=merchant_name,
        vertical=vertical,
        merchant_description=description,
        seasonal_events=seasonal_events,
        competitor_events=tuple(competitor_events),
        customer_service_themes=tuple(service_themes),
        inventory_notes=inventory_notes,
        trading_notes=tuple(trading),
    )


# --------------------------------------------------------------------------- #
# Segments, customers, interventions
# --------------------------------------------------------------------------- #


def _sample_segments(rng: np.random.Generator) -> tuple[Segment, ...]:
    n_segments = int(rng.integers(4, 7))
    archetypes = _choose(rng, vocab.SEGMENT_ARCHETYPES, n_segments)
    shares = rng.dirichlet(np.full(n_segments, 2.5))
    return tuple(
        Segment(
            segment_id=f"seg_{index}",
            name=str(archetype["name"]),
            share=_round(float(share)),
            notes=str(archetype["notes"]),
            behaviour_tags=tuple(archetype["tags"]),  # type: ignore[arg-type]
            conversion_multiplier=float(archetype["conversion_multiplier"]),  # type: ignore[arg-type]
            elasticity_multiplier=float(archetype["elasticity_multiplier"]),  # type: ignore[arg-type]
            aov_multiplier=float(archetype["aov_multiplier"]),  # type: ignore[arg-type]
            responsiveness_mean=float(archetype["responsiveness_mean"]),  # type: ignore[arg-type]
        )
        for index, (archetype, share) in enumerate(zip(archetypes, shares))
    )


def _sample_customers(
    rng: np.random.Generator, params: WorldParams, segments: tuple[Segment, ...]
) -> tuple[Customer, ...]:
    shares = np.array([s.share for s in segments], dtype=float)
    shares = shares / shares.sum()
    assignments = rng.choice(len(segments), size=params.n_customers, p=shares)

    customers: list[Customer] = []
    for index in range(params.n_customers):
        segment = segments[int(assignments[index])]

        p0 = (
            params.baseline_conversion
            * params.seasonality_index
            * segment.conversion_multiplier
            * float(rng.lognormal(0.0, 0.25))
        )
        p0 = float(min(max(p0, 0.005), 0.60))

        elasticity = -abs(
            params.elasticity_mean * segment.elasticity_multiplier
            + float(rng.normal(0.0, params.elasticity_sd))
        )
        elasticity = float(min(max(elasticity, -5.0), -0.30))

        responsiveness = (
            segment.responsiveness_mean
            * params.promo_response_scale
            * float(rng.lognormal(0.0, params.responsiveness_sigma))
        )
        responsiveness = float(min(max(responsiveness, 0.05), 12.0))

        order_value = (
            params.aov_median_inr
            * segment.aov_multiplier
            * float(rng.lognormal(0.0, params.aov_sigma))
        )
        order_value = float(min(max(order_value, 99.0), 50_000.0))

        customers.append(
            Customer(
                customer_id=f"cust_{index:05d}",
                segment_id=segment.segment_id,
                baseline_purchase_prob=_round(p0),
                price_elasticity=_round(elasticity),
                responsiveness=_round(responsiveness),
                expected_order_value_inr=_round(order_value, 2),
                tenure_days=int(rng.integers(1, 1460)),
                orders_last_90d=int(rng.poisson(2.0)),
                days_since_last_order=int(rng.integers(0, 400)),
            )
        )
    return tuple(customers)


#: Depth as a multiple of contribution margin, per intervention kind.
#:
#: Anchored to **margin**, deliberately not to break-even. Break-even depth is
#: ``margin x (incremental / treated)``, which contains the true treatment
#: effect; sampling ``d = k x d*`` would make ``d / margin`` an observable
#: readout of ``incr/treat``, and a baseline could then rank interventions by
#: profitability without running a single experiment. That artefact would be
#: worse than the one it fixed.
#:
#: The offsets keep free shipping trending shallow and bundles deep, as in
#: retail practice, while every range straddles the break-even line so that no
#: kind is dominated by construction. Calibrated on dev worlds only.
DEPTH_MULTIPLE_OF_MARGIN: dict[InterventionKind, tuple[float, float]] = {
    InterventionKind.FLAT_DISCOUNT: (0.07, 0.29),
    InterventionKind.PERCENTAGE_DISCOUNT: (0.07, 0.30),
    InterventionKind.FREE_SHIPPING: (0.06, 0.25),
    InterventionKind.BUNDLE: (0.09, 0.34),
}


def _sample_interventions(
    rng: np.random.Generator, products: tuple[Product, ...], params: WorldParams
) -> tuple[Intervention, ...]:
    """Exactly four interventions, one per kind.

    Each magnitude is set so the intervention's depth lands at ``j x margin``
    with ``j`` drawn from :data:`DEPTH_MULTIPLE_OF_MARGIN`. Rupee-denominated
    kinds convert through the world's AOV, so a flat discount is a comparable
    proposition in a Rs.600-AOV store and a Rs.2,400-AOV one.

    The generator never forces a policy violation: depths stay below the ceiling
    Day 7 will enforce, so violations have to originate in an agent proposal or
    the adversarial scenarios would be testing the simulator instead of the agent.
    """
    aging = [p for p in products if p.stock_status in ("aging", "overstocked", "clearance")]
    pool = aging or list(products)

    def targets(n: int) -> tuple[str, ...]:
        chosen = _choose(rng, tuple(pool), min(n, len(pool)))
        return tuple(sorted(p.product_id for p in chosen))

    def depth_for(kind: InterventionKind) -> float:
        low, high = DEPTH_MULTIPLE_OF_MARGIN[kind]
        return float(rng.uniform(low, high)) * params.margin_mean

    # Rupee-denominated offers convert through the MEAN basket, not the median.
    # Order values are lognormal, so anchoring a rupee amount to the median makes
    # its realized depth land systematically shallower than a percentage offer of
    # the same nominal j — which would hand flat discounts and free shipping an
    # advantage that is an artefact of the parameterization rather than a fact
    # about retail.
    mean_basket = params.aov_median_inr * float(np.exp(params.aov_sigma**2 / 2.0))

    flat = float(np.clip(np.round(depth_for(InterventionKind.FLAT_DISCOUNT) * mean_basket, -1), 20.0, 2000.0))
    pct = _round(depth_for(InterventionKind.PERCENTAGE_DISCOUNT), 4)
    shipping = float(np.clip(np.round(depth_for(InterventionKind.FREE_SHIPPING) * mean_basket, -1), 20.0, 250.0))
    bundle_pct = _round(depth_for(InterventionKind.BUNDLE), 4)
    bundle_value = float(np.round(params.aov_median_inr * rng.uniform(0.15, 0.45), 2))

    return (
        Intervention(
            intervention_id="int_flat",
            kind=InterventionKind.FLAT_DISCOUNT,
            name=f"Rs.{flat:.0f} off",
            description=(
                f"A flat Rs.{flat:.0f} off the order, applied to a targeted product set. "
                "Deepest in relative terms for small baskets."
            ),
            target_product_ids=targets(4),
            flat_discount_inr=flat,
        ),
        Intervention(
            intervention_id="int_pct",
            kind=InterventionKind.PERCENTAGE_DISCOUNT,
            name=f"{pct * 100:.0f}% off",
            description=(
                f"{pct * 100:.0f}% off the order value on a targeted product set. "
                "Scales with basket size, so the cost is largest on the orders that "
                "were most likely to happen anyway."
            ),
            target_product_ids=targets(5),
            discount_pct=pct,
        ),
        Intervention(
            intervention_id="int_shipping",
            kind=InterventionKind.FREE_SHIPPING,
            name="Free shipping",
            description=(
                f"Waives the Rs.{shipping:.0f} shipping fee. A genuine price cut to the "
                "customer, booked by the merchant as a cost line rather than a discount."
            ),
            target_product_ids=targets(6),
            shipping_fee_waived_inr=shipping,
        ),
        Intervention(
            intervention_id="int_bundle",
            kind=InterventionKind.BUNDLE,
            name="Bundle offer",
            description=(
                f"Two frequently co-bought SKUs sold together at {bundle_pct * 100:.0f}% "
                f"off the combined price, adding about Rs.{bundle_value:.0f} of basket value."
            ),
            target_product_ids=targets(3),
            discount_pct=bundle_pct,
            bundle_added_value_inr=bundle_value,
        ),
    )


# --------------------------------------------------------------------------- #
# Response model — the single source of truth for treated conversion
# --------------------------------------------------------------------------- #


#: Asymptote of the demand-saturation curve: response approaches, but never
#: reaches, a tripling of conversion probability.
#:
#: Constant-elasticity demand is unbounded, and a deep discount priced by an
#: elastic customer implies conversion multiples no retailer has measured. The
#: earlier form was a hard ``min(x, 3.0)``, which bounded the tail by flattening
#: it: every customer past the threshold was assigned an identical response,
#: erasing exactly the individual variation uplift modelling exists to find. The
#: smooth form below bounds the same tail while keeping it ordered.
#:
#: **Assumption**, chosen for plausibility rather than estimated. Set on dev
#: worlds only, before any agent existed and before any holdout world was read.
RESPONSE_ASYMPTOTE = 3.0

#: Scale of the exponential approach. Equal to ``RESPONSE_ASYMPTOTE - 1`` so the
#: curve's slope at the origin is exactly 1, i.e. weak promotions behave exactly
#: as the unsaturated constant-elasticity model says they do. Saturation is then
#: something that only bites where the linear extrapolation was implausible.
_SATURATION_SCALE = RESPONSE_ASYMPTOTE - 1.0


def response_multiplier(raw_response: float) -> float:
    """Saturating map from raw response to a conversion multiplier.

    ``m(x) = 1 + A(1 - exp(-x/A))`` with ``A = RESPONSE_ASYMPTOTE - 1``.

    * ``m(0) = 1`` — no promotion, no effect.
    * ``m'(0) = 1`` — agrees with the unsaturated model to first order, so the
      elasticity ranges from the literature still mean what they say.
    * ``m(x) -> RESPONSE_ASYMPTOTE`` as ``x -> inf``, never reaching it.
    * strictly increasing everywhere, so two customers who differ in response
      still differ after saturation. Nothing clips.
    """
    return 1.0 + _SATURATION_SCALE * (1.0 - float(np.exp(-raw_response / _SATURATION_SCALE)))


def intervention_affinity(params: WorldParams, intervention: Intervention) -> float:
    """Hidden per-intervention response multiplier for this world.

    All four kinds carry one. Depth is observable, so if depth alone decided
    which promotion pays, a baseline could rank the four without running an
    experiment — the same leak that ruled out anchoring depth to break-even.
    Affinity moves the decision into a latent the agent can only reach by
    measuring, and which two semantic signals hint at imperfectly.
    """
    return {
        InterventionKind.FREE_SHIPPING: params.shipping_affinity,
        InterventionKind.FLAT_DISCOUNT: params.clearance_affinity,
        InterventionKind.PERCENTAGE_DISCOUNT: params.pct_affinity,
        InterventionKind.BUNDLE: params.bundle_affinity,
    }[intervention.kind]


def treated_conversion_probability(
    customer: Customer,
    intervention: Intervention,
    order_value_inr: float,
    affinity: float = 1.0,
) -> float:
    """Probability this customer converts under this intervention.

    Public because the sanity report needs the same curve the outcome draw uses.
    Two implementations of one demand model would drift, and the report's job is
    to tell you whether the worlds look like retail — which it cannot do if it is
    describing a different world than the one on disk.

    ``affinity`` is the world's hidden multiplier for this intervention kind;
    callers get it from :func:`intervention_affinity`.
    """
    depth = intervention.effective_depth(order_value_inr)
    lift = (1.0 - depth) ** customer.price_elasticity - 1.0
    multiplier = response_multiplier(customer.responsiveness * affinity * max(lift, 0.0))

    # Applied to the *no-purchase* probability rather than as a bare multiple of
    # p0. For small p0 this is p0 * m to first order, so the multiplicative
    # reading still holds; for large p0 it approaches 1 smoothly instead of
    # needing a clip at 0.98. The probability bound is then a property of the
    # functional form, not a ceiling that flattens the customers who hit it.
    p1 = 1.0 - (1.0 - customer.baseline_purchase_prob) ** multiplier
    return float(min(max(p1, 0.0), 1.0))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def generate_world(seed: int, *, split: str = "dev") -> World:
    """Sample a world. Pure function of ``seed``; ``split`` is only a label."""
    streams = _streams(seed)
    vertical_rng = streams[_STREAM_PARAMS]
    vertical = sorted(vocab.VERTICALS)[int(vertical_rng.integers(0, len(vocab.VERTICALS)))]

    # Order matters: the calendar sets seasonality, seasonality feeds the
    # structural parameters, and the catalogue is drawn from those parameters so
    # that a world's stated numbers describe the world it actually is.
    seasonal_events, seasonality_index = _sample_calendar(streams[_STREAM_SEMANTIC])
    params = _sample_params(streams[_STREAM_PARAMS], seasonality_index)
    products = _sample_catalogue(streams[_STREAM_CATALOGUE], vertical, params)
    semantic = _sample_semantic(
        streams[_STREAM_SEMANTIC], vertical, products, seasonal_events, params
    )
    segments = _sample_segments(streams[_STREAM_SEGMENTS])
    customers = _sample_customers(streams[_STREAM_CUSTOMERS], params, segments)
    interventions = _sample_interventions(streams[_STREAM_INTERVENTIONS], products, params)

    return World(
        world_id=f"world_{seed:05d}",
        seed=seed,
        split=split,
        schema_version=SCHEMA_VERSION,
        params=params,
        semantic=semantic,
        segments=segments,
        products=products,
        customers=customers,
        interventions=interventions,
    )


def generate_ground_truth(world: World) -> GroundTruth:
    """Draw ``Y(0)`` and ``Y(1)`` for every customer x intervention.

    Sealed output: visible to ``src/eval/`` only (CLAUDE.md invariant 8). It is
    written to a separate file from the world so that an agent-facing loader
    physically cannot read it, not merely so that it promises not to.
    """
    rng = _streams(world.seed)[_STREAM_OUTCOMES]
    catalogue_margin = float(np.mean([p.contribution_margin for p in world.products]))

    n = len(world.customers)
    # Common random numbers: one uniform per customer decides both arms.
    conversion_draws = rng.random(n)
    basket_noise = rng.lognormal(0.0, 0.20, size=n)
    # One pull-forward draw per customer per intervention, drawn up front so the
    # stream does not depend on how many customers happen to convert.
    pull_forward_draws = rng.random((n, len(world.interventions)))

    outcomes: dict[str, dict[str, PotentialOutcomePair]] = {}
    for index, customer in enumerate(world.customers):
        u = float(conversion_draws[index])
        basket = _round(customer.expected_order_value_inr * float(basket_noise[index]), 2)

        converted0 = u < customer.baseline_purchase_prob
        y0 = PotentialOutcome(
            converted=converted0,
            order_value_inr=basket if converted0 else 0.0,
            contribution_inr=_round(basket * catalogue_margin, 2) if converted0 else 0.0,
        )

        per_intervention: dict[str, PotentialOutcomePair] = {}
        for j, intervention in enumerate(world.interventions):
            treated_basket = basket
            if intervention.kind is InterventionKind.BUNDLE:
                treated_basket = _round(basket + (intervention.bundle_added_value_inr or 0.0), 2)

            p1 = treated_conversion_probability(
                customer,
                intervention,
                treated_basket,
                affinity=intervention_affinity(world.params, intervention),
            )
            converted1 = u < p1

            contribution1 = _round(treated_basket * catalogue_margin, 2) if converted1 else 0.0
            # An order that is pulled forward rather than created adds no net
            # contribution: the customer would have bought later anyway. Applied
            # only to genuinely incremental conversions.
            if (
                converted1
                and not converted0
                and float(pull_forward_draws[index, j]) < world.params.cannibalization_rate
            ):
                contribution1 = 0.0

            per_intervention[intervention.intervention_id] = PotentialOutcomePair(
                y0=y0,
                y1=PotentialOutcome(
                    converted=converted1,
                    order_value_inr=treated_basket if converted1 else 0.0,
                    contribution_inr=contribution1,
                ),
            )
        outcomes[customer.customer_id] = per_intervention

    return GroundTruth(
        world_id=world.world_id,
        seed=world.seed,
        schema_version=SCHEMA_VERSION,
        outcomes=outcomes,
    )


def generate(seed: int, *, split: str = "dev") -> tuple[World, GroundTruth]:
    """A world and its sealed ground truth, in one deterministic call."""
    world = generate_world(seed, split=split)
    return world, generate_ground_truth(world)
