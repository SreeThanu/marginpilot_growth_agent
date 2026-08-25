"""The experiment record: what was decided, before any data existed.

Two CLAUDE.md invariants live in this file.

**Invariant 3 (no peeking).** The horizon is computed at design time from a
minimum detectable effect and written here at launch. Nothing in this module can
change it afterwards — there is no setter, no ``update``, and the record is a
frozen dataclass, so an attempt to move the finish line raises
``FrozenInstanceError`` rather than quietly succeeding.

**Invariant 7 (pre-committed hypotheses).** A :class:`Hypothesis` states its
prediction, reasoning, expected effect size, required sample and explicit
success/failure conditions, and all of them are required at construction — an
incomplete hypothesis cannot be built, so it cannot be launched. Once attached
to a launched experiment it cannot be edited: the agent may diagnose a failure
and propose a *new* hypothesis, but retroactively editing a prediction to match
an outcome would invalidate the calibration analysis that makes Day 9 worth
reading.

Immutability is enforced three ways, because one is not enough:

1. ``Hypothesis`` and ``LaunchedExperiment`` are ``frozen=True`` dataclasses.
2. The registry stores each launched record exactly once. There is no code path
   that replaces one — ``launch`` on an already-launched experiment raises.
3. Status is derived from an append-only event log rather than mutated on the
   record, so the record itself never needs to change after it is written.

Someone can still build an edited copy with ``dataclasses.replace``. What they
cannot do is get the registry to accept it in place of the original, and
:meth:`ExperimentRegistry.verify_hypothesis` will show the fingerprint no longer
matches the one recorded at launch.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterator, Mapping

from src.experiment.power import ContributionPowerAnalysis, PowerAnalysis
from src.experiment.randomize import assignment_rule


class ExperimentStatus(str, Enum):
    """Derived from the event log, never stored on the record."""

    DESIGNED = "designed"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A falsifiable prediction, fixed before launch.

    Every field is mandatory. A "hypothesis" without a success condition is a
    hope, and one without a failure condition cannot be wrong — neither can be
    scored honestly on Day 9, so neither is accepted here.
    """

    hypothesis_id: str
    #: What is predicted to happen, in one sentence.
    prediction: str
    #: Why the agent believes it — the reasoning that will be graded later.
    reasoning: str
    #: Predicted absolute lift in conversion, e.g. 0.06 for 12% -> 18%.
    expected_effect_absolute: float
    #: Sample the design requires per arm, from src.experiment.power.
    required_sample_per_arm: int
    #: The observation that would confirm the prediction.
    success_condition: str
    #: The observation that would refute it. Stated in advance, deliberately.
    failure_condition: str
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        for name in ("hypothesis_id", "prediction", "reasoning", "success_condition", "failure_condition"):
            if not str(getattr(self, name)).strip():
                raise ValueError(
                    f"Hypothesis.{name} must be non-empty: a hypothesis missing its "
                    f"{name} cannot be scored after the fact (CLAUDE.md invariant 7)."
                )
        if self.expected_effect_absolute == 0.0:
            raise ValueError("expected_effect_absolute of 0 predicts nothing")
        if self.required_sample_per_arm < 1:
            raise ValueError(
                f"required_sample_per_arm must be positive, got {self.required_sample_per_arm}"
            )

    def fingerprint(self) -> str:
        """Content hash. Recorded at launch so later edits are detectable."""
        payload = json.dumps(
            {
                "hypothesis_id": self.hypothesis_id,
                "prediction": self.prediction,
                "reasoning": self.reasoning,
                "expected_effect_absolute": self.expected_effect_absolute,
                "required_sample_per_arm": self.required_sample_per_arm,
                "success_condition": self.success_condition,
                "failure_condition": self.failure_condition,
                "created_at": self.created_at,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperimentDesign:
    """A proposal. Not yet authoritative, and not yet running."""

    experiment_id: str
    world_id: str
    #: Arm names, index 0 being control. Order is the arm index.
    arms: tuple[str, ...]
    hypothesis: Hypothesis
    #: Conversion-based power. Kept for reporting: it is the number a merchant
    #: recognises, and it is not what the horizon is derived from.
    power: PowerAnalysis
    #: Contribution-based power. When present this sets the horizon, because the
    #: decision rule is a confidence interval over rupees, not over conversion.
    #: Sizing for a conversion MDE and then deciding on contribution is a
    #: category error — the rupee quantity carries the incentive cost as a second
    #: variance source that the conversion calculation cannot see.
    contribution_power: ContributionPowerAnalysis | None
    intervention_id: str
    budget_inr: float
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if len(self.arms) < 2:
            raise ValueError(
                f"an experiment needs at least a control and one treatment arm, got {self.arms}"
            )
        if len(set(self.arms)) != len(self.arms):
            raise ValueError(f"arm names must be unique, got {self.arms}")
        if self.budget_inr < 0:
            raise ValueError(f"budget_inr cannot be negative, got {self.budget_inr}")
        if self.horizon_per_arm != self.hypothesis.required_sample_per_arm:
            raise ValueError(
                "the hypothesis claims a required sample of "
                f"{self.hypothesis.required_sample_per_arm} per arm but the power "
                f"analysis computes {self.horizon_per_arm}. The horizon must follow "
                "from the power calculation, not from the proposal."
            )

    @property
    def n_arms(self) -> int:
        return len(self.arms)

    @property
    def horizon_per_arm(self) -> int:
        """The finish line, fixed at design time.

        Taken from the contribution power calculation when there is one: the
        experiment is read on a confidence interval over rupees, so that is the
        quantity it must be powered for.
        """
        if self.contribution_power is not None:
            return self.contribution_power.n_per_arm
        return self.power.n_per_arm


@dataclass(frozen=True, slots=True)
class LaunchedExperiment:
    """A running experiment. Immutable for its whole life.

    Carries its own copy of the horizon and the hypothesis fingerprint rather
    than reaching through to the design for them, so that the launched record is
    self-contained evidence of what was committed to at launch time.
    """

    design: ExperimentDesign
    launched_at: str
    horizon_per_arm: int
    hypothesis_fingerprint: str
    assignment_rule: str

    @property
    def experiment_id(self) -> str:
        return self.design.experiment_id

    @property
    def hypothesis(self) -> Hypothesis:
        return self.design.hypothesis

    @property
    def n_arms(self) -> int:
        return self.design.n_arms

    def horizon_reached(self, observed_per_arm: Mapping[int, int] | tuple[int, ...]) -> bool:
        """True only when *every* arm has reached the horizon.

        Every arm, not the total and not the smallest treatment arm: a
        comparison is only as powered as its thinner side.
        """
        counts = (
            observed_per_arm.values()
            if isinstance(observed_per_arm, Mapping)
            else observed_per_arm
        )
        counts = list(counts)
        if len(counts) != self.n_arms:
            raise ValueError(
                f"expected counts for {self.n_arms} arms, got {len(counts)}"
            )
        return all(c >= self.horizon_per_arm for c in counts)


@dataclass(frozen=True, slots=True)
class ExperimentEvent:
    """One entry in the append-only log."""

    experiment_id: str
    kind: str
    at: str
    detail: str = ""


class ExperimentAlreadyLaunchedError(RuntimeError):
    """Raised on any attempt to launch, or relaunch, an experiment twice."""


class ExperimentNotFoundError(KeyError):
    pass


class ExperimentRegistry:
    """Holds designs and launched experiments. Append-only by construction.

    Note what is *absent*: no ``update``, no ``set_horizon``, no
    ``replace_hypothesis``, no ``delete``. That absence is the enforcement
    mechanism, and ``tests/experiment/test_registry_immutability.py`` asserts it
    by scanning the public API so that adding one is a test failure.
    """

    def __init__(self) -> None:
        self._designs: dict[str, ExperimentDesign] = {}
        self._launched: dict[str, LaunchedExperiment] = {}
        self._events: list[ExperimentEvent] = []

    # -- registration -------------------------------------------------------

    def register(self, design: ExperimentDesign) -> ExperimentDesign:
        """Record a design. Still editable in the sense that it can be discarded
        and replaced *before* launch — after launch, nothing can."""
        if design.experiment_id in self._designs:
            raise ExperimentAlreadyLaunchedError(
                f"{design.experiment_id} is already registered"
            )
        self._designs[design.experiment_id] = design
        self._append(design.experiment_id, "registered", f"hypothesis={design.hypothesis.hypothesis_id}")
        return design

    def launch(self, experiment_id: str, *, launched_at: str | None = None) -> LaunchedExperiment:
        """Freeze a design into a running experiment.

        After this returns, the horizon and the hypothesis are settled. Calling
        it twice raises rather than re-freezing with a new hypothesis — which is
        the shape a "let me just revise the prediction" bug would take.
        """
        design = self._designs.get(experiment_id)
        if design is None:
            raise ExperimentNotFoundError(f"no registered design for {experiment_id!r}")
        if experiment_id in self._launched:
            raise ExperimentAlreadyLaunchedError(
                f"{experiment_id} was already launched at "
                f"{self._launched[experiment_id].launched_at}. A launched experiment's "
                "horizon and hypothesis are immutable (CLAUDE.md invariants 3 and 7); "
                "propose a new experiment instead."
            )

        launched = LaunchedExperiment(
            design=design,
            launched_at=launched_at or _utc_now(),
            horizon_per_arm=design.horizon_per_arm,
            hypothesis_fingerprint=design.hypothesis.fingerprint(),
            assignment_rule=json.dumps(
                assignment_rule(experiment_id, design.n_arms), sort_keys=True
            ),
        )
        self._launched[experiment_id] = launched
        self._append(experiment_id, "launched", f"horizon_per_arm={launched.horizon_per_arm}")
        return launched

    # -- reads --------------------------------------------------------------

    def get(self, experiment_id: str) -> LaunchedExperiment:
        try:
            return self._launched[experiment_id]
        except KeyError as exc:
            raise ExperimentNotFoundError(
                f"{experiment_id!r} is not launched"
            ) from exc

    def get_design(self, experiment_id: str) -> ExperimentDesign:
        try:
            return self._designs[experiment_id]
        except KeyError as exc:
            raise ExperimentNotFoundError(f"{experiment_id!r} is not registered") from exc

    def horizon(self, experiment_id: str) -> int:
        return self.get(experiment_id).horizon_per_arm

    def status(self, experiment_id: str) -> ExperimentStatus:
        """Derived from events, so the record never has to be rewritten."""
        kinds = {e.kind for e in self._events if e.experiment_id == experiment_id}
        if not kinds:
            raise ExperimentNotFoundError(experiment_id)
        if "stopped" in kinds:
            return ExperimentStatus.STOPPED
        if "completed" in kinds:
            return ExperimentStatus.COMPLETED
        if "launched" in kinds:
            return ExperimentStatus.RUNNING
        return ExperimentStatus.DESIGNED

    def verify_hypothesis(self, experiment_id: str, hypothesis: Hypothesis) -> bool:
        """Does this hypothesis match the one committed at launch?

        Exists so a later edit is *detectable*, not merely disallowed. An agent
        that revises a prediction and presents it as the original fails here.
        """
        return self.get(experiment_id).hypothesis_fingerprint == hypothesis.fingerprint()

    @property
    def events(self) -> tuple[ExperimentEvent, ...]:
        return tuple(self._events)

    def __iter__(self) -> Iterator[LaunchedExperiment]:
        return iter(self._launched.values())

    def __len__(self) -> int:
        return len(self._launched)

    # -- lifecycle events ---------------------------------------------------

    def complete(self, experiment_id: str, *, detail: str = "") -> None:
        """Mark an experiment finished. Records an event; changes no record."""
        self.get(experiment_id)
        self._append(experiment_id, "completed", detail)

    def stop(self, experiment_id: str, *, reason: str) -> None:
        """Stop an experiment. The reason is mandatory and is logged.

        Stopping does not produce a verdict. An experiment stopped before its
        horizon yields no KEEP/KILL decision — that is the whole point of the
        horizon, and the evaluator enforces it independently of this call.
        """
        if not reason.strip():
            raise ValueError("stopping an experiment requires a recorded reason")
        self.get(experiment_id)
        self._append(experiment_id, "stopped", reason)

    def _append(self, experiment_id: str, kind: str, detail: str = "") -> None:
        self._events.append(
            ExperimentEvent(
                experiment_id=experiment_id, kind=kind, at=_utc_now(), detail=detail
            )
        )


def design_experiment(
    *,
    experiment_id: str,
    world_id: str,
    intervention_id: str,
    hypothesis_id: str,
    prediction: str,
    reasoning: str,
    baseline_conversion: float,
    expected_effect_absolute: float,
    success_condition: str,
    failure_condition: str,
    budget_inr: float,
    arms: tuple[str, ...] = ("control", "treatment"),
    alpha: float = 0.05,
    power_level: float = 0.80,
) -> ExperimentDesign:
    """Build a design with its horizon derived from the power calculation.

    A convenience so the horizon cannot be passed in by hand — it is computed
    from the stated effect, which is what makes it a commitment rather than a
    preference.
    """
    from src.experiment import power as power_module

    analysis = power_module.analyse(
        baseline_conversion,
        abs(expected_effect_absolute),
        alpha=alpha,
        power=power_level,
        comparisons=max(len(arms) - 1, 1),
    )
    hypothesis = Hypothesis(
        hypothesis_id=hypothesis_id,
        prediction=prediction,
        reasoning=reasoning,
        expected_effect_absolute=expected_effect_absolute,
        required_sample_per_arm=analysis.n_per_arm,
        success_condition=success_condition,
        failure_condition=failure_condition,
    )
    return ExperimentDesign(
        experiment_id=experiment_id,
        world_id=world_id,
        arms=arms,
        hypothesis=hypothesis,
        power=analysis,
        contribution_power=None,
        intervention_id=intervention_id,
        budget_inr=budget_inr,
    )


def design_experiment_on_contribution(
    *,
    experiment_id: str,
    world_id: str,
    intervention_id: str,
    hypothesis_id: str,
    prediction: str,
    reasoning: str,
    baseline_conversion: float,
    expected_effect_absolute: float,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float,
    mde_contribution_per_customer_inr: float,
    success_condition: str,
    failure_condition: str,
    budget_inr: float,
    arms: tuple[str, ...] = ("control", "treatment"),
    alpha: float = 0.05,
    power_level: float = 0.80,
) -> ExperimentDesign:
    """Design an experiment whose horizon is powered on **contribution**.

    This is the path that should normally be used. The conversion power analysis
    is computed too and carried alongside, because it is the number a merchant
    recognises and the gap between the two is worth showing — but the horizon
    comes from the rupee calculation, since that is the quantity the SCALE/KILL
    decision is read from.
    """
    from src.experiment import power as power_module

    comparisons = max(len(arms) - 1, 1)
    contribution_analysis = power_module.analyse_contribution(
        baseline_conversion,
        expected_effect_absolute,
        contribution_per_incremental_order_inr=contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr=incentive_cost_per_treated_order_inr,
        mde_contribution_per_customer_inr=mde_contribution_per_customer_inr,
        alpha=alpha,
        power=power_level,
        comparisons=comparisons,
    )
    conversion_analysis = power_module.analyse(
        baseline_conversion,
        abs(expected_effect_absolute),
        alpha=alpha,
        power=power_level,
        comparisons=comparisons,
    )
    hypothesis = Hypothesis(
        hypothesis_id=hypothesis_id,
        prediction=prediction,
        reasoning=reasoning,
        expected_effect_absolute=expected_effect_absolute,
        required_sample_per_arm=contribution_analysis.n_per_arm,
        success_condition=success_condition,
        failure_condition=failure_condition,
    )
    return ExperimentDesign(
        experiment_id=experiment_id,
        world_id=world_id,
        arms=arms,
        hypothesis=hypothesis,
        power=conversion_analysis,
        contribution_power=contribution_analysis,
        intervention_id=intervention_id,
        budget_inr=budget_inr,
    )
