"""DEMONSTRATION FIXTURES — NOT RESEARCH EVIDENCE.

Three hand-declared merchants used to exercise the product's decision path on
camera. They are **not** drawn from ``worlds/`` or ``worlds_cycle2/``, they are
never scored, and no number produced from them is evidence about anything.

Every parameter below is declared in the open, including each fixture's *true*
response — which the fixture's own executor uses to generate experiment
observations, and which the decision path never sees. The seeds are committed
before the first execution so that a later "let me try another seed" is visible
in the git history rather than invisible in a result.

Why the true response may be declared here at all: this is a demonstration, not
a measurement. The scientific constraint is not that a demo merchant must be
unprofitable — it is that the *decision path* must never read the merchant's
true response, must earn PROMOTE through a real experiment, and must not be
retuned until it passes. All three hold.

What the decision path is given: the merchant brief only. What it is never
given: ``declared_true_lift_absolute``, ``Y(0)``/``Y(1)``, ``u_i``, any hidden
simulator parameter, and any ``SegmentView`` name, tag or note.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from src.eval.contracts import (
    CustomerView,
    InterventionHistory,
    MerchantView,
    SegmentView,
)
from src.experiment.evaluator import ArmObservation
from src.experiment.registry import LaunchedExperiment
from src.world.schema import Intervention, InterventionKind, Product, SemanticContext

FIXTURE_LABEL = "DEMONSTRATION FIXTURE — NOT RESEARCH EVIDENCE"

LOCK_PATH = Path(__file__).resolve().parent / "SCENARIO_C.lock"


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    """A declared demonstration merchant. Frozen once committed."""

    scenario_id: str
    title: str
    story: str
    population: int
    budget_inr: float
    observed_conversion: float
    aov_inr: float
    margin: float
    intervention_kind: str
    #: Rupees for flat/shipping offers, a fraction for percentage/bundle offers.
    intervention_magnitude: float
    intervention_name: str
    intervention_description: str
    #: The fixture's OWN response. Used only to generate experiment
    #: observations. Never reaches the brief, the model, or the policy.
    declared_true_lift_absolute: float
    #: Committed before the first execution. Changing it after is an integrity
    #: failure, and ``ADV-12`` checks for exactly that.
    seed: int
    history_net_per_treated_customer_inr: float
    history_standard_error_inr: float
    #: The model-side proposal this scenario exercises.
    proposed_lift_absolute: float
    proposed_evidence_basis: str
    proposed_hypothesis: str
    proposed_mechanism: str
    aov_dispersion: float = 0.35

    def fingerprint(self) -> str:
        """Stable hash of every declared parameter, including the seed."""
        blob = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


# --------------------------------------------------------------------------- #
# The three declared fixtures
# --------------------------------------------------------------------------- #

#: A thin-margin merchant running a deep rupee discount. Contribution per order
#: is Rs.132 and the incentive costs Rs.120 of it, leaving Rs.12 to buy an
#: incremental order with. No response level repays that, and the arithmetic
#: says so before any experiment is contemplated.
SCENARIO_A = FixtureSpec(
    scenario_id="A",
    title="Thin margin, deep discount",
    story=(
        "A homeware merchant whose growth tool is recommending a flat Rs.120 off "
        "to lift a soft month. Conversion would almost certainly rise."
    ),
    population=30_000,
    budget_inr=400_000.0,
    observed_conversion=0.10,
    aov_inr=600.0,
    margin=0.22,
    intervention_kind="flat_discount",
    intervention_magnitude=120.0,
    intervention_name="Rs.120 off",
    intervention_description=(
        "A flat Rs.120 off the order. Deepest in relative terms for small baskets."
    ),
    declared_true_lift_absolute=0.05,
    seed=1_000_001,
    history_net_per_treated_customer_inr=-11.40,
    history_standard_error_inr=4.10,
    proposed_lift_absolute=0.04,
    proposed_evidence_basis="PRIOR",
    proposed_hypothesis=(
        "A flat discount will lift conversion in a soft month, as it did across "
        "the category last quarter."
    ),
    proposed_mechanism="Price-sensitive buyers convert when the effective price falls.",
)

#: A merchant where the offer genuinely could pay — contribution per order is
#: Rs.270 against an incentive of Rs.108 — but the only evidence is one small
#: past campaign whose error bar is wide enough to contain zero.
SCENARIO_B = FixtureSpec(
    scenario_id="B",
    title="Plausible offer, thin evidence",
    story=(
        "A speciality foods merchant considering 12% off. A past campaign looked "
        "positive, but it treated only 300 customers."
    ),
    population=30_000,
    budget_inr=400_000.0,
    observed_conversion=0.09,
    aov_inr=900.0,
    margin=0.30,
    intervention_kind="percentage_discount",
    intervention_magnitude=0.12,
    intervention_name="12% off",
    intervention_description=(
        "12% off the order value. Scales with basket size, so the cost is largest "
        "on the orders that were most likely to happen anyway."
    ),
    declared_true_lift_absolute=0.05,
    seed=1_000_002,
    history_net_per_treated_customer_inr=3.90,
    history_standard_error_inr=5.60,
    proposed_lift_absolute=0.08,
    proposed_evidence_basis="HISTORY",
    proposed_hypothesis=(
        "12% off will lift conversion by around 8 points, in line with the last "
        "campaign's point estimate."
    ),
    proposed_mechanism=(
        "The past campaign's incremental net per treated customer was positive."
    ),
)

#: A high-margin merchant with a cheap, fixed-cost offer. Contribution per order
#: is Rs.540 and free shipping costs Rs.60, so break-even sits near one point of
#: lift. The economics can work; whether they do is a question for a test.
SCENARIO_C = FixtureSpec(
    scenario_id="C",
    title="High margin, cheap offer, untested",
    story=(
        "A premium accessories merchant with 45% margins. Support tickets keep "
        "mentioning the Rs.60 delivery fee. Waiving it is cheap — but nobody has "
        "measured whether it moves anyone."
    ),
    population=40_000,
    budget_inr=120_000.0,
    observed_conversion=0.08,
    aov_inr=1_200.0,
    margin=0.45,
    intervention_kind="free_shipping",
    intervention_magnitude=60.0,
    intervention_name="Free shipping",
    intervention_description=(
        "Waives the Rs.60 delivery fee. A genuine price cut to the customer, "
        "booked by the merchant as a cost line rather than a discount."
    ),
    declared_true_lift_absolute=0.035,
    seed=1_000_003,
    history_net_per_treated_customer_inr=6.20,
    history_standard_error_inr=7.80,
    proposed_lift_absolute=0.03,
    proposed_evidence_basis="HISTORY",
    proposed_hypothesis=(
        "Waiving the delivery fee lifts conversion by about 3 points among "
        "customers whose baskets already clear the threshold."
    ),
    proposed_mechanism=(
        "Support themes repeatedly name the delivery fee as the reason for "
        "abandoning a full cart."
    ),
)

FIXTURES = {spec.scenario_id: spec for spec in (SCENARIO_A, SCENARIO_B, SCENARIO_C)}


# --------------------------------------------------------------------------- #
# Building a merchant view from a spec
# --------------------------------------------------------------------------- #

_KINDS = {
    "flat_discount": InterventionKind.FLAT_DISCOUNT,
    "percentage_discount": InterventionKind.PERCENTAGE_DISCOUNT,
    "free_shipping": InterventionKind.FREE_SHIPPING,
    "bundle": InterventionKind.BUNDLE,
}


def _intervention(spec: FixtureSpec) -> Intervention:
    kind = _KINDS[spec.intervention_kind]
    return Intervention(
        intervention_id=f"demo_{spec.intervention_kind}",
        kind=kind,
        name=spec.intervention_name,
        description=spec.intervention_description,
        target_product_ids=("sku_000",),
        flat_discount_inr=spec.intervention_magnitude if kind is InterventionKind.FLAT_DISCOUNT else None,
        discount_pct=(
            spec.intervention_magnitude
            if kind in (InterventionKind.PERCENTAGE_DISCOUNT, InterventionKind.BUNDLE)
            else None
        ),
        shipping_fee_waived_inr=(
            spec.intervention_magnitude if kind is InterventionKind.FREE_SHIPPING else None
        ),
        bundle_added_value_inr=None,
    )


def build_view(spec: FixtureSpec) -> MerchantView:
    """A merchant view for one fixture. Deterministic in the committed seed."""
    rng = np.random.default_rng(spec.seed)
    aovs = np.clip(
        spec.aov_inr * rng.lognormal(0.0, spec.aov_dispersion, size=spec.population),
        99.0,
        50_000.0,
    )
    # Re-centre so the merchant's published average order value is exactly the
    # declared one; otherwise the fixture's headline number and its customer
    # records would disagree.
    aovs = aovs * (spec.aov_inr / float(aovs.mean()))

    customers = tuple(
        CustomerView(
            customer_id=f"cust_{i:05d}",
            segment_id=f"seg_{i % 4}",
            tenure_days=int(rng.integers(1, 1460)),
            orders_last_90d=int(rng.poisson(2.0)),
            days_since_last_order=int(rng.integers(0, 400)),
            historical_aov_inr=round(float(aovs[i]), 2),
        )
        for i in range(spec.population)
    )

    product = Product(
        product_id="sku_000",
        name="Demonstration SKU",
        category="demo",
        description="A single representative product for the demonstration.",
        unit_price_inr=spec.aov_inr,
        unit_cost_inr=round(spec.aov_inr * (1.0 - spec.margin), 2),
        inventory_units=1_000,
        inventory_age_days=45,
        stock_status="steady",
    )

    intervention = _intervention(spec)

    return MerchantView(
        world_id=f"demo_scenario_{spec.scenario_id}",
        population=spec.population,
        budget_inr=spec.budget_inr,
        observed_conversion=spec.observed_conversion,
        observed_aov_inr=spec.aov_inr,
        observed_margin=spec.margin,
        experiment_window_days=28,
        semantic=SemanticContext(
            merchant_name=spec.title,
            vertical="demonstration",
            merchant_description=spec.story,
            seasonal_events=("A quiet stretch with no festival anchor",),
            competitor_events=(),
            customer_service_themes=(
                "customers ask whether delivery is free above a threshold",
            ),
            inventory_notes=("No SKU is currently flagged for stock age.",),
            trading_notes=("Trading is steady week on week.",),
        ),
        products=(product,),
        customers=customers,
        # Neutral placeholders. build_brief() reads no segment field at all, so
        # nothing here can reach the model — see SCI-1.
        segments=tuple(
            SegmentView(
                segment_id=f"seg_{i}",
                name=f"Group {i + 1}",
                share=0.25,
                notes="",
                behaviour_tags=(),
            )
            for i in range(4)
        ),
        interventions=(intervention,),
        history=(
            InterventionHistory(
                intervention_id=intervention.intervention_id,
                treated_customers=300,
                orders=int(300 * (spec.observed_conversion + 0.01)),
                net_per_treated_customer_inr=spec.history_net_per_treated_customer_inr,
                standard_error_inr=spec.history_standard_error_inr,
            ),
        ),
    )


def proposal_payload(spec: FixtureSpec) -> dict:
    """The model-side proposal this scenario exercises.

    Written as a raw payload so it goes through the same validation an actual
    model reply would.
    """
    return {
        "intervention_id": f"demo_{spec.intervention_kind}",
        "cohort_id": "ALL",
        "expected_lift_absolute": spec.proposed_lift_absolute,
        "evidence_basis": spec.proposed_evidence_basis,
        "hypothesis": spec.proposed_hypothesis,
        "mechanism": spec.proposed_mechanism,
        "citations": ["history", "context", "interventions"],
        "requested_decision": "PROMOTE",
    }


# --------------------------------------------------------------------------- #
# The executor
# --------------------------------------------------------------------------- #


class FixtureExecutor:
    """Supplies experiment observations for a fixture.

    Implements the production ``ExperimentExecutor`` protocol, so the fixture
    enters the real evaluation machinery — ``evaluate()`` then ``assess_scale()``
    then ``gate_rollout()`` — rather than a parallel demo path.

    Outcomes are drawn from the fixture's declared response with its committed
    seed. Nothing here touches ``Y(0)``/``Y(1)``, the simulator's latents, or
    any sealed corpus: this module imports no world generator and no ground
    truth loader.
    """

    def __init__(self, spec: FixtureSpec) -> None:
        self.spec = spec
        self._intervention = _intervention(spec)

    def observe(
        self, experiment: LaunchedExperiment, intervention_id: str
    ) -> Sequence[ArmObservation]:
        spec = self.spec
        n = experiment.horizon_per_arm
        rng = np.random.default_rng(spec.seed)

        basket = spec.aov_inr
        gross = basket * spec.margin
        incentive = self._intervention.incentive_cost_inr(basket)

        p0 = spec.observed_conversion
        p1 = min(p0 + spec.declared_true_lift_absolute, 1.0)

        control = rng.random(n) < p0
        treated = rng.random(n) < p1

        control_values = np.where(control, gross, 0.0)
        treated_values = np.where(treated, gross - incentive, 0.0)

        return (
            ArmObservation(
                arm=0,
                name="control",
                n_assigned=n,
                n_converted=int(control.sum()),
                contribution_mean_inr=float(control_values.mean()),
                contribution_sd_inr=float(control_values.std(ddof=1)),
            ),
            ArmObservation(
                arm=1,
                name="treatment",
                n_assigned=n,
                n_converted=int(treated.sum()),
                contribution_mean_inr=float(treated_values.mean()),
                contribution_sd_inr=float(treated_values.std(ddof=1)),
            ),
        )

    def population_not_in_experiment(self, experiment: LaunchedExperiment) -> int:
        return max(self.spec.population - 2 * experiment.horizon_per_arm, 0)


def write_lock() -> str:
    """Record Scenario C's fingerprint. Called once, before the first execution."""
    fingerprint = SCENARIO_C.fingerprint()
    LOCK_PATH.write_text(
        "# Scenario C fixture lock.\n"
        "# Committed BEFORE the first execution. If this no longer matches,\n"
        "# the fixture parameters or seed were changed after the fact.\n"
        f"{fingerprint}\n",
        encoding="utf-8",
    )
    return fingerprint


def locked_fingerprint() -> str:
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise ValueError("SCENARIO_C.lock contains no fingerprint")
