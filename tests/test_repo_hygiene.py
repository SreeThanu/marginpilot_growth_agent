"""The repo must stay clean, and the test suite must not dirty it.

A judge cloning this next week should get the same versions that produced the
recorded results, and `git status` should be clean after running everything.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_generated_artifacts_default_to_the_data_directory() -> None:
    """Databases belong under data/, which is gitignored — not in the repo root
    where a careless `git add -A` could commit a decision log."""
    from src.audit.log import DEFAULT_DB_PATH as AUDIT_DB
    from src.payments.webhooks import DEFAULT_DB_PATH as PAYMENTS_DB

    for path in (AUDIT_DB, PAYMENTS_DB):
        assert path.parts[0] == "data", f"{path} should live under data/"


def test_gitignore_covers_every_generated_path() -> None:
    required = ["__pycache__/", "*.py[cod]", ".pytest_cache/", "data/", "worlds/",
                "results/", ".env", "*.db"]
    text = (ROOT / ".gitignore").read_text()
    for pattern in required:
        assert pattern in text, f".gitignore is missing {pattern!r}"
    # .env.example must stay tracked, or nobody knows which keys to set.
    assert "!.env.example" in text


#: The one deliberate exception to "nothing generated is tracked".
#:
#: The recorded holdout run is evidence, not an intermediate: it cost real API
#: calls, an LLM cannot reproduce it deterministically, and the README's
#: headline rests on it. Without it the dashboard cannot be built from a clean
#: clone. Listed here by name so that tracking anything *else* under data/ still
#: fails — the exception is one file, not a relaxed rule.
TRACKED_EVIDENCE = {"data/holdout_results.json"}


def test_nothing_generated_is_tracked_by_git() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = [
        f for f in tracked
        if re.search(r"\.db$|\.sqlite\d?$|__pycache__|\.pyc$|^data/|^worlds/|^results/", f)
        and f not in TRACKED_EVIDENCE
    ]
    assert not offenders, f"generated files are tracked: {offenders}"

    # And the exception must actually be present — if it disappears, the
    # dashboard silently stops building from a clean clone.
    for evidence in TRACKED_EVIDENCE:
        assert evidence in tracked, f"{evidence} should be tracked but is not"
    assert ".env" not in tracked, "the real .env must never be committed"
    assert ".env.example" in tracked


def test_the_lock_file_pins_every_direct_dependency() -> None:
    """A clone must resolve to the tree that produced the results."""
    direct = {
        line.split("==")[0].lower()
        for line in (ROOT / "requirements.txt").read_text().splitlines()
        if "==" in line and not line.strip().startswith("#")
    }
    locked = {
        line.split("==")[0].lower()
        for line in (ROOT / "requirements.lock.txt").read_text().splitlines()
        if "==" in line and not line.strip().startswith("#")
    }
    missing = direct - locked
    assert not missing, f"direct dependencies absent from the lock file: {missing}"
    assert len(locked) > len(direct), "the lock file should also pin transitive deps"


def test_every_pin_is_exact() -> None:
    for name in ("requirements.txt", "requirements.lock.txt"):
        for line in (ROOT / name).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            assert "==" in line, f"{name} has an unpinned requirement: {line!r}"
            assert not any(op in line for op in (">=", "<=", "~=", ">", "<")), (
                f"{name} has a range rather than an exact pin: {line!r}"
            )
