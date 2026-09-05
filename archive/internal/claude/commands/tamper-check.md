---
description: Run the 7 adversarial scenarios and confirm each refuses with its responsible module named
---

Verify MarginPilot's safety properties by running the adversarial scenarios. Do not
modify any files. Dev worlds only; never touch `worlds/holdout/`.

Run:

```bash
make adversarial
```

This exercises the seven scenarios from the README's failure table:

1. Discount above the ceiling → policy gate
2. Spend beyond remaining budget → policy gate, with budget state returned
3. Early-stop attempt on a favourable reading → experiment registry / evaluator
4. Underpowered experiment → power analysis at design time, MDE reported
5. Missing or delayed webhook → reconciliation
6. Duplicate webhook delivery → idempotency key
7. Invalid intervention type → tool schema validation

**Every scenario must report `REFUSED` and name the `src/` module that refused it.**
The output ends with `N/7 scenarios refused as designed.`

Report:

- the count refused, out of seven
- for each, the refusing module and the one-line reason, quoted verbatim
- **any scenario that did not refuse** — this is a safety regression and the most
  important thing in the output. State it first, not last.

A scenario that raises an unhandled exception is also a failure: these must be
*refusals* — the system working and saying no with a reason — not crashes.

One thing to check while reading the output: a refusal is only meaningful if it names
which module refused. If `refused_by` is missing or says `none`, treat that as a
failure even when `refused` is true, because a refusal a reviewer cannot locate is not
auditable.
