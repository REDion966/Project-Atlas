"""Atlas Evolution — Specification-Driven Self-Development (Step 24).

A bounded, deterministic, model-free BRIDGE from an authorized Step 23 capability
specification to the EXISTING governed development pipeline: it translates the
specification into a bounded `DevelopmentNeed`, prepares the DRAFT proposal and its
approval request through the EXISTING `DevelopmentCycleController`, exposes the
human approval boundary, and — ONLY when the proposal is explicitly authorized —
runs the EXISTING governed sandbox execution, verification and promotion review.

It adds NO implementation engine, NO approval system and NO promotion path:

* the proposal/approval lifecycle is the EXISTING `DevelopmentCycleController` +
  `ApprovalManager` (the bridge stops at ``PENDING_APPROVAL``);
* the sandbox execution is the EXISTING `run_development_execution` seam (injected
  as ``execute``), which owns the `CodeSandbox` and the live-repository boundary;
* the verification is the EXISTING `DevelopmentVerification` (read-only);
* the promotion decision is the EXISTING `PromotionGate`, and the review is opened
  by the EXISTING promotion-preparer seam — the bridge never promotes.

Design guarantees:

* **Authorized input only.** Only a `SPECIFIED`, complete Step 23 specification is
  accepted; a refused, incomplete, ambiguous or malformed one fails closed with no
  workflow. Execution happens ONLY when the prepared proposal is ``APPROVED`` /
  ``SANDBOX_AUTHORIZED`` or an explicit authorization bound to that proposal is
  supplied — a Step-23 design is NEVER silently converted into authorization.
* **Human approval is the boundary.** Without authorization the bridge stops at
  ``awaiting_approval`` and exposes the bounded approval request; it never
  approves, authorizes or promotes anything.
* **Failed or unverified work is never promoted.** A failed run or a
  non-``verified`` verification yields ``not_promotable`` with NO promotion
  request; the EXISTING promotion gate's ``not_promotable`` verdict is honoured.
* **Evidence preserved.** The result records what changed (bounded changed files),
  why (the specification and its originating gap reason) and how it was verified
  (the verification status and its own evidence string), for audit.
* **Model-independent.** No model is consulted anywhere in this module; the change
  payload is explicit bounded input and the pipeline is the existing deterministic
  one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

#: Bounds (a malformed specification can never produce unbounded output).
_MAX_TEXT_CHARS: int = 300
_MAX_ITEMS: int = 8
_MAX_FILES: int = 20
_MAX_PAYLOAD_ITEMS: int = 5

#: Proposal statuses that already authorize SANDBOX-only development (the EXISTING
#: governance states). EVERY other status requires an explicit authorization.
_AUTHORIZED_STATUSES: frozenset[str] = frozenset({"APPROVED", "SANDBOX_AUTHORIZED"})

#: The workflow rule, stated once so callers can report it verbatim.
SELF_DEVELOPMENT_RULE: str = (
    "A specification becomes development ONLY through the existing governed "
    "pipeline: a bounded need, a DRAFT proposal, the human approval boundary, the "
    "sandbox-only authorized execution and the existing promotion review. The "
    "bridge never approves, authorizes, promotes or touches the live repository."
)


class SelfDevelopmentStage(str, Enum):
    """The bounded stage of a specification-driven development run (closed set)."""

    REFUSED = "refused"
    AWAITING_APPROVAL = "awaiting_approval"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    PROMOTION_REVIEW = "promotion_review"
    NOT_PROMOTABLE = "not_promotable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SpecificationDevelopmentResult:
    """The bounded, auditable result of one specification-driven run (immutable)."""

    stage: SelfDevelopmentStage
    spec_id: str = ""
    capability: str = ""
    request: str = ""
    authorized: bool = False
    proposal_id: str = ""
    approval_request_id: str = ""
    proposal_status: str = ""
    plan_id: str = ""
    execution_status: str = ""
    verification_status: str = ""
    promotion_request_id: str = ""
    changed_files: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    need: Any = field(default=None, repr=False, compare=False)

    @property
    def refused(self) -> bool:
        return self.stage is SelfDevelopmentStage.REFUSED

    @property
    def awaiting_approval(self) -> bool:
        """True when the workflow is stopped at the human approval boundary."""
        return self.stage is SelfDevelopmentStage.AWAITING_APPROVAL

    @property
    def executed(self) -> bool:
        """True once the governed sandbox implementation actually ran."""
        return self.stage in (
            SelfDevelopmentStage.IMPLEMENTATION,
            SelfDevelopmentStage.VERIFICATION,
            SelfDevelopmentStage.PROMOTION_REVIEW,
            SelfDevelopmentStage.NOT_PROMOTABLE,
        )

    @property
    def verified(self) -> bool:
        """True only when the EXISTING verifier reported ``verified``."""
        return self.verification_status == "verified"

    @property
    def promotable(self) -> bool:
        """True only when verified work reached an explicit promotion review."""
        return self.stage is SelfDevelopmentStage.PROMOTION_REVIEW and bool(
            self.promotion_request_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "spec_id": self.spec_id,
            "capability": self.capability,
            "request": self.request,
            "authorized": self.authorized,
            "proposal_id": self.proposal_id,
            "approval_request_id": self.approval_request_id,
            "proposal_status": self.proposal_status,
            "plan_id": self.plan_id,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
            "promotion_request_id": self.promotion_request_id,
            "changed_files": list(self.changed_files),
            "evidence": list(self.evidence),
            "reasons": list(self.reasons),
            "refused": self.refused,
            "awaiting_approval": self.awaiting_approval,
            "executed": self.executed,
            "verified": self.verified,
            "promotable": self.promotable,
            "self_development_rule": SELF_DEVELOPMENT_RULE,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _value(value: Any, limit: int = 48) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return ""
    return _clean(raw, limit)


def _strings(values: Any, limit: int = _MAX_ITEMS, width: int = 200) -> tuple[str, ...]:
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[str] = []
    for item in items:
        text = _clean(item, width)
        if text and text not in out:
            out.append(text)
    return tuple(out[:limit])


def _pairs(values: Any, limit: int = _MAX_PAYLOAD_ITEMS) -> tuple[tuple[str, str], ...]:
    """Normalize a bounded sequence of ``(path, content)`` pairs (fail-soft)."""
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[tuple[str, str]] = []
    for item in items:
        try:
            path, content = item
        except Exception:
            continue
        path_text = _clean(path, 256)
        if path_text and isinstance(content, str):
            out.append((path_text, content))
    return tuple(out[:limit])


def _authorization_valid(proposal: Any, authorization: Any) -> bool:
    """The EXISTING governance states, plus an explicitly supplied grant.

    Authorized iff the proposal already carries an authorizing status
    (``APPROVED`` / ``SANDBOX_AUTHORIZED`` — the EXISTING states the planner and the
    development loop both accept) or a supplied authorization is bound to it
    (``DevelopmentAuthorization.is_valid_for``). Nothing is inferred.
    """
    if proposal is None:
        return False
    status = _clean(getattr(getattr(proposal, "status", None), "name", ""), 40)
    if status in _AUTHORIZED_STATUSES:
        return True
    if authorization is None:
        return False
    check = getattr(authorization, "is_valid_for", None)
    if callable(check):
        try:
            return bool(check(proposal))
        except Exception:
            return False
    return False


def _verification_of(run: Any) -> tuple[str, str]:
    """``(status, evidence)`` from the run, via the EXISTING read-only verifier."""
    report = getattr(run, "verification", None)
    if report is None and run is not None:
        try:
            from atlas.evolution.development_verification import (
                DevelopmentVerification,
            )

            report = DevelopmentVerification().verify(run)
        except Exception:  # fail-closed: no verification, no promotable claim
            report = None
    if report is None:
        return "", ""
    return (
        _value(getattr(report, "status", "")),
        _clean(getattr(report, "evidence", ""), 300),
    )


def _changed_files(run: Any, payload: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    """Bounded changed-file evidence from the run, falling back to the payload."""
    files: list[str] = []
    for outcome in getattr(run, "outcomes", ()) or ():
        for path in getattr(outcome, "changed_files", ()) or ():
            text = _clean(path, 256)
            if text and text not in files:
                files.append(text)
    if not files:
        files = [path for path, _content in payload]
    return tuple(files[:_MAX_FILES])


# ---------------------------------------------------------------------------
# Specification -> DevelopmentNeed
# ---------------------------------------------------------------------------


def development_need_from_specification(
    specification: Any,
    *,
    code_changes: Any = (),
    test_files: Any = (),
    target_components: Any = (),
    evidence_ids: Any = (),
) -> Any:
    """Translate a Step 23 specification into the EXISTING ``DevelopmentNeed``.

    Deterministic and bounded: the specification's own fields supply the title,
    summary, rationale and evidence, the bounded change payload is carried in the
    EXISTING ``metadata["code_changes"]`` / ``metadata["test_files"]`` convention,
    and the specification's provenance (id, capability, request, gap kind, gap
    reason, evidence) is preserved under ``metadata["specification"]``.
    """
    from atlas.evolution.development_cycle import DevelopmentNeed

    capability = _clean(getattr(specification, "capability", ""), 200)
    request = _clean(getattr(specification, "request", ""), 300)
    purpose = _clean(getattr(specification, "purpose", ""), 400) or request
    operations = _strings(getattr(specification, "operations", ()) or ())
    known = _strings(getattr(specification, "known_facts", ()) or ())
    gap_reason = _clean(getattr(specification, "gap_reason", ""), 300)

    changes = _pairs(code_changes)
    tests = _pairs(test_files)
    components = _strings(target_components) or _strings(
        getattr(specification, "affected_areas", ()) or ()
    )
    evidence = _strings(getattr(specification, "evidence", ()) or ()) + _strings(
        evidence_ids
    )

    title = f"Implement the '{capability}' capability" if capability else (
        "Implement the specified capability"
    )
    summary_parts = [purpose]
    if operations:
        summary_parts.append("operations: " + ", ".join(operations))
    rationale_parts = list(known)
    if gap_reason:
        rationale_parts.append(f"gap: {gap_reason}")

    return DevelopmentNeed(
        title=title[:200],
        summary=" | ".join(part for part in summary_parts if part)[:2000],
        rationale=" | ".join(part for part in rationale_parts if part)[:4000],
        expected_benefit=(
            f"Atlas gains the '{capability}' capability" if capability else ""
        )[:2000],
        target_components=tuple(components)[:_MAX_ITEMS],
        candidate_id=_clean(getattr(specification, "spec_id", ""), 128),
        evidence_change_ids=tuple(evidence)[:20],
        metadata={
            "code_changes": [
                {"path": path, "content": content} for path, content in changes
            ],
            "test_files": {path: content for path, content in tests},
            "specification": {
                "spec_id": _clean(getattr(specification, "spec_id", ""), 128),
                "capability": capability,
                "request": request,
                "purpose": purpose,
                "operations": list(operations),
                "mechanism": _clean(getattr(specification, "mechanism", ""), 60),
                "gap_kind": _clean(getattr(specification, "gap_kind", ""), 60),
                "gap_boundary": _clean(getattr(specification, "gap_boundary", ""), 60),
                "gap_reason": gap_reason,
                "evidence": list(
                    _strings(getattr(specification, "evidence", ()) or ())
                ),
            },
        },
    )


# ---------------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------------


class SpecificationDevelopmentBridge:
    """Carry an authorized specification through the EXISTING governed pipeline.

    ``cycle_runner`` is the EXISTING development-cycle entry point
    (``DevelopmentCycleController.run_development_cycle`` / the kernel wrapper);
    ``execute`` is the EXISTING authorized sandbox-execution seam (supplied only
    by the caller/kernel — it owns the sandbox and the live-repository boundary);
    ``gate`` is the EXISTING ``PromotionGate``; ``promotion_preparer`` is the
    EXISTING review-opening seam. Every collaborator is optional: the bridge never
    fabricates one, and without them it stops at the honest boundary.
    """

    def __init__(
        self,
        *,
        cycle_runner: Callable[[Any], Any] | None = None,
        execute: Callable[[Any], Any] | None = None,
        gate: Any | None = None,
        promotion_preparer: Callable[[Any, Any], Any] | None = None,
    ) -> None:
        self._cycle_runner = cycle_runner
        self._execute = execute
        self._gate = gate
        self._promotion_preparer = promotion_preparer

    # -- validation --------------------------------------------------------

    @staticmethod
    def _refusal(specification: Any) -> tuple[str, str]:
        """``(spec_id, reason)`` when the specification cannot be developed."""
        if specification is None or not hasattr(specification, "is_specified"):
            return "", (
                "no capability specification was supplied, so nothing can be "
                "developed (fail-closed)"
            )
        spec_id = _clean(getattr(specification, "spec_id", ""), 128)
        if not bool(getattr(specification, "is_specified", False)):
            return spec_id, (
                "the specification was refused, so it is not a development target "
                "(fail-closed)"
            )
        if not _clean(getattr(specification, "request", ""), 300):
            return spec_id, "the specification carries no request (incomplete)"
        if not _strings(getattr(specification, "operations", ()) or ()):
            return spec_id, (
                "the specification carries no operations, so the design is "
                "incomplete (fail-closed)"
            )
        if not _clean(getattr(specification, "mechanism", ""), 60):
            return spec_id, (
                "the specification carries no existing development mechanism, so "
                "the design is incomplete (fail-closed)"
            )
        return spec_id, ""

    # -- entry point -------------------------------------------------------

    def run(
        self,
        specification: Any,
        *,
        proposal: Any | None = None,
        authorization: Any = None,
        code_changes: Any = (),
        test_files: Any = (),
        target_components: Any = (),
        evidence_ids: Any = (),
    ) -> SpecificationDevelopmentResult:
        """Run ONE bounded specification-driven development invocation.

        Never raises, never approves or promotes, and never touches the live
        repository itself: the injected ``execute`` owns that boundary.
        """
        spec_id, refusal = self._refusal(specification)
        request = _clean(getattr(specification, "request", ""), 300)
        capability = _clean(getattr(specification, "capability", ""), 200)
        if refusal:
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.REFUSED,
                spec_id=spec_id,
                capability=capability,
                request=request,
                reasons=(refusal,),
            )

        need = development_need_from_specification(
            specification,
            code_changes=code_changes,
            test_files=test_files,
            target_components=target_components,
            evidence_ids=evidence_ids,
        )
        evidence: list[str] = []
        gap_reason = _clean(getattr(specification, "gap_reason", ""), 300)
        evidence.append(f"specification {spec_id}: {request or capability}")
        if gap_reason:
            evidence.append(f"gap: {gap_reason}")

        # 1. Prepare through the EXISTING governed cycle (STOP at approval).
        if proposal is None:
            if self._cycle_runner is None:
                return SpecificationDevelopmentResult(
                    stage=SelfDevelopmentStage.FAILED,
                    spec_id=spec_id,
                    capability=capability,
                    request=request,
                    reasons=("no development cycle is wired (fail-closed)",),
                    evidence=tuple(evidence),
                    need=need,
                )
            try:
                cycle = self._cycle_runner(need)
            except Exception as exc:  # fail-closed
                return SpecificationDevelopmentResult(
                    stage=SelfDevelopmentStage.FAILED,
                    spec_id=spec_id,
                    capability=capability,
                    request=request,
                    reasons=(
                        f"development cycle failed closed ({type(exc).__name__})",
                    ),
                    evidence=tuple(evidence),
                    need=need,
                )
            if not bool(getattr(cycle, "ok", False)):
                reasons = tuple(
                    f"{stage}: {message}"
                    for stage, message in (getattr(cycle, "failures", ()) or ())
                ) or ("the development cycle did not prepare a proposal",)
                return SpecificationDevelopmentResult(
                    stage=SelfDevelopmentStage.FAILED,
                    spec_id=spec_id,
                    capability=capability,
                    request=request,
                    reasons=tuple(reasons)[:_MAX_ITEMS],
                    evidence=tuple(evidence),
                    need=need,
                )
            proposal_id = _clean(getattr(cycle, "proposal_id", ""), 128)
            approval_request_id = _clean(
                getattr(cycle, "approval_request_id", ""), 128
            )
            proposal_status = _clean(getattr(cycle, "proposal_status", ""), 40)
            proposal = getattr(cycle, "proposal", None)
            evidence.append(
                f"prepared proposal {proposal_id} (status {proposal_status}): the "
                "human approval boundary is the next step"
            )
        else:
            proposal_id = _clean(getattr(proposal, "proposal_id", ""), 128)
            approval_request_id = ""
            proposal_status = _clean(
                getattr(getattr(proposal, "status", None), "name", ""), 40
            )

        # 2. The authorization boundary: nothing runs without it.
        authorized = _authorization_valid(proposal, authorization)
        if authorization is not None and not authorized:
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.REFUSED,
                spec_id=spec_id,
                capability=capability,
                request=request,
                proposal_id=proposal_id,
                proposal_status=proposal_status,
                reasons=(
                    "the supplied authorization is not valid for this proposal, so "
                    "nothing was executed (fail-closed)",
                ),
                evidence=tuple(evidence),
                need=need,
            )
        if not authorized:
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.AWAITING_APPROVAL,
                spec_id=spec_id,
                capability=capability,
                request=request,
                proposal_id=proposal_id,
                approval_request_id=approval_request_id,
                proposal_status=proposal_status,
                reasons=(
                    "awaiting approval: the development workflow stops at the "
                    "existing human approval boundary",
                ),
                evidence=tuple(evidence),
                need=need,
            )

        # 3. Implementation inside the EXISTING governed sandbox boundary.
        if self._execute is None:
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.FAILED,
                spec_id=spec_id,
                capability=capability,
                request=request,
                authorized=True,
                proposal_id=proposal_id,
                approval_request_id=approval_request_id,
                proposal_status=proposal_status,
                reasons=("no governed executor is wired (fail-closed)",),
                evidence=tuple(evidence),
                need=need,
            )
        try:
            run = self._execute(proposal)
        except Exception as exc:  # fail-closed: nothing is promoted
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.FAILED,
                spec_id=spec_id,
                capability=capability,
                request=request,
                authorized=True,
                proposal_id=proposal_id,
                approval_request_id=approval_request_id,
                proposal_status=proposal_status,
                reasons=(f"authorized execution failed closed ({type(exc).__name__})",),
                evidence=tuple(evidence),
                need=need,
            )

        execution_status = _clean(
            getattr(getattr(run, "status", None), "name", "")
            or getattr(run, "status", ""),
            40,
        )
        plan = getattr(run, "plan", None)
        plan_id = _clean(getattr(plan, "plan_id", ""), 128)
        changed = _changed_files(run, _pairs(code_changes) + _pairs(test_files))
        evidence.append(
            "changed files: " + (", ".join(changed) if changed else "none recorded")
        )

        # 4. Verification through the EXISTING read-only verifier.
        verification_status, verification_evidence = _verification_of(run)
        if verification_evidence:
            evidence.append(f"verification: {verification_evidence}")

        # 5. Promotion readiness through the EXISTING gate; never a promotion.
        recommendation = ""
        if self._gate is not None:
            try:
                assessment = self._gate.assess(run, proposal_id=proposal_id)
                recommendation = _value(
                    getattr(assessment, "recommendation", "")
                )
            except Exception:  # fail-soft: an unreadable gate is not promotable
                recommendation = "not_promotable"

        promotable = verification_status == "verified" and recommendation != (
            "not_promotable"
        )
        if not promotable:
            reasons = []
            if verification_status != "verified":
                reasons.append(
                    f"the run was not verified (verification: "
                    f"{verification_status or 'unavailable'}), so it is not "
                    "promotable"
                )
            else:
                reasons.append(
                    "the existing promotion gate did not recommend promotion, so no "
                    "promotion review was opened"
                )
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.NOT_PROMOTABLE,
                spec_id=spec_id,
                capability=capability,
                request=request,
                authorized=True,
                proposal_id=proposal_id,
                approval_request_id=approval_request_id,
                proposal_status=proposal_status,
                plan_id=plan_id,
                execution_status=execution_status,
                verification_status=verification_status,
                changed_files=changed,
                reasons=tuple(reasons)[:_MAX_ITEMS],
                evidence=tuple(evidence),
                need=need,
            )

        if self._promotion_preparer is None:
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.VERIFICATION,
                spec_id=spec_id,
                capability=capability,
                request=request,
                authorized=True,
                proposal_id=proposal_id,
                approval_request_id=approval_request_id,
                proposal_status=proposal_status,
                plan_id=plan_id,
                execution_status=execution_status,
                verification_status=verification_status,
                changed_files=changed,
                reasons=(
                    "verified inside the sandbox; promotion is a separate explicit "
                    "OWNER step",
                ),
                evidence=tuple(evidence),
                need=need,
            )

        try:
            promotion_request_id = _clean(
                self._promotion_preparer(proposal, run), 128
            )
        except Exception:  # fail-soft: no review, no promotion claim
            promotion_request_id = ""
        if not promotion_request_id:
            return SpecificationDevelopmentResult(
                stage=SelfDevelopmentStage.VERIFICATION,
                spec_id=spec_id,
                capability=capability,
                request=request,
                authorized=True,
                proposal_id=proposal_id,
                approval_request_id=approval_request_id,
                proposal_status=proposal_status,
                plan_id=plan_id,
                execution_status=execution_status,
                verification_status=verification_status,
                changed_files=changed,
                reasons=(
                    "verified inside the sandbox, but no promotion review was opened",
                ),
                evidence=tuple(evidence),
                need=need,
            )

        evidence.append(
            f"promotion review {promotion_request_id} opened: promotion remains an "
            "explicit OWNER step"
        )
        return SpecificationDevelopmentResult(
            stage=SelfDevelopmentStage.PROMOTION_REVIEW,
            spec_id=spec_id,
            capability=capability,
            request=request,
            authorized=True,
            proposal_id=proposal_id,
            approval_request_id=approval_request_id,
            proposal_status=proposal_status,
            plan_id=plan_id,
            execution_status=execution_status,
            verification_status=verification_status,
            promotion_request_id=promotion_request_id,
            changed_files=changed,
            reasons=(
                "sandbox implementation verified; the change is ready for the "
                "existing OWNER promotion decision",
            ),
            evidence=tuple(evidence),
            need=need,
        )


def specification_development_bridge(
    *,
    cycle_runner: Callable[[Any], Any] | None = None,
    execute: Callable[[Any], Any] | None = None,
    gate: Any | None = None,
    promotion_preparer: Callable[[Any, Any], Any] | None = None,
) -> SpecificationDevelopmentBridge:
    """Convenience constructor for :class:`SpecificationDevelopmentBridge`."""
    return SpecificationDevelopmentBridge(
        cycle_runner=cycle_runner,
        execute=execute,
        gate=gate,
        promotion_preparer=promotion_preparer,
    )


__all__ = [
    "SELF_DEVELOPMENT_RULE",
    "SelfDevelopmentStage",
    "SpecificationDevelopmentBridge",
    "SpecificationDevelopmentResult",
    "development_need_from_specification",
    "specification_development_bridge",
]
