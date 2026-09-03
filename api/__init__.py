"""HTTP boundary between the MarginPilot engine and the web frontend.

A thin adapter and nothing more. Every number this package serves is produced by
code that already existed — ``demo.run_scenarios`` for decisions,
``demo.audit_demo`` for the hash chain, ``src.eval.adversarial`` for the
refusals, ``demo.evidence`` for the reproducibility pins. This package computes
no economics, applies no gate and decides nothing; it selects fields, names
them, and serialises them.

The rule that keeps the boundary honest: if a value is not already returned by
the engine, it does not appear in a response. A frontend that wants a quantity
the engine does not produce gets ``null`` and says so on screen.
"""
