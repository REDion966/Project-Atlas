"""Atlas Advanced Reasoning — Data Models (Track D, Batch 1).

Pure data containers for the Track D advanced-reasoning layer. Every model
is a frozen, slotted dataclass with a ``to_dict()`` serializer — mirroring
the Phase 17.1 research-models, Phase 18.1 toolchain-models, and Phase 19.1
longterm-models contract so storage adapters and capability handlers can
serialize reasoning artifacts without touching business logic.

No infrastructure dependencies. No AI. No storage. No gateway. No kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReasoningStrategy(Enum):
    """How a multi-step reasoning trace is constructed.

    DECOMPOSE  — structural decomposition: split the query/claim into
                 sub-goals, bind each to evidence, and chain the steps.
    CAUSAL     — cause-first expansion: trace causal consequences from the
                 world model before evaluating the claim.
    HYPOTHESIS — generate competing hypotheses and evaluate the strongest
                 against available evidence.
    VERIFY     — verification-focused: build the support argument for or
                 against a claim and self-verify it.
    META       — strategy-selection mode: score candidate strategies before
                 committing a trace to one.
    """

    DECOMPOSE = auto()
    CAUSAL = auto()
    HYPOTHESIS = auto()
    VERIFY = auto()
    META = auto()


class TraceStatus(Enum):
    """Lifecycle state of a reasoning trace.

    DRAFT         — trace created but not yet finalized.
    COMPLETED     — trace finished successfully with a conclusion.
    RAN_OUT_OF_BUDGET — the step/effort budget was exceeded before a conclusion.
    FAILED        — trace failed for a structural reason (e.g. no evidence).
    """

    DRAFT = auto()
    COMPLETED = auto()
    RAN_OUT_OF_BUDGET = auto()
    FAILED = auto()


class HypothesisSupport(Enum):
    """Evidence-alignment state of a generated hypothesis.

    SUPPORTED   — evidence aligns with the hypothesis.
    CONTRADICTED — evidence conflicts with the hypothesis.
    UNVERIFIED  — no usable evidence for or against the hypothesis.
    """

    SUPPORTED = auto()
    CONTRADICTED = auto()
    UNVERIFIED = auto()


class VerificationVerdict(Enum):
    """Outcome of a self-verification report.

    PASSED       — all checks passed; the trace/conclusion is internally sound.
    FAILED       — at least one check failed and the result is not trustworthy.
    INCONCLUSIVE — checks could not determine a clear outcome.
    """

    PASSED = auto()
    FAILED = auto()
    INCONCLUSIVE = auto()


# ---------------------------------------------------------------------------
# ReasoningTrace
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReasoningTraceStep:
    """A single inference step within a :class:`ReasoningTrace`.

    Attributes:
        step_id: Stable identifier unique within the trace.
        description: What the step establishes.
        premise_step_ids: Step IDs the step depends on (empty for premises).
        evidence_refs: Optional references to supporting evidence.
        confidence: Confidence in the step (0.0–1.0).
        conclusion: The proposition the step establishes.
        metadata: Additional step context.
    """

    step_id: str
    description: str = ""
    premise_step_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    conclusion: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "step_id": self.step_id,
            "description": self.description,
            "premise_step_ids": tuple(self.premise_step_ids),
            "evidence_refs": tuple(self.evidence_refs),
            "confidence": self.confidence,
            "conclusion": self.conclusion,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ReasoningTrace:
    """A deterministic multi-step reasoning artifact.

    Attributes:
        trace_id: Stable unique identifier.
        question: The original query/claim being reasoned about.
        strategy: The strategy used to construct the trace.
        steps: Ordered tuple of :class:`ReasoningTraceStep`.
        status: Lifecycle state (see :class:`TraceStatus`).
        conclusion: The final proposition reached (empty if unresolved).
        confidence: Final confidence (0.0–1.0).
        evidence_refs: Aggregate evidence references used across steps.
        started_at: When the trace was created.
        completed_at: When the trace was finalized (None if not completed).
        reasoner_version: Version tag of the reasoner that produced the trace.
        metadata: Additional context.
    """

    trace_id: str
    question: str
    strategy: ReasoningStrategy = ReasoningStrategy.DECOMPOSE
    steps: tuple[ReasoningTraceStep, ...] = ()
    status: TraceStatus = TraceStatus.DRAFT
    conclusion: str = ""
    confidence: float = 0.0
    evidence_refs: tuple[str, ...] = ()
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    reasoner_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested steps become dicts)."""
        return {
            "trace_id": self.trace_id,
            "question": self.question,
            "strategy": self.strategy.name,
            "steps": tuple(s.to_dict() for s in self.steps),
            "status": self.status.name,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "evidence_refs": tuple(self.evidence_refs),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "reasoner_version": self.reasoner_version,
            "metadata": self.metadata,
        }

    @property
    def step_count(self) -> int:
        """Number of steps in the trace."""
        return len(self.steps)

    @property
    def is_completed(self) -> bool:
        """True when the trace reached a completed state."""
        return self.status == TraceStatus.COMPLETED


# ---------------------------------------------------------------------------
# Causal reasoning
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CausalPath:
    """A single causal chain between two entities/events.

    Attributes:
        path_id: Stable unique identifier.
        source: The originating entity/event.
        target: The resulting entity/event.
        entity_ids: Ordered entity/event IDs along the path.
        relation_types: Ordered relation labels along the path.
        confidence: Confidence in the causal chain (0.0–1.0).
        metadata: Additional context.
    """

    path_id: str
    source: str
    target: str
    entity_ids: tuple[str, ...] = ()
    relation_types: tuple[str, ...] = ()
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "path_id": self.path_id,
            "source": self.source,
            "target": self.target,
            "entity_ids": tuple(self.entity_ids),
            "relation_types": tuple(self.relation_types),
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @property
    def length(self) -> int:
        """Number of edges in the causal chain."""
        return max(0, len(self.entity_ids) - 1)


@dataclass(frozen=True, slots=True)
class CounterfactualResult:
    """Outcome of a counterfactual ("what-if") evaluation.

    Attributes:
        result_id: Stable unique identifier.
        source_event: The event being evaluated.
        assumption: The altered assumption applied.
        paths_before: Causal paths observed without the assumption.
        paths_after: Causal paths observed with the assumption applied.
        changed: Whether the assumption changed any observed path.
        effect_summary: Human-readable description of the effect.
        metadata: Additional context.
    """

    result_id: str
    source_event: str
    assumption: str = ""
    paths_before: tuple[CausalPath, ...] = ()
    paths_after: tuple[CausalPath, ...] = ()
    changed: bool = False
    effect_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested paths become dicts)."""
        return {
            "result_id": self.result_id,
            "source_event": self.source_event,
            "assumption": self.assumption,
            "paths_before": tuple(p.to_dict() for p in self.paths_before),
            "paths_after": tuple(p.to_dict() for p in self.paths_after),
            "changed": self.changed,
            "effect_summary": self.effect_summary,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A single competing explanation for an observation/claim.

    Attributes:
        hypothesis_id: Stable unique identifier.
        claim: The hypothesis statement.
        kind: Template family (e.g. "direct", "inverse", "alternative_cause").
        support: Evidence-alignment state (see :class:`HypothesisSupport`).
        score: Deterministic ranking score (higher is more plausible).
        evidence_refs: Evidence references supporting the hypothesis.
        metadata: Additional context.
    """

    hypothesis_id: str
    claim: str
    kind: str = ""
    support: HypothesisSupport = HypothesisSupport.UNVERIFIED
    score: float = 0.0
    evidence_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "claim": self.claim,
            "kind": self.kind,
            "support": self.support.name,
            "score": self.score,
            "evidence_refs": tuple(self.evidence_refs),
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class HypothesisSet:
    """A ranked collection of competing hypotheses.

    Attributes:
        set_id: Stable unique identifier.
        claim: The observation/claim the hypotheses explain.
        hypotheses: Ranked tuple of :class:`Hypothesis` (best first).
        top_hypothesis_id: ID of the highest-scoring hypothesis ('' if none).
        created_at: When the set was generated.
        metadata: Additional context.
    """

    set_id: str
    claim: str
    hypotheses: tuple[Hypothesis, ...] = ()
    top_hypothesis_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested hypotheses become dicts)."""
        return {
            "set_id": self.set_id,
            "claim": self.claim,
            "hypotheses": tuple(h.to_dict() for h in self.hypotheses),
            "top_hypothesis_id": self.top_hypothesis_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @property
    def count(self) -> int:
        """Number of hypotheses in the set."""
        return len(self.hypotheses)

    @property
    def top_hypothesis(self) -> Hypothesis | None:
        """The highest-scoring hypothesis, or None if the set is empty."""
        if not self.hypotheses:
            return None
        return self.hypotheses[0]


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerificationFinding:
    """A single check result produced by the :class:`SelfVerifier`.

    Attributes:
        finding_id: Stable unique identifier.
        check_type: Type of check (e.g. "premise_usage", "circularity",
            "contradiction", "evidence_support", "calibration").
        passed: Whether the check passed.
        message: Human-readable explanation.
        severity: Severity of the finding when it fails (e.g. "error", "warning").
        metadata: Additional context.
    """

    finding_id: str
    check_type: str = ""
    passed: bool = False
    message: str = ""
    severity: str = "error"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "finding_id": self.finding_id,
            "check_type": self.check_type,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """The complete result of a self-verification run.

    Attributes:
        report_id: Stable unique identifier.
        target_id: ID of the trace/conclusion that was verified.
        verdict: Overall verdict (see :class:`VerificationVerdict`).
        findings: Tuple of :class:`VerificationFinding`.
        confidence_before: Calibrated confidence before verification.
        confidence_after: Calibrated confidence after verification.
        verified_at: When the verification ran.
        metadata: Additional context.
    """

    report_id: str
    target_id: str
    verdict: VerificationVerdict = VerificationVerdict.INCONCLUSIVE
    findings: tuple[VerificationFinding, ...] = ()
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    verified_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested findings become dicts)."""
        return {
            "report_id": self.report_id,
            "target_id": self.target_id,
            "verdict": self.verdict.name,
            "findings": tuple(f.to_dict() for f in self.findings),
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "verified_at": self.verified_at,
            "metadata": self.metadata,
        }

    @property
    def finding_count(self) -> int:
        """Number of findings in the report."""
        return len(self.findings)

    @property
    def passed_count(self) -> int:
        """Number of passed findings."""
        return sum(1 for f in self.findings if f.passed)

    @property
    def failed_count(self) -> int:
        """Number of failed findings."""
        return sum(1 for f in self.findings if not f.passed)

    @property
    def is_passed(self) -> bool:
        """True when the verdict is PASSED."""
        return self.verdict == VerificationVerdict.PASSED


# ---------------------------------------------------------------------------
# Meta-reasoning
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyScore:
    """Effectiveness score for a single reasoning strategy.

    Attributes:
        strategy: The strategy being scored.
        success_count: Number of successful traces using the strategy.
        failure_count: Number of failed traces using the strategy.
        total_count: Total traces using the strategy.
        success_rate: Success rate (0.0–1.0; 0.0 when never used).
        avg_verification_pass_rate: Average verification pass rate (0.0–1.0).
        avg_steps: Average number of steps per trace.
        score: Aggregate effectiveness score (0.0–1.0).
        metadata: Additional context.
    """

    strategy: ReasoningStrategy
    success_count: int = 0
    failure_count: int = 0
    total_count: int = 0
    success_rate: float = 0.0
    avg_verification_pass_rate: float = 0.0
    avg_steps: float = 0.0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "strategy": self.strategy.name,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_count": self.total_count,
            "success_rate": self.success_rate,
            "avg_verification_pass_rate": self.avg_verification_pass_rate,
            "avg_steps": self.avg_steps,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class MetaAssessment:
    """A meta-reasoning report over collected trace history.

    Attributes:
        assessment_id: Stable unique identifier.
        strategy_scores: Tuple of :class:`StrategyScore` (one per strategy).
        recommended_strategy: The strategy recommended for future traces.
        recommendation_reason: Why the recommendation was made.
        assessed_at: When the assessment was generated.
        metadata: Additional context.
    """

    assessment_id: str
    strategy_scores: tuple[StrategyScore, ...] = ()
    recommended_strategy: ReasoningStrategy = ReasoningStrategy.DECOMPOSE
    recommendation_reason: str = ""
    assessed_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested scores become dicts)."""
        return {
            "assessment_id": self.assessment_id,
            "strategy_scores": tuple(s.to_dict() for s in self.strategy_scores),
            "recommended_strategy": self.recommended_strategy.name,
            "recommendation_reason": self.recommendation_reason,
            "assessed_at": self.assessed_at,
            "metadata": self.metadata,
        }

    @property
    def best_strategy_score(self) -> StrategyScore | None:
        """Highest-scoring strategy, or None if no strategy was scored."""
        if not self.strategy_scores:
            return None
        return max(
            self.strategy_scores,
            key=lambda s: (s.score, s.success_rate),
        )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReasoningConfig:
    """Configuration for the advanced-reasoning track.

    Attributes:
        max_steps: Maximum inference steps per multi-step trace.
        max_depth: Maximum causal path depth / decomposition depth.
        max_hypotheses: Maximum hypotheses generated per set.
        confidence_threshold: Minimum final confidence for a trace conclusion.
        verification_enabled: Whether self-verification runs by default.
        verification_check_types: Check types enabled for verification.
        meta_window_size: Number of recent traces scored by meta-reasoning.
        evidence_limit: Maximum evidence references bound per step.
        enabled: Whether the advanced-reasoning track is active.
    """

    max_steps: int = 20
    max_depth: int = 5
    max_hypotheses: int = 5
    confidence_threshold: float = 0.6
    verification_enabled: bool = True
    verification_check_types: tuple[str, ...] = (
        "premise_usage",
        "circularity",
        "contradiction",
        "evidence_support",
        "calibration",
    )
    meta_window_size: int = 100
    evidence_limit: int = 10
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "max_steps": self.max_steps,
            "max_depth": self.max_depth,
            "max_hypotheses": self.max_hypotheses,
            "confidence_threshold": self.confidence_threshold,
            "verification_enabled": self.verification_enabled,
            "verification_check_types": tuple(self.verification_check_types),
            "meta_window_size": self.meta_window_size,
            "evidence_limit": self.evidence_limit,
            "enabled": self.enabled,
        }
