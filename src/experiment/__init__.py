"""Experiment engine — registry, randomization, power/horizon, evaluator.

Responsibility
--------------
Own everything about how an experiment is assigned, how long it runs, and when
a verdict may be read. This module is deterministic and is the sole authority on
arm assignment and stopping.

Boundary rules (CLAUDE.md)
--------------------------
* **Randomization is not delegable.** Assignment is
  ``hash(customer_id + experiment_id) mod n_arms``, computed here. No agent tool
  may accept an arm assignment as an argument or move a customer between arms.
* **No peeking.** The horizon is computed at design time from a minimum
  detectable effect and written immutably into the registry at launch.
  ``get_experiment_results()`` must refuse to return a KEEP/KILL-eligible
  verdict before the horizon is reached. There is no "early stop if
  significant" path. If sequential testing is added later it uses a
  pre-specified alpha-spending or Bayesian rule fixed before data is seen.
* A registry record is immutable after launch.
* Must never import ``src.agent``; must be testable with no LLM present.

Built Day 3:

* ``registry`` — designs, launched records, append-only status events.
* ``randomize`` — stable-hash arm assignment.
* ``power`` — sample size, and the inverse for refusing underpowered designs.
* ``evaluator`` — interim counts before the horizon, verdict only at it.

Contribution arithmetic is Day 4; the evaluator takes per-order figures as
arguments and does not know what a margin is.
"""
