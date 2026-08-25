"""MarginPilot — an autonomous merchant growth agent that allocates a bounded
promotion budget on incremental contribution rather than conversion lift.

Package layout and the boundaries between modules are specified in CLAUDE.md.
The two boundaries that carry the project's central claim:

* The LLM lives only in ``src.agent``. It reasons; it never decides anything
  involving money, randomization, or stopping.
* ``src.policy``, ``src.experiment`` and ``src.economics`` must be importable
  and runnable with no LLM client present, and must never import ``src.agent``.
  ``tests/test_module_boundaries.py`` enforces this by scanning imports.
"""
