"""The merchant brief: everything the model is allowed to read, and nothing else.

Built from :class:`~src.eval.contracts.MerchantView` by **explicit field
selection**, the same discipline ``merchant_view()`` itself uses. A latent added
to ``WorldParams`` later is invisible here by default, because nothing in this
module reaches for a field it was not told to take.

Two exclusions are deliberate and enforced by test:

* **Ground truth**, which this module has no route to and never names.
* **``SegmentView.name`` / ``notes`` / ``behaviour_tags``** (SCI-1). Provenance
  analysis found these are a bijective key to the withheld archetype
  multipliers — seven names mapping one-to-one onto seven response quadruples in
  a module constant — so publishing the label is informationally identical to
  publishing the multipliers. See
  ``analysis/posthoc/provenance/segmentview.md``. Until that is ruled on
  separately, they stay out.

What replaces them is a cohort split on ``historical_aov_inr``, which is a
genuine customer record field. It is a weaker targeting representation, and
that weakness is the honest consequence of the exclusion rather than a
limitation to engineer around.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping, Sequence

from src.economics.contribution import contribution_per_order_inr
from src.eval.contracts import MerchantView

#: Quantile bins over the customer AOV distribution. Fixed in advance so the
#: split is a declared choice rather than something tuned per merchant.
DEFAULT_COHORT_COUNT = 4


class BriefBoundaryError(ValueError):
    """An attempt to put non-merchant information into the brief."""


@dataclass(frozen=True, slots=True)
class Cohort:
    """Customers grouped by their own order history. No segment identity."""

    cohort_id: str
    n_customers: int
    mean_aov_inr: float
    min_aov_inr: float
    max_aov_inr: float


@dataclass(frozen=True, slots=True)
class InterventionBrief:
    """A promotion as the merchant would describe it, priced at observed AOV."""

    intervention_id: str
    kind: str
    name: str
    description: str
    incentive_cost_per_order_inr: float
    depth_at_observed_aov: float


@dataclass(frozen=True, slots=True)
class CohortEconomics:
    """One cohort priced against one intervention.

    Precomputed here, using the intervention's own
    :meth:`~src.world.schema.Intervention.incentive_cost_inr`, so the decision
    layer never has to re-derive depth arithmetic and the two cannot drift.
    Rupee-denominated offers cost a fixed amount per order, so their relative
    depth falls as basket rises — which is exactly why cohort-level pricing
    differs from the merchant average.
    """

    cohort_id: str
    intervention_id: str
    contribution_per_order_inr: float
    incentive_cost_per_order_inr: float


@dataclass(frozen=True, slots=True)
class HistoryBrief:
    """A past campaign's measured incremental result, with its own error bar.

    Small on purpose (300 treated in the simulator), so it is informative
    without being decisive — which is why it can raise a hypothesis but cannot
    on its own authorise a rollout.
    """

    intervention_id: str
    treated_customers: int
    orders: int
    net_per_treated_customer_inr: float
    standard_error_inr: float


@dataclass(frozen=True, slots=True)
class MerchantBrief:
    """The complete model-facing view of one merchant."""

    merchant_id: str
    population: int
    budget_inr: float
    observed_conversion: float
    observed_aov_inr: float
    observed_margin: float
    contribution_per_order_inr: float
    experiment_window_days: int
    cohorts: tuple[Cohort, ...]
    interventions: tuple[InterventionBrief, ...]
    cohort_economics: tuple[CohortEconomics, ...]
    history: tuple[HistoryBrief, ...]
    context: tuple[str, ...]

    def economics_for(self, cohort_id: str, intervention_id: str) -> CohortEconomics:
        for entry in self.cohort_economics:
            if entry.cohort_id == cohort_id and entry.intervention_id == intervention_id:
                return entry
        raise KeyError((cohort_id, intervention_id))

    def intervention(self, intervention_id: str) -> InterventionBrief:
        for candidate in self.interventions:
            if candidate.intervention_id == intervention_id:
                return candidate
        raise KeyError(intervention_id)

    def cohort(self, cohort_id: str) -> Cohort:
        for candidate in self.cohorts:
            if candidate.cohort_id == cohort_id:
                return candidate
        raise KeyError(cohort_id)

    def history_for(self, intervention_id: str) -> HistoryBrief | None:
        for entry in self.history:
            if entry.intervention_id == intervention_id:
                return entry
        return None

    @property
    def whole_base(self) -> Cohort:
        """Every customer, as a single cohort — the untargeted option."""
        return Cohort(
            cohort_id="ALL",
            n_customers=self.population,
            mean_aov_inr=self.observed_aov_inr,
            min_aov_inr=min((c.min_aov_inr for c in self.cohorts), default=0.0),
            max_aov_inr=max((c.max_aov_inr for c in self.cohorts), default=0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def brief_field_names() -> tuple[str, ...]:
    """Every field name reachable in a brief. Used by the boundary test."""
    names: list[str] = []
    for dataclass_type in (
        MerchantBrief, Cohort, InterventionBrief, CohortEconomics, HistoryBrief
    ):
        names.extend(f.name for f in fields(dataclass_type))
    return tuple(sorted(set(names)))


def _quantile_cohorts(aovs: Sequence[float], n_cohorts: int) -> tuple[Cohort, ...]:
    """Split customers into equal-count bins by their own average order value.

    Equal-count rather than equal-width, so every cohort carries enough
    customers to be a plausible campaign target rather than a long tail of one.
    """
    ordered = sorted(aovs)
    total = len(ordered)
    if total == 0 or n_cohorts < 1:
        return ()

    bins = min(n_cohorts, total)
    edges = [round(total * i / bins) for i in range(bins + 1)]
    cohorts: list[Cohort] = []
    for index in range(bins):
        chunk = ordered[edges[index]: edges[index + 1]]
        if not chunk:
            continue
        cohorts.append(
            Cohort(
                cohort_id=f"aov_q{index + 1}",
                n_customers=len(chunk),
                mean_aov_inr=round(sum(chunk) / len(chunk), 2),
                min_aov_inr=round(chunk[0], 2),
                max_aov_inr=round(chunk[-1], 2),
            )
        )
    return tuple(cohorts)


def build_brief(
    view: MerchantView,
    *,
    n_cohorts: int = DEFAULT_COHORT_COUNT,
    _unsafe_extra_fields: Mapping[str, Any] | None = None,
) -> MerchantBrief:
    """Project a merchant view into the model-facing brief.

    ``_unsafe_extra_fields`` exists only so the boundary test can prove the
    refusal path is real. Offering anything through it raises: silently
    discarding the extras would let a caller believe information had been used
    when it had not, which is a worse failure than a loud one.
    """
    if _unsafe_extra_fields:
        raise BriefBoundaryError(
            "the brief is built by explicit field selection; "
            f"refusing extra fields {sorted(_unsafe_extra_fields)}"
        )

    per_order = contribution_per_order_inr(view.observed_aov_inr, view.observed_margin)

    interventions = tuple(
        InterventionBrief(
            intervention_id=i.intervention_id,
            kind=i.kind.value,
            name=i.name,
            description=i.description,
            incentive_cost_per_order_inr=round(
                i.incentive_cost_inr(view.observed_aov_inr), 4
            ),
            depth_at_observed_aov=round(i.effective_depth(view.observed_aov_inr), 6),
        )
        for i in view.interventions
    )

    history = tuple(
        HistoryBrief(
            intervention_id=h.intervention_id,
            treated_customers=h.treated_customers,
            orders=h.orders,
            net_per_treated_customer_inr=round(h.net_per_treated_customer_inr, 4),
            standard_error_inr=round(h.standard_error_inr, 4),
        )
        for h in view.history
    )

    semantic = view.semantic
    context = (
        (f"vertical: {semantic.vertical}",)
        + tuple(f"season: {e}" for e in semantic.seasonal_events)
        + tuple(f"competitor: {e}" for e in semantic.competitor_events)
        + tuple(f"support: {t}" for t in semantic.customer_service_themes)
        + tuple(f"inventory: {n}" for n in semantic.inventory_notes)
        + tuple(f"trading: {t}" for t in semantic.trading_notes)
    )

    cohorts = _quantile_cohorts(
        [c.historical_aov_inr for c in view.customers], n_cohorts
    )

    priced: list[CohortEconomics] = []
    all_cohorts = cohorts + (
        Cohort(
            cohort_id="ALL",
            n_customers=view.population,
            mean_aov_inr=view.observed_aov_inr,
            min_aov_inr=min((c.min_aov_inr for c in cohorts), default=0.0),
            max_aov_inr=max((c.max_aov_inr for c in cohorts), default=0.0),
        ),
    )
    for cohort in all_cohorts:
        for intervention in view.interventions:
            priced.append(
                CohortEconomics(
                    cohort_id=cohort.cohort_id,
                    intervention_id=intervention.intervention_id,
                    contribution_per_order_inr=round(
                        contribution_per_order_inr(
                            cohort.mean_aov_inr, view.observed_margin
                        ),
                        4,
                    ),
                    incentive_cost_per_order_inr=round(
                        intervention.incentive_cost_inr(cohort.mean_aov_inr), 4
                    ),
                )
            )

    return MerchantBrief(
        merchant_id=view.world_id,
        population=view.population,
        budget_inr=view.budget_inr,
        observed_conversion=view.observed_conversion,
        observed_aov_inr=view.observed_aov_inr,
        observed_margin=view.observed_margin,
        contribution_per_order_inr=round(per_order, 4),
        experiment_window_days=view.experiment_window_days,
        cohorts=cohorts,
        interventions=interventions,
        cohort_economics=tuple(priced),
        history=history,
        context=context,
    )
