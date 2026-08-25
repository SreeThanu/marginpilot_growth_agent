"""Placeholder for tests/agent. Replaced by real tests when src/agent is built.

Until then it asserts the one thing that is already true: the package imports
with no LLM client, no network and no credentials present, and carries the
docstring that records its boundary rules.
"""

import importlib


def test_agent_package_imports_and_declares_its_boundary() -> None:
    module = importlib.import_module("src.agent")
    assert module.__doc__, "src/agent must document its responsibility and boundary rules"
