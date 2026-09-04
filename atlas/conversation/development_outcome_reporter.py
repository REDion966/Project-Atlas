"""Atlas Conversation — Development Outcome Reporter (P7.5).

Pure, deterministic conversation-layer reporter that maps EXISTING F9
development states into truthful conversational :class:`Message` reports.

This module does NOT create a new lifecycle. It only renders the states the
F9 pipeline already substantiates, using the actual status/outcome
representations:

    DevelopmentCycleResult      -> AWAITING_APPROVAL | PREPARATION_FAILED
    ApprovalDecision            -> APPROVED | APPROVAL_REJECTED | APPROVAL_DEFERRED
    DevelopmentRunResult        -> EXECUTION_SUCCEEDED | EXECUTION_FAILED | ROLLED_BACK
    PromotionStatus             -> PROMOTION_REVIEW_PENDING | PROMOTION_APPROVED | PROMOTION_REJECTED

Critical invariant: the reporter NEVER approves, rejects, executes, promotes,
mutates the repository, retries, or invokes any development execution. It is
reporting-only. A conversational "yes" (P7.3 confirmation) is NOT approval,
NOT execution, and NOT promotion — and neither is reporting an outcome.

Design contract:
  * Pure: imports only conversation-owned data types. No kernel, no runtime,
    no storage, no AI, no evolution execution, no orchestration execution,
    no advisory runtime, no approval, no execution.
  * Deterministic + idempotent: the same snapshot always produces the same
    message; reporting a terminal outcome twice never creates a request,
    retries, approves, executes, or promotes anything.
  * Fail-closed: unknown/missing state renders a neutral "outcome not
    determined" message rather than guessing success.
  * Provenance-preserving: session_id / principal_id / authority flow into
    the report metadata; authority is never elevated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from atlas.conversation.message import Message

# ---------------------------------------------------------------------------
# Outcome states (all backed by existing F9 representations)
# ---------------------------------------------------------------------------


class DevelopmentOutcomeState(str, Enum):
    """Truthful terminal states already represented by the F9 pipeline."""

    AWAITING_APPROVAL = "awaiting_approval"
    PREPARATION_FAILED = "preparation_failed"
    APPROVED = "approved"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_DEFERRED = "approval_deferred"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"
    ROLLED_BACK = "rolled_back"
    PROMOTION_REVIEW_PENDING = "promotion_review_pending"
    PROMOTION_APPROVED = "promotion_approved"
    PROMOTION_REJECTED = "promotion_rejected"


# ---------------------------------------------------------------------------
# Snapshot (conversation-owned projection)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DevelopmentOutcomeSnapshot:
    """Bounded, provenance-carrying projection of one F9 outcome.

    Carries only what is needed for truthful reporting. It never carries
    execution/promotion *state machines* — only the already-produced outcome
    evidence from F9.
    """

    state: str
    proposal_id: str = ""
    approval_request_id: str = ""
    message: str = ""
    verification_passed: bool | None = None
    rollback_occurred: bool = False
    test_outcome: str = ""
    session_id: str = ""
    principal_id: str = ""
    authority: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "proposal_id": self.proposal_id,
            "approval_request_id": self.approval_request_id,
            "message": self.message,
            "verification_passed": self.verification_passed,
            "rollback_occurred": self.rollback_occurred,
            "test_outcome": self.test_outcome,
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "authority": self.authority,
        }


# ---------------------------------------------------------------------------
# Projection helpers (duck-typed — no evolution imports)
# ---------------------------------------------------------------------------


def _bounded_text(value: Any, limit: int = 300) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _enum_name(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "name"):
        return str(value.name)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def snapshot_from_cycle_result(result: Any, **provenance: str) -> DevelopmentOutcomeSnapshot:
    """Project a ``DevelopmentCycleResult`` into an outcome snapshot.

    ``ok`` -> AWAITING_APPROVAL (the authoritative stop-at-approval state).
    otherwise -> PREPARATION_FAILED (fail-closed).
    """
    ok = bool(getattr(result, "ok", False))
    if ok:
        state = DevelopmentOutcomeState.AWAITING_APPROVAL.value
        message = (
            "The development request was submitted and is awaiting human approval."
        )
    else:
        state = DevelopmentOutcomeState.PREPARATION_FAILED.value
        failures = getattr(result, "failures", ()) or ()
        details = "; ".join(
            f"{stage}: {msg}"
            for stage, msg in failures[:5]
            if isinstance(stage, str) and isinstance(msg, str)
        )
        message = "Development preparation failed." + (
            f" Details: {details}." if details else ""
        )
    return DevelopmentOutcomeSnapshot(
        state=state,
        proposal_id=_bounded_text(getattr(result, "proposal_id", ""), 128),
        approval_request_id=_bounded_text(
            getattr(result, "approval_request_id", ""), 128
        ),
        message=message,
        **provenance,
    )


def snapshot_from_approval_decision(request: Any, **provenance: str) -> DevelopmentOutcomeSnapshot:
    """Project an ``ApprovalRequest`` decision into an outcome snapshot."""
    decision = _enum_name(getattr(request, "decision", ""))
    proposal_id = _bounded_text(getattr(request, "proposal_id", ""), 128)
    request_id = _bounded_text(getattr(request, "request_id", ""), 128)
    if decision == "REJECTED":
        state = DevelopmentOutcomeState.APPROVAL_REJECTED.value
        message = "The development request was denied by human approval."
    elif decision == "DEFERRED":
        state = DevelopmentOutcomeState.APPROVAL_DEFERRED.value
        message = "The development request was deferred by human approval."
    elif decision == "APPROVED":
        state = DevelopmentOutcomeState.APPROVED.value
        message = "The development request was approved and is ready to proceed."
    else:
        state = DevelopmentOutcomeState.AWAITING_APPROVAL.value
        message = "The development request is awaiting human approval."
    return DevelopmentOutcomeSnapshot(
        state=state,
        proposal_id=proposal_id,
        approval_request_id=request_id,
        message=message,
        **provenance,
    )


def snapshot_from_run_result(result: Any, **provenance: str) -> DevelopmentOutcomeSnapshot:
    """Project a ``DevelopmentRunResult`` into an outcome snapshot.

    Uses the authoritative ``status`` plus the last ``DevelopmentOutcome``'s
    ``rollback_occurred`` / ``verification_passed`` fields. Never infers
    success from proposal/approval creation.
    """
    status_name = _enum_name(getattr(result, "status", ""))
    outcomes = getattr(result, "outcomes", ()) or ()
    last = outcomes[-1] if outcomes else None
    rollback = bool(getattr(last, "rollback_occurred", False))
    verification = bool(getattr(last, "verification_passed", False))
    test_outcome = _bounded_text(getattr(last, "test_outcome", ""), 120)
    proposal_id = _bounded_text(getattr(result, "plan", None) and getattr(result.plan, "proposal_id", ""), 128) if getattr(result, "plan", None) else ""
    message = _bounded_text(getattr(result, "message", ""), 300)

    if status_name == "SUCCESS":
        state = DevelopmentOutcomeState.EXECUTION_SUCCEEDED.value
        text = "Development execution completed successfully in the sandbox."
    elif rollback:
        state = DevelopmentOutcomeState.ROLLED_BACK.value
        text = "Development execution failed and the sandbox was rolled back."
    else:
        state = DevelopmentOutcomeState.EXECUTION_FAILED.value
        text = "Development execution failed."
    if message and message not in text:
        text += f" {message}"
    return DevelopmentOutcomeSnapshot(
        state=state,
        proposal_id=proposal_id,
        message=text,
        verification_passed=None if verification is False and status_name != "SUCCESS" else verification,
        rollback_occurred=rollback,
        test_outcome=test_outcome,
        **provenance,
    )


def snapshot_from_promotion_status(status_value: Any, proposal_id: str = "", **provenance: str) -> DevelopmentOutcomeSnapshot:
    """Project a ``PromotionStatus`` into an outcome snapshot.

    ``APPROVED`` means exactly "ready for human promotion" — it NEVER means
    the repository was modified. ``PROMOTED`` is reserved for out-of-scope
    operator tooling and is NOT reported as success here.
    """
    status = _enum_name(status_value)
    proposal_id = _bounded_text(proposal_id, 128)
    if status == "approved":
        state = DevelopmentOutcomeState.PROMOTION_APPROVED.value
        message = (
            "Development execution completed and the result is ready for "
            "human promotion. The repository has not been modified."
        )
    elif status == "rejected":
        state = DevelopmentOutcomeState.PROMOTION_REJECTED.value
        message = "The promotion review was rejected."
    else:
        state = DevelopmentOutcomeState.PROMOTION_REVIEW_PENDING.value
        message = (
            "Development execution completed and the result is awaiting human "
            "promotion review."
        )
    return DevelopmentOutcomeSnapshot(
        state=state,
        proposal_id=proposal_id,
        message=message,
        **provenance,
    )


def snapshot_from_result(result: Any, **provenance: str) -> DevelopmentOutcomeSnapshot:
    """Duck-typed dispatcher: project an authoritative F9 result object into
    an outcome snapshot, or fail closed when the shape is unknown.

    Detection order (deterministic, non-overlapping):
      * ``.ok`` attribute            -> ``DevelopmentCycleResult``
      * ``.decision`` + ``.request_id`` -> ``ApprovalRequest``
      * ``.outcomes`` attribute      -> ``DevelopmentRunResult``
    Anything else is UNKNOWN (never guessed as success).
    """
    if result is None:
        return DevelopmentOutcomeSnapshot(
            state="unknown",
            message="The development outcome could not be determined.",
            **provenance,
        )
    if hasattr(result, "ok"):
        return snapshot_from_cycle_result(result, **provenance)
    if hasattr(result, "decision") and hasattr(result, "request_id"):
        return snapshot_from_approval_decision(result, **provenance)
    if hasattr(result, "outcomes"):
        return snapshot_from_run_result(result, **provenance)
    return DevelopmentOutcomeSnapshot(
        state="unknown",
        message="The development outcome could not be determined.",
        **provenance,
    )


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


class DevelopmentOutcomeReporter:
    """Deterministic, idempotent, reporting-only renderer of F9 outcomes.

    Stateless. ``report`` never mutates anything and never invokes any
    development/approval/execution/promotion machinery.
    """

    def report_result(self, result: Any, **provenance: str) -> Message:
        """Convenience: project an authoritative F9 result object and render
        its truthful conversational report in one step. Pure and reporting-
        only — never approves, executes, or promotes."""
        return self.report(snapshot_from_result(result, **provenance))

    def report(self, snapshot: DevelopmentOutcomeSnapshot) -> Message:
        """Render a truthful conversational report for one outcome snapshot.

        The returned message is tagged with the outcome state + provenance
        (authority projected verbatim, never elevated).
        """
        return Message(
            role="assistant",
            content=self._content(snapshot),
            metadata={
                "development_outcome": {
                    "state": snapshot.state,
                    "proposal_id": snapshot.proposal_id,
                    "approval_request_id": snapshot.approval_request_id,
                },
                "session_id": snapshot.session_id,
                "principal_id": snapshot.principal_id,
                "authority": snapshot.authority,
            },
        )

    # ------------------------------------------------------------------

    def _content(self, snapshot: DevelopmentOutcomeSnapshot) -> str:
        # A provided truthful message is authoritative; otherwise derive from
        # the state using only statements the existing F9 substantiates.
        if snapshot.message:
            return snapshot.message

        state = snapshot.state
        if state == DevelopmentOutcomeState.AWAITING_APPROVAL.value:
            return "The development request was submitted and is awaiting human approval."
        if state == DevelopmentOutcomeState.PREPARATION_FAILED.value:
            return "Development preparation failed."
        if state == DevelopmentOutcomeState.APPROVED.value:
            return "The development request was approved and is ready to proceed."
        if state == DevelopmentOutcomeState.APPROVAL_REJECTED.value:
            return "The development request was denied by human approval."
        if state == DevelopmentOutcomeState.APPROVAL_DEFERRED.value:
            return "The development request was deferred by human approval."
        if state == DevelopmentOutcomeState.EXECUTION_SUCCEEDED.value:
            return "Development execution completed successfully in the sandbox."
        if state == DevelopmentOutcomeState.EXECUTION_FAILED.value:
            return "Development execution failed."
        if state == DevelopmentOutcomeState.ROLLED_BACK.value:
            return "Development execution failed and the sandbox was rolled back."
        if state == DevelopmentOutcomeState.PROMOTION_REVIEW_PENDING.value:
            return (
                "Development execution completed and the result is awaiting "
                "human promotion review."
            )
        if state == DevelopmentOutcomeState.PROMOTION_APPROVED.value:
            return (
                "Development execution completed and the result is ready for "
                "human promotion. The repository has not been modified."
            )
        if state == DevelopmentOutcomeState.PROMOTION_REJECTED.value:
            return "The promotion review was rejected."
        # Fail-closed: never guess success.
        return "The development outcome could not be determined."
