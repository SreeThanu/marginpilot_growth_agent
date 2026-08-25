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

Not implemented yet — Day 7.
"""
