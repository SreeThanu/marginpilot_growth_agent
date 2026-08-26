"""Dataclasses describing a generated world and its sealed ground truth.

Two objects come out of the generator and they are deliberately *not* connected:

* :class:`World` — the merchant: catalogue, customers, segments, interventions,
  semantic context, and the structural parameters that produced them.
* :class:`GroundTruth` — the potential outcomes ``Y(0)``/``Y(1)`` for every
  customer x intervention.

``World`` holds no reference to ``GroundTruth`` and there is no attribute,
property or method on ``World`` that can reach it. That is the first line of
defence for CLAUDE.md invariant 8: ground truth is visible to ``src/eval/``
only, and no agent tool may ever return it, directly or derived. The second line
is the caller guard in :mod:`src.world.persistence`, the third is the static
scan in ``tests/test_ground_truth_isolation.py``.

A note on ``World.params``: those are the *true* structural parameters of the
merchant — true baseline conversion, true elasticity, true budget. They are here
because the simulator and the evaluation harness need them. They are not the
agent's view of the world. The agent-facing projection (noisy observed metrics,
segments, product context, semantic notes) is the tool layer's job on Day 6, and
it must not simply hand ``params`` over.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

# Bumped whenever the on-disk shape changes. Persistence refuses to load a world
# written by a different major schema rather than silently mis-parsing it.
SCHEMA_VERSION = "4.0.0"


class InterventionKind(str, Enum):
    """The four promotion types. CLAUDE.md's locked list caps this at ~4.

    More kinds would widen the agent's action space without testing anything the
    existing four do not already test, so additions need an explicit reason.
    """

    FLAT_DISCOUNT = "flat_discount"
    PERCENTAGE_DISCOUNT = "percentage_discount"
    FREE_SHIPPING = "free_shipping"
    BUNDLE = "bundle"


# --------------------------------------------------------------------------- #
# Semantic context — the LLM's reasoning surface
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SemanticContext:
    """Human-readable business context attached to a world.

    This exists so the agent faces a genuine reasoning problem over unstructured
    merchant context rather than a menu of enumerable options. It is generated
    from templates and a controlled vocabulary — never by calling an LLM, which
    would make worlds non-deterministic, slow and expensive to regenerate.
    """

    merchant_name: str
    vertical: str
    merchant_description: str
    #: Named trading events in the window ("Ganesh Chaturthi gifting peak").
    seasonal_events: tuple[str, ...]
    #: What competitors are visibly doing. Sometimes a red herring, by design.
    competitor_events: tuple[str, ...]
    #: Recurring themes from support tickets ("customers ask if shipping is free
    #: above a threshold"). A hint at which intervention might land.
    customer_service_themes: tuple[str, ...]
    #: Qualitative inventory commentary, e.g. ageing stock that wants clearing.
    inventory_notes: tuple[str, ...]
    #: Recent trading commentary a merchant would write in a weekly review.
    trading_notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "merchant_name": self.merchant_name,
            "vertical": self.vertical,
            "merchant_description": self.merchant_description,
            "seasonal_events": list(self.seasonal_events),
            "competitor_events": list(self.competitor_events),
            "customer_service_themes": list(self.customer_service_themes),
            "inventory_notes": list(self.inventory_notes),
            "trading_notes": list(self.trading_notes),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SemanticContext":
        return cls(
            merchant_name=raw["merchant_name"],
            vertical=raw["vertical"],
            merchant_description=raw["merchant_description"],
            seasonal_events=tuple(raw["seasonal_events"]),
            competitor_events=tuple(raw["competitor_events"]),
            customer_service_themes=tuple(raw["customer_service_themes"]),
            inventory_notes=tuple(raw["inventory_notes"]),
            trading_notes=tuple(raw["trading_notes"]),
        )


# --------------------------------------------------------------------------- #
# Catalogue, customers, segments
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Product:
    """One SKU.

    ``inventory_age_days`` and ``stock_status`` are carried because ageing stock
    is a legitimate business reason to promote — and a reason the agent can only
    find by reading context rather than by scanning numeric fields.
    """

    product_id: str
    name: str
    category: str
    description: str
    unit_price_inr: float
    unit_cost_inr: float
    inventory_units: int
    inventory_age_days: int
    #: Controlled vocabulary: fresh | steady | aging | overstocked | clearance.
    stock_status: str

    @property
    def contribution_margin(self) -> float:
        """Fraction of price that survives cost of goods."""
        if self.unit_price_inr <= 0:
            return 0.0
        return (self.unit_price_inr - self.unit_cost_inr) / self.unit_price_inr

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "unit_price_inr": self.unit_price_inr,
            "unit_cost_inr": self.unit_cost_inr,
            "inventory_units": self.inventory_units,
            "inventory_age_days": self.inventory_age_days,
            "stock_status": self.stock_status,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Product":
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class Segment:
    """A customer segment: quantitative behaviour plus a qualitative note.

    ``notes`` is the field that makes segments a reasoning problem — "bulk
    buyers, price-insensitive, order on salary week" tells the agent something
    the multipliers alone do not spell out.
    """

    segment_id: str
    name: str
    share: float
    notes: str
    behaviour_tags: tuple[str, ...]
    conversion_multiplier: float
    elasticity_multiplier: float
    aov_multiplier: float
    #: Mean promo-responsiveness for the segment; individual customers vary
    #: around it, which is where within-world heterogeneity comes from.
    responsiveness_mean: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "name": self.name,
            "share": self.share,
            "notes": self.notes,
            "behaviour_tags": list(self.behaviour_tags),
            "conversion_multiplier": self.conversion_multiplier,
            "elasticity_multiplier": self.elasticity_multiplier,
            "aov_multiplier": self.aov_multiplier,
            "responsiveness_mean": self.responsiveness_mean,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Segment":
        return cls(
            segment_id=raw["segment_id"],
            name=raw["name"],
            share=raw["share"],
            notes=raw["notes"],
            behaviour_tags=tuple(raw["behaviour_tags"]),
            conversion_multiplier=raw["conversion_multiplier"],
            elasticity_multiplier=raw["elasticity_multiplier"],
            aov_multiplier=raw["aov_multiplier"],
            responsiveness_mean=raw["responsiveness_mean"],
        )


@dataclass(frozen=True, slots=True)
class Customer:
    """One customer's latent parameters.

    ``price_elasticity`` and ``responsiveness`` vary per customer, not just per
    world. Treatment-effect heterogeneity within a world is the property uplift
    modelling depends on, and it cannot be added later without invalidating any
    world the agent has already been tuned against.
    """

    customer_id: str
    segment_id: str
    baseline_purchase_prob: float
    price_elasticity: float
    responsiveness: float
    expected_order_value_inr: float
    tenure_days: int
    orders_last_90d: int
    days_since_last_order: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "segment_id": self.segment_id,
            "baseline_purchase_prob": self.baseline_purchase_prob,
            "price_elasticity": self.price_elasticity,
            "responsiveness": self.responsiveness,
            "expected_order_value_inr": self.expected_order_value_inr,
            "tenure_days": self.tenure_days,
            "orders_last_90d": self.orders_last_90d,
            "days_since_last_order": self.days_since_last_order,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Customer":
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class Intervention:
    """A promotion the merchant could run.

    Magnitude lives in the field matching ``kind``; the others are ``None``.
    Explicit optional fields are used rather than a free-form params mapping so
    that a malformed intervention fails at construction, not at simulation.
    """

    intervention_id: str
    kind: InterventionKind
    name: str
    description: str
    target_product_ids: tuple[str, ...]
    flat_discount_inr: float | None = None
    discount_pct: float | None = None
    shipping_fee_waived_inr: float | None = None
    bundle_added_value_inr: float | None = None

    def effective_depth(self, order_value_inr: float) -> float:
        """Discount depth ``d`` this intervention represents for a basket.

        Everything is expressed as a fraction of basket value so one demand
        curve, ``(1 - d) ** elasticity``, covers all four kinds. Free shipping
        is a genuine price cut to the customer even though the merchant books it
        as a cost line, which is why it maps onto the same curve.
        """
        if order_value_inr <= 0:
            return 0.0
        if self.kind is InterventionKind.FLAT_DISCOUNT:
            depth = (self.flat_discount_inr or 0.0) / order_value_inr
        elif self.kind is InterventionKind.PERCENTAGE_DISCOUNT:
            depth = self.discount_pct or 0.0
        elif self.kind is InterventionKind.FREE_SHIPPING:
            depth = (self.shipping_fee_waived_inr or 0.0) / order_value_inr
        elif self.kind is InterventionKind.BUNDLE:
            depth = self.discount_pct or 0.0
        else:  # pragma: no cover - Enum is closed
            raise ValueError(f"unknown intervention kind: {self.kind}")
        # Capped at 0.5. Constant-elasticity demand is a local approximation
        # fitted over ordinary promotional depths; extrapolating it to a
        # near-free basket produces lifts no retailer has ever observed. The cap
        # keeps the model inside the range the cited elasticities were estimated
        # over, and sits well above the depths the generator actually samples.
        return float(min(max(depth, 0.0), 0.5))

    def incentive_cost_inr(self, order_value_inr: float) -> float:
        """What the merchant pays for one treated *order*.

        Paid on every treated order, incremental or not. That asymmetry is the
        whole point of the project, so it is modelled here rather than assumed
        away in the economics layer.
        """
        return self.effective_depth(order_value_inr) * order_value_inr

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "kind": self.kind.value,
            "name": self.name,
            "description": self.description,
            "target_product_ids": list(self.target_product_ids),
            "flat_discount_inr": self.flat_discount_inr,
            "discount_pct": self.discount_pct,
            "shipping_fee_waived_inr": self.shipping_fee_waived_inr,
            "bundle_added_value_inr": self.bundle_added_value_inr,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Intervention":
        return cls(
            intervention_id=raw["intervention_id"],
            kind=InterventionKind(raw["kind"]),
            name=raw["name"],
            description=raw["description"],
            target_product_ids=tuple(raw["target_product_ids"]),
            flat_discount_inr=raw["flat_discount_inr"],
            discount_pct=raw["discount_pct"],
            shipping_fee_waived_inr=raw["shipping_fee_waived_inr"],
            bundle_added_value_inr=raw["bundle_added_value_inr"],
        )


# --------------------------------------------------------------------------- #
# Structural parameters and the world itself
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class WorldParams:
    """The true structural parameters of a world.

    Ranges and their sourcing are in ``docs/simulator.md``. These are simulator
    truth, not merchant-observable facts: the agent must never be handed this
    object, or it would read the answer instead of estimating it.
    """

    baseline_conversion: float
    elasticity_mean: float
    elasticity_sd: float
    #: Lognormal sigma of per-customer promo responsiveness. This is the
    #: treatment-effect heterogeneity knob.
    responsiveness_sigma: float
    #: World-level "how promotable is this demand". Multiplies every customer's
    #: promo responsiveness. Profitability is decided by response strength
    #: rather than by discount depth (depth cancels to first order), so this is
    #: the latent that determines whether a merchant's promotions can pay at
    #: all. Hidden: never exposed to the agent, and one of the latents the
    #: semantic context is coupled to.
    promo_response_scale: float
    #: True when the market is in a price war. Raises elasticity for everyone.
    #: Hidden; the competitor-discount event in the semantic context is emitted
    #: from it at partial fidelity.
    competitive_pressure: bool
    #: Per-intervention hidden response multipliers. Which promotion works for a
    #: given merchant is decided here, and none of it is visible in the
    #: agent-facing view — depth is observable, so if depth alone decided the
    #: winner a baseline could rank offers without experimenting.
    #:
    #: Two of the four are hinted at by a semantic signal emitted at partial
    #: fidelity (shipping, clearance); the other two carry no signal at all, so
    #: reading the context helps on some worlds and not others.
    shipping_affinity: float
    clearance_affinity: float
    pct_affinity: float
    bundle_affinity: float
    aov_median_inr: float
    aov_sigma: float
    margin_mean: float
    margin_sd: float
    #: Share of gross lift that is not genuinely incremental (pull-forward,
    #: stockpiling, own-SKU switching). Sourced range in docs/simulator.md.
    cannibalization_rate: float
    seasonality_index: float
    #: Revenue the merchant is projected to turn over in one experiment window.
    #: The basis for the promotion budget, and recorded so the budget can be
    #: checked against the world that produced it.
    projected_revenue_inr: float
    #: Promotion budget as a fraction of projected revenue. Sampled per world.
    budget_share_of_revenue: float
    promotion_budget_inr: float
    n_customers: int
    experiment_window_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_conversion": self.baseline_conversion,
            "elasticity_mean": self.elasticity_mean,
            "elasticity_sd": self.elasticity_sd,
            "responsiveness_sigma": self.responsiveness_sigma,
            "promo_response_scale": self.promo_response_scale,
            "competitive_pressure": self.competitive_pressure,
            "shipping_affinity": self.shipping_affinity,
            "clearance_affinity": self.clearance_affinity,
            "pct_affinity": self.pct_affinity,
            "bundle_affinity": self.bundle_affinity,
            "aov_median_inr": self.aov_median_inr,
            "aov_sigma": self.aov_sigma,
            "margin_mean": self.margin_mean,
            "margin_sd": self.margin_sd,
            "cannibalization_rate": self.cannibalization_rate,
            "seasonality_index": self.seasonality_index,
            "projected_revenue_inr": self.projected_revenue_inr,
            "budget_share_of_revenue": self.budget_share_of_revenue,
            "promotion_budget_inr": self.promotion_budget_inr,
            "n_customers": self.n_customers,
            "experiment_window_days": self.experiment_window_days,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "WorldParams":
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class World:
    """One merchant economy.

    Holds no reference to :class:`GroundTruth`, by design — see the module
    docstring.
    """

    world_id: str
    seed: int
    #: "dev" or "holdout". Recorded so a misfiled world is detectable.
    split: str
    schema_version: str
    params: WorldParams
    semantic: SemanticContext
    segments: tuple[Segment, ...]
    products: tuple[Product, ...]
    customers: tuple[Customer, ...]
    interventions: tuple[Intervention, ...]

    def segment(self, segment_id: str) -> Segment:
        for segment in self.segments:
            if segment.segment_id == segment_id:
                return segment
        raise KeyError(segment_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "seed": self.seed,
            "split": self.split,
            "schema_version": self.schema_version,
            "params": self.params.to_dict(),
            "semantic": self.semantic.to_dict(),
            "segments": [s.to_dict() for s in self.segments],
            "products": [p.to_dict() for p in self.products],
            "customers": [c.to_dict() for c in self.customers],
            "interventions": [i.to_dict() for i in self.interventions],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "World":
        return cls(
            world_id=raw["world_id"],
            seed=raw["seed"],
            split=raw["split"],
            schema_version=raw["schema_version"],
            params=WorldParams.from_dict(raw["params"]),
            semantic=SemanticContext.from_dict(raw["semantic"]),
            segments=tuple(Segment.from_dict(s) for s in raw["segments"]),
            products=tuple(Product.from_dict(p) for p in raw["products"]),
            customers=tuple(Customer.from_dict(c) for c in raw["customers"]),
            interventions=tuple(Intervention.from_dict(i) for i in raw["interventions"]),
        )


# --------------------------------------------------------------------------- #
# Ground truth — eval/ only
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PotentialOutcome:
    """What happens to one customer under one arm of the world."""

    converted: bool
    order_value_inr: float
    #: Gross contribution before any promotion cost, net of the share of lift
    #: that is pull-forward rather than new demand.
    contribution_inr: float


@dataclass(frozen=True, slots=True)
class PotentialOutcomePair:
    """``Y(0)`` and ``Y(1)`` for one customer under one intervention.

    The experiment observes exactly one of these per customer. Holding both is
    what lets Day 9 report estimation error against the true individual effect,
    separately from whether the agent happened to make money.
    """

    y0: PotentialOutcome
    y1: PotentialOutcome

    @property
    def tau_contribution_inr(self) -> float:
        """True individual treatment effect on contribution."""
        return self.y1.contribution_inr - self.y0.contribution_inr

    @property
    def tau_converted(self) -> int:
        """True individual treatment effect on conversion: -1, 0 or +1."""
        return int(self.y1.converted) - int(self.y0.converted)


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """Sealed potential outcomes for a world.

    ``outcomes[customer_id][intervention_id]`` -> :class:`PotentialOutcomePair`.

    Never returned by an agent tool, directly or derived. Loaded only through
    :func:`src.world.persistence.load_ground_truth`, which refuses callers
    outside ``src/eval/``.
    """

    world_id: str
    seed: int
    schema_version: str
    outcomes: Mapping[str, Mapping[str, PotentialOutcomePair]]

    def to_dict(self) -> dict[str, Any]:
        """Serialize columnar: 4,000 customers x 4 interventions as per-field
        arrays is several times smaller and faster to parse than nested objects,
        and the file is read on every eval run."""
        customer_ids = list(self.outcomes)
        intervention_ids = sorted(
            {iid for per_customer in self.outcomes.values() for iid in per_customer}
        )
        columns: dict[str, dict[str, list[Any]]] = {}
        for intervention_id in intervention_ids:
            pairs = [self.outcomes[cid][intervention_id] for cid in customer_ids]
            columns[intervention_id] = {
                "y0_converted": [int(p.y0.converted) for p in pairs],
                "y0_order_value_inr": [p.y0.order_value_inr for p in pairs],
                "y0_contribution_inr": [p.y0.contribution_inr for p in pairs],
                "y1_converted": [int(p.y1.converted) for p in pairs],
                "y1_order_value_inr": [p.y1.order_value_inr for p in pairs],
                "y1_contribution_inr": [p.y1.contribution_inr for p in pairs],
            }
        return {
            "world_id": self.world_id,
            "seed": self.seed,
            "schema_version": self.schema_version,
            "customer_ids": customer_ids,
            "columns": columns,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GroundTruth":
        customer_ids: Sequence[str] = raw["customer_ids"]
        outcomes: dict[str, dict[str, PotentialOutcomePair]] = {
            cid: {} for cid in customer_ids
        }
        for intervention_id, column in raw["columns"].items():
            for index, cid in enumerate(customer_ids):
                outcomes[cid][intervention_id] = PotentialOutcomePair(
                    y0=PotentialOutcome(
                        converted=bool(column["y0_converted"][index]),
                        order_value_inr=column["y0_order_value_inr"][index],
                        contribution_inr=column["y0_contribution_inr"][index],
                    ),
                    y1=PotentialOutcome(
                        converted=bool(column["y1_converted"][index]),
                        order_value_inr=column["y1_order_value_inr"][index],
                        contribution_inr=column["y1_contribution_inr"][index],
                    ),
                )
        return cls(
            world_id=raw["world_id"],
            seed=raw["seed"],
            schema_version=raw["schema_version"],
            outcomes=outcomes,
        )
