"""Atlas Post-Core F7 — Autonomous Operation Policy.

Deterministic, injectable policy governing one bounded operation invocation.

An ``OperationPolicy`` is pure configuration: it owns no controller logic, no
infrastructure, and no AI. It bounds how many adaptation cycles a single
explicit ``OperationController.run_operation()`` may run, how long the
controller must wait between cycles, and how many consecutive cycle failures
stop further work.

Pure config. No infra. No AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class OperationDecision(Enum):
    """Deterministic classification of an operation-outcome outcome.

    Deliberately separates "no signal" from "policy stopped us":
      * NO_WORK           - useful-work probe says no meaningful work exists.
      * RAN_LIMITED       - at least one adaptation cycle was invoked.
      * COOLDOWN_ACTIVE   - a previous cycle ran too recently.
      * BUDGET_EXHAUSTED  - the per-invocation cycle bound was reached.
      * FAILURE_LIMIT     - consecutive failures reached the configured cap.
      * STOPPED           - an explicit stop was requested.
    """

    NO_WORK = auto()
    RAN_LIMITED = auto()
    COOLDOWN_ACTIVE = auto()
    BUDGET_EXHAUSTED = auto()
    FAILURE_LIMIT = auto()
    STOPPED = auto()


@dataclass(frozen=True, slots=True)
class OperationPolicy:
    """Deterministic bounded-operation policy.

    Attributes:
        max_cycles_per_invocation: Maximum adaptation cycles a single explicit
            ``run_operation()`` call may run (default 5). Bounded and >=1.
        cooldown_seconds: Minimum wall-gap between cycles, in seconds
            (default 0). Deterministic and non-negative.
        max_consecutive_failures: Number of consecutive failed cycles after
            which the controller stops and returns FAILURE_LIMIT (default 3).
        max_work_probe: Upper bound on the number of work-probe signals the
            controller may inspect per invocation (default 100).
        max_budget_cycles: Hard absolute cap on cycles per invocation (>=1).
    """

    max_cycles_per_invocation: int = 5
    cooldown_seconds: float = 0.0
    max_consecutive_failures: int = 3
    max_work_probe: int = 100
    max_budget_cycles: int = 1000

    def __post_init__(self) -> None:
        if self.max_cycles_per_invocation < 1:
            raise ValueError("max_cycles_per_invocation must be >= 1")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be >= 1")
        if self.max_work_probe < 1:
            raise ValueError("max_work_probe must be >= 1")
        if self.max_budget_cycles < 1:
            raise ValueError("max_budget_cycles must be >= 1")
        if self.max_cycles_per_invocation > self.max_budget_cycles:
            raise ValueError(
                "max_cycles_per_invocation must not exceed max_budget_cycles"
            )