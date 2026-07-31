"""
Atlas Evolution — Data Models

Pure data models for the self-evolution subsystem.
Phase 7.0 — Self-Evolution Foundation.
Phase 11.0 — Added ExecutionLevel enum and ExecutionResult dataclass.
Phase 12.0 — Added EvolutionInsight dataclass for evolution outcome analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Execution capability levels (Phase 11.0+)
# ---------------------------------------------------------------------------


class ExecutionLevel(IntEnum):
    """Capability level for the EvolutionExecutionEngine.

    Each level is a superset of all lower levels.
    Phase 11 implements ADMINISTRATIVE only.
    """

    ADMINISTRATIVE = 0  # Phase 11: record-keeping only
    SELF_CONFIG = 1     # Phase 12+: modify internal Atlas configuration
    INFORMATION = 2     # Phase 12+: modify memory, knowledge, world model
    CODE_ARTIFACT = 3   # Phase 13+: generate code patches
    SANDBOXED = 4       # Phase 14+: apply changes in sandbox, test, rollback
    AUTONOMOUS = 5      # Future: self-directed improvement within constitutional bounds


@dataclass(slots=True)
class ExecutionResult:
    """Result of a single proposal execution by EvolutionExecutionEngine.

    Attributes:
        success: Whether the execution completed without error.
        proposal_id: The ID of the executed proposal.
        status: The new status of the proposal after execution.
        record_id: The ID of the EvolutionRecord created, if any.
        tracked_goal_id: The ID of the TrackedGoal created, if any.
        error: Error message if execution failed.
    """

    success: bool
    proposal_id: str = ""
    status: str = ""
    record_id: str = ""
    tracked_goal_id: str = ""
    error: str = ""


@dataclass(slots=True)
class GatewayExecutionResult:
    """Result of a proposal execution attempt through EvolutionExecutionGateway.

    Produced exclusively by EvolutionExecutionGateway. Wraps either a
    successful delegation to EvolutionExecutionEngine or a governance
    refusal.

    Attributes:
        success: Whether execution completed. False for refusals and errors.
        proposal_id: The ID of the proposal that was evaluated.
        status: Outcome status: "IMPLEMENTED" when the engine executed
            the proposal, "REFUSED" when governance denied execution.
        governance_decision: The GovernanceDecision produced by RuleEngine,
            or None if no evaluation occurred (e.g. missing dependencies).
        record_id: The ID of the EvolutionRecord created (execution or
            refusal), or empty if no record was stored.
        tracked_goal_id: The ID of the TrackedGoal created by the engine,
            if any.
        error: Error message when execution could not proceed.
    """

    success: bool
    proposal_id: str = ""
    status: str = ""
    governance_decision: Any = None
    record_id: str = ""
    tracked_goal_id: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Observation types
# ---------------------------------------------------------------------------


class ObservationCategory(Enum):
    """Category of an observation produced by SelfObservationEngine."""

    RUNTIME_METRICS = auto()
    REASONING_QUALITY = auto()
    TOOL_USAGE = auto()
    MEMORY_QUALITY = auto()
    SYSTEM_HEALTH = auto()


@dataclass(slots=True)
class Observation:
    """
    A single structured observation produced by SelfObservationEngine.

    Attributes:
        category: The domain this observation relates to.
        metric_name: Specific measured value name (e.g. "avg_response_time").
        value: The observed numeric or categorical value.
        unit: Optional unit label for the value (e.g. "ms", "percent").
        description: Human-readable explanation of the observation.
        timestamp: When the observation was recorded.
        source: Identifier for the component that produced the observation.
        metadata: Optional additional context.
    """

    category: ObservationCategory
    metric_name: str
    value: Any
    unit: str = ""
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Improvement types
# ---------------------------------------------------------------------------


class ImprovementPriority(Enum):
    """Priority level for an improvement opportunity."""

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


class ImprovementStatus(Enum):
    """Status of an improvement opportunity in its lifecycle."""

    IDENTIFIED = auto()
    PLANNED = auto()
    PROPOSED = auto()
    APPROVED = auto()
    COMPLETED = auto()
    REJECTED = auto()
    DEFERRED = auto()


@dataclass(slots=True)
class Weakness:
    """
    A detected weakness identified from observations.

    Attributes:
        area: The component or domain the weakness applies to.
        description: Human-readable explanation of the weakness.
        severity: Impact severity of the weakness.
        supporting_observations: List of Observation IDs that support this finding.
        detected_at: When the weakness was first identified.
    """

    area: str
    description: str
    severity: ImprovementPriority
    supporting_observations: list[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class ImprovementPlan:
    """
    A structured plan for addressing identified weaknesses.

    Attributes:
        plan_id: Unique identifier for this plan.
        title: Concise title of the improvement.
        description: Full description of the proposed improvement.
        priority: Priority level of this improvement.
        weaknesses: The weaknesses this plan addresses.
        expected_benefit: Description of the expected improvement.
        complexity_estimate: Rough complexity estimate (e.g. "low", "medium", "high").
        target_components: List of component paths affected.
        created_at: When the plan was created.
    """

    plan_id: str
    title: str
    description: str
    priority: ImprovementPriority
    weaknesses: list[Weakness] = field(default_factory=list)
    expected_benefit: str = ""
    complexity_estimate: str = "medium"
    target_components: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Research types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResearchQuery:
    """
    A research query to be handled by a ResearchCoordinator implementation.

    Attributes:
        query_id: Unique identifier for this query.
        question: The research question to investigate.
        context: Relevant context for the research.
        created_at: When the query was created.
    """

    query_id: str
    question: str
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class ResearchResult:
    """
    The result of a research query.

    Attributes:
        query_id: The query this result corresponds to.
        findings: The findings discovered.
        sources: Optional list of sources consulted.
        confidence: Confidence in the result (0.0 to 1.0).
        completed_at: When the research completed.
    """

    query_id: str
    findings: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    completed_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Proposal types
# ---------------------------------------------------------------------------


class ProposalStatus(Enum):
    """Status of an evolution proposal."""

    DRAFT = auto()
    PENDING_APPROVAL = auto()
    APPROVED = auto()
    REJECTED = auto()
    DEFERRED = auto()
    IMPLEMENTED = auto()
    SUPERSEDED = auto()


@dataclass(slots=True)
class EvolutionProposal:
    """
    A human-readable engineering proposal for an improvement.

    Attributes:
        proposal_id: Unique identifier for this proposal.
        title: Concise title of the proposal.
        summary: High-level summary of the proposal.
        rationale: Explanation of why this change is needed.
        expected_benefit: Description of expected improvements.
        risks: Known risks and mitigations.
        impact_analysis: Description of affected components.
        implementation_approach: High-level implementation strategy.
        plan: The ImprovementPlan this proposal originates from.
        status: Current status of the proposal.
        rejection_reason: If rejected, the reason for rejection.
        created_at: When the proposal was created.
        approved_at: When the proposal was approved (if applicable).
        metadata: Optional additional context.
    """

    proposal_id: str
    title: str
    summary: str
    rationale: str
    expected_benefit: str
    risks: str
    impact_analysis: str
    implementation_approach: str
    plan: ImprovementPlan
    status: ProposalStatus = ProposalStatus.DRAFT
    rejection_reason: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    approved_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Approval types
# ---------------------------------------------------------------------------


class ApprovalDecision(Enum):
    """User decision on an approval request."""

    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()
    DEFERRED = auto()


@dataclass(slots=True)
class ApprovalRequest:
    """
    An approval request sent to the user.

    Attributes:
        request_id: Unique identifier for this request.
        proposal_id: The proposal requiring approval.
        title: Short title of the request.
        description: Full description for the user.
        rationale: Why this change is needed.
        risks: What could go wrong.
        expected_benefit: What will improve.
        decision: Current decision status.
        decision_comment: User's comment on the decision.
        created_at: When the request was created.
        decided_at: When the decision was made (if applicable).
    """

    request_id: str
    proposal_id: str
    title: str
    description: str
    rationale: str
    risks: str
    expected_benefit: str
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decision_comment: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    decided_at: datetime | None = None


# ---------------------------------------------------------------------------
# Evolution memory record types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvolutionRecord:
    """
    A historical record of an evolution event.

    Attributes:
        record_id: Unique identifier for this record.
        event_type: Type of event (observation, proposal, approval, etc.).
        description: Human-readable description.
        related_ids: IDs of related observations, plans, proposals, etc.
        timestamp: When the event occurred.
        metadata: Optional additional context.
    """

    record_id: str
    event_type: str
    description: str
    related_ids: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evolution insight types (Phase 12.0+)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvolutionInsight:
    """
    A structured analysis of whether a previous evolution proposal succeeded.

    Connects a proposal to its execution record, tracked goal outcome, and
    supporting evidence. Produced by EvolutionIntelligenceEngine (Phase 12+)
    and consumed by ImprovementPlanner to inform future planning.

    Pure data. No infrastructure or engine dependencies.

    Attributes:
        insight_id: Unique identifier for this insight.
        proposal_id: The ID of the original EvolutionProposal.
        execution_record_id: The ID of the EvolutionRecord documenting
            the execution event.
        tracked_goal_id: The ID of the TrackedGoal created by
            OutcomeTracker for outcome verification.

        outcome: Overall assessment of the proposal's result
            (e.g. "success", "partial", "failure", "inconclusive").
        confidence: Confidence in the outcome assessment, from 0.0
            (no confidence) to 1.0 (high confidence).
        effectiveness_score: How much the change actually helped, from
            0.0 (no improvement) to 1.0 (significant improvement).

        evidence_summary: Human-readable explanation of the evidence
            supporting this insight.
        evidence_count: Number of data points supporting the assessment.
        evidence_quality: Quality assessment of the evidence, from 0.0
            (poor) to 1.0 (strong).
        regression_risk: Estimated probability that the change introduced
            negative side effects, from 0.0 (no risk) to 1.0 (high risk).

        analyzed_at: When the analysis was performed.
        proposal_title: Denormalized title of the original proposal for
            convenient querying.
        proposal_summary: Denormalized summary of the original proposal.
        metadata: Optional additional context.
    """

    insight_id: str
    proposal_id: str
    execution_record_id: str
    tracked_goal_id: str

    outcome: str = "inconclusive"
    confidence: float = 0.0
    effectiveness_score: float = 0.0

    evidence_summary: str = ""
    evidence_count: int = 0
    evidence_quality: float = 0.0
    regression_risk: float = 0.0

    analyzed_at: datetime = field(default_factory=datetime.now)
    proposal_title: str = ""
    proposal_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
