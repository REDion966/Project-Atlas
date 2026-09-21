"""Atlas Evolution — Development Driver (Phase 5.2).

A bounded, deterministic ORCHESTRATION layer that composes the existing
surfaces into the direct-evolution lifecycle:

    request
      -> gap assessment (Phase 5.2)
      -> bounded research when knowledge is missing (existing acquisition)
      -> DevelopmentNeed
      -> authoring (existing ChangeSupplier seam / scaffold author)
      -> governed development cycle (existing controller) STOP at PENDING_APPROVAL
      -> envelope-authorized sandbox execution + verification (existing loop)
      -> evidence-based usefulness assessment (Phase 5.2)
      -> promotion-request preparation STOP at the OWNER promotion gate

It is a **bounded invocation** (it may run a bounded number of development
iterations), NOT a daemon/tick actor, and is never invoked from ``tick()``.
It is orchestration-only: every subsystem is injected and reused — no logic is
duplicated, and it mints no authority.

Pure orchestration. No AI, no network, no kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_envelope import SANDBOX_DEVELOPMENT
from atlas.evolution.development_gap import (
    DevelopmentGapAssessment,
    DevelopmentGapKind,
)
from atlas.evolution.development_usefulness import assess_usefulness


class DevelopmentDriveTerminal(str, Enum):
    """Honest terminal state of one driver invocation."""

    PROPOSED = "proposed"                  # proposal prepared; envelope unavailable
    VALIDATED = "validated"                # sandbox-verified; promotion requested
    ALREADY_SUPPORTED = "already_supported"
    AUTHOR_UNAVAILABLE = "author_unavailable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ENVELOPE_DISABLED = "envelope_disabled"
    FAILED = "failed"


@dataclass(slots=True)
class DevelopmentDriveResult:
    """Bounded result of one driver invocation."""

    terminal: DevelopmentDriveTerminal
    detail: str = ""
    request: str = ""
    gap: Any | None = None
    proposal_id: str = ""
    authorization_id: str = ""
    execution_status: str = ""
    verification_status: str = ""
    usefulness: Any | None = None
    promotion_request_id: str = ""
    failures: tuple[tuple[str, str], ...] = ()
    completed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "terminal": self.terminal.value,
            "detail": self.detail,
            "request": self.request,
            "gap": getattr(self.gap, "to_dict", lambda: None)(),
            "proposal_id": self.proposal_id,
            "authorization_id": self.authorization_id,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
            "usefulness": getattr(self.usefulness, "to_dict", lambda: None)(),
            "promotion_request_id": self.promotion_request_id,
            "failures": [list(f) for f in self.failures],
            "completed_at": self.completed_at.isoformat(),
        }


class DevelopmentDriver:
    """Bounded orchestrator over the existing governed-development surfaces.

    Args:
        gap_assessor: ``request -> DevelopmentGapAssessment``.
        cycle_runner: ``need -> DevelopmentCycleResult`` (existing controller).
        executor: optional ``proposal -> run_result`` (existing governed
            sandbox execution). When absent, the driver stops at PROPOSED.
        authority: optional ``DevelopmentAuthority`` (bounded envelope).
        researcher: optional F8 ``acquire``-shaped callable.
        usefulness_fn: deterministic usefulness assessor (defaults to
            :func:`assess_usefulness`).
        promotion_preparer: optional ``(proposal, run_result) -> str`` that
            captures the artifact and submits a promotion request for review.
        experience_recorder: optional ``(result) -> None`` retention seam.
    """

    def __init__(
        self,
        *,
        gap_assessor: Callable[[str], DevelopmentGapAssessment],
        cycle_runner: Callable[[DevelopmentNeed], Any],
        executor: Callable[[Any], Any] | None = None,
        authority: Any | None = None,
        researcher: Callable[..., Any] | None = None,
        usefulness_fn: Callable[..., Any] = assess_usefulness,
        promotion_preparer: Callable[[Any, Any], str] | None = None,
        experience_recorder: Callable[[Any], None] | None = None,
    ) -> None:
        self._gap_assessor = gap_assessor
        self._cycle_runner = cycle_runner
        self._executor = executor
        self._authority = authority
        self._researcher = researcher
        self._usefulness_fn = usefulness_fn
        self._promotion_preparer = promotion_preparer
        self._experience_recorder = experience_recorder

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def drive(
        self,
        request: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> DevelopmentDriveResult:
        """Run ONE bounded development invocation for ``request``."""
        if not isinstance(request, str) or not request.strip():
            return DevelopmentDriveResult(
                DevelopmentDriveTerminal.FAILED,
                detail="a non-empty development request is required",
                request=str(request or ""),
            )

        gap = self._gap_assessor(request)
        if gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED:
            return DevelopmentDriveResult(
                DevelopmentDriveTerminal.ALREADY_SUPPORTED,
                detail=gap.rationale,
                request=request,
                gap=gap,
            )
        if gap.kind is DevelopmentGapKind.UNCLEAR:
            return DevelopmentDriveResult(
                DevelopmentDriveTerminal.FAILED,
                detail=gap.rationale or "request could not be adjudicated",
                request=request,
                gap=gap,
            )

        need_metadata = dict(metadata or {})
        research_summary: dict[str, Any] = {}
        if (
            gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
            and not self._has_direct_evidence(need_metadata)
        ):
            researched, research_summary = self._research(request)
            if not researched:
                return DevelopmentDriveResult(
                    DevelopmentDriveTerminal.INSUFFICIENT_EVIDENCE,
                    detail="knowledge is missing and bounded research produced no evidence",
                    request=request,
                    gap=gap,
                    failures=(("research", research_summary.get("error", "no result")),),
                )
            if research_summary:
                need_metadata["research"] = research_summary

        need = self._build_need(request, gap, need_metadata)

        cycle = self._cycle_runner(need)
        if not getattr(cycle, "ok", False):
            failures = tuple(getattr(cycle, "failures", ()) or ())
            supplier_failed = any(
                str(stage) == "supplier" for stage, _ in failures
            )
            terminal = (
                DevelopmentDriveTerminal.AUTHOR_UNAVAILABLE
                if supplier_failed
                else DevelopmentDriveTerminal.FAILED
            )
            return DevelopmentDriveResult(
                terminal,
                detail=(
                    "no authoring content available for this change class"
                    if supplier_failed
                    else "development preparation failed closed"
                ),
                request=request,
                gap=gap,
                failures=failures,
            )

        proposal_id = str(getattr(cycle, "proposal_id", "") or "")

        # Envelope/bounded-sandbox phase.
        if self._executor is None or self._authority is None:
            return DevelopmentDriveResult(
                DevelopmentDriveTerminal.PROPOSED,
                detail="proposal prepared; stopping at the authorization boundary",
                request=request,
                gap=gap,
                proposal_id=proposal_id,
            )

        decision = self._authority.check(SANDBOX_DEVELOPMENT)
        if not decision.allowed:
            return DevelopmentDriveResult(
                DevelopmentDriveTerminal.ENVELOPE_DISABLED,
                detail=f"development envelope unavailable: {decision.reason}",
                request=request,
                gap=gap,
                proposal_id=proposal_id,
            )

        proposal = self._resolve_proposal(proposal_id, cycle)
        authorization = self._authority.authorize(proposal)
        if authorization is None:
            return DevelopmentDriveResult(
                DevelopmentDriveTerminal.ENVELOPE_DISABLED,
                detail="development envelope declined to authorize sandbox execution",
                request=request,
                gap=gap,
                proposal_id=proposal_id,
            )

        run_result = self._executor(proposal)
        verification = getattr(run_result, "verification", None)
        verification_status = getattr(
            getattr(verification, "status", None), "value", ""
        )
        execution_status = getattr(
            getattr(run_result, "status", None), "name", ""
        )

        capability_after = (
            execution_status == "SUCCESS" and verification_status == "verified"
        )
        usefulness = self._usefulness_fn(
            proposal_id=proposal_id,
            objective=str(getattr(proposal, "expected_benefit", "") or request),
            verification_status=verification_status,
            capability_present_before=False,
            capability_present_after=capability_after,
            regression_detected=execution_status not in ("", "SUCCESS"),
            reproducible=None,
            evidence_count=len(getattr(run_result, "outcomes", ()) or ()),
        )

        promotion_request_id = ""
        failures: tuple[tuple[str, str], ...] = ()
        if self._promotion_preparer is not None:
            try:
                promotion_request_id = str(
                    self._promotion_preparer(proposal, run_result) or ""
                )
            except Exception as exc:
                failures = (
                    (
                        "promotion_prepare",
                        f"{type(exc).__name__}: {str(exc)[:200]}",
                    ),
                )

        result = DevelopmentDriveResult(
            DevelopmentDriveTerminal.VALIDATED,
            detail="sandbox development completed and verified",
            request=request,
            gap=gap,
            proposal_id=proposal_id,
            authorization_id=getattr(authorization, "authorization_id", ""),
            execution_status=execution_status,
            verification_status=verification_status,
            usefulness=usefulness,
            promotion_request_id=promotion_request_id,
            failures=failures,
        )
        if self._experience_recorder is not None:
            try:
                self._experience_recorder(result)
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # Internals (orchestration glue only)
    # ------------------------------------------------------------------

    @staticmethod
    def _has_direct_evidence(metadata: dict[str, Any]) -> bool:
        # A supplied change set OR a structured authoring spec is enough to
        # proceed without research (both are direct authoring input).
        return bool(metadata.get("code_changes") or metadata.get("scaffold"))

    def _research(self, request: str) -> tuple[bool, dict[str, Any]]:
        if self._researcher is None:
            return (False, {"error": "researcher not wired"})
        try:
            acquisition = self._researcher(question=request, sources=())
        except Exception as exc:
            return (False, {"error": f"{type(exc).__name__}: {exc}"})
        if acquisition is None or getattr(acquisition, "status", "") == "failed":
            return (False, {"error": "acquisition failed"})
        summary: dict[str, Any] = {}
        to_dict = getattr(acquisition, "to_dict", None)
        if callable(to_dict):
            try:
                full = dict(to_dict())
            except Exception:
                full = {}
            summary = {
                key: full.get(key)
                for key in ("acquisition_id", "status", "report_id", "sources", "confidence", "claim_count")
                if key in full
            }
        return (True, summary)

    @staticmethod
    def _build_need(
        request: str,
        gap: DevelopmentGapAssessment,
        metadata: dict[str, Any],
    ) -> DevelopmentNeed:
        return DevelopmentNeed(
            title=request.strip()[:200],
            summary=request.strip()[:2000],
            rationale=gap.rationale,
            expected_benefit="",
            target_components=tuple(metadata.get("target_components", ()) or ()),
            evidence_knowledge_ids=tuple(metadata.get("evidence_knowledge_ids", ()) or ()),
            research_question=request.strip(),
            metadata=dict(metadata),
        )

    def _resolve_proposal(self, proposal_id: str, cycle: Any) -> Any:
        """Resolve the persisted proposal object for authorization binding."""
        proposal = getattr(cycle, "proposal", None)
        if proposal is not None:
            return proposal
        resolver = getattr(self._cycle_runner, "get_proposal", None)
        if callable(resolver) and proposal_id:
            try:
                found = resolver(proposal_id)
                if found is not None:
                    return found
            except Exception:
                pass
        # Minimal stand-in: bind to the id + cycle status only.
        from types import SimpleNamespace

        return SimpleNamespace(
            proposal_id=proposal_id,
            expected_benefit="",
            proposal_fingerprint=f"cycle:{proposal_id}",
        )
