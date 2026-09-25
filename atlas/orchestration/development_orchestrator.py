"""Atlas — Development Independence Orchestration (D5).

A bounded, deterministic coordinator that connects D4 self-directed work
orchestration to the EXISTING governed development lifecycle:

    objective
      -> investigation / gap assessment + proposal   (existing DevelopmentDriver)
      -> OWNER approval                              (existing approval mechanism)
      -> sandbox implementation                      (existing SelfDevelopmentLoop/CodeSandbox)
      -> verification                                (existing DevelopmentVerification)
      -> promotion review + promotion                (existing PromotionGate/Executor)
      -> self-knowledge refresh                       (existing capability/architecture model)
      -> bounded report

It is a COORDINATOR ONLY. Every authority remains with the component that owns
it, injected as a callable by the kernel:

  * proposal preparation  -> existing ``Atlas.run_development_driver``
  * approval state        -> existing ``ApprovalManager`` / persisted proposal status
  * implementation        -> existing ``Atlas.run_development_execution`` (OWNER-gated, sandboxed)
  * promotion review      -> existing ``Atlas.submit_development_for_promotion_review``
  * promotion             -> existing ``Atlas.promote_validated_change`` (OWNER-only gate+executor)
  * self-knowledge        -> existing ``Atlas.capability_model`` / architecture model

The orchestrator NEVER approves, NEVER authorizes, NEVER executes without an
existing approved proposal, and NEVER promotes itself. Deterministic and
model-independent: no ``atlas.ai`` import, no network.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

_MAX_TEXT: int = 400


class DevelopmentState(str, Enum):
    """Lifecycle states of one governed development run."""

    RECEIVED = "received"
    INVESTIGATING = "investigating"
    PROPOSAL_CREATED = "proposal_created"
    AWAITING_OWNER = "awaiting_owner"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    PROMOTING = "promoting"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFICATION_FAILED = "verification_failed"
    PROMOTION_FAILED = "promotion_failed"


def _bounded(value: Any, limit: int = _MAX_TEXT) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _name(value: Any) -> str:
    """Return an enum ``name`` (or ``value`` / str) for a status-ish object."""
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    val = getattr(value, "value", None)
    if isinstance(val, str) and val:
        return val
    return value if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class DevelopmentRun:
    """Bounded, JSON-safe record of one governed development run.

    Records facts and the existing components' identities only (proposal /
    approval / promotion review). It carries no authority and no invented
    authority field.
    """

    run_id: str
    objective: str
    state: DevelopmentState
    transitions: tuple[tuple[str, str], ...] = ()
    proposal_id: str = ""
    proposal_status: str = ""
    approval_status: str = ""
    execution_status: str = ""
    verification_status: str = ""
    promotion_review_id: str = ""
    promotion_status: str = ""
    self_knowledge: dict[str, Any] | None = None
    report: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "objective": self.objective,
            "state": self.state.value,
            "transitions": [list(t) for t in self.transitions],
            "proposal_id": self.proposal_id,
            "proposal_status": self.proposal_status,
            "approval_status": self.approval_status,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
            "promotion_review_id": self.promotion_review_id,
            "promotion_status": self.promotion_status,
            "self_knowledge": dict(self.self_knowledge) if self.self_knowledge else None,
            "report": self.report,
            "error": self.error,
        }

    @property
    def completed(self) -> bool:
        return self.state is DevelopmentState.COMPLETED


class DevelopmentOrchestrator:
    """Deterministic coordinator over the EXISTING governed development lifecycle.

    All dependencies are injected by the kernel; none of the authority-owning
    components are reimplemented here.
    """

    def __init__(
        self,
        *,
        driver: Callable[..., Any],
        approval_checker: Callable[[str], bool],
        execution_runner: Callable[..., Any],
        promotion_reviewer: Callable[..., Any] | None = None,
        promotion_executor: Callable[..., Any] | None = None,
        self_knowledge_refresher: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._driver = driver
        self._approval_checker = approval_checker
        self._execution_runner = execution_runner
        self._promotion_reviewer = promotion_reviewer
        self._promotion_executor = promotion_executor
        self._self_knowledge_refresher = self_knowledge_refresher

    # ------------------------------------------------------------------

    def run(
        self,
        objective: str,
        *,
        session_context: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DevelopmentRun:
        """Run ONE bounded governed development lifecycle for ``objective``.

        The orchestrator never grants approval: it reads the EXISTING approval
        state and stops at ``AWAITING_OWNER`` when approval is absent.
        """
        transitions: list[tuple[str, str]] = []

        def _step(state: DevelopmentState, detail: str = "") -> None:
            transitions.append((state.value, _bounded(detail, 160)))

        objective_text = _bounded(objective)
        run_id = f"DEVRUN-{hashlib.sha256(objective_text.encode('utf-8')).hexdigest()[:12]}"
        _step(DevelopmentState.RECEIVED, objective_text)
        if not objective_text:
            _step(DevelopmentState.FAILED, "empty objective")
            return self._finish(
                run_id, "", DevelopmentState.FAILED, transitions,
                error="A non-empty development objective is required.",
            )

        # 1. Investigation / gap assessment + proposal (existing driver).
        _step(DevelopmentState.INVESTIGATING, "gap assessment + proposal preparation")
        try:
            prepared = self._driver(objective_text, metadata or {})
        except Exception as exc:  # fail closed
            _step(DevelopmentState.FAILED, f"driver error: {type(exc).__name__}")
            return self._finish(
                run_id, objective_text, DevelopmentState.FAILED, transitions,
                error=f"Proposal preparation failed: {type(exc).__name__}.",
            )
        proposal_id = _bounded(getattr(prepared, "proposal_id", ""), 128)
        if not proposal_id:
            detail = _bounded(getattr(prepared, "detail", ""), 200)
            _step(DevelopmentState.FAILED, "no proposal produced")
            return self._finish(
                run_id, objective_text, DevelopmentState.FAILED, transitions,
                error=detail or "No development proposal could be prepared.",
                report=(
                    "I could not prepare a governed development proposal for "
                    "that objective."
                ),
            )
        proposal_status = _bounded(getattr(prepared, "terminal", ""), 64) or "pending"
        _step(DevelopmentState.PROPOSAL_CREATED, proposal_id)

        # 2. OWNER approval boundary (READ-ONLY: the orchestrator never approves).
        approved = False
        try:
            approved = bool(self._approval_checker(proposal_id))
        except Exception:
            approved = False
        if not approved:
            _step(DevelopmentState.AWAITING_OWNER, "no OWNER approval present")
            return self._finish(
                run_id, objective_text, DevelopmentState.AWAITING_OWNER, transitions,
                proposal_id=proposal_id,
                proposal_status=_bounded(proposal_status, 64),
                approval_status="awaiting_owner",
                report=(
                    f"Governed development proposal {proposal_id} is prepared "
                    "and waiting for OWNER approval. I have made no code "
                    "changes and will not implement anything until it is "
                    "approved."
                ),
            )
        approval_status = "approved"

        # 3. Sandbox implementation (existing OWNER-gated, sandboxed runner).
        _step(DevelopmentState.IMPLEMENTING, proposal_id)
        try:
            run_result = self._execution_runner(session_context, proposal_id)
        except Exception as exc:  # fail closed
            _step(DevelopmentState.FAILED, f"execution error: {type(exc).__name__}")
            return self._finish(
                run_id, objective_text, DevelopmentState.FAILED, transitions,
                proposal_id=proposal_id, proposal_status=proposal_status,
                approval_status=approval_status,
                error=f"Sandbox execution failed: {type(exc).__name__}.",
            )
        execution_status = _name(getattr(run_result, "status", ""))
        verification = getattr(run_result, "verification", None)
        verification_status = _name(getattr(verification, "status", ""))

        # 4. Verification gate (mandatory before promotion).
        _step(DevelopmentState.VERIFYING, verification_status or execution_status)
        if execution_status != "SUCCESS" or verification_status != "verified":
            failed_state = (
                DevelopmentState.VERIFICATION_FAILED
                if verification_status in ("failed", "unverified", "inconclusive")
                or execution_status == "SUCCESS"
                else DevelopmentState.FAILED
            )
            _step(failed_state, "verification not satisfied")
            return self._finish(
                run_id, objective_text, failed_state, transitions,
                proposal_id=proposal_id, proposal_status=proposal_status,
                approval_status=approval_status,
                execution_status=execution_status,
                verification_status=verification_status,
                report=(
                    "Implementation did not verify, so I am not promoting it "
                    "and I am not reporting success."
                ),
                error=f"Verification not satisfied (execution={execution_status}).",
            )

        # 5. Promotion (existing review + existing promotion executor only).
        _step(DevelopmentState.PROMOTING, "promotion review")
        promotion_review_id = ""
        promotion_status = ""
        if self._promotion_reviewer is not None:
            try:
                review = self._promotion_reviewer(
                    session_context, run_result, proposal_id
                )
                promotion_review_id = _bounded(
                    getattr(review, "request_id", ""), 128
                )
            except Exception as exc:  # fail closed
                _step(DevelopmentState.PROMOTION_FAILED, f"review error: {type(exc).__name__}")
                return self._finish(
                    run_id, objective_text, DevelopmentState.PROMOTION_FAILED, transitions,
                    proposal_id=proposal_id, proposal_status=proposal_status,
                    approval_status=approval_status, execution_status=execution_status,
                    verification_status=verification_status,
                    error=f"Promotion review failed: {type(exc).__name__}.",
                )
        if self._promotion_executor is None:
            _step(DevelopmentState.PROMOTION_FAILED, "promotion executor unavailable")
            return self._finish(
                run_id, objective_text, DevelopmentState.PROMOTION_FAILED, transitions,
                proposal_id=proposal_id, proposal_status=proposal_status,
                approval_status=approval_status, execution_status=execution_status,
                verification_status=verification_status,
                promotion_review_id=promotion_review_id,
                error="Promotion executor is not available (fail-closed).",
            )
        try:
            promotion = self._promotion_executor(session_context, promotion_review_id)
        except Exception as exc:  # fail closed
            _step(DevelopmentState.PROMOTION_FAILED, f"promotion error: {type(exc).__name__}")
            return self._finish(
                run_id, objective_text, DevelopmentState.PROMOTION_FAILED, transitions,
                proposal_id=proposal_id, proposal_status=proposal_status,
                approval_status=approval_status, execution_status=execution_status,
                verification_status=verification_status,
                promotion_review_id=promotion_review_id,
                error=f"Promotion failed: {type(exc).__name__}.",
            )
        promotion_status = _name(getattr(promotion, "status", "")) or "promoted"

        # 6. Self-knowledge refresh (ONLY after successful promotion).
        self_knowledge: dict[str, Any] | None = None
        if self._self_knowledge_refresher is not None:
            try:
                self_knowledge = dict(self._self_knowledge_refresher() or {})
            except Exception:
                self_knowledge = None

        _step(DevelopmentState.COMPLETED, "verified and promoted")
        return self._finish(
            run_id, objective_text, DevelopmentState.COMPLETED, transitions,
            proposal_id=proposal_id, proposal_status=proposal_status,
            approval_status=approval_status, execution_status=execution_status,
            verification_status=verification_status,
            promotion_review_id=promotion_review_id, promotion_status=promotion_status,
            self_knowledge=self_knowledge,
            report=(
                f"Governed development completed for objective: {objective_text}. "
                f"Proposal {proposal_id} was approved, implemented in the "
                "sandbox, verified, and promoted."
            ),
        )

    @staticmethod
    def _finish(
        run_id: str,
        objective: str,
        state: DevelopmentState,
        transitions: list[tuple[str, str]],
        *,
        proposal_id: str = "",
        proposal_status: str = "",
        approval_status: str = "",
        execution_status: str = "",
        verification_status: str = "",
        promotion_review_id: str = "",
        promotion_status: str = "",
        self_knowledge: dict[str, Any] | None = None,
        report: str = "",
        error: str = "",
    ) -> DevelopmentRun:
        return DevelopmentRun(
            run_id=run_id,
            objective=objective,
            state=state,
            transitions=tuple(transitions),
            proposal_id=proposal_id,
            proposal_status=proposal_status,
            approval_status=approval_status,
            execution_status=execution_status,
            verification_status=verification_status,
            promotion_review_id=promotion_review_id,
            promotion_status=promotion_status,
            self_knowledge=self_knowledge,
            report=report,
            error=error,
        )
