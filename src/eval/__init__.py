"""Evaluation harness — holdout protocol, metrics, failure taxonomy.

Responsibility
--------------
Run a strategy across a set of worlds and collect the five primary metrics
(incremental conversion, incremental revenue, incremental contribution,
promotion spend, ROMI) plus the secondaries (policy violations, budget
overruns, false-positive campaigns scaled, true-positive campaigns killed in
error, experiments killed/scaled, estimation error against the simulator's known
``tau``).

Boundary rules (CLAUDE.md)
--------------------------
* **The holdout is sealed.** ``worlds/holdout/`` sits behind a path guard here
  that raises unless an explicit ``--final-eval`` flag is set. Peeking must be
  mechanically annoying, not merely discouraged.
* Headline results are reported on the holdout worlds only.
* **Never fabricate a result.** Placeholders stay ``TBD`` until this harness
  produces real values. A missed target is reported as missed.
* Tuning against holdout results to reverse an unfavourable finding is the one
  unrecoverable mistake in this project.

Not implemented yet — Day 4 (harness), Day 9 (holdout run).
"""
