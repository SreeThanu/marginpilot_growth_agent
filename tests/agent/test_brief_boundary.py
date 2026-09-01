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
from dataclasses import replace
from pathlib import Path

import pytest

from src.agent.brief import BriefBoundaryError, build_brief, brief_field_names
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


def test_brief_is_unmoved_by_every_hidden_response_parameter(world) -> None:
    """The sentinel. Mutate the latents that decide response; the brief must not
    notice. This catches a leak the static scan cannot, because it tests what the
    code does rather than what it is called."""
    baseline = build_brief(merchant_view(world))

    perturbed_params = replace(
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
    )
    perturbed = build_brief(merchant_view(replace(world, params=perturbed_params)))

    assert perturbed.to_dict() == baseline.to_dict(), (
        "a hidden response parameter reached the merchant brief"
    )


def test_brief_carries_no_segment_name_tags_or_notes(world) -> None:
    """SCI-1. The archetype key must not appear in any form."""
    brief = build_brief(merchant_view(world))
    blob = repr(brief.to_dict()).lower()

    view = merchant_view(world)
    for segment in view.segments:
        assert segment.name.lower() not in blob, f"segment name leaked: {segment.name}"
        assert segment.notes.lower()[:40] not in blob, "segment notes leaked"
        for tag in segment.behaviour_tags:
            assert tag.lower() not in blob, f"behaviour tag leaked: {tag}"

    for name in brief_field_names():
        assert name not in {"name", "notes", "behaviour_tags", "tags"}


def test_adv8_segment_fields_are_rejected_if_offered(world) -> None:
    """ADV-8. Supplying the archetype key to the pipeline must fail, not be
    silently dropped — a silent drop would let a caller believe it was used."""
    view = merchant_view(world)
    with pytest.raises(BriefBoundaryError):
        build_brief(view, _unsafe_extra_fields={"segment_name": view.segments[0].name})


def test_no_production_module_names_ground_truth() -> None:
    """Static scan. Mirrors tests/test_ground_truth_isolation.py's approach."""
    for relative in PRODUCTION_MODULES:
        source = (SRC / relative).read_text(encoding="utf-8").lower()
        stripped = re.sub(r"#.*", "", source)
        stripped = re.sub(r'""".*?"""', "", stripped, flags=re.S)
        for token in FORBIDDEN_TOKENS:
            assert token not in stripped, f"{relative} names {token!r}"


def test_the_static_scan_detects_a_planted_reference(tmp_path: Path) -> None:
    """A scan is only worth having if it fails when it should."""
    planted = tmp_path / "leaky.py"
    planted.write_text("def f(pair):\n    return pair.y1.contribution_inr\n")
    source = planted.read_text().lower()
    assert any(token in source for token in FORBIDDEN_TOKENS)


def test_production_modules_do_not_import_eval_or_posthoc() -> None:
    """Production decision code must run without the evaluation layer, and must
    never import post-hoc research scripts."""
    for relative in PRODUCTION_MODULES:
        source = (SRC / relative).read_text(encoding="utf-8")
        assert "src.eval.oracle" not in source
        assert "src.eval.replay" not in source
        assert "src.eval.harness" not in source
        assert "analysis" not in source or "analysis/posthoc" not in source
