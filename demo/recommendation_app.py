"""Standalone recommendation demo. DEMONSTRATION FIXTURES — NOT RESEARCH EVIDENCE.

Separate from ``src/ui/app.py`` on purpose: that dashboard reports the research
evaluation and is left untouched. This app reports a *product* decision on
hand-declared fixtures, and nothing it displays is evidence about anything.

Written against the installed Streamlit API (1.32) rather than the pinned one,
so the demo runs without disturbing the environment the research reproduces in.

Run with:  python -m streamlit run demo/recommendation_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo.fixtures import FIXTURE_LABEL, FIXTURES  # noqa: E402
from demo.run_scenarios import run_scenario  # noqa: E402
from src.agent.recommendation import (  # noqa: E402
    UNRESOLVED_VALUE_OF_INFORMATION,
    RecommendationDecision,
)

DECISION_COLOUR = {
    RecommendationDecision.PROMOTE.value: "#137333",
    RecommendationDecision.DO_NOT_PROMOTE.value: "#a50e0e",
    RecommendationDecision.RUN_EXPERIMENT_FIRST.value: "#8a6d00",
    RecommendationDecision.INSUFFICIENT_EVIDENCE.value: "#5f6368",
}

DECISION_GLOSS = {
    RecommendationDecision.PROMOTE.value: (
        "Earned through a measured experiment, not assumed from a prior."
    ),
    RecommendationDecision.DO_NOT_PROMOTE.value: (
        "Not caution for its own sake — the arithmetic below does not support "
        "putting the merchant's margin at risk."
    ),
    RecommendationDecision.RUN_EXPERIMENT_FIRST.value: (
        "The economics could work, but the confidence is not sourced from a "
        "measurement on this merchant. Test before spending."
    ),
    RecommendationDecision.INSUFFICIENT_EVIDENCE.value: (
        "The proposal could not be priced. The system fails closed rather than "
        "guessing."
    ),
}


def rupees(amount: float) -> str:
    return f"Rs.{amount:,.0f}"


st.set_page_config(page_title="MarginPilot — recommendation", layout="wide")

st.warning(f"**{FIXTURE_LABEL}**  ·  These merchants are hand-declared for the "
           "demo. No number on this page is a research result, and none of it "
           "is a claim about real merchants.")

st.title("MarginPilot — should this merchant promote?")
st.caption(
    "The assistant reads the merchant's context and proposes. A deterministic "
    "economic policy decides. Where they disagree, the policy wins."
)

choice = st.sidebar.radio(
    "Scenario",
    options=sorted(FIXTURES),
    format_func=lambda k: f"{k} — {FIXTURES[k].title}",
)
spec = FIXTURES[choice]

st.sidebar.markdown("**The merchant**")
st.sidebar.write(spec.story)
st.sidebar.markdown(
    f"- population: {spec.population:,}\n"
    f"- budget: {rupees(spec.budget_inr)}\n"
    f"- conversion: {spec.observed_conversion:.1%}\n"
    f"- AOV: {rupees(spec.aov_inr)}\n"
    f"- margin: {spec.margin:.0%}\n"
    f"- offer: {spec.intervention_name}"
)

record = run_scenario(spec)
final = record["final"]
initial = record["initial"]

colour = DECISION_COLOUR.get(final["decision"], "#5f6368")
st.markdown(
    f"<div style='padding:1rem 1.25rem;border-left:6px solid {colour};"
    f"background:rgba(128,128,128,0.08);border-radius:4px'>"
    f"<div style='font-size:0.85rem;letter-spacing:0.08em;opacity:0.7'>DECISION</div>"
    f"<div style='font-size:2rem;font-weight:700;color:{colour}'>{final['decision']}</div>"
    f"<div style='opacity:0.85'>{DECISION_GLOSS.get(final['decision'], '')}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

st.write("")
left, middle, right = st.columns(3)
left.metric("Expected incremental contribution",
            rupees(final["expected_incremental_contribution_inr"]))
middle.metric("Expected incentive cost",
              rupees(final["expected_incentive_cost_inr"]))
right.metric("Expected NET contribution",
             rupees(final["expected_net_contribution_inr"]),
             delta=("positive" if final["expected_net_contribution_inr"] > 0 else "negative"),
             delta_color=("normal" if final["expected_net_contribution_inr"] > 0 else "inverse"))

if final["required_break_even_lift_absolute"] is not None:
    st.info(
        f"**Break-even needs a {final['required_break_even_lift_absolute']:.2%} "
        "conversion lift.** The incentive is charged on every treated order, not "
        "only the extra ones, so the promotion has to buy that many new orders "
        "before the first rupee of contribution survives."
    )

st.subheader("Why")
st.write(final["diagnosis"])
st.write(final["rationale"])

if initial["overruled_the_model"]:
    st.error(
        f"The assistant asked for **{initial['model_requested']}**. The policy "
        f"returned **{initial['decision']}**. The model reasons; it does not "
        "hold the budget."
    )

cols = st.columns(2)
with cols[0]:
    st.markdown("**Gates passed**")
    st.write(", ".join(final["gates_passed"]) or "—")
    if final["binding_constraints"]:
        st.markdown("**Binding constraint**")
        for constraint in final["binding_constraints"]:
            st.write(f"- `{constraint}`")

with cols[1]:
    if final["unresolved"]:
        st.markdown("**Open questions this recommendation does not settle**")
        for item in final["unresolved"]:
            if item == UNRESOLVED_VALUE_OF_INFORMATION:
                st.warning(
                    f"`{item}` — we can tell you the experiment is affordable. "
                    "Whether it costs less than the information it buys is an "
                    "open question in this project, and we are not going to "
                    "invent a threshold to make it look settled."
                )
            else:
                st.warning(f"`{item}`")

if record["experiment"]:
    exp = record["experiment"]
    st.subheader("The experiment that was actually run")
    st.caption(
        f"{exp['horizon_per_arm']:,} customers per arm, sized on contribution "
        f"rather than conversion. Pilot spend {rupees(exp['pilot_spend_inr'])}."
    )
    st.table(
        [
            {
                "arm": arm["name"],
                "assigned": f"{arm['n_assigned']:,}",
                "converted": f"{arm['n_converted']:,}",
                "conversion": f"{arm['conversion_rate']:.2%}",
                "contribution / customer": rupees(arm["contribution_mean_inr"]),
            }
            for arm in exp["arms"]
        ]
    )
    st.caption(
        "The result then went back through the same scaling rule and rollout "
        "gate the research evaluation uses. PROMOTE is reachable only that way."
    )

with st.expander("What the assistant was allowed to see"):
    st.write(
        "Merchant aggregates, the product catalogue, the four offers and their "
        "costs, past campaign results with their error bars, customer records "
        "grouped into order-value cohorts, and the merchant's own written "
        "context."
    )
    st.write(
        "**Not** shown to it: any hidden simulator parameter, any customer's "
        "true response, any realized outcome, and no segment name, tag or note "
        "— those are a key to withheld response multipliers in the research "
        "simulator, so they stay out of the product."
    )
    st.json(initial)
