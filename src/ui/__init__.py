"""Streamlit dashboard.

Responsibility
--------------
Display real state: budget remaining, live experiments, arm counts, the
contribution breakdown, the KILL/SCALE decision, and the audit-trail panel.

Boundary rules (CLAUDE.md)
--------------------------
* Read-only over the audit log and experiment registry. The UI decides nothing.
* Show real counts. No fake green dashboards, and no example numbers presented
  as measured.
* Deliberately built last (Day 10), and first on the fallback-cut list — if time
  runs short this degrades to console output plus a screen recording.

Built Day 10.

``snapshot.py`` runs the strategies against dev worlds and writes
``data/dashboard_snapshot.json``. ``app.py`` renders that file and nothing else
— it has no import path to the world generator, the harness or ground truth, so
it cannot reach ``worlds/holdout/`` even by mistake. ``tests/ui/`` enforces
that, along with the rule that nothing on the page may credit the policy gates
with catching the selection failure (docs/simulator.md 4g).
"""
