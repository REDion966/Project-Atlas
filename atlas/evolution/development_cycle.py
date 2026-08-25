"""Atlas Post-Core F9 - Governed Autonomous Development (preparation only).

A thin, bounded, deterministic, single-shot composition controller that turns
a development need into a DRAFT ``EvolutionProposal`` and submits it to the
EXISTING ``ApprovalManager``. It then STOPS at the human approval boundary.

Pipeline position (all downstream stages already exist and are reused):

    development need / F6 candidate signal
        -> evidence sufficiency check
        -> (insufficient?) ONE bounded F8 acquisition invocation
        -> injectable change supplier (deterministic default)
        -> bounded DRAFT EvolutionProposal
        -> existing ApprovalManager  ->  PENDING_APPROVAL
        -> STOP

ARCHITECTURAL BOUNDARY:
  * never approves, authorizes, schedules, executes, applies, or promotes;
  * never touches ``SelfDevelopmentLoop`` / gateway / dispatcher directly —
    everything after approval remains owned by the existing infrastructure
    (request_factory -> dispatcher -> gateway -> SDL);
  * never mutates the real repository; the proposal payload is DATA consumed
    later inside a disposable ``CodeSandbox`` by the existing E2/E5 path;
  * no second scheduler / EventBus / memory / governance / research system;
  * model-independent by default: the deterministic supplier needs no AI.
    Optional model assistance may ONLY enter through an injected
    ``ChangeSupplier`` backed by existing provider seams; its output is
    marked as unverified draft content and is still subject to human
    approval plus sandbox verification. The module itself never imports
    ``atlas.ai``.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, runtime_checkable

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)


def utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


def _stable_id(seed: str) -> str:
    """Deterministic short identifier for a seed string."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _bounded_text(exc: Exception, limit: int = 200) -> str:
    """Return a bounded, secret-free error message for a failure."""
    text = str(exc).strip() or type(exc).__name__
    return text[:limit]


# ---------------------------------------------------------------------------
# Policy (pure configuration; conservative bounds consistent with F7/F8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DevelopmentCyclePolicy:
    """Deterministic bounds for one development-cycle preparation.

    Attributes:
        max_code_changes: Upper bound on supplied file changes (default 5).
        max_test_files: Upper bound on supplied test files (default 3).
        max_path_chars: Upper bound per path string (default 256).
        max_content_chars: Upper bound per file content (default 32_000,
            sized for real single-file production modules).
        max_title_chars: Upper bound for the proposal title (default 200).
        max_summary_chars: Upper bound for the summary (default 2_000).
        max_text_chars: Upper bound per free-text field (default 4_000).
        max_evidence_ids: Upper bound on recorded evidence ids (default 20).
        max_research_sources: Upper bound on researched sources (default 5).
    """

    max_code_changes: int = 5
    max_test_files: int = 3
    max_path_chars: int = 256
    max_content_chars: int = 32_000
    max_title_chars: int = 200
    max_summary_chars: int = 2_000
    max_text_chars: int = 4_000
    max_evidence_ids: int = 20
    max_research_sources: int = 5

    def __post_init__(self) -> None:
        for name in (
            "max_code_changes",
            "max_test_files",
            "max_path_chars",
            "max_content_chars",
            "max_title_chars",
            "max_summary_chars",
            "max_text_chars",
            "max_evidence_ids",
            "max_research_sources",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")


# ---------------------------------------------------------------------------
# Development need (input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DevelopmentNeed:
    """Bounded input describing one development need.

    Attributes:
        title: Short need title (required).
        summary: What the need is about.
        rationale: Why the need exists (evidence-backed when available).
        expected_benefit: Expected improvement if addressed.
        target_components: Bounded list of affected component paths.
        candidate_id: Originating F6 ``AdaptationProposalCandidate`` id.
        evidence_change_ids: F1 environment-change evidence ids.
        evidence_knowledge_ids: F2 freshness/knowledge evidence ids.
        research_question: Question used for the optional F8 invocation.
        sources: Explicit sources for the optional F8 invocation.
        metadata: Extra context; the deterministic supplier reads
            ``metadata["code_changes"]`` / ``metadata["test_files"]`` using
            the same convention as the E5 ``metadata_change_supplier``.
    """

    title: str
    summary: str = ""
    rationale: str = ""
    expected_benefit: str = ""
    target_components: tuple[str, ...] = ()
    candidate_id: str = ""
    evidence_change_ids: tuple[str, ...] = ()
    evidence_knowledge_ids: tuple[str, ...] = ()
    research_question: str = ""
    sources: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_direct_evidence(self) -> bool:
        """True when direct evidence ids accompany the need."""
        return bool(self.evidence_change_ids or self.evidence_knowledge_ids)


# ---------------------------------------------------------------------------
# Change supplier (the F9 authoring gap; deterministic by default)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SuppliedChanges:
    """Bounded change payload produced by a supplier (draft content only).

    Attributes:
        code_changes: ``(path, content)`` pairs for non-test source files.
        test_files: ``(path, content)`` pairs for test files.
        origin: Provenance marker, e.g. ``deterministic`` or
            ``model-assisted-draft`` (never treated as verified knowledge).
        confidence: Supplier self-assessed confidence in [0.0, 1.0].
        notes: Bounded free-text notes.
    """

    code_changes: tuple[tuple[str, str], ...] = ()
    test_files: tuple[tuple[str, str], ...] = ()
    origin: str = "deterministic"
    confidence: float = 0.0
    notes: str = ""


@runtime_checkable
class ChangeSupplier(Protocol):
    """Protocol for bounded change authoring.

    Implementations must be deterministic-or-injectable, fail-closed, and
    must NEVER touch the repository, approvals, or execution. A supplier
    backed by an existing AI-provider seam remains optional and injectable;
    it should mark its output with an explicit unverified-draft origin.
    """

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        """Return draft changes for ``need`` or ``None`` when unable."""
        ...


class DeterministicChangeSupplier:
    """Default fail-closed supplier over the existing E5 metadata convention.

    Reads ``need.metadata["code_changes"]`` (list of
    ``{"path": ..., "content": ...}`` dicts) and ``need.metadata["test_files"]``
    (``{path: content}`` mapping) — exactly the shape the E5
    ``metadata_change_supplier`` consumes later inside the sandbox. Returns
    ``None`` when nothing was supplied; raises ``ValueError`` on malformed
    payloads so the controller can fail closed.
    """

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        raw_changes = need.metadata.get("code_changes", [])
        raw_tests = need.metadata.get("test_files", {})
        if not isinstance(raw_changes, list) or not raw_changes:
            return None

        changes: list[tuple[str, str]] = []
        for item in raw_changes:
            if (
                not isinstance(item, dict)
                or "path" not in item
                or "content" not in item
            ):
                raise ValueError("malformed code_changes entry")
            changes.append((str(item["path"]), str(item["content"])))

        tests: list[tuple[str, str]] = []
        if isinstance(raw_tests, dict):
            tests = [(str(p), str(c)) for p, c in raw_tests.items()]
        elif isinstance(raw_tests, list):
            for item in raw_tests:
                if (
                    not isinstance(item, dict)
                    or "path" not in item
                    or "content" not in item
                ):
                    raise ValueError("malformed test_files entry")
                tests.append((str(item["path"]), str(item["content"])))
        else:
            raise ValueError("malformed test_files payload")

        return SuppliedChanges(
            code_changes=tuple(changes),
            test_files=tuple(tests),
            origin="deterministic",
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DevelopmentCycleResult:
    """Bounded, deterministic result of one preparation invocation.

    Attributes:
        cycle_id: Monotonic identifier for this run.
        decision: ``prepared`` | ``failed``.
        status: ``ok`` | ``failed``.
        proposal_id: DRAFT proposal id (empty on failure).
        approval_request_id: Approval request id (empty on failure).
        proposal_status: Proposal status after submission (``PENDING_APPROVAL``).
        researched: Whether the optional F8 invocation ran.
        research_summary: Bounded acquisition summary (when research ran).
        failures: Bounded (stage, message) fail-closed records.
        ran_at: When this run happened.
        elapsed_seconds: Wall-clock duration.
    """

    cycle_id: str
    decision: str = "failed"
    status: str = "failed"
    proposal_id: str = ""
    approval_request_id: str = ""
    proposal_status: str = ""
    researched: bool = False
    research_summary: dict[str, Any] = field(default_factory=dict)
    failures: tuple[tuple[str, str], ...] = ()
    ran_at: datetime = field(default_factory=utc_now)
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.decision == "prepared"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "decision": self.decision,
            "status": self.status,
            "proposal_id": self.proposal_id,
            "approval_request_id": self.approval_request_id,
            "proposal_status": self.proposal_status,
            "researched": self.researched,
            "research_summary": self.research_summary,
            "failures": [list(f) for f in self.failures],
            "ran_at": self.ran_at.isoformat(),
            "elapsed_seconds": round(self.elapsed_seconds, 4),
        }


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class DevelopmentCycleController:
    """Single-shot, bounded preparation controller stopping at approval.

    Args:
        approval_manager: EXISTING ``ApprovalManager`` (required). The
            controller submits the DRAFT proposal through it and stops.
        change_supplier: Injectable :class:`ChangeSupplier`. Defaults to the
            deterministic supplier; a model-assisted supplier may be injected
            but is never required and never imported here.
        researcher: Optional duck-typed callable matching the F8
            ``InformationAcquisitionService.acquire`` keyword surface. The
            kernel injects its existing acquisition service; the controller
            never imports or duplicates the research pipeline.
        policy: Deterministic bounds (defaults).
        now: Optional clock callable (UTC) — injectable for tests.
        proposal_store: Optional duck-typed durable store exposing
            ``store_proposal(proposal)`` (the EXISTING EvolutionMemory /
            EvolutionSQLiteStorage surface). When wired, every prepared
            proposal is persisted so operators can inspect/approve it in a
            later process. Persistence failures fail closed (an explicit
            partial-state failure is returned after submission).
        approval_request_store: Optional duck-typed durable store exposing
            ``store_approval_request(request)``; wire alongside
            ``proposal_store`` so cross-process ``approve_proposal_by_id``
            lookups can find the pending request.
    """

    def __init__(
        self,
        *,
        approval_manager: ApprovalManager,
        change_supplier: ChangeSupplier | None = None,
        researcher: Callable[..., Any] | None = None,
        policy: DevelopmentCyclePolicy | None = None,
        now: Callable[[], datetime] | None = None,
        proposal_store: Any | None = None,
        approval_request_store: Any | None = None,
    ) -> None:
        if approval_manager is None:
            raise ValueError("approval_manager is required (fail-closed)")
        self._approval_manager = approval_manager
        self._change_supplier: ChangeSupplier = (
            change_supplier
            if change_supplier is not None
            else DeterministicChangeSupplier()
        )
        self._researcher = researcher
        self._policy = policy or DevelopmentCyclePolicy()
        self._now = now or utc_now
        self._counter = 0
        self._proposal_store = proposal_store
        self._approval_request_store = approval_request_store

    @property
    def policy(self) -> DevelopmentCyclePolicy:
        """The applied bounds (read-only)."""
        return self._policy

    # -- public single-shot entry -------------------------------------------

    def run_development_cycle(
        self,
        need: DevelopmentNeed,
        *,
        force_research: bool = False,
    ) -> DevelopmentCycleResult:
        """Run ONE bounded preparation invocation and STOP at approval.

        Steps: validate need -> evidence-sufficiency gate -> optional single
        F8 research invocation -> supplier -> bounded DRAFT proposal ->
        ``ApprovalManager.create_approval_request``. Never approves,
        authorizes, executes, or promotes anything.
        """
        started = time.monotonic()
        ran_at = self._now()
        self._counter += 1
        cycle_id = f"DEVC-{self._counter:06d}"

        def _failed(
            failures: list[tuple[str, str]],
        ) -> DevelopmentCycleResult:
            return DevelopmentCycleResult(
                cycle_id=cycle_id,
                decision="failed",
                status="failed",
                failures=tuple(failures)[-10:],
                ran_at=ran_at,
                elapsed_seconds=time.monotonic() - started,
            )

        # 1. Validate the need (bounded, fail-closed).
        try:
            need = self._validate_need(need)
        except Exception as exc:
            return _failed([("need", _bounded_text(exc))])

        # 2. Evidence-sufficiency gate.
        researched = False
        research_summary: dict[str, Any] = {}
        if force_research or not need.has_direct_evidence:
            outcome = self._run_research(need)
            if outcome is None:
                return _failed([
                    ("evidence", "insufficient evidence and no researcher wired"),
                ])
            error, summary = outcome
            if error is not None:
                return _failed([("research", error)])
            researched = True
            research_summary = summary

        # 3. Author draft changes via the injected supplier (once).
        try:
            supplied = self._change_supplier.supply_changes(need)
        except Exception as exc:
            return _failed([("supplier", _bounded_text(exc))])
        if supplied is None:
            return _failed([("supplier", "supplier produced no changes")])

        # 4. Enforce bounds on the supplied payload (fail-closed).
        try:
            code_changes, test_files = self._bound_payload(supplied)
        except Exception as exc:
            return _failed([("bounds", _bounded_text(exc))])

        # 5. Formulate the bounded DRAFT EvolutionProposal.
        try:
            proposal = self._build_proposal(
                need, supplied, code_changes, test_files, research_summary, ran_at
            )
        except Exception as exc:
            return _failed([("proposal", _bounded_text(exc))])

        # 6. Submit to the EXISTING ApprovalManager, then STOP.
        try:
            request = self._approval_manager.create_approval_request(proposal)
        except Exception as exc:
            return _failed([("approval", _bounded_text(exc))])

        # 6b. Persist durably through the EXISTING stores so operators can
        # inspect/approve this proposal in a later process: the proposal at
        # PENDING_APPROVAL plus its approval request (required by
        # ``approve_proposal_by_id``'s lookup). Fail closed with an explicit
        # partial-state report if persistence itself fails.
        if self._proposal_store is not None:
            try:
                self._proposal_store.store_proposal(proposal)
            except Exception as exc:
                return _failed([(
                    "persistence",
                    "proposal submitted but not persisted: "
                    + _bounded_text(exc),
                )])
        if self._approval_request_store is not None:
            try:
                self._approval_request_store.store_approval_request(request)
            except Exception as exc:
                return _failed([(
                    "persistence",
                    "approval request submitted but not persisted: "
                    + _bounded_text(exc),
                )])

        return DevelopmentCycleResult(
            cycle_id=cycle_id,
            decision="prepared",
            status="ok",
            proposal_id=proposal.proposal_id,
            approval_request_id=getattr(request, "request_id", ""),
            proposal_status=proposal.status.name,
            researched=researched,
            research_summary=research_summary,
            ran_at=ran_at,
            elapsed_seconds=time.monotonic() - started,
        )

    # -- internals -----------------------------------------------------------

    def _validate_need(self, need: DevelopmentNeed) -> DevelopmentNeed:
        if not isinstance(need, DevelopmentNeed):
            raise ValueError("need must be a DevelopmentNeed")
        title = (need.title or "").strip()
        if not title:
            raise ValueError("need title must be non-empty")
        p = self._policy
        return DevelopmentNeed(
            title=title[: p.max_title_chars],
            summary=(need.summary or "")[: p.max_summary_chars],
            rationale=(need.rationale or "")[: p.max_text_chars],
            expected_benefit=(need.expected_benefit or "")[: p.max_text_chars],
            target_components=(
                tuple(dict.fromkeys(need.target_components))[: p.max_code_changes]
            ),
            candidate_id=(need.candidate_id or "")[:128],
            evidence_change_ids=tuple(dict.fromkeys(need.evidence_change_ids))[
                : p.max_evidence_ids
            ],
            evidence_knowledge_ids=(
                tuple(dict.fromkeys(need.evidence_knowledge_ids))[: p.max_evidence_ids]
            ),
            research_question=(need.research_question or "")[: p.max_summary_chars],
            sources=tuple(dict.fromkeys(need.sources))[: p.max_research_sources],
            metadata=need.metadata if isinstance(need.metadata, dict) else {},
        )

    def _run_research(
        self, need: DevelopmentNeed
    ) -> tuple[str | None, dict[str, Any]]:
        """Run at most ONE bounded acquisition invocation (duck-typed F8).

        Returns ``(error, summary)``; ``error is None`` means success.
        """
        if self._researcher is None:
            return ("researcher not wired", {})
        question = need.research_question.strip() or f"development need: {need.title}"
        try:
            acquisition = self._researcher(
                question=question,
                sources=need.sources,
            )
        except Exception as exc:
            return (_bounded_text(exc), {})
        if acquisition is None:
            return ("acquisition returned no result", {})
        if getattr(acquisition, "status", "") == "failed":
            failures = getattr(acquisition, "failures", ()) or ()
            message = str(failures[0][1])[:200] if failures else "acquisition failed"
            return (message, {})
        summary: dict[str, Any] = {}
        if hasattr(acquisition, "to_dict"):
            try:
                full = dict(acquisition.to_dict())
            except Exception:
                full = {}
            summary = {
                key: full.get(key)
                for key in (
                    "acquisition_id",
                    "status",
                    "report_id",
                    "sources",
                    "confidence",
                    "claim_count",
                )
                if key in full
            }
        return (None, summary)

    def _bound_payload(
        self, supplied: SuppliedChanges
    ) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
        p = self._policy
        changes: list[tuple[str, str]] = []
        for path, content in tuple(supplied.code_changes)[: p.max_code_changes]:
            if not path.strip():
                raise ValueError("empty change path")
            if len(path) > p.max_path_chars:
                raise ValueError("change path exceeds bound")
            if len(content) > p.max_content_chars:
                raise ValueError("change content exceeds bound")
            changes.append((path, content))
        tests: list[tuple[str, str]] = []
        for path, content in tuple(supplied.test_files)[: p.max_test_files]:
            if not path.strip():
                raise ValueError("empty test path")
            if len(path) > p.max_path_chars:
                raise ValueError("test path exceeds bound")
            if len(content) > p.max_content_chars:
                raise ValueError("test content exceeds bound")
            tests.append((path, content))
        if not changes:
            raise ValueError("no bounded code changes after validation")
        return (tuple(changes), tuple(tests))

    def _build_proposal(
        self,
        need: DevelopmentNeed,
        supplied: SuppliedChanges,
        code_changes: tuple[tuple[str, str], ...],
        test_files: tuple[tuple[str, str], ...],
        research_summary: dict[str, Any],
        ran_at: datetime,
    ) -> EvolutionProposal:
        plan = ImprovementPlan(
            plan_id=f"plan::{_stable_id(f'{need.candidate_id}:{need.title}')}",
            title=f"Development: {need.title}"[: self._policy.max_title_chars],
            description=need.summary or need.title,
            priority=ImprovementPriority.MEDIUM,
            target_components=list(need.target_components),
            created_at=ran_at,
        )
        seed = f"{self._counter}:{need.candidate_id}:{need.title}:{ran_at.isoformat()}"
        affected = ", ".join(need.target_components) or "unspecified"
        research_note = (
            "direct-source research performed before drafting"
            if research_summary
            else "prepared from existing evidence"
        )
        return EvolutionProposal(
            proposal_id=f"DEV-{_stable_id(seed)}",
            title=need.title,
            summary=need.summary or need.title,
            rationale=need.rationale or "deterministic development-need evidence",
            expected_benefit=(
                need.expected_benefit or "addresses the recorded development need"
            ),
            risks=(
                "Draft content is UNVERIFIED; requires human approval, "
                "sandbox verification, and governance before any effect."
            ),
            impact_analysis=affected,
            implementation_approach=(
                f"{research_note}; bounded sandbox apply/verify via the "
                f"existing E2/E5 infrastructure after authorization."
            ),
            plan=plan,
            status=ProposalStatus.DRAFT,
            created_at=ran_at,
            metadata={
                "code_changes": [
                    {"path": path, "content": content}
                    for path, content in code_changes
                ],
                "test_files": {path: content for path, content in test_files},
                "development_cycle": {
                    "candidate_id": need.candidate_id,
                    "evidence_change_ids": list(need.evidence_change_ids),
                    "evidence_knowledge_ids": list(need.evidence_knowledge_ids),
                    "change_origin": supplied.origin,
                    "content_status": "unverified-draft",
                    "supplier_confidence": float(supplied.confidence),
                    "generated_by": "F9-development-cycle",
                },
                "research": research_summary,
                "supplier_notes": (supplied.notes or "")[:500],
            },
        )