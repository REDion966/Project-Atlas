"""Atlas Post-Core F7 - Autonomous Operation.

A thin, bounded, manually-invoked operational controller around the existing
F1-F6 adaptation pipeline.

Provides:
  * ``OperationPolicy`` - deterministic cooldown / budget / failure policy.
  * ``OperationController`` - the bounded manual/external-driven loop.
  * ``OperationResult``  - bounded, deterministic run result.
  * ``OperationDecision`` - deterministic classification of an invocation.

Never a daemon; never approves; never executes; never calls an AI model;
never introduces a second EventBus / scheduler / memory / governance / registry.
"""

from atlas.evolution.operation.policy import (
    OperationDecision,
    OperationPolicy,
)
from atlas.evolution.operation.controller import (
    OperationController,
    OperationResult,
)

__all__ = [
    "OperationController",
    "OperationDecision",
    "OperationPolicy",
    "OperationResult",
]

__version__ = "1.0.0"