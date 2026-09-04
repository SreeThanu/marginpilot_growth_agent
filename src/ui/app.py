"""MarginPilot dashboard. Reads one snapshot file; reaches for nothing.

Run with ``streamlit run src/ui/app.py`` after ``python -m src.ui.snapshot``.

The UI has no import path to the world generator, the harness or ground truth.
It renders ``data/dashboard_snapshot.json`` and can therefore not read
``worlds/holdout/`` even by mistake — the seal holds because there is no route,
not because this file promises to be careful.

Every figure shown comes from the sealed holdout worlds and is labelled as such.

**One framing rule.** The policy gates approved the experiments the agent chose,
correctly: budget, discount, margin, exposure and power were all within limits.
Nothing on this page may imply the gates caught the selection failure. What
caught it was measurement — the horizon, the posterior and the scaling rule.
See ``docs/simulator.md`` 4g, which a test pins.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

#: Overridable so a test can render a snapshot other than the live one — the
#: SCALE branch of the Decision view is otherwise unreachable, since the holdout
#: featured experiment is a KILL.
SNAPSHOT = Path(os.environ.get("MARGINPILOT_SNAPSHOT", "data/dashboard_snapshot.json"))

#: The posterior probability a campaign must clear to be scaled. Mirrors
#: src/experiment/evaluator.py; shown on the Decision view as the bar the
#: measured value is read against.
SCALE_THRESHOLD = 0.80

st.set_page_config(page_title="MarginPilot", layout="wide")


@st.cache_data
def load(path: str) -> dict:
    """Read the snapshot.

    Keyed on the path: a zero-argument cache would key on nothing and keep
    serving the first snapshot it ever read, even after the file underneath it
    changed.
    """
    snapshot = Path(path)
    if not snapshot.exists():
        st.error(
            f"No snapshot at {snapshot}. Generate it with:\n\n"
            "    python -m src.ui.snapshot"
        )
        st.stop()
    return json.loads(snapshot.read_text())


def dataset_badge() -> None:
    """State which dataset this view is showing, in the view itself.

    Two datasets now exist — development worlds and the sealed holdout — and
    their headline figures differ (5 experiments across 10 dev worlds against 9
    across 20 holdout). A number without its dataset attached is a number a
    reader can misattribute, and a page footer is too far from the figure to
    prevent that.
    """
    st.caption(f":grey[**{data['dataset']}**  ·  {data['dataset_detail']}]")


def rupees(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rs.{abs(amount):,.0f}"


data = load(str(SNAPSHOT))
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
        # "normal", so the sign carries the meaning: a negative contribution is
        # a loss and renders red. "inverse" flipped that and painted a
        # -Rs.4,269 loss GREEN beside a KILL verdict — the same defect already
        # fixed on the P(net > 0) metric, in the same direction.
        delta_color="normal",
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
    dataset_badge()
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
        width="stretch",
    )
    st.caption(
        f"Budget overruns: **{budget['overruns']}**. Both the pilot and the rollout "
        "pass the gate; gating only the pilot would gate the cheaper half."
    )

elif view == "Live experiment":
    dataset_badge()
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
            "experiment early, however favourable it looks."
        )

elif view == "Contribution":
    dataset_badge()
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
            width="stretch",
        )
        st.caption(
            "Contribution is earned on the incremental orders. The incentive is paid "
            "on all of them. That asymmetry is the entire finding."
        )

elif view == "Decision":
    dataset_badge()
    if not featured:
        st.info("No decision in this snapshot.")
    else:
        # Three elements. This view is the scaling rule and should read as one
        # idea: the verdict, the evidence bar it had to clear, and the interval
        # that decides. Anything else here competes with the thing being shown.
        verdict = "SCALE" if featured["scaled"] else "KILL"
        if featured["scaled"]:
            st.success(f"### {verdict}")
        else:
            st.error(f"### {verdict}")

        # delta_color is "normal" so the sign carries the meaning: a shortfall
        # is negative and renders red, a clearance is positive and renders
        # green. The earlier conditional selected "inverse" on a miss, which
        # flips that — a -41% shortfall rendered GREEN beside a KILL verdict,
        # with the colour and the number saying opposite things.
        st.metric(
            "P(net > 0)",
            f"{featured['probability_net_positive']:.0%}",
            f"{featured['probability_net_positive'] - SCALE_THRESHOLD:+.0%} "
            f"against the {SCALE_THRESHOLD:.2f} threshold",
            delta_color="normal",
        )

        st.code(
            f"  point estimate   {rupees(featured['net_contribution_inr'])}\n"
            f"  95% interval     [{rupees(featured['ci_low_inr'])}, "
            f"{rupees(featured['ci_high_inr'])}]\n"
            f"  projected 5th %  {rupees(featured['projected_downside_inr'])}",
            language="text",
        )

elif view == "Audit chain":
    dataset_badge()
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
    dataset_badge()
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
    dataset_badge()
    ledger = data["ledger"]
    frame = pd.DataFrame(
        {
            "strategy": [
                "do nothing (baseline)",
                "conversion optimizer",
                "MarginPilot",
                "oracle — cheating diagnostic",
            ],
            "net contribution": [
                ledger["do_nothing"], ledger["conversion_optimizer"],
                ledger["marginpilot"], ledger["oracle"],
            ],
        }
    )
    # Horizontal. Vertical bars rotate these labels to unreadable stubs, and the
    # do-nothing bar is exactly zero — invisible as a bar, so the zero line has
    # to be the reference the others are read against rather than a bar of its own.
    st.bar_chart(
        frame, x="net contribution", y="strategy",
        horizontal=True, height=300, color="#E8A33D",
    )
    st.caption(
        "**Zero is the line to beat** — *do nothing* sits exactly on it and has no "
        "visible bar. Every strategy falls to its left. The oracle reads ground "
        "truth to pick the best intervention: an upper bound, not a competitor."
    )
    st.write("")
    st.markdown(
        f"**Cost of learning — {rupees(data['cost_of_learning_inr'])}** "
        "spent on experiments that found nothing."
    )
    st.caption(
        f"Across {data['dataset_short']}, MarginPilot ran {data['marginpilot']['ran']} "
        f"experiments and declined {data['marginpilot']['skipped']} merchants outright — "
        f"against the unreasoning engine's 77. It read "
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
    "All figures from the 20 sealed holdout worlds, opened once at final evaluation "
    "and read through the guard with an explicit final_eval flag. Nothing on this "
    "page was tuned in response to them."
)
