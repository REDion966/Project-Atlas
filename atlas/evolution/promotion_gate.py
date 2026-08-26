"""Atlas Evolution — Promotion Gate Foundation — Stage E.

A controlled promotion-review layer between successful sandbox
development and the real repository.

What this IS:
* A deterministic risk assessor for ``DevelopmentRunResult`` evidence.
* A bounded review-request lifecycle: PENDING_REVIEW → APPROVED /
  REJECTED. APPROVED means exactly one thing: *ready for human/operator
  promotion*. It never means "the repository was modified".
* An audit surface reusing ``EvolutionMemory.store_record()`` with
  ``event_type="promotion_review"`` — no new storage.

What this is NOT:
* Not an executor. There is no promotion execution anywhere in this
  module; the real repository is never touched.
* Not a second approval framework: it consumes already-approved
  proposals' development outcomes and defers final promotion to the
  existing human/operator governance boundary.
* Not automatic: reviews are opened only from explicit kernel bridging,
  and nothing here advances on its own.

Pure logic. Deterministic. Fail-soft. No AI. No filesystem mutation.
No git operations. No infrastructure imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.models import EvolutionRecord


# ---------------------------------------------------------------------------
# Boundedness constants
# ---------------------------------------------------------------------------

MAX_CHANGED_FILES_LISTED: int = 50
MAX_AFFECTED_MODULES_LISTED: int = 50

# Module-name prefixes considered architecture-sensitive: changes here
# escalate risk regardless of size, because they touch composition roots,
# storage schema, or the runtime pipeline itself.
ARCHITECTURE_SENSITIVE_PREFIXES: tuple[str, ...] = (
    "atlas.kernel.",
    "atlas.storage.",
    "atlas.runtime.",
    "atlas.evolution.governance",
)

SMALL_CHANGE_FILE_COUNT: int = 3

# Bounded change-manifest limits (Stage H review evidence).
MAX_MANIFEST_FILES: int = 20
MAX_EXCERPT_CHARS: int = 500
MAX_MANIFEST_TOTAL_CHARS: int = 4000


class PromotionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PromotionStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROMOTED = "promoted"  # reserved: set ONLY by out-of-scope operator tooling


class PromotionRecommendation(str, Enum):
    READY_FOR_PROMOTION = "ready_for_promotion"
    NEEDS_REVIEW = "needs_review"
    NOT_PROMOTABLE = "not_promotable"


def _clamp01(value: Any) -> float:
    """Coerce an arbitrary value into a bounded [0.0, 1.0] float.

    Fail-soft: any malformed input becomes ``0.0``.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, number))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class PromotionAssessment:
    """Deterministic promotion-readiness analysis of one development run."""

    assessment_id: str
    proposal_id: str
    development_record_id: str
    changed_files: list[str] = field(default_factory=list)
    affected_modules: list[str] = field(default_factory=list)
    verification_status: str = ""
    test_summary: str = ""
    risk_level: PromotionRisk = PromotionRisk.LOW
    recommendation: PromotionRecommendation = (
        PromotionRecommendation.NEEDS_REVIEW
    )
    change_manifest: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection."""
        return {
            "assessment_id": self.assessment_id,
            "proposal_id": self.proposal_id,
            "development_record_id": self.development_record_id,
            "changed_files": list(self.changed_files)[
                :MAX_CHANGED_FILES_LISTED
            ],
            "affected_modules": list(self.affected_modules)[
                :MAX_AFFECTED_MODULES_LISTED
            ],
            "verification_status": self.verification_status,
            "test_summary": self.test_summary,
            "risk_level": self.risk_level.value,
            "recommendation": self.recommendation.value,
            "change_manifest": dict(self.change_manifest),
            "metadata": dict(self.metadata),
        }


def build_change_manifest(
    changed_contents: Any,
    max_files: int = MAX_MANIFEST_FILES,
    max_excerpt_chars: int = MAX_EXCERPT_CHARS,
    max_total_chars: int = MAX_MANIFEST_TOTAL_CHARS,
) -> dict[str, Any]:
    """Bounded, deterministic change manifest for human review.

    Accepts the sandbox workload's ``code_changes``-shaped entries
    (``{"path": ..., "content": ...}`` dicts). Purely lexical: no
    filesystem, subprocess, or git access. Fail-soft — malformed
    entries are skipped. Output is JSON-safe:

    ``{"files": [{"path", "size", "excerpt"}],
      "total_files": int, "truncated": bool}``
    """
    files: list[dict[str, Any]] = []
    total_files = 0
    truncated = False

    try:
        entries = list(changed_contents or [])
    except TypeError:
        return {"files": [], "total_files": 0, "truncated": False}

    valid: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            continue
        content = entry.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        valid.append((path, content))

    total_files = len(valid)
    ordered = sorted(valid, key=lambda pair: pair[0])
    budget = max(0, max_total_chars)

    for path, content in ordered:
        if len(files) >= max_files or budget <= 0:
            truncated = True
            break
        excerpt = content[:max(0, max_excerpt_chars)]
        if len(excerpt) < len(content):
            truncated = True
        if len(excerpt) > budget:
            excerpt = excerpt[:budget]
            truncated = True
        budget -= len(excerpt)
        files.append({"path": path, "size": len(content), "excerpt": excerpt})

    return {
        "files": files,
        "total_files": total_files,
        "truncated": truncated,
    }


@dataclass
class PromotionRequest:
    """A review request tracking one assessment through its lifecycle."""

    request_id: str
    assessment_id: str
    proposal_id: str = ""
    status: PromotionStatus = PromotionStatus.PENDING_REVIEW
    created_at: datetime = field(default_factory=datetime.now)
    decided_at: datetime | None = None
    decision_comment: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "assessment_id": self.assessment_id,
            "proposal_id": self.proposal_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "decided_at": (
                self.decided_at.isoformat() if self.decided_at else ""
            ),
            "decision_comment": self.decision_comment,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


class PromotionGate:
    """
    Controlled promotion-review lifecycle over development outcomes.

    Constructor-injected ``evolution_memory`` (optional) is used ONLY to
    persist ``event_type="promotion_review"`` audit records via the
    existing ``store_record()`` surface — best-effort, never breaking.
    All lifecycle transitions are explicit operator-facing calls;
    nothing advances automatically.
    """

    def __init__(self, evolution_memory: Any = None) -> None:
        self._evolution_memory = evolution_memory
        self._record_counter = 0
        self._assessment_counter = 0
        self._request_counter = 0

    # -- assessment ------------------------------------------------------

    def assess(
        self,
        run_result: Any,
        proposal_id: str = "",
        change_manifest: dict[str, Any] | None = None,
    ) -> PromotionAssessment:
        """
        Deterministically assess a ``DevelopmentRunResult``.

        A failed / rolled-back / unverified run yields HIGH risk and
        NOT_PROMOTABLE; only verified SUCCESS runs can be recommended for
        promotion review. Fail-soft on any missing evidence.
        """
        last_outcome = run_result.outcomes[-1] if run_result.outcomes else None
        changed_files = list(getattr(last_outcome, "changed_files", []) or [])
        verification_passed = bool(
            getattr(last_outcome, "verification_passed", False)
        )
        rollback_occurred = bool(
            getattr(last_outcome, "rollback_occurred", False)
        )
        test_summary = str(getattr(last_outcome, "test_outcome", ""))
        affected_modules = sorted(
            {
                _path_to_module(path)
                for path in changed_files
            }
        )[:MAX_AFFECTED_MODULES_LISTED]
        run_success = (
            run_result.status is DevelopmentOutcomeStatus.SUCCESS
        )

        risk = _risk_level(
            verification_passed=verification_passed,
            rollback_occurred=rollback_occurred,
            changed_files=changed_files,
            affected_modules=affected_modules,
            run_success=run_success,
        )
        if not run_success or not verification_passed or rollback_occurred:
            recommendation = PromotionRecommendation.NOT_PROMOTABLE
        elif risk is PromotionRisk.LOW:
            recommendation = PromotionRecommendation.READY_FOR_PROMOTION
        else:
            recommendation = PromotionRecommendation.NEEDS_REVIEW

        proposal_id = proposal_id or (
            run_result.plan.proposal_id if run_result.plan else ""
        )

        return PromotionAssessment(
            assessment_id=self._next_assessment_id(),
            proposal_id=proposal_id,
            development_record_id="",
            changed_files=changed_files[:MAX_CHANGED_FILES_LISTED],
            affected_modules=affected_modules,
            verification_status=(
                "passed"
                if verification_passed
                else ("rolled_back" if rollback_occurred else "not_verified")
            ),
            test_summary=test_summary[:120],
            risk_level=risk,
            recommendation=recommendation,
            change_manifest=dict(change_manifest or {}),
            metadata={
                "terminal_status": run_result.status.name,
                "iterations_used": run_result.iterations_used,
                "run_message": run_result.message[:150],
            },
        )

    def _next_assessment_id(self) -> str:
        self._assessment_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PASSESS-{timestamp}-{self._assessment_counter:04d}"

    def _next_record_id(self) -> str:
        self._record_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PGATE-{timestamp}-{self._record_counter:04d}"

    # -- lifecycle ---------------------------------------------------------

    def request_review(
        self,
        assessment: PromotionAssessment,
        development_record_id: str = "",
    ) -> PromotionRequest:
        """
        Open a PENDING_REVIEW request for an assessment.

        Persists a ``promotion_review`` audit record best-effort; the
        request is returned regardless of storage availability.
        """
        request = PromotionRequest(
            request_id=self._next_request_id(),
            assessment_id=assessment.assessment_id,
            proposal_id=assessment.proposal_id,
            metadata={
                "risk_level": assessment.risk_level.value,
                "recommendation": assessment.recommendation.value,
                "changed_file_count": len(assessment.changed_files),
                "development_record_id": (
                    development_record_id
                    or assessment.development_record_id
                ),
            },
        )
        self._persist(request, assessment, development_record_id)
        return request

    def approve(
        self,
        request: PromotionRequest,
        comment: str = "",
    ) -> PromotionRequest:
        """
        Approve a pending review: the assessed change becomes *ready for
        human/operator promotion*. This NEVER modifies the repository —
        ``PROMOTED`` is reserved for out-of-scope operator tooling.
        """
        self._decide(request, PromotionStatus.APPROVED, comment)
        return request

    def reject(
        self,
        request: PromotionRequest,
        reason: str = "",
    ) -> PromotionRequest:
        """Reject a pending review with an optional reason."""
        self._decide(request, PromotionStatus.REJECTED, reason)
        return request

    def pending_reviews(self) -> list[dict[str, Any]]:
        """Stage H: read-only prioritized view of PENDING_REVIEW promotion
        requests (highest decision-quality score first).

        Reads existing ``promotion_review`` records through the injected
        ``EvolutionMemory`` and joins the associated proposal's decision
        quality when available. Purely read-only — no repository mutation,
        no approve/promote/execute capability. Fail-soft on malformed
        records.
        """
        if self._evolution_memory is None:
            return []

        # Proposal lookup for decision-quality joins.
        proposals: dict[str, Any] = {}
        try:
            for proposal in (self._evolution_memory.get_all_proposals() or []):
                pid = getattr(proposal, "proposal_id", "")
                if pid:
                    proposals[pid] = proposal
        except Exception:
            proposals = {}

        try:
            records = self._evolution_memory.get_records_by_type(
                "promotion_review"
            )
        except Exception:
            return []

        pending: list[tuple[dict[str, Any], bool]] = []
        for record in records:
            try:
                metadata = dict(getattr(record, "metadata", {}) or {})
                status = metadata.get("status", "")
                if status != PromotionStatus.PENDING_REVIEW.value:
                    continue

                request_id = getattr(record, "record_id", "") or metadata.get(
                    "request_id", ""
                )
                related_ids = list(getattr(record, "related_ids", []) or [])
                proposal_id = metadata.get("proposal_id", "")
                if not proposal_id and related_ids:
                    proposal_id = str(related_ids[0])

                # Assessment may be nested under ``assessment`` (the write
                # path of ``request_review``) or flat (bridge/seed records).
                assessment = metadata.get("assessment", {})
                if not isinstance(assessment, dict):
                    assessment = {}

                risk_level = metadata.get("risk_level") or assessment.get(
                    "risk_level", ""
                )
                recommendation = metadata.get("recommendation") or (
                    assessment.get("recommendation", "")
                )

                manifest = metadata.get("change_manifest")
                if manifest is None:
                    manifest = assessment.get("change_manifest", {})
                if not isinstance(manifest, dict):
                    manifest = {}
                manifest_files = manifest.get("files", [])
                if not isinstance(manifest_files, list):
                    manifest_files = []
                manifest_file_count = len(manifest_files)
                evidence_complete = manifest_file_count > 0

                final_priority_score = 0.0
                has_priority_score = False
                proposal = proposals.get(proposal_id)
                if proposal is not None:
                    prop_metadata = dict(getattr(proposal, "metadata", {}) or {})
                    dq = prop_metadata.get("decision_quality", {})
                    if isinstance(dq, dict) and "final_priority_score" in dq:
                        final_priority_score = _clamp01(
                            dq.get("final_priority_score")
                        )
                        has_priority_score = True

                pending.append(
                    (
                        {
                            "request_id": request_id,
                            "proposal_id": proposal_id,
                            "status": status,
                            "risk_level": risk_level,
                            "recommendation": recommendation,
                            "final_priority_score": final_priority_score,
                            "evidence_complete": evidence_complete,
                            "manifest_file_count": manifest_file_count,
                        },
                        has_priority_score,
                    )
                )
            except Exception:
                # Fail-soft: skip malformed records; never break the view.
                continue

        # Deterministic ordering:
        #   primary — scored requests first (missing scores last)
        #   then highest final_priority_score first
        #   secondary — stable tiebreak by request_id
        pending.sort(
            key=lambda entry: (
                0 if entry[1] else 1,
                -entry[0]["final_priority_score"],
                entry[0]["request_id"],
            )
        )
        return [item for item, _ in pending]

    # -- internals -----------------------------------------------------------

    def _next_request_id(self) -> str:
        self._request_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PROM-{timestamp}-{self._request_counter:04d}"

    def _decide(
        self,
        request: PromotionRequest,
        decision: PromotionStatus,
        comment: str = "",
    ) -> None:
        if request.status is not PromotionStatus.PENDING_REVIEW:
            raise ValueError(
                f"Cannot {decision.value} promotion request "
                f"'{request.request_id}' with status "
                f"'{request.status.value}'."
            )
        request.status = decision
        request.decided_at = datetime.now()
        request.decision_comment = comment
        self._persist(request)

    def _persist(
        self,
        request: PromotionRequest,
        assessment: PromotionAssessment | None = None,
        development_record_id: str = "",
    ) -> None:
        """Best-effort audit record via the existing EvolutionMemory surface."""
        if self._evolution_memory is None:
            return
        try:
            related: list[str] = []
            if request.proposal_id:
                related.append(request.proposal_id)
            if request.assessment_id:
                related.append(request.assessment_id)
            if development_record_id:
                related.append(development_record_id)

            metadata: dict[str, Any] = {
                "status": request.status.value,
                "risk_level": request.metadata.get("risk_level", ""),
                "recommendation": request.metadata.get("recommendation", ""),
            }
            if assessment is not None:
                metadata["assessment"] = assessment.to_dict()

            self._evolution_memory.store_record(
                EvolutionRecord(
                    record_id=self._next_record_id(),
                    event_type="promotion_review",
                    description=(
                        f"Promotion review '{request.request_id}' for "
                        f"proposal '{request.proposal_id}': "
                        f"{request.status.value}."
                    ),
                    related_ids=related,
                    metadata=metadata,
                )
            )
        except Exception:
            # Audit persistence must never break the review lifecycle.
            pass


def _path_to_module(path: str) -> str:
    """Full dotted-ish module path from a relative file path.

    Preserves package context (``atlas/kernel/atlas.py`` →
    ``atlas.kernel.atlas``) so architecture-sensitive prefix matching
    works. Purely lexical — no filesystem access.
    """
    normalized = str(path).replace("\\", "/")
    if normalized.endswith(".py"):
        normalized = normalized[: -len(".py")]
    return normalized.replace("/", ".")


def _risk_level(
    verification_passed: bool,
    rollback_occurred: bool,
    changed_files: list[str],
    affected_modules: list[str],
    run_success: bool,
) -> PromotionRisk:
    """
    Simple, deterministic risk classification.

    HIGH   — failed validation, a rollback occurred, the run failed outright,
             or architecture-sensitive modules were touched.
    MEDIUM — more than a small number of changed files/modules affected.
    LOW    — tests passed and the change is small.
    """
    if not run_success or not verification_passed or rollback_occurred:
        return PromotionRisk.HIGH
    if any(
        str(module).startswith(ARCHITECTURE_SENSITIVE_PREFIXES)
        for module in affected_modules
    ):
        return PromotionRisk.HIGH
    if len(changed_files) > SMALL_CHANGE_FILE_COUNT or len(affected_modules) > 2:
        return PromotionRisk.MEDIUM
    return PromotionRisk.LOW
