"""Contribution economics — the business metric the whole project optimizes.

Responsibility
--------------
Pure functions over experiment counts: incremental orders, incremental revenue,
incremental contribution, discount cost across *all* treatment buyers (not only
the incremental ones — that asymmetry is the point of the project), and ROMI.

The worked example these functions must reproduce exactly (README, 1,000 per
arm): 120 control orders vs. 180 treatment orders at 12% -> 18% conversion
gives 60 incremental orders; 60 x Rs.800 AOV x 30% margin = Rs.14,400
contribution; 180 x Rs.100 discount = Rs.18,000 cost; net **-Rs.3,600**, and
-Rs.36,000 projected at full scale.

Boundary rules (CLAUDE.md)
--------------------------
* Small pure functions only. No I/O, no state, no LLM.
* Unit-tested against hand-computed expected values — these tests carry the
  project's credibility.
* Must never import ``src.agent``; must be runnable with no LLM present.

Not implemented yet — Day 4.
"""
