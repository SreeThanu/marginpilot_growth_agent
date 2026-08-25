"""Arm assignment. The one place in the project that decides who gets treated.

CLAUDE.md invariant 1: the LLM never assigns customers to arms. Assignment is
``hash(customer_id + experiment_id) mod n_arms``, computed here, and no agent
tool may accept an arm assignment as an argument or move a customer between arms.

Two design choices carry that invariant:

* :func:`assign` takes exactly three arguments — customer, experiment, arm count.
  There is no seed parameter, no override, no salt, no "force" flag. A caller
  holding the full agent toolbox still has no way to express a preference about
  where a customer lands. ``tests/experiment/test_randomization.py`` asserts the
  signature, so adding such a parameter breaks the build rather than the science.
* The hash is ``blake2b``, not Python's ``hash()``. String hashing is salted per
  process, so ``hash()`` would silently reassign every customer on restart and
  make an experiment unreproducible — and unauditable, since the audit trail
  records the assignment rule rather than every individual assignment.

Assignment is a pure function of the pair. It needs no stored state, which is
what lets the audit log record *how* a customer was assigned rather than a list
of who was assigned where.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Mapping, Sequence

#: Separator between the two identifiers. A byte that cannot occur in an
#: identifier, so ``("ab", "c")`` and ``("a", "bc")`` cannot collide into the
#: same digest.
_SEPARATOR = b"\x1f"

#: 8 bytes = 64 bits. Modulo bias against any realistic arm count is on the
#: order of 2**-64 and is not worth the rejection-sampling loop.
_DIGEST_BYTES = 8

CONTROL_ARM = 0


def assign(customer_id: str, experiment_id: str, n_arms: int) -> int:
    """Return the arm index for this customer in this experiment.

    Deterministic, stateless, and stable across processes and machines. The same
    pair always yields the same arm; the same customer in a different experiment
    is assigned independently.

    Raises:
        ValueError: if ``n_arms`` is less than 2. A one-arm "experiment" has no
            control group and cannot measure an effect; refusing it here stops
            that mistake at the only place it could be made.
    """
    if n_arms < 2:
        raise ValueError(
            f"n_arms must be at least 2 (got {n_arms}): an experiment without a "
            "control arm cannot measure an incremental effect."
        )

    payload = customer_id.encode("utf-8") + _SEPARATOR + experiment_id.encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=_DIGEST_BYTES).digest()
    return int.from_bytes(digest, "big") % n_arms


def assign_many(
    customer_ids: Iterable[str], experiment_id: str, n_arms: int
) -> dict[str, int]:
    """Assign a population. Convenience only — identical to calling :func:`assign`."""
    return {cid: assign(cid, experiment_id, n_arms) for cid in customer_ids}


def arm_counts(
    customer_ids: Iterable[str], experiment_id: str, n_arms: int
) -> tuple[int, ...]:
    """Customers per arm, for power checks and for the audit record."""
    counts = [0] * n_arms
    for customer_id in customer_ids:
        counts[assign(customer_id, experiment_id, n_arms)] += 1
    return tuple(counts)


def customers_in_arm(
    customer_ids: Iterable[str], experiment_id: str, n_arms: int, arm: int
) -> tuple[str, ...]:
    """The customers assigned to one arm, in input order."""
    if not 0 <= arm < n_arms:
        raise ValueError(f"arm {arm} outside range 0..{n_arms - 1}")
    return tuple(c for c in customer_ids if assign(c, experiment_id, n_arms) == arm)


def assignment_rule(experiment_id: str, n_arms: int) -> Mapping[str, object]:
    """A description of the rule, for the audit trail.

    The log records the rule rather than a list of assignments: the rule is
    small, and anyone can replay it to verify any customer's arm. A stored list
    would be large, and would be a thing that could be edited after the fact.
    """
    return {
        "algorithm": "blake2b",
        "digest_bytes": _DIGEST_BYTES,
        "expression": "int(blake2b(customer_id + 0x1f + experiment_id)) % n_arms",
        "experiment_id": experiment_id,
        "n_arms": n_arms,
    }


def verify_assignment(customer_id: str, experiment_id: str, n_arms: int, arm: int) -> bool:
    """Re-derive an assignment and check it. For audit replay, not for control flow."""
    return assign(customer_id, experiment_id, n_arms) == arm


def balance_summary(counts: Sequence[int]) -> dict[str, float]:
    """Observed imbalance, as a fraction of the expected per-arm count.

    Reported rather than acted on. A hash-based assignment is balanced in
    expectation but not exactly, and "rebalancing" after the fact would be
    interference with randomization.
    """
    total = sum(counts)
    if total == 0 or not counts:
        return {"total": 0.0, "max_relative_deviation": 0.0}
    expected = total / len(counts)
    return {
        "total": float(total),
        "expected_per_arm": expected,
        "max_relative_deviation": max(abs(c - expected) for c in counts) / expected,
    }
