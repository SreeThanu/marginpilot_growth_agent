"""The dashboard renders results; it must not be able to reach for them.

The holdout seal holds here because the UI has no route to a world at all, not
because it promises to be careful. That is worth a test: a future convenience
import of the generator would open exactly such a route.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "ui" / "app.py"
SNAPSHOT = ROOT / "data" / "dashboard_snapshot.json"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_the_app_cannot_reach_a_world_or_ground_truth() -> None:
    """No import path to the generator, the harness, or the executor."""
    forbidden = ("src.world", "src.eval.harness", "src.eval.executor", "src.eval.oracle")
    found = {i for i in _imports(APP) if i.startswith(forbidden)}
    assert not found, (
        f"src/ui/app.py imports {found}; the dashboard must read the snapshot and "
        "nothing else, so that it has no route to worlds/holdout/"
    )


def _rendered_source() -> str:
    """The app without its module docstring.

    The docstring states the rules this file must follow, including quoting the
    claims it must not make. Scanning it for those phrases would flag the
    prohibition as the offence.
    """
    tree = ast.parse(APP.read_text())
    body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    return "\n".join(ast.unparse(node) for node in body)


def test_the_app_never_reaches_for_a_world() -> None:
    """Prose about the holdout is fine — a path or an API call is not."""
    source = _rendered_source()
    for marker in ("worlds/", "worlds\\", "generate_world", "GroundTruth",
                   "load_world", "generate("):
        assert marker not in source, f"src/ui/app.py references {marker!r} in code"


def test_the_app_reads_exactly_one_file() -> None:
    """One input. A second would be a second thing that could go stale."""
    source = APP.read_text()
    assert source.count("Path(") == 1
    assert 'SNAPSHOT = Path("data/dashboard_snapshot.json")' in source


def test_the_app_does_not_poll_or_autorefresh() -> None:
    """This displays a completed evaluation, not a live operations feed."""
    source = APP.read_text()
    for marker in ("autorefresh", "auto_refresh", "st.rerun", "experimental_rerun",
                   "time.sleep", "while True"):
        assert marker not in source, f"src/ui/app.py appears to poll: {marker!r}"


def test_the_app_does_not_credit_the_gates_with_catching_selection() -> None:
    """Pinned in docs/simulator.md 4g: the gates approved those experiments.

    Any wording implying they caught the selection failure is false and would be
    contradicted by gates.py, which has no view on which intervention pays.
    """
    source = _rendered_source().lower()
    assert "have no view on which intervention" in source, (
        "the ledger caption must state what the gates do not do"
    )
    for claim in ("gates caught", "gate caught", "gates detected", "gates prevented",
                  "gates blocked", "policy saved", "gates saved"):
        assert claim not in source, f"src/ui/app.py implies {claim!r}"


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="snapshot not generated")
def test_the_snapshot_is_labelled_as_holdout_and_carries_real_figures() -> None:
    data = json.loads(SNAPSHOT.read_text())
    assert "holdout" in data["generated_from"]
    assert data["dataset"] == "HOLDOUT WORLDS"
    assert "opened once" in data["dataset_detail"]

    # Four ledger entries, no more — four bars read, six get skipped.
    assert set(data["ledger"]) == {
        "do_nothing", "conversion_optimizer", "marginpilot", "oracle"
    }
    assert data["ledger"]["do_nothing"] == 0.0

    # The headline case must genuinely diverge, or the page is illustrating
    # something that did not happen.
    featured = data["featured_experiment"]
    assert featured is not None
    assert featured["conversion_lift"] > 0, "featured case must show a conversion win"
    assert featured["net_contribution_inr"] < 0, "featured case must show a contribution loss"

    assert data["audit_chain"]["verified"] is True
    assert data["audit_chain"]["entries"] > 0
    assert len(data["adversarial"]) == 7
    assert all(s["refused"] for s in data["adversarial"])
