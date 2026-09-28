"""Atlas Orchestration — Result Reporting (P2/B2.3).

Converts a deterministic :class:`OrchestrationResult` (B2.2) into a
conversational :class:`Message` that truthfully reflects what actually ran.
Reporting never invents work and never fabricates authority.

Reporting is SEPARATE from execution: the executor's decision payload is
the ground truth; the conversational envelope carries it best-effort. A
best-effort failure never transforms the decision itself.

Step 11 — the *presentation* of that ground truth is delegated to the shared
deterministic response-realization layer
(:func:`atlas.conversation.response_layer.render_outcome`), so every surface
that reports an orchestration outcome speaks in one truthful, natural shape
(what each step was and what it produced) instead of exposing internal step ids
and echoing the request. The deterministic decision carried in ``metadata`` is
unchanged.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation.message import Message
from atlas.conversation.response_layer import render_outcome
from atlas.orchestration.execution_models import OrchestrationResult


def orchestration_result_to_message(
    result: OrchestrationResult,
    intent: str = "",
) -> Message:
    """Convert an :class:`OrchestrationResult` into a conversational reply.

    The message content reflects the actual execution status honestly:

    * ``COMPLETED`` — reports ``Steps completed: N/M.`` and each step with what
      it was and what it produced.
    * ``PARTIAL`` — reports ``Completed with issues`` (and, for a
      dimension-partial research result, the supported/unsupported dimensions).
    * ``FAILED`` / ``REJECTED`` / ``EMPTY`` — describe the failure/rejection
      without ever claiming ``Done`` or a completed count.
    * ``SKIPPED`` / ``BLOCKED`` steps are differentiated from failures.

    The deterministic decision is carried in the message ``metadata``
    best-effort under the ``orchestration`` key so that later capture systems
    (B2.4/experience) and diagnostics can consume it. Attachments never
    transform the decision.

    Args:
        result: The bounded, deterministic execution result from the executor.
        intent: Optional bounded intent text (presentation does not echo it).

    Returns:
        A :class:`Message` whose ``content`` is a bounded conversational report
        and whose ``metadata`` carries the deterministic payload.

    Never raises; malformed result payloads are handled at the boundary.
    """
    if not isinstance(result, OrchestrationResult):
        # Defense in depth: the caller must never fabricate work, so an
        # unexpected invocation produces an explicit, bounded reply.
        return Message(
            role="assistant",
            content="I could not prepare the execution report.",
        )

    try:
        content = render_outcome(result)
    except Exception:  # best-effort envelope; the decision itself is untouched
        content = "Execution finished."

    return Message(
        role="assistant",
        content=content,
        metadata={"orchestration": result.to_dict()},
    )
