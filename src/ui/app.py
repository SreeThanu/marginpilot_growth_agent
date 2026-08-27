"""MarginPilot dashboard. Reads one snapshot file; reaches for nothing.

Run with ``streamlit run src/ui/app.py`` after ``python -m src.ui.snapshot``.

The UI has no import path to the world generator, the harness or ground truth.
It renders ``data/dashboard_snapshot.json`` and can therefore not read
``worlds/holdout/`` even by mistake — the seal holds because there is no route,
not because this file promises to be careful.

Every figure shown comes from dev worlds and is labelled as such.

**One framing rule.** The policy gates approved the experiments the agent chose,
correctly: budget, discount, margin, exposure and power were all within limits.
Nothing on this page may imply the gates caught the selection failure. What
caught it was measurement — the horizon, the posterior and the scaling rule.
See ``docs/simulator.md`` 4g, which a test pins.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

SNAPSHOT = Path("data/dashboard_snapshot.json")

st.set_page_config(page_title="MarginPilot", page_icon="▲", layout="wide")


@st.cache_data
def load() -> dict:
    if not SNAPSHOT.exists():
        st.error(
            f"No snapshot at {SNAPSHOT}. Generate it with:\n\n"
            "    python -m src.ui.snapshot"
        )
        st.stop()
    return json.loads(SNAPSHOT.read_text())


def rupees(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rs.{abs(amount):,.0f}"


data = load()
featured = data["featured_experiment"]

st.title("MarginPilot")
st.caption(
    f"Autonomous merchant growth agent · reasoning on `{data['model']}` · "
    f"{data['generated_from']}"
)
st.write("")

# --------------------------------------------------------------------------- #
# The headline. Everything else on this page is supporting evidence.
# --------------------------------------------------------------------------- #

if featured:
    st.subheader(f"{featured['merchant']} — {featured['intervention_id']}")
    left, right = st.columns(2)
    left.metric(
        "Conversion",
        f"{featured['conversion_treatment']:.1%}",
        f"{featured['conversion_lift'] * 100:+.2f} pts vs control",
        delta_color="normal",       # green: conversion went up
    )
    right.metric(
        "Net incremental contribution",
        rupees(featured["net_contribution_inr"]),
        f"{rupees(featured['net_contribution_inr'])} at pilot scale",
        delta_color="inverse",      # red: contribution went down
    )
    st.caption(
        "The discount is paid to every treated buyer, including the ones who would "
        "have bought anyway. Only the genuinely incremental orders add contribution."
    )

st.write("")
st.divider()

view = st.radio(
    "View",
    ["Budget", "Live experiment", "Contribution", "Decision",
     "Audit chain", "Adversarial", "Counterfactual ledger"],
    horizontal=True,
    label_visibility="collapsed",
)
st.write("")

# --------------------------------------------------------------------------- #

if view == "Budget":
    budget = data["budget"]
    a, b, c = st.columns(3)
    a.metric("Promotion budget", rupees(budget["total_inr"]))
    b.metric("Spent", rupees(budget["spent_inr"]))
    c.metric("Remaining", rupees(budget["remaining_inr"]))

    st.write("")
    st.markdown("**Policy ceilings** — checked before every money-adjacent action")
    st.dataframe(
        pd.DataFrame(
            [
                {"rule": "max discount", "limit": f"{budget['max_discount_pct']:.0%} of order value"},
                {"rule": "min contribution margin", "limit": f"{budget['min_contribution_margin']:.0%}"},
                {"rule": "max customer exposure", "limit": f"{budget['max_customer_exposure_share']:.0%} of base"},
                {"rule": "min experiment power", "limit": f"{budget['min_experiment_power']:.2f}"},
                {"rule": "remaining budget", "limit": "projected spend must fit"},
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        f"Budget overruns: **{budget['overruns']}**. Both the pilot and the rollout "
        "pass the gate; gating only the pilot would gate the cheaper half."
    )

elif view == "Live experiment":
    if not featured:
        st.info("No launched experiment in this snapshot.")
    else:
        horizon = featured["horizon_per_arm"]
        a, b = st.columns(2)
        a.metric("Control arm", f"{featured['n_control']:,} customers",
                 f"{featured['control_orders']:,} orders")
        b.metric("Treatment arm", f"{featured['n_treatment']:,} customers",
                 f"{featured['treatment_orders']:,} orders")

        st.write("")
        st.markdown(f"**Horizon** — {horizon:,} per arm, fixed at design time")
        st.progress(min(featured["n_treatment"] / horizon, 1.0))
        st.caption(
            f"{featured['n_treatment']:,} of {horizon:,} per arm. Assignment is "
            "`hash(customer_id + experiment_id) mod n_arms` — no agent tool can "
            "influence it."
        )
        st.write("")
        st.warning(
            "**Before the horizon there is no verdict.** The evaluator returns counts "
            "only — no difference, no interval, no p-value, no scale-eligibility. "
            "Those fields do not exist on the interim result, so nothing can read the "
            "experiment early, however favourable it looks.",
            icon="■",
        )

elif view == "Contribution":
    if not featured:
        st.info("No experiment in this snapshot.")
    else:
        incremental = (
            featured["conversion_lift"] * featured["n_treatment"]
        )
        a, b = st.columns(2)
        a.metric("Conversion lift", f"{featured['conversion_lift'] * 100:+.2f} pts",
                 f"{featured['conversion_control']:.1%} → {featured['conversion_treatment']:.1%}",
                 delta_color="normal")
        b.metric("Net contribution", rupees(featured["net_contribution_inr"]),
                 "after incentive paid on every treated order", delta_color="inverse")

        st.write("")
        st.markdown("**Where the money went**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"line": "Incremental orders", "value": f"{incremental:,.0f}"},
                    {"line": "Treated orders (all paid the incentive)",
                     "value": f"{featured['treatment_orders']:,}"},
                    {"line": "Pilot spend", "value": rupees(featured["pilot_spend_inr"])},
                    {"line": "Net incremental contribution",
                     "value": rupees(featured["net_contribution_inr"])},
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Contribution is earned on the incremental orders. The incentive is paid "
            "on all of them. That asymmetry is the entire finding."
        )

elif view == "Decision":
    if not featured:
        st.info("No decision in this snapshot.")
    else:
        verdict = "SCALE" if featured["scaled"] else "KILL"
        if featured["scaled"]:
            st.success(f"### {verdict}", icon="▲")
        else:
            st.error(f"### {verdict}", icon="▼")

        a, b = st.columns(2)
        a.metric("P(net > 0)", f"{featured['probability_net_positive']:.0%}",
                 "0.80 required to scale")
        b.metric("Posterior 5th percentile (projected)",
                 rupees(featured["projected_downside_inr"]),
                 "must clear the tolerable loss")

        st.write("")
        st.markdown("**Posterior interval on net contribution**")
        st.code(
            f"  point estimate   {rupees(featured['net_contribution_inr'])}\n"
            f"  95% interval     [{rupees(featured['ci_low_inr'])}, "
            f"{rupees(featured['ci_high_inr'])}]\n"
            f"  P(net > 0)       {featured['probability_net_positive']:.2f}",
            language="text",
        )
        st.caption(featured["decision_reason"])
        st.write("")
        st.caption(
            "A positive point estimate is never authority to spend. Scaling requires "
            "the campaign to be probably profitable *and* its bad tail to be survivable."
        )

elif view == "Audit chain":
    chain = data["audit_chain"]
    st.markdown(f"**`make audit EXPERIMENT={chain['experiment_id']}`**")
    st.code(chain["text"], language="text")
    status = "intact" if chain["verified"] else "TAMPERED"
    st.caption(
        f"{chain['entries']} entries in the log · hash chain **{status}** · "
        "append-only: no update path, no delete path, enforced by SQLite triggers "
        "and a SHA-256 chain."
    )

elif view == "Adversarial":
    st.markdown("**Seven attacks, seven refusals.** Each names the module that refused it.")
    st.write("")
    for scenario in data["adversarial"]:
        mark = "REFUSED" if scenario["refused"] else "NOT REFUSED"
        with st.expander(f"{scenario['name']}  —  {mark}", expanded=False):
            st.markdown(f"**Attempted:** {scenario['attempted']}")
            st.markdown(f"**Refused by:** `{scenario['refused_by']}`")
            st.code(scenario["reason"], language="text")
    refused = sum(1 for s in data["adversarial"] if s["refused"])
    st.caption(f"{refused}/{len(data['adversarial'])} refused as designed.")

elif view == "Counterfactual ledger":
    ledger = data["ledger"]
    frame = pd.DataFrame(
        {
            "strategy": ["do nothing", "conversion optimizer", "MarginPilot", "oracle*"],
            "net contribution": [
                ledger["do_nothing"], ledger["conversion_optimizer"],
                ledger["marginpilot"], ledger["oracle"],
            ],
        }
    ).set_index("strategy")
    st.bar_chart(frame, height=340, color="#E8A33D")
    st.caption(
        f"Realized net contribution across {len(data['seeds'])} dev worlds. "
        "*oracle reads ground truth to pick the best intervention — a cheating "
        "diagnostic, shown as an upper bound, not a competitor."
    )
    st.write("")
    st.markdown(
        f"**Cost of learning — {rupees(data['cost_of_learning_inr'])}** "
        "spent on experiments that found nothing."
    )
    st.caption(
        f"MarginPilot ran {data['marginpilot']['ran']} experiments and declined "
        f"{data['marginpilot']['skipped']} merchants outright. On this corpus it read "
        "each merchant accurately and still chose worse than a fixed rule, because the "
        "signals it read predict response, not profitability. The experimental "
        "machinery caught it — the horizon, the posterior and the scaling rule. The "
        "policy gates approved these experiments, correctly; they check budget, "
        "discount, margin, exposure and power, and have no view on which intervention "
        "pays."
    )

st.write("")
st.divider()
st.caption(
    "All figures from development worlds. The 20 holdout worlds are sealed and were "
    "not read to produce this page."
)
