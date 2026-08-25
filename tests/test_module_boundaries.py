"""Structural guard: policy/, experiment/ and economics/ must never import agent/.

CLAUDE.md: "If an ``import`` would make ``policy/``, ``experiment/`` or
``economics/`` depend on ``agent/``, the design is wrong. Those three must be
testable and runnable with no LLM present."

That rule is what makes the reasoning/authority split verifiable rather than
asserted, so it is enforced mechanically from Day 1 instead of by review. The
scan is AST-based rather than textual: it resolves relative imports against the
importing module's own package, so ``from ..agent import x`` inside
``src/policy/gates.py`` is caught exactly like ``import src.agent``.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

# The modules that must stay LLM-free, and what they may not reach.
DETERMINISTIC_MODULES = ("policy", "experiment", "economics")
FORBIDDEN_PACKAGE = "agent"

# Importing any of these directly would smuggle an LLM into a deterministic
# module without naming src.agent at all.
FORBIDDEN_LLM_CLIENTS = frozenset(
    {"anthropic", "openai", "cohere", "google.generativeai", "litellm", "langchain"}
)


def _imported_modules(source: str, module_path: Path) -> set[str]:
    """Return every module name imported by ``source``, dotted and absolute.

    Relative imports are resolved against the importing file's package so that
    ``from ..agent import tools`` is reported as ``src.agent.tools``.
    """
    package_parts = module_path.resolve().relative_to(SRC.parent).parent.parts
    imported: set[str] = set()

    for node in ast.walk(ast.parse(source, filename=str(module_path))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                # level 1 == current package, level 2 == parent, and so on.
                trimmed = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join([*trimmed, *([node.module] if node.module else [])])
            imported.add(base)
            imported.update(f"{base}.{alias.name}" for alias in node.names if base)

    return imported


def _python_files(module: str) -> list[Path]:
    return sorted((SRC / module).rglob("*.py"))


def _violates(imported: str, banned_roots: frozenset[str]) -> bool:
    """True if ``imported`` is one of ``banned_roots`` or lives beneath one."""
    return any(
        imported == root or imported.startswith(f"{root}.") for root in banned_roots
    )


def test_deterministic_modules_do_not_import_the_agent() -> None:
    banned = frozenset({f"src.{FORBIDDEN_PACKAGE}", FORBIDDEN_PACKAGE})
    violations: list[str] = []

    for module in DETERMINISTIC_MODULES:
        for path in _python_files(module):
            for imported in _imported_modules(path.read_text(), path):
                if _violates(imported, banned):
                    violations.append(f"{path.relative_to(SRC.parent)} imports {imported}")

    assert not violations, (
        "policy/, experiment/ and economics/ must never depend on agent/:\n  "
        + "\n  ".join(violations)
    )


def test_deterministic_modules_do_not_import_an_llm_client() -> None:
    violations: list[str] = []

    for module in DETERMINISTIC_MODULES:
        for path in _python_files(module):
            for imported in _imported_modules(path.read_text(), path):
                if _violates(imported, FORBIDDEN_LLM_CLIENTS):
                    violations.append(f"{path.relative_to(SRC.parent)} imports {imported}")

    assert not violations, (
        "policy/, experiment/ and economics/ must run with no LLM present:\n  "
        + "\n  ".join(violations)
    )


def test_world_does_not_import_the_agent() -> None:
    """CLAUDE.md marks src/world/ 'NO agent imports' — the simulator must not be
    reachable from, or reach into, the thing being evaluated."""
    banned = frozenset({f"src.{FORBIDDEN_PACKAGE}", FORBIDDEN_PACKAGE})
    violations = [
        f"{path.relative_to(SRC.parent)} imports {imported}"
        for path in _python_files("world")
        for imported in _imported_modules(path.read_text(), path)
        if _violates(imported, banned)
    ]
    assert not violations, "src/world/ must never import agent/:\n  " + "\n  ".join(violations)


def test_boundary_scanner_actually_detects_a_violation(tmp_path: Path) -> None:
    """The guard is only worth having if it fails when it should.

    Without this, an accidentally-broken scanner would pass silently forever and
    the boundary would be unguarded while looking guarded.
    """
    offender = SRC / "policy" / "_scanner_probe.py"
    banned = frozenset({f"src.{FORBIDDEN_PACKAGE}", FORBIDDEN_PACKAGE})

    absolute = _imported_modules("from src.agent import tools", offender)
    assert any(_violates(name, banned) for name in absolute)

    relative = _imported_modules("from ..agent import tools", offender)
    assert any(_violates(name, banned) for name in relative)

    llm = _imported_modules("import anthropic", offender)
    assert any(_violates(name, FORBIDDEN_LLM_CLIENTS) for name in llm)

    clean = _imported_modules("from ..economics import contribution\nimport numpy", offender)
    assert not any(_violates(name, banned | FORBIDDEN_LLM_CLIENTS) for name in clean)
