"""World generation and simulation — the evaluation substrate.

Responsibility
--------------
Sample self-contained merchant worlds (baseline conversion, price elasticity,
customer mix, segment structure, seasonality, AOV distribution, contribution
margins, treatment effects and their heterogeneity, cannibalization, budget)
from documented parameter distributions, and simulate customer behaviour under
an intervention.

For every customer and every intervention type this module generates *both*
potential outcomes ``Y(0)`` and ``Y(1)``. The simulator knows both; an
experiment observes exactly one per customer, as in reality. Retaining both is
what lets ``src.eval`` report estimation error against the known individual
treatment effect ``tau_i = Y_i(1) - Y_i(0)``.

Boundary rules (CLAUDE.md)
--------------------------
* No agent imports. This module must never import ``src.agent``.
* Generation is seeded and reproducible: ``generate_world(seed)`` returns
  identical output on every run.
* Holdout worlds are sealed. Their structural parameters are never read,
  printed, tuned against or inspected during development. They are opened once,
  by ``make eval``. Debugging uses a freshly generated dev world instead.
* Parameter ranges are sourced from published retail price-elasticity
  literature and documented in ``docs/simulator.md`` before the code that uses
  them is written.

Not implemented yet — Day 2.
"""
