"""Every view must render. Two of them shipped broken.

`st.warning(..., icon="■")` and `st.error(..., icon="▼")` raise: Streamlit takes
a valid emoji or a material shortcode there, not an arbitrary glyph. Both the
Live experiment and Decision views died with a traceback, and nothing caught it
because no test ever ran the app.

AppTest executes the real script, so this exercises what a viewer would see
rather than a stand-in for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "ui" / "app.py"
SNAPSHOT = ROOT / "data" / "dashboard_snapshot.json"

VIEWS = [
    "Budget", "Live experiment", "Contribution", "Decision",
    "Audit chain", "Adversarial", "Counterfactual ledger",
]

pytestmark = pytest.mark.skipif(
    not SNAPSHOT.exists(), reason="snapshot not generated; run python -m src.ui.snapshot"
)


def _run(view: str | None = None) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run()
    if view is not None:
        app.radio[0].set_value(view).run()
    return app


def test_the_page_loads() -> None:
    app = _run()
    assert not app.exception, f"app raised on load: {app.exception}"
    assert app.title[0].value == "MarginPilot"


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_renders_without_error(view: str) -> None:
    """The regression guard. Both crashes were in this list."""
    app = _run(view)
    assert not app.exception, f"view {view!r} raised: {app.exception}"


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_states_which_dataset_it_shows(view: str) -> None:
    """A figure without its dataset attached is one a reader can misattribute,
    and the page footer is too far from the number to prevent that."""
    app = _run(view)
    captions = " ".join(c.value for c in app.caption)
    assert "HOLDOUT WORLDS" in captions, (
        f"view {view!r} does not name its dataset in the view itself"
    )


def test_no_icon_arguments_survive() -> None:
    """The exact defect: Streamlit rejects a geometric glyph as an icon."""
    assert "icon=" not in APP.read_text(), (
        "st.warning/st.error/st.success take a valid emoji or material shortcode; "
        "an arbitrary glyph raises at render time"
    )


def test_the_ledger_plots_four_horizontal_bars() -> None:
    app = _run("Counterfactual ledger")
    assert not app.exception
    source = APP.read_text()
    assert "horizontal=True" in source, "vertical bars rotate the labels unreadable"
    for label in ("do nothing (baseline)", "conversion optimizer", "MarginPilot",
                  "oracle — cheating diagnostic"):
        assert label in source, f"ledger is missing the {label!r} bar"
    # Exactly four. Six bars need a legend and get skipped.
    data = json.loads(SNAPSHOT.read_text())
    assert len(data["ledger"]) == 4


def test_the_decision_view_reads_as_one_idea() -> None:
    """Three elements: the verdict, the evidence bar, the interval.

    This view *is* the scaling rule. Anything else on it competes with the thing
    being shown, so the count is pinned rather than left to drift.
    """
    app = _run("Decision")
    assert not app.exception
    # The two headline metrics render on every view; the Decision view adds one.
    assert len(app.metric) == 3, f"Decision view has {len(app.metric)} metrics, expected 3"
    assert len(app.code) == 1, "the posterior interval should be the only code block"
    assert len(app.dataframe) == 0, "no table belongs on this view"


# --------------------------------------------------------------------------- #
# The delta badge's colour must agree with its number
# --------------------------------------------------------------------------- #


def _decision_metric(snapshot_path: Path | None = None):
    """Render the Decision view, optionally against a substitute snapshot."""
    import os

    from streamlit.proto.Metric_pb2 import Metric

    if snapshot_path is not None:
        os.environ["MARGINPILOT_SNAPSHOT"] = str(snapshot_path)
    else:
        os.environ.pop("MARGINPILOT_SNAPSHOT", None)
    try:
        app = _run("Decision")
        assert not app.exception, app.exception
        metric = app.metric[-1]
        return app, metric, Metric.MetricColor.Name(metric.proto.color)
    finally:
        os.environ.pop("MARGINPILOT_SNAPSHOT", None)


def test_a_missed_threshold_renders_red() -> None:
    """The defect: `delta_color="inverse"` painted a -41% shortfall GREEN, next
    to a KILL verdict. Colour and number said opposite things."""
    app, metric, colour = _decision_metric()
    assert metric.delta.startswith("-"), "the holdout's featured experiment misses the bar"
    assert colour == "RED", f"a shortfall rendered {colour}, not RED"
    assert len(app.error) == 1, "a missed threshold should carry the KILL verdict"


def test_a_cleared_threshold_renders_green(tmp_path: Path) -> None:
    """The other branch. The holdout's featured case is a KILL, so the SCALE
    path is only reachable by rendering a snapshot that contains one — which is
    why the snapshot path is overridable."""
    snapshot = json.loads(SNAPSHOT.read_text())
    snapshot["featured_experiment"] = {
        **snapshot["featured_experiment"],
        "scaled": True,
        "probability_net_positive": 0.94,
        "net_contribution_inr": 51_000.0,
        "ci_low_inr": 8_000.0,
        "ci_high_inr": 94_000.0,
        "projected_downside_inr": 12_000.0,
    }
    path = tmp_path / "scale_snapshot.json"
    path.write_text(json.dumps(snapshot))

    app, metric, colour = _decision_metric(path)
    assert metric.delta.startswith("+"), "this snapshot clears the bar"
    assert colour == "GREEN", f"a clearance rendered {colour}, not GREEN"
    assert len(app.success) == 1, "a cleared threshold should carry the SCALE verdict"


def test_the_delta_sign_and_the_verdict_never_disagree() -> None:
    """The invariant behind both tests above.

    A negative delta means the campaign failed the evidence bar, which is what a
    KILL is. If the sign and the verdict ever diverge, one of them is lying.
    """
    app, metric, colour = _decision_metric()
    killed = len(app.error) == 1
    missed = metric.delta.startswith("-")
    assert killed == missed, (
        f"verdict says {'KILL' if killed else 'SCALE'} but the delta is "
        f"{metric.delta!r} — the badge and the verdict disagree"
    )
    assert (colour == "RED") == missed, "colour must follow the sign"


def test_the_snapshot_cache_is_keyed_on_its_path() -> None:
    """A zero-argument cache keys on nothing and keeps serving the first file it
    read. That hid the SCALE branch entirely until it was found."""
    source = APP.read_text()
    assert "def load(path: str)" in source
    assert "load(str(SNAPSHOT))" in source
