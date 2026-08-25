"""The LLM agent and its tool layer — the only module that may touch an LLM.

Responsibility
--------------
Observe merchant state, form growth hypotheses, propose experiment designs,
interpret results once the horizon is reached, and recommend SCALE / KILL /
MODIFY. Reasoning only.

Boundary rules (CLAUDE.md)
--------------------------
* This is the **only** module permitted to import an LLM client.
* The agent may never: assign customers to arms, set or exceed a budget, set a
  discount ceiling or margin floor, decide an experiment has run long enough,
  execute a payment, or modify an audit record.
* The tool list is closed. Exactly these ten, and no more without an explicit
  recorded reason — tool sprawl is how the reasoning/authority boundary erodes::

      get_merchant_metrics()
      get_customer_segments()
      get_product_context()
      propose_experiment()
      validate_experiment()      # returns policy verdict; does NOT execute
      launch_experiment()        # only executes an already-validated design
      get_experiment_results()   # refuses verdict-eligible data before horizon
      evaluate_experiment()
      scale_experiment()         # policy-gated
      stop_experiment()

* The agent must not be able to retry an experiment until it gets a favourable
  read.

Not implemented yet — Day 6 (stub agent Day 4).
"""
