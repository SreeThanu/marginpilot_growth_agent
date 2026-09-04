"""Standalone recommendation demo. DEMONSTRATION FIXTURES — NOT RESEARCH EVIDENCE.

Separate from ``src/ui/app.py`` on purpose: that dashboard reports the research
evaluation and is left untouched. This app reports a *product* decision on
hand-declared fixtures, and nothing it displays is evidence about anything.

Every figure on this page comes from an object the existing code returned or
from a committed artifact read at runtime. This module formats and arranges; it
computes nothing. It reimplements no gate, no economics and no validation — it
calls the functions that already own those and renders what they say.

Laid out for a reader who has ten seconds: what was decided, what it earns after
the incentive is paid, and why. Everything that supports the claim — the pilot,
the audit chain, the safety refusals, the reproducibility pins — sits below the
decision rather than beside it.

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


def chip(text: str, tone: str = "neutral") -> str:
    """A small inline pill. Presentation only."""
    colours = {
        "neutral": ("rgba(128,128,128,0.14)", "inherit"),
        "good": ("rgba(19,115,51,0.14)", "#137333"),
        "warn": ("rgba(138,109,0,0.16)", "#8a6d00"),
        "bad": ("rgba(165,14,14,0.12)", "#a50e0e"),
    }
    background, colour = colours.get(tone, colours["neutral"])
    return (
        f"<span style='display:inline-block;padding:0.15rem 0.6rem;margin:0 0.3rem "
        f"0.3rem 0;border-radius:999px;background:{background};color:{colour};"
        f"font-size:0.82rem;white-space:nowrap'>{text}</span>"
    )


st.set_page_config(page_title="MarginPilot — recommendation", layout="wide")

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #

st.title("MarginPilot — should this merchant promote?")
st.caption(
    "The assistant reads the merchant's context and proposes. A deterministic "
    "economic policy decides. Where they disagree, the policy wins."
)

# The integrity notice. Compact, but it stays on the main page and stays
# obvious in a screenshot — the wording is unchanged from the banner it
# replaces, only its weight is.
st.markdown(
    f"<div style='padding:0.5rem 0.85rem;margin:0.25rem 0 1.1rem 0;"
    f"border-left:4px solid #8a6d00;background:rgba(138,109,0,0.10);"
    f"border-radius:3px;font-size:0.86rem;line-height:1.45'>"
    f"<strong style='color:#8a6d00;letter-spacing:0.02em'>{FIXTURE_LABEL}</strong>"
    f"  ·  These merchants are hand-declared for the demo. No number on this page "
    f"is a research result, and none of it is a claim about real merchants."
    f"</div>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Sidebar — scenario navigation and a compact merchant snapshot
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
st.sidebar.caption(
    f"{spec.population:,} customers · {rupees(spec.aov_inr)} AOV · "
    f"{spec.margin:.0%} margin · {rupees(spec.budget_inr)} budget · "
    f"{spec.observed_conversion:.1%} conversion · {spec.intervention_name}"
)

record = run_scenario(spec)
final = record["final"]
initial = record["initial"]

# --------------------------------------------------------------------------- #
# SCENARIO STRIP
# --------------------------------------------------------------------------- #

st.markdown(
    f"<div style='font-size:0.78rem;letter-spacing:0.09em;opacity:0.6'>SCENARIO "
    f"{record['scenario']}</div>"
    f"<div style='font-size:1.15rem;font-weight:600;margin-bottom:0.15rem'>"
    f"{spec.title}</div>"
    f"<div style='font-size:0.86rem;opacity:0.75'>{spec.population:,} customers "
    f"· {rupees(spec.aov_inr)} AOV · {spec.margin:.0%} margin · "
    f"{rupees(spec.budget_inr)} budget · offer: {spec.intervention_name}</div>",
    unsafe_allow_html=True,
)
st.write("")

# --------------------------------------------------------------------------- #
# RECOMMENDATION — the hero
# --------------------------------------------------------------------------- #

colour = DECISION_COLOUR.get(final["decision"], "#5f6368")
st.markdown(
    f"<div style='padding:1.1rem 1.35rem;border-left:7px solid {colour};"
    f"background:rgba(128,128,128,0.08);border-radius:5px'>"
    f"<div style='font-size:0.78rem;letter-spacing:0.09em;opacity:0.65'>"
    f"RECOMMENDATION</div>"
    f"<div style='font-size:2.4rem;font-weight:700;color:{colour};"
    f"line-height:1.15'>{final['decision']}</div>"
    f"<div style='opacity:0.85;font-size:0.95rem'>"
    f"{DECISION_GLOSS.get(final['decision'], '')}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# ECONOMIC SUMMARY — three cards, NET dominant
# --------------------------------------------------------------------------- #

st.write("")


def money_card(label: str, value: str, *, hero: bool = False, tone: str = "") -> str:
    accent = tone or "inherit"
    return (
        f"<div style='padding:{'1rem 1.15rem' if hero else '0.8rem 1rem'};"
        f"border:1px solid rgba(128,128,128,{'0.45' if hero else '0.25'});"
        f"border-radius:6px;background:rgba(128,128,128,{'0.07' if hero else '0.03'});"
        f"height:100%'>"
        f"<div style='font-size:0.74rem;letter-spacing:0.07em;opacity:0.65;"
        f"text-transform:uppercase'>{label}</div>"
        f"<div style='font-size:{'2.1rem' if hero else '1.45rem'};font-weight:"
        f"{'700' if hero else '600'};color:{accent};line-height:1.25'>{value}</div>"
        f"</div>"
    )


net = final["expected_net_contribution_inr"]
net_tone = "#137333" if net > 0 else "#a50e0e" if net < 0 else "inherit"

econ_left, econ_mid, econ_right = st.columns([1, 1, 1.3])
econ_left.markdown(
    money_card("Incremental contribution",
               rupees(final["expected_incremental_contribution_inr"])),
    unsafe_allow_html=True,
)
econ_mid.markdown(
    money_card("Incentive cost", rupees(final["expected_incentive_cost_inr"])),
    unsafe_allow_html=True,
)
econ_right.markdown(
    money_card("Net contribution", rupees(net), hero=True, tone=net_tone),
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# MODEL → POLICY — a one-line trust signal
# --------------------------------------------------------------------------- #

st.write("")
overruled = initial["overruled_the_model"]
signal_colour = "#a50e0e" if overruled else "#137333"
signal_note = (
    "The model reasons; it does not hold the budget. Its request was recomputed "
    "from the merchant's own data and refused on the arithmetic."
    if overruled
    else "Agreement, not deference — the policy recomputed every figure regardless."
)
st.markdown(
    f"<div style='padding:0.6rem 0.9rem;border:1px solid rgba(128,128,128,0.28);"
    f"border-radius:5px;font-size:0.9rem'>"
    f"<span style='opacity:0.65'>Model proposed</span> "
    f"<strong>{initial['model_requested']}</strong> "
    f"<span style='opacity:0.5'>&nbsp;→&nbsp;</span> "
    f"<span style='opacity:0.65'>Policy returned</span> "
    f"<strong style='color:{signal_colour}'>{initial['decision']}</strong>"
    f"<span style='opacity:0.5'>&nbsp;·&nbsp;</span>"
    f"<span style='opacity:0.75'>{signal_note}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# WHY — page level, scannable before it is readable
# --------------------------------------------------------------------------- #

st.write("")
st.subheader("Why")

chips = [chip(f"evidence: {final['evidence_basis']}")]
if final["gates_passed"]:
    chips.append(chip("gates " + " ".join(final["gates_passed"]), "good"))
if final["required_break_even_lift_absolute"] is not None:
    chips.append(
        chip(f"break-even {final['required_break_even_lift_absolute']:.2%} lift", "warn")
    )
for constraint in final["binding_constraints"]:
    chips.append(chip(constraint, "bad"))
for item in final["unresolved"]:
    chips.append(chip(item, "warn"))
st.markdown("".join(chips), unsafe_allow_html=True)

st.markdown(f"**Diagnosis.** {final['diagnosis']}")
st.markdown(f"**Rationale.** {final['rationale']}")

if final["required_break_even_lift_absolute"] is not None:
    st.caption(
        f"Break-even needs a {final['required_break_even_lift_absolute']:.2%} "
        "conversion lift. The incentive is charged on every treated order, not "
        "only the extra ones, so the promotion has to buy that many new orders "
        "before the first rupee of contribution survives."
    )

with st.expander("Evidence this rests on"):
    a, b = st.columns(2)
    with a:
        if final["citations"]:
            st.markdown("**Cited from the merchant's data**")
            for citation in final["citations"]:
                st.write(f"- `{citation}`")
        if final["binding_constraints"]:
            st.markdown("**Binding constraint**")
            for constraint in final["binding_constraints"]:
                st.write(f"- `{constraint}`")
    with b:
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
# SUPPORTING EVIDENCE — everything that backs the decision, below it
# --------------------------------------------------------------------------- #

st.write("")
st.divider()
st.subheader("Supporting evidence")
st.caption(
    "The pilot behind the decision, the audit record of it, the refusals the "
    "system makes under attack, and how all of it pins down."
)

tab_exp, tab_audit, tab_safety, tab_repro = st.tabs(
    ["Experiment", "Audit", "Safety", "Reproducibility"]
)

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
# SAFETY — seven refusals run live, twelve read from the test suite, and the
# fail-closed control that used to live in the sidebar
# --------------------------------------------------------------------------- #

with tab_safety:
    st.markdown("**Send the policy a bad proposal**")
    st.caption(
        "Routed through the same `recommend_from_raw` the real path uses. No "
        "separate validation exists for the demo; a reply the system cannot "
        "trust produces no recommendation at all."
    )
    broken = st.selectbox(
        "Malformed proposal", ["(none)"] + sorted(MALFORMED_PROPOSALS), index=0
    )
    if broken != "(none)":
        bad_brief = build_brief(build_view(spec))
        refused = recommend_from_raw(bad_brief, MALFORMED_PROPOSALS[broken])
        st.error(
            f"**{broken} → {refused.decision.value}**  \n{refused.rationale}"
        )
        with st.expander("What was sent"):
            st.json(MALFORMED_PROPOSALS[broken])

    st.divider()
    st.markdown("**Seven scenarios, executed now**")
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
    st.markdown("**ADV-1 … ADV-12 — test-suite outcomes**")
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
    st.markdown("**How this pins itself**")
    for badge in reproducibility_badges():
        st.markdown(f"**{badge.label}** — `{badge.value}`  \n{badge.detail}")

    st.divider()
    st.markdown("**The recorded holdout run**")
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
