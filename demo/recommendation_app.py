"""Standalone recommendation demo. DEMONSTRATION FIXTURES — NOT RESEARCH EVIDENCE.

Separate from ``src/ui/app.py`` on purpose: that dashboard reports the research
evaluation and is left untouched. This app reports a *product* decision on
hand-declared fixtures, and nothing it displays is evidence about anything.

Every figure on this page comes from an object the existing code returned or
from a committed artifact read at runtime. This module formats and arranges; it
computes nothing. It reimplements no gate, no economics and no validation — it
calls the functions that already own those and renders what they say.

Written against the installed Streamlit API (1.32) rather than the pinned one,
so the demo runs without disturbing the environment the research reproduces in.

Run with:  python -m streamlit run demo/recommendation_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo.audit_demo import MALFORMED_PROPOSALS, audit_recommendation  # noqa: E402
from demo.evidence import (  # noqa: E402
    HOLDOUT_COLUMNS,
    adv_command,
    holdout_results,
    reproducibility_badges,
    run_adv_tests,
    run_live_scenarios,
)
from demo.fixtures import FIXTURE_LABEL, FIXTURES, build_view  # noqa: E402
from demo.run_scenarios import run_scenario  # noqa: E402
from src.agent.brief import build_brief  # noqa: E402
from src.agent.decision_policy import recommend_from_raw  # noqa: E402
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

st.warning(
    f"**{FIXTURE_LABEL}**  ·  These merchants are hand-declared for the demo. No "
    "number on this page is a research result, and none of it is a claim about "
    "real merchants."
)

st.title("MarginPilot — should this merchant promote?")
st.caption(
    "The assistant reads the merchant's context and proposes. A deterministic "
    "economic policy decides. Where they disagree, the policy wins."
)

# --------------------------------------------------------------------------- #
# Sidebar — scenario choice and the fail-closed control
# --------------------------------------------------------------------------- #

# Labels are baked into the option strings rather than applied through
# format_func: Streamlit 1.32's AppTest reads a radio's raw value against its
# formatted options and cannot reconcile the two, which would leave this page
# untestable. Same labels on screen, testable underneath.
SCENARIO_LABELS = {f"{key} — {FIXTURES[key].title}": key for key in sorted(FIXTURES)}

choice = SCENARIO_LABELS[st.sidebar.radio("Scenario", options=list(SCENARIO_LABELS))]
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

st.sidebar.divider()
st.sidebar.markdown("**Break it**")
st.sidebar.caption(
    "Send the deterministic layer a bad proposal and watch it fail closed."
)
broken = st.sidebar.selectbox(
    "Malformed proposal", ["(none)"] + sorted(MALFORMED_PROPOSALS), index=0
)

record = run_scenario(spec)
final = record["final"]
initial = record["initial"]

# --------------------------------------------------------------------------- #
# Graceful failure — the same recommend_from_raw path, given a bad input
# --------------------------------------------------------------------------- #

if broken != "(none)":
    bad_brief = build_brief(build_view(spec))
    refused = recommend_from_raw(bad_brief, MALFORMED_PROPOSALS[broken])
    st.error(
        f"**Malformed proposal — “{broken}” → {refused.decision.value}**  \n"
        f"{refused.rationale}"
    )
    st.caption(
        "Routed through the same `recommend_from_raw` the real path uses. No "
        "separate validation exists for the demo; a reply the system cannot "
        "trust produces no recommendation at all."
    )
    with st.expander("What was sent"):
        st.json(MALFORMED_PROPOSALS[broken])
    st.divider()

# --------------------------------------------------------------------------- #
# The decision
# --------------------------------------------------------------------------- #

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
             rupees(final["expected_net_contribution_inr"]))

# --- model override, made prominent ----------------------------------------- #

if initial["overruled_the_model"]:
    st.error(
        f"### The assistant asked for {initial['model_requested']}. "
        f"The policy returned {initial['decision']}.\n\n"
        "The model reasons; it does not hold the budget. Its expected-net figure "
        "was recomputed from the merchant's own data and the request was refused "
        "on the arithmetic — this is the ADV-1 behaviour, live."
    )
else:
    st.success(
        f"Assistant requested **{initial['model_requested']}**; the deterministic "
        f"policy independently reached **{initial['decision']}**. Agreement here "
        "is a coincidence of the evidence, not deference — the policy recomputed "
        "every figure regardless."
    )

st.write("")
tab_why, tab_exp, tab_audit, tab_adv, tab_repro = st.tabs(
    ["Why", "Experiment", "Audit", "Adversarial", "Reproducibility"]
)

# --------------------------------------------------------------------------- #
# WHY — explainability, promoted out of the JSON blob
# --------------------------------------------------------------------------- #

with tab_why:
    st.subheader("Diagnosis")
    st.write(final["diagnosis"])
    st.subheader("Rationale")
    st.write(final["rationale"])

    if final["required_break_even_lift_absolute"] is not None:
        st.info(
            f"**Break-even needs a {final['required_break_even_lift_absolute']:.2%} "
            "conversion lift.** The incentive is charged on every treated order, "
            "not only the extra ones, so the promotion has to buy that many new "
            "orders before the first rupee of contribution survives."
        )

    a, b = st.columns(2)
    with a:
        st.markdown("**Evidence basis**")
        st.write(f"`{final['evidence_basis']}`")
        st.markdown("**Gates passed**")
        st.write(", ".join(final["gates_passed"]) or "—")
        if final["binding_constraints"]:
            st.markdown("**Binding constraint**")
            for constraint in final["binding_constraints"]:
                st.write(f"- `{constraint}`")
    with b:
        if final["citations"]:
            st.markdown("**Cited from the merchant's data**")
            for citation in final["citations"]:
                st.write(f"- `{citation}`")
        if final["assumptions"]:
            st.markdown("**Assumptions this rests on**")
            for assumption in final["assumptions"]:
                st.write(f"- {assumption}")

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

# --------------------------------------------------------------------------- #
# EXPERIMENT
# --------------------------------------------------------------------------- #

with tab_exp:
    experiment = record["experiment"]
    if experiment is None:
        st.info(
            "No experiment was run for this merchant. "
            + (
                "The economics cannot reach break-even, so there is nothing worth "
                "testing."
                if final["decision"] == RecommendationDecision.DO_NOT_PROMOTE.value
                else "The recommendation is to run one before spending; the demo "
                "stops where the merchant would."
            )
        )
        if final["experiment_required"]:
            st.write("")
            c1, c2 = st.columns(2)
            c1.metric("Proposed horizon", f"{final['experiment_horizon_per_arm']:,} / arm")
            c2.metric("Estimated pilot cost", rupees(final["experiment_cost_inr"]))
    else:
        st.caption(
            f"{experiment['horizon_per_arm']:,} customers per arm, sized on "
            "contribution rather than conversion by "
            "`design_experiment_on_contribution`. Pilot spend "
            f"{rupees(experiment['pilot_spend_inr'])}."
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
                for arm in experiment["arms"]
            ]
        )
        st.markdown(
            "**How this became a rollout.** The result went back through the same "
            "machinery the research evaluation uses: `evaluate()` refused a verdict "
            "before the pre-committed horizon, `assess_scale()` applied the posterior "
            "rule, and `gate_rollout()` checked the standing limits. "
            f"Gates cleared: `{', '.join(final['gates_passed'])}`."
        )
        st.caption(
            "PROMOTE is unreachable from the initial reasoning by construction — "
            "`recommend()` has no branch that returns it."
        )

# --------------------------------------------------------------------------- #
# AUDIT — the decision on screen, written to the project's own log
# --------------------------------------------------------------------------- #

with tab_audit:
    trail = audit_recommendation(record)
    a, b = st.columns(2)
    a.metric("Chain verification", "PASS" if trail.verified else "FAIL")
    b.metric("Entries", f"{len(trail.entries)}")

    if trail.payload_is_the_rendered_object:
        st.success(
            "The audited payload **is** the recommendation displayed above — the "
            "same object, not a copy and not a re-derivation. A chain of unrelated "
            "valid entries would show a green tick and prove nothing."
        )
    else:
        st.error("The audited payload is not the rendered recommendation.")

    st.caption(
        "Written through `src/audit/log.py` unmodified: same `append()`, same "
        "`Stage` values, same SHA-256 chain. UPDATE and DELETE are refused by "
        "SQLite triggers inside the schema, so append-only holds no matter who "
        "opens the database."
    )
    st.code(trail.rendered or "(no entries)", language="text")

# --------------------------------------------------------------------------- #
# ADVERSARIAL — seven run live, twelve read from the test suite
# --------------------------------------------------------------------------- #

with tab_adv:
    st.subheader("Seven scenarios, executed now")
    st.caption(
        "Run live against `src/eval/adversarial.py` — the same code `make "
        "adversarial` runs. Each attempts something the system must refuse."
    )
    scenarios = run_live_scenarios()
    for result in scenarios:
        icon = "✅" if result.refused else "❌"
        with st.expander(f"{icon}  {result.name} — "
                         f"{'REFUSED' if result.refused else 'NOT REFUSED'}"):
            st.write(f"**Attempted:** {result.attempted}")
            st.write(f"**Refused by:** `{result.refused_by}`")
            st.write(f"**Reason:** {result.reason}")

    st.divider()
    st.subheader("ADV-1 … ADV-12 — test-suite outcomes")
    st.caption(
        "These are not run on this page by default. Pressing the button runs the "
        "existing tests and reads pytest's own verdict for each; no pass/fail "
        "label is written into the demo."
    )
    st.code(adv_command(), language="bash")

    if st.button("Run the ADV tests now"):
        with st.spinner("running pytest…"):
            outcomes, tail = run_adv_tests()
        st.session_state["adv_outcomes"] = [
            {"case": o.label, "test": o.test, "file": o.path, "pytest verdict": o.status}
            for o in outcomes
        ]
        st.session_state["adv_tail"] = tail

    if "adv_outcomes" in st.session_state:
        st.table(st.session_state["adv_outcomes"])
        st.caption("pytest output, last lines:")
        st.code(st.session_state["adv_tail"], language="text")

# --------------------------------------------------------------------------- #
# REPRODUCIBILITY — secondary, but checkable
# --------------------------------------------------------------------------- #

with tab_repro:
    st.subheader("How this pins itself")
    for badge in reproducibility_badges():
        st.markdown(f"**{badge.label}** — `{badge.value}`  \n{badge.detail}")

    st.divider()
    st.subheader("The recorded holdout run")
    rows, meta = holdout_results()
    if not rows:
        st.info("`data/holdout_results.json` is not present in this checkout.")
    else:
        st.caption(
            f"Read at runtime from `data/holdout_results.json` — "
            f"{meta.get('worlds_seen')} sealed worlds, opened once, payments in "
            f"`{meta.get('payment_client_mode')}` mode. This is the research "
            "result, not a demo fixture."
        )
        money = {"realized_net_inr", "promotion_spend_inr", "cost_of_learning_inr"}
        st.table(
            [
                {
                    label: (
                        rupees(row[key]) if key in money and row.get(key) is not None
                        else row.get(key)
                    )
                    for key, label in HOLDOUT_COLUMNS
                }
                for row in rows
            ]
        )
        st.caption(
            "Do-nothing wins. That is the finding, and it was predicted before the "
            "seal was opened."
        )
