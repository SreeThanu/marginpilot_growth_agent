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

Not implemented yet — Day 10.
"""
