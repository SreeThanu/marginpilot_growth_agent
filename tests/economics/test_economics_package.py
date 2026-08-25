"""Placeholder for tests/economics. Replaced by real tests when src/economics is built.

Until then it asserts the one thing that is already true: the package imports
with no LLM client, no network and no credentials present, and carries the
docstring that records its boundary rules.
"""

import importlib


def test_economics_package_imports_and_declares_its_boundary() -> None:
    module = importlib.import_module("src.economics")
    assert module.__doc__, "src/economics must document its responsibility and boundary rules"
