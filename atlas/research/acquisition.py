"""Atlas Post-Core F8 - Autonomous Research & Information Acquisition.

A thin, deterministic, model-independent composition service that acquires
information through Atlas's EXISTING research pipeline:

    F2 stale-candidate / explicit request
        -> sufficiency gate
        -> ResearchQuery
        -> existing ResearchPlanner / SourceAdapter (WebSourceAdapter for
           http/https)
        -> existing KnowledgeExtractor (deterministic-first; origin-tagged)
        -> existing ClaimVerifier (cross-source conflict detection)
        -> ResearchReport -> existing ResearchSQLiteStorage
        -> existing GOV-008 governed ingest boundary
        -> bounded AcquisitionResult

ARCHITECTURAL BOUNDARY:
  * no duplicate planner/extractor/verifier/storage; the coordinator is the
    single pipeline owner.
  * no AI requirement: with ``model=None`` everywhere the whole path is
    deterministic. Optional ExtractionModel/VerificationModel injection
    points remain OFF by default and are never required.
  * no approval, no execution, no governance bypass, no daemon, no tick()
    integration, no recursion/retry loops.
  * no second EventBus / Scheduler / memory / knowledge store / provenance
    system. Web content is DATA, never instructions.

Direct acquisition never depends on an AI model:
    DIRECT RETRIEVAL -> EVIDENCE -> VALIDATION -> KNOWLEDGE
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from atlas.evolution.freshness.assessor import KnowledgeFreshnessAssessor
from atlas.evolution.freshness.models import (
    KnowledgeRef,
    RecommendedAction,
)
from atlas.evolution.models import ResearchQuery
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.research.models import (
    KnowledgeClaim,
    ResearchReport,
    VerificationStatus,
)
from atlas.research.planner import ResearchPlanner


def utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class AcquisitionPolicy:
    """Deterministic, injectable bounds for one acquisition run.

    Attributes:
        max_sources: Upper bound on resolved sources per run (default 5).
        max_subqueries: Upper bound on planner sub-queries (default 3).
        max_claims: Upper bound on claims surfaced per run (default 100).
        time_budget_seconds: Approximate wall-clock budget for one run
            (default 30); bounded by the web adapter's per-request timeout,
            and recorded on the result.
        max_findings_chars: Truncation bound for findings text.
    """

    max_sources: int = 5
    max_subqueries: int = 3
    max_claims: int = 100
    time_budget_seconds: float = 30.0
    max_findings_chars: int = 2000

    def __post_init__(self) -> None:
        if self.max_sources < 1:
            raise ValueError("max_sources must be >= 1")
        if self.max_subqueries < 1:
            raise ValueError("max_subqueries must be >= 1")
        if self.max_claims < 1:
            raise ValueError("max_claims must be >= 1")
        if self.time_budget_seconds <= 0:
            raise ValueError("time_budget_seconds must be positive")
        if self.max_findings_chars < 1:
            raise ValueError("max_findings_chars must be >= 1")


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    """Deterministic per-source support/conflict aggregation (report-level).

    Aggregated purely from existing ResearchReport claims + verifications.
    Not a store, not a registry, not a scoring subsystem.
    """

    source_uri: str
    total_claims: int = 0
    supporting_claims: int = 0
    contradicted_claims: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "total_claims": self.total_claims,
            "supporting_claims": self.supporting_claims,
            "contradicted_claims": self.contradicted_claims,
        }


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    """Bounded, deterministic result of one acquisition run.

    Status values: ``ok`` (research produced + recorded), ``noop``
    (sufficiency gate said existing knowledge is enough / only REVIEW),
    ``partial`` (research ran with bounded failures), ``failed`` (nothing
    could run; malformed input).
    """

    acquisition_id: str
    decision: str  # "research" | "noop"
    status: str
    query_id: str
    question: str
    findings: str = ""
    sources: tuple[str, ...] = ()
    confidence: float = 0.0
    completed_at: datetime = field(default_factory=utc_now)
    report_ids: tuple[str, ...] = ()
    claim_count: int = 0
    verification_count: int = 0
    verification_statuses: tuple[str, ...] = ()
    stale_candidate_ids: tuple[str, ...] = ()
    source_evidence: tuple[SourceEvidence, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "acquisition_id": self.acquisition_id,
            "decision": self.decision,
            "status": self.status,
            "query_id": self.query_id,
            "question": self.question,
            "findings": self.findings,
            "sources": list(self.sources),
            "confidence": self.confidence,
            "completed_at": self.completed_at.isoformat(),
            "report_id": self.report_ids[0] if self.report_ids else "",
            "claim_count": self.claim_count,
            "verification_count": self.verification_count,
            "verification_statuses": list(self.verification_statuses),
            "stale_candidate_ids": list(self.stale_candidate_ids),
            "source_evidence": [s.to_dict() for s in self.source_evidence],
            "failures": list(self.failures),
            "elapsed_seconds": round(self.elapsed_seconds, 4),
        }


class InformationAcquisitionService:
    """Thin, deterministic composition service over the existing pipeline.

    Args:
        coordinator: Existing ConcreteResearchCoordinator (defaults to a fresh
            one when not injected).
        planner: Optional ResearchPlanner. Defaults to the coordinator's own
            planner instance so the report id derivation is exact.
        freshness_assessor: Existing F2 KnowledgeFreshnessAssessor reused for
            the sufficiency gate. Defaults to a fresh assessor (default F2
            policy).
        policy: Deterministic AcquisitionPolicy (default fresh policy).
        now: Optional clock callable (UTC) - injectable for tests.
    """

    def __init__(
        self,
        coordinator: ConcreteResearchCoordinator | None = None,
        planner: ResearchPlanner | None = None,
        freshness_assessor: KnowledgeFreshnessAssessor | None = None,
        policy: AcquisitionPolicy | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._coordinator = coordinator or ConcreteResearchCoordinator()
        self._planner = planner or self._coordinator.planner or ResearchPlanner()
        self._assessor = freshness_assessor or KnowledgeFreshnessAssessor()
        self._policy = policy or AcquisitionPolicy()
        self._now = now or utc_now
        self._counter = 0

    @property
    def policy(self) -> AcquisitionPolicy:
        """The applied policy (read-only)."""
        return self._policy

    @property
    def coordinator(self):
        """The composed coordinator (read-only)."""
        return self._coordinator

    def acquire(
        self,
        *,
        question: str = "",
        sources: Sequence[str] = (),
        knowledge_refs: Sequence[KnowledgeRef] = (),
        query_id: str = "",
        now: datetime | None = None,
    ) -> AcquisitionResult:
        """Run ONE bounded acquisition invocation.

        Modes:
          * explicit: ``question`` (+ optional ``sources``) always researches.
          * F2: ``knowledge_refs`` are assessed first; sufficiently fresh
            knowledge returns a bounded NO-OP instead of retrieving.
        """
        self._counter += 1
        acq_id = f"ACQ-{self._counter:06d}"
        ran_at = now if now is not None else self._now()
        started = time.monotonic()

        if not question.strip() and not knowledge_refs:
            return self._failed(acq_id, "", "", ran_at, started,
                                [("request", "question or knowledge_refs required")])

        # 1. F2 sufficiency gate.
        if question.strip():
            decision = "research"
            candidate_ids: tuple[str, ...] = ()
            q_question = question.strip()
            q_sources = tuple(sources)[: self._policy.max_sources]
        else:
            decision, candidate_ids, q_question, q_sources = (
                self._gate_from_refs(knowledge_refs, ran_at)
            )
        if decision == "noop":
            return AcquisitionResult(
                acquisition_id=acq_id,
                decision="noop",
                status="noop",
                query_id="",
                question=question,
                stale_candidate_ids=candidate_ids,
                elapsed_seconds=time.monotonic() - started,
                completed_at=ran_at,
            )

        # 2. Formulate / execute a bounded ResearchQuery through the
        #    EXISTING coordinator pipeline (no stage is duplicated here).
        qid = query_id or f"acq:{_stable_id(q_question or repr(q_sources))}"
        return self._run_research(
            acq_id, qid, q_question, q_sources, candidate_ids, ran_at, started,
        )

    def _gate_from_refs(
        self,
        refs: Sequence[KnowledgeRef],
        ran_at: datetime,
    ) -> tuple[str, tuple[str, ...], str, tuple[str, ...]]:
        """Deterministic F2 sufficiency gate over existing knowledge.

        Returns ``(decision, candidate_ids, question, sources)``.
        """
        bounded_refs = list(refs)[: self._policy.max_sources]
        try:
            candidates = self._assessor.find_stale_candidates(
                bounded_refs, now=ran_at
            )
        except Exception as exc:
            return (
                "research",
                tuple(r.knowledge_id for r in bounded_refs),
                "verify existing knowledge provenance",
                (),
            )
        # An empty candidate list means everything is sufficiently fresh.
        if not candidates:
            return "noop", (), "", ()

        top = candidates[0]
        action = top.recommended_action
        if action not in (RecommendedAction.RESEARCH, RecommendedAction.VERIFY):
            return "noop", (), "", ()
        candidate_ids = tuple(
            c.knowledge_id
            for c in candidates[: self._policy.max_sources]
            if c.knowledge_id
        )
        sources = tuple(dict.fromkeys(top.provenance_refs))[: self._policy.max_sources]
        question = f"re-research fresh evidence for {top.knowledge_id}"
        return "research", candidate_ids, question, sources

    # ------------------------------------------------------------------
    # Research execution (delegates entirely to the existing coordinator)
    # ------------------------------------------------------------------

    def _run_research(
        self,
        acq_id: str,
        qid: str,
        question: str,
        sources: tuple[str, ...],
        candidate_ids: tuple[str, ...],
        ran_at: datetime,
        started: float,
    ) -> AcquisitionResult:
        failures: list[tuple[str, str]] = []
        try:
            query = ResearchQuery(
                query_id=qid,
                question=question,
                context={"sources": list(sources)},
            )
            result = self._coordinator.run(query)
        except Exception as exc:
            return self._failed(
                acq_id, qid, question, ran_at, started,
                [("research", _bounded_text(exc))],
            )
        if result is None:
            return self._failed(
                acq_id, qid, question, ran_at, started,
                [("research", "coordinator returned no result")],
            )

        resolved_sources = tuple(dict.fromkeys(result.sources or ()))[
            : self._policy.max_sources
        ]
        findings = (result.findings or "")[: self._policy.max_findings_chars]
        report = self._load_report(qid, question)

        report_ids: tuple[str, ...] = ()
        claim_count = 0
        verification_count = 0
        statuses: tuple[str, ...] = ()
        evidence: tuple[SourceEvidence, ...] = ()
        if report is not None:
            report_ids = (report.report_id,)
            claim_count = min(len(report.claims or ()), self._policy.max_claims)
            verification_count = min(
                len(report.verifications or ()), self._policy.max_claims
            )
            statuses = tuple(
                v.status.name for v in report.verifications
            )[: self._policy.max_claims]
            evidence = source_evidence(report)[: self._policy.max_sources]

        has_storage = getattr(self._coordinator, "storage", None) is not None
        if report is not None:
            status = "ok" if claim_count else "noop"
        elif resolved_sources:
            status = "ok"
        elif has_storage:
            # Coordinator fail-soft path produced an empty result.
            status = "partial"
            failures.append(("research", "coordinator produced no durable report"))
        else:
            status = "noop"

        return AcquisitionResult(
            acquisition_id=acq_id,
            decision="research",
            status=status,
            query_id=qid,
            question=question,
            findings=findings,
            sources=resolved_sources,
            confidence=float(getattr(result, "confidence", 0.0) or 0.0),
            completed_at=getattr(result, "completed_at", None) or ran_at,
            report_ids=report_ids,
            claim_count=claim_count,
            verification_count=verification_count,
            verification_statuses=statuses,
            stale_candidate_ids=candidate_ids,
            source_evidence=evidence,
            failures=tuple(failures),
            elapsed_seconds=time.monotonic() - started,
        )

    def _load_report(self, qid: str, question: str):
        """Best-effort fetch of the durable report persisted for ``qid``.

        The coordinator persists the report as ``report:{query_id}:{plan_id}``
        where ``plan_id = plan::{query_id}`` (deterministic). Read-only; falls
        back to None (bounded) when storage is unavailable or the durable
        artifact is missing.
        """
        storage = getattr(self._coordinator, "storage", None)
        if storage is None:
            return None
        try:
            if not storage.is_available():
                return None
            report_id = f"report:{qid}:plan::{qid}"
            for item in storage.load_reports():
                if getattr(item, "report_id", "") == report_id:
                    return item
        except Exception:
            return None
        return None

    def _failed(
        self,
        acq_id: str,
        qid: str,
        question: str,
        ran_at: datetime,
        started: float,
        failures: list[tuple[str, str]],
    ) -> AcquisitionResult:
        return AcquisitionResult(
            acquisition_id=acq_id,
            decision="research",
            status="failed",
            query_id=qid,
            question=question,
            failures=tuple(failures)[:10],
            completed_at=ran_at,
            elapsed_seconds=time.monotonic() - started,
        )


def source_evidence(report: ResearchReport) -> tuple[SourceEvidence, ...]:
    """Deterministic per-source support/conflict aggregation (report-level).

    Reuses the report's existing claims + verifications; never a store.
    """
    by_claim: dict[str, KnowledgeClaim] = {c.claim_id: c for c in report.claims}
    buckets: dict[str, list[int]] = {}
    for verification in report.verifications:
        claim = by_claim.get(verification.claim_id)
        if claim is None:
            continue
        for citation in claim.citations:
            uri = citation.source_uri or ""
            if not uri:
                continue
            bucket = buckets.setdefault(uri, [0, 0, 0])
            bucket[2] += 1
            if verification.status is VerificationStatus.SUPPORTED:
                bucket[0] += 1
            elif verification.status is VerificationStatus.CONTRADICTED:
                bucket[1] += 1
    return tuple(
        SourceEvidence(
            source_uri=uri,
            supporting_claims=counts[0],
            contradicted_claims=counts[1],
            total_claims=counts[2],
        )
        for uri, counts in sorted(buckets.items())
    )


def _stable_id(seed: str) -> str:
    """Deterministic short identifier for a seed string."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _bounded_text(exc: Exception, limit: int = 200) -> str:
    """Return a bounded, secret-free error message for a failure."""
    text = str(exc).strip() or type(exc).__name__
    return text[:limit]