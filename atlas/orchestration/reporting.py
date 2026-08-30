"""Atlas Orchestration — Result Reporting (P2/B2.3).

Converts a deterministic :class:`OrchestrationResult` (B2.2) into a
conversational :class:`Message` that truthfully reflects what actually ran.
Reporting never invents work and never fabricates authority.

Reporting is SEPARATE from execution: the executor's decision payload is
the ground truth; the conversational envelope carries it best-effort. A
best-effort failure never transforms the decision itself.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation.message import Message
from atlas.orchestration.execution_models import OrchestrationResult

_MAX_STEPS_IN_REPORT: int = 8
_MAX_ERROR_CHARS: int = 400


def orchestration_result_to_message(
    result: OrchestrationResult,
    intent: str = "",
) -> Message:
    """Convert an :class:`OrchestrationResult` into a conversational reply.

    The message content reflects the actual execution status honestly:

    * ``COMPLETED`` — report the goal and count; include output when
      bounded evidence exists.
    * ``PARTIAL`` — name which steps completed and which did not.
    * ``FAILED`` / ``REJECTED`` / ``EMPTY`` — describe the failure/rejection.
    * ``SKIPPED`` / ``BLOCKED`` steps are differentiated from failures.

    The deterministic decision is also carried in the message ``metadata``
    best-effort under the ``orchestration`` key so that later capture
    systems (B2.4/experience) and diagnostics can consume it. Attachments
    never transform the decision.

    Args:
        result: The bounded, deterministic execution result from the executor.
        intent: Optional bounded intent text for context.

    Returns:
        A :class:`Message` whose ``content`` is a bounded conversational
        report and whose ``metadata`` carries the deterministic payload.

    Never raises; malformed result payloads are handled at the boundary.
    """
    if not isinstance(result, OrchestrationResult):
        # Defense in depth: the caller must never fabricate work, so an
        # unexpected invocation produces an explicit, bounded reply.
        return Message(
            role="assistant",
            content="I could not prepare the execution report.",
        )

    lines: list[str] = []
    intent_line = intent.strip()[:200] if isinstance(intent, str) and intent.strip() else ""

    status = result.status.value

    if status == "completed":
        if intent_line:
            lines.append(f"Done: {intent_line}")
        else:
            lines.append("Done.")
        lines.append(f"Steps completed: {result.completed_count}/{len(result.steps)}.")
        # Bounded per-step evidence (only bounded text; no secret propagation).
        for step in tuple(result.steps)[:_MAX_STEPS_IN_REPORT]:
            summary = _step_summary(step)
            if summary:
                lines.append(summary)
        # Session attribution is reflected (non-secret, non-secret-bound).
        if result.principal_id:
            lines.append(f"Executed as: {result.principal_id} ({result.authority or ''}).".strip())
        content = "\n".join(lines)
        return Message(
            role="assistant",
            content=content,
            metadata={"orchestration": result.to_dict()},
        )

    if status == "rejected":
        target_types = {
            f.name: f.type.value if getattr(f.type, "value", None) else str(f.type)
            for f in getattr(result, "steps", ()) or ()
        }
        if intent_line:
            lines.append(f"Could not execute: {intent_line}")
        else:
            lines.append("Could not execute the request.")
        # Report the deterministic reason; never fabricate authority from text.
        reason = (getattr(result, "error", "") or "").strip()[:_MAX_ERROR_CHARS]
        if reason:
            lines.append(f"Reason: {reason}")
        # Surface per-step failure kinds only as bounded, derived evidence.
        denials = [
            f"{s.target} ({s.failure_kind.value if hasattr(s.failure_kind, 'value') else s.failure_kind})"
            for s in tuple(result.steps)[:_MAX_STEPS_IN_REPORT]
            if getattr(s, "failure_kind", None) is not None
        ]
        if denials:
            lines.append("Details: " + "; ".join(denials))
        content = "\n".join(lines)
        return Message(
            role="assistant",
            content=content,
            metadata={"orchestration": result.to_dict()},
        )

    if status in ("failed", "partial", "empty"):
        if intent_line:
            prefix = "Completed with issues:" if status == "partial" else "Could not complete:"
            lines.append(f"{prefix} {intent_line}")
        else:
            lines.append(
                "Completed with issues." if status == "partial" else "Could not complete the request."
            )
        lines.append(
            f"Steps: {result.completed_count} completed, {result.failed_count} failed, {result.blocked_count} blocked, {result.skipped_count} skipped."
        )
        fail_kinds = tuple(result.failure_kinds) if hasattr(result, "failure_kinds") else ()
        if fail_kinds:
            lines.append(f"Failure kinds: {', '.join(fail_kinds)}.")
        # Bounded per-step evidence; truncated deterministically.
        for step in tuple(result.steps)[:_MAX_STEPS_IN_REPORT]:
            summary = _step_summary(step)
            if summary:
                lines.append(summary)
        if result.error:
            lines.append(result.error.strip()[:_MAX_ERROR_CHARS])
        content = "\n".join(lines[: 64])
        return Message(
            role="assistant",
            content=content,
            metadata={"orchestration": result.to_dict()},
        )

    # Unknown/edge status — still truthful; do not fabricate a success.
    return Message(
        role="assistant",
        content=(f"Execution {status}." if status else "Execution finished."),
        metadata={"orchestration": result.to_dict()},
    )


def _step_summary(result: Any) -> str:
    """Build a bounded, truthful per-step evidence line."""
    if result is None or not hasattr(result, "step_id"):
        return ""
    state = getattr(result, "state", None)
    failure_kind = getattr(result, "failure_kind", None)
    target = getattr(result, "target", "")
    step_id = getattr(result, "step_id", "")
    state_label = state.value if getattr(state, "value", None) is not None else str(state or "")
    fk_label = (
        failure_kind.value if getattr(failure_kind, "value", None) is not None else ""
    )
    output = getattr(result, "output", {}) or {}
    # Bounded output evidence: never dumps secrets; only bounded text.
    output_hint = ""
    if isinstance(output, dict) and output:
        try:
            output_hint = next(iter(output.values())) if output else ""
            if isinstance(output_hint, str) and len(output_hint) > 120:
                output_hint = output_hint[:117] + "..."
        except (StopIteration, TypeError):
            output_hint = ""
    parts = [f"- {step_id}: {target} — {state_label}"]
    if fk_label:
        parts[-1] += f" ({fk_label})"
    error = (getattr(result, "error", "") or "").strip()[:_MAX_ERROR_CHARS]
    if error and result.state.value in ("failed", "skipped", "blocked"):
        parts[-1] += f": {error}"
    if output_hint and result.state.value == "completed":
        parts[-1] += f" — {str(output_hint).strip()[:120]}"
    return " ".join(parts)
