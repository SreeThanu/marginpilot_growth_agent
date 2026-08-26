"""Policy gate — the deterministic authority over every money-adjacent action.

Responsibility
--------------
Evaluate a proposed experiment or scale action against the hard constraints:
budget remaining, maximum discount percentage, minimum contribution margin,
maximum customer exposure, and minimum experiment power. Each rule returns a
structured verdict naming the rule that fired and the value that violated it —
never a bare boolean — so the rejection can be logged and returned to the agent.

Boundary rules (CLAUDE.md)
--------------------------
* **The agent proposes; this module disposes.** Every money-adjacent action
  passes through here. ``validate_experiment()`` returns a verdict and does not
  execute; ``launch_experiment()`` may only execute an already-validated design.
* **No LLM calls in this module, ever.** It must never import ``src.agent``.
* Deterministic and fully testable offline. Every rule needs a test proving it
  rejects a violating proposal.

Built Day 7. ``gates.py`` holds the five rules; every verdict names the rule
that fired, the value that violated it and the limit it violated.

Two gates, not one. Day 5 measured four to seven budget overruns per run
because only the pilot was checked and the rollout — the larger of the two
spends — was not. ``gate_rollout`` closes that, and
``affordable_rollout_customers`` makes the refusal constructive by saying how
much of a campaign is fundable rather than rejecting it outright.
"""
