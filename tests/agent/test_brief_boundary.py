"""The production feature pipeline must not carry hidden simulator structure.

Three separate guards, because one is not enough:

* a **sentinel** test that mutates the hidden response latents and asserts the
  brief does not move — the strongest of the three, since it tests behaviour
  rather than spelling;
* a **static scan** for the vocabulary of ground truth and archetype structure;
* a **planted-reference** test, because a scan that never fails is not a guard.

SCI-1 is enforced here: ``SegmentView.name``/``notes``/``behaviour_tags`` are a
bijective key to the withheld archetype multipliers (see
``analysis/posthoc/provenance/segmentview.md``) and must never reach production
features.
"""

from __future__ import annotations

import re
from dataclasses import fields, replace
from pathlib import Path

import pytest

from src.agent.brief import (
    BriefBoundaryError,
    HistoryBrief,
    build_brief,
    brief_field_names,
)
from src.eval.contracts import merchant_view
from src.world.generator import generate_world

SRC = Path(__file__).resolve().parent.parent.parent / "src"

#: Hidden latents that decide treatment response. None may influence the brief.
HIDDEN_RESPONSE_PARAMS = (
    "promo_response_scale",
    "responsiveness_sigma",
    "shipping_affinity",
    "clearance_affinity",
    "pct_affinity",
    "bundle_affinity",
    "elasticity_mean",
    "elasticity_sd",
    "cannibalization_rate",
    "competitive_pressure",
)

#: Vocabulary that must not appear anywhere in the production agent modules.
FORBIDDEN_TOKENS = (
    "y0", "y1", "potentialoutcome", "groundtruth", "load_ground_truth",
    "tau_contribution", "tau_converted", "true_population_net",
    "best_intervention_id",
)

PRODUCTION_MODULES = (
    "agent/brief.py",
    "agent/net_value.py",
    "agent/recommendation.py",
    "agent/decision_policy.py",
)


@pytest.fixture(scope="module")
def world():
    return generate_world(20001, split="dev")


def _perturbed(world):
    """The same world with every hidden response latent moved to an extreme."""
    return replace(
        world,
        params=replace(
            world.params,
            promo_response_scale=2.1,
            responsiveness_sigma=0.60,
            shipping_affinity=2.2,
            clearance_affinity=2.2,
            pct_affinity=2.2,
            bundle_affinity=2.2,
            elasticity_mean=-5.0,
            elasticity_sd=0.90,
            cannibalization_rate=0.45,
            competitive_pressure=not world.params.competitive_pressure,
        ),
    )


def test_only_campaign_history_moves_when_the_hidden_latents_move(world) -> None:
    """The sentinel, and the sharpest guard here: it tests behaviour, not spelling.

    Mutate every latent that decides treatment response and the brief must not
    notice — with one declared exception. ``InterventionHistory`` is a *measured
    past campaign*, so it is downstream of the response model by construction and
    legitimately moves. That is the documented Class-A channel, not a leak: it
    carries a noisy realised outcome with its own standard error, never a latent.

    Pinning the exception to exactly one field is the point. If any other field
    starts moving, a latent has found a new route into the brief.
    """
    baseline = build_brief(merchant_view(world)).to_dict()
    perturbed = build_brief(merchant_view(_perturbed(world))).to_dict()

    moved = {k for k in baseline if baseline[k] != perturbed[k]}
    assert moved <= {"history"}, f"a hidden response parameter reached: {moved}"


#: Every field ``HistoryBrief`` is permitted to carry. An **allowlist**, not a
#: denylist, and the distinction is the whole point.
#:
#: The sentinel above exempts ``history`` from the no-movement rule, because a
#: measured past campaign is legitimately downstream of the response model. That
#: exemption is only as narrow as the shape of what ``history`` contains — and
#: until this test existed, that shape was guaranteed by nothing but the current
#: dataclass definition.
#:
#: A denylist of suspicious names would not do. ``SegmentView.name`` is the
#: precedent: an innocuous, legitimate-sounding field that turned out to be a
#: bijective key to withheld response multipliers. A latent proxy added here
#: under a plausible name — ``response_index``, ``category_score`` — would pass
#: any name-based filter. So the rule is equality against an enumerated set:
#: anything not on the list fails, whatever it is called.
#:
#: Adding a field is not forbidden. It requires editing this list, which is a
#: deliberate act a reviewer can see in a diff.
ALLOWED_REALIZED_HISTORY_FIELDS = frozenset(
    {
        # which past campaign this describes
        "intervention_id",
        # how large it was — the denominator behind the estimate
        "treated_customers",
        # realized orders observed in the treated arm
        "orders",
        # realized incremental net per treated customer, measured against a
        # control arm the merchant held back at the time
        "net_per_treated_customer_inr",
        # the honest width of that estimate
        "standard_error_inr",
    }
)


def test_the_history_exemption_is_bounded_by_an_explicit_allowlist() -> None:
    """Fail closed on any field the allowlist does not name.

    Equality, not containment. A superset fails (a field was added), a subset
    fails (one was removed or renamed), and a same-size swap fails. The test
    cannot be satisfied by a field that merely *looks* legitimate.
    """
    actual = {field.name for field in fields(HistoryBrief)}

    assert actual == ALLOWED_REALIZED_HISTORY_FIELDS, (
        "HistoryBrief's shape changed, and it is the one field the sentinel "
        "exempts from the hidden-latent check.\n"
        f"  unexpected fields: {sorted(actual - ALLOWED_REALIZED_HISTORY_FIELDS)}\n"
        f"  missing fields:    {sorted(ALLOWED_REALIZED_HISTORY_FIELDS - actual)}\n"
        "Every field here must be a realized outcome of a past campaign, never "
        "a latent response parameter or a proxy for one. If the addition is "
        "legitimate, add it to ALLOWED_REALIZED_HISTORY_FIELDS deliberately."
    )


def test_the_sentinel_would_notice_a_latent_reaching_the_brief(world) -> None:
    """A guard that cannot fail is not a guard."""
    baseline = build_brief(merchant_view(world)).to_dict()
    perturbed = build_brief(merchant_view(_perturbed(world))).to_dict()
    planted_baseline = dict(baseline, observed_margin=world.params.promo_response_scale)
    planted_perturbed = dict(
        perturbed, observed_margin=_perturbed(world).params.promo_response_scale
    )
    moved = {k for k in planted_baseline if planted_baseline[k] != planted_perturbed[k]}
    assert not moved <= {"history"}


def test_brief_carries_no_segment_identity(world) -> None:
    """SCI-1. Poison the segment labels; none of it may reach the brief.

    Substring-matching the real archetype text would be unreliable — the tag
    ``gifting`` legitimately appears inside a seasonal-calendar string — so the
    segments are replaced with markers that could only come from one place.
    """
    from dataclasses import replace as dc_replace

    view = merchant_view(world)
    poisoned = dc_replace(
        view,
        segments=tuple(
            dc_replace(
                s,
                name=f"POISON_NAME_{i}",
                notes=f"POISON_NOTES_{i}",
                behaviour_tags=(f"POISON_TAG_{i}",),
            )
            for i, s in enumerate(view.segments)
        ),
    )

    clean = build_brief(view).to_dict()
    assert build_brief(poisoned).to_dict() == clean, "a segment field reached the brief"
    assert "POISON" not in repr(clean).upper()

    # The brief has no segment container at all, which is why the poison above
    # cannot reach it. ``name`` does appear — as InterventionBrief.name, the
    # offer's own label ("Free shipping") — so the field is scoped, not banned.
    fields = brief_field_names()
    assert "segments" not in fields
    for segment_only in ("behaviour_tags", "tags", "notes"):
        assert segment_only not in fields, f"the brief carries {segment_only}"


def test_adv8_segment_fields_are_rejected_if_offered(world) -> None:
    """ADV-8. Supplying the archetype key to the pipeline must fail, not be
    silently dropped — a silent drop would let a caller believe it was used."""
    view = merchant_view(world)
    with pytest.raises(BriefBoundaryError):
        build_brief(view, _unsafe_extra_fields={"segment_name": view.segments[0].name})


def _executable_source(relative: str) -> str:
    """Module source with comments, docstrings and the denylist literal removed.

    The denylist in ``recommendation.py`` names every forbidden token on purpose
    — it is what rejects them — so scanning it would flag the guard for being a
    guard. Everything else in the module is still scanned.
    """
    source = (SRC / relative).read_text(encoding="utf-8").lower()
    source = re.sub(r'""".*?"""', "", source, flags=re.S)
    source = re.sub(r"#.*", "", source)
    return re.sub(r"forbidden_proposal_tokens\s*=\s*\(.*?\)", "", source, flags=re.S)


def test_no_production_module_names_ground_truth() -> None:
    """Static scan. Mirrors tests/test_ground_truth_isolation.py's approach."""
    for relative in PRODUCTION_MODULES:
        stripped = _executable_source(relative)
        for token in FORBIDDEN_TOKENS:
            assert token not in stripped, f"{relative} names {token!r}"


def test_the_static_scan_detects_a_planted_reference(tmp_path: Path) -> None:
    """A scan is only worth having if it fails when it should."""
    planted = tmp_path / "leaky.py"
    planted.write_text("def f(pair):\n    return pair.y1.contribution_inr\n")
    source = planted.read_text().lower()
    assert any(token in source for token in FORBIDDEN_TOKENS)


#: Modules the production decision path may never import. ``src.eval.contracts``
#: is deliberately absent: it defines the merchant view, carries no ground truth,
#: and is the shared vocabulary the research and the product both speak.
BANNED_IMPORTS = (
    "src.eval.oracle", "src.eval.replay", "src.eval.harness",
    "src.eval.devcorpus", "src.eval.executor", "src.world.persistence",
    "analysis",
)


def _imported_modules(relative: str) -> set[str]:
    """Every module named by an import statement. Prose in docstrings is ignored."""
    import ast

    tree = ast.parse((SRC / relative).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_production_modules_do_not_import_eval_internals_or_posthoc() -> None:
    """Production decision code must run without the evaluation layer.

    Checked against actual import statements rather than raw text, so a
    docstring that *names* a research path in order to explain a boundary does
    not read as a dependency on it.
    """
    for relative in PRODUCTION_MODULES:
        for imported in _imported_modules(relative):
            for banned in BANNED_IMPORTS:
                assert not imported.startswith(banned), (
                    f"{relative} imports {imported}"
                )
