"""A money metric must never render a loss green.

This defect has now appeared twice, on two different metrics, both times from
``delta_color="inverse"`` on a value whose sign already carries the meaning. A
dashboard that paints a loss green beside a KILL verdict reads as either a bug
or a dishonest chart, and this project's entire claim is that it reports what it
measured.

Asserted on the *rendered* proto rather than on the source, because the argument
and the colour are two different things and only the second one is what a reader
sees.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from streamlit.proto.Metric_pb2 import Metric
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APP = str(ROOT / "src" / "ui" / "app.py")
SNAPSHOT = ROOT / "data" / "dashboard_snapshot.json"

RED = Metric.MetricColor.RED
GREEN = Metric.MetricColor.GREEN

#: Metrics whose value is money or a probability against a threshold: negative
#: means worse, and must render red.
SIGNED_MONEY_LABELS = ("Net incremental contribution",)


def _render(snapshot_path: Path):
    os.environ["MARGINPILOT_SNAPSHOT"] = str(snapshot_path)
    return AppTest.from_file(APP, default_timeout=120).run()


def _metric(app, label: str):
    for m in app.metric:
        if label in str(m.label):
            return m
    return None


@pytest.fixture(scope="module")
def snapshot() -> dict:
    if not SNAPSHOT.exists():
        pytest.skip("dashboard snapshot not built")
    return json.loads(SNAPSHOT.read_text())


@pytest.mark.parametrize("label", SIGNED_MONEY_LABELS)
def test_a_loss_renders_red(snapshot, tmp_path, label) -> None:
    payload = json.loads(json.dumps(snapshot))
    payload["featured_experiment"]["net_contribution_inr"] = -4_269.0
    path = tmp_path / "loss.json"
    path.write_text(json.dumps(payload))
    metric = _metric(_render(path), label)
    assert metric is not None, f"{label!r} did not render"
    assert metric.proto.color == RED, (
        f"{label!r} rendered a loss in colour {metric.proto.color} "
        f"(RED={RED}); a negative contribution must not read as good news"
    )


@pytest.mark.parametrize("label", SIGNED_MONEY_LABELS)
def test_a_gain_renders_green(snapshot, tmp_path, label) -> None:
    """The other direction, so the fix is a sign convention and not a constant."""
    payload = json.loads(json.dumps(snapshot))
    payload["featured_experiment"]["net_contribution_inr"] = 51_234.0
    path = tmp_path / "gain.json"
    path.write_text(json.dumps(payload))
    metric = _metric(_render(path), label)
    assert metric is not None
    assert metric.proto.color == GREEN
