"""
Atlas Evolution Autonomy — Data Models — Phase 16.1

Pure data models for governed autonomous evolution.

These dataclasses carry the request lifecycle, risk, authorization,
scheduling, rollback, verification, versioning, and outcome evidence
for changes Atlas applies to its own operational state. They are pure
data: no business logic, no infrastructure, no AI.

The `EvolutionOutcomeRecord` is the Phase 17 evidence contract,
mirroring the role of `GoalExecutionRecord` in Phase 15 — Phase 16
persists these records only and never aggregates them.

Pure data. No business logic. No infrastructure. No AI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel


# ---------------------------------------------------------------------------
# Status and risk enums
# ---------------------------------------------------------------------------


class EvolutionRequestStatus(Enum):
    """Lifecycle status of an EvolutionRequest.

    ``VERIFIED`` is intentionally absent — verification is carried by
    ``VerificationResult``. ``DETECTED`` is intentionally absent —
    provenance lives in ``EvolutionRequest.source``.
    """

    DRAFTED = auto()
    VALIDATED = auto()
    RISK_ASSESSED = auto()
    PENDING_AUTHORIZATION = auto()
    AUTHORIZED = auto()
    SCHEDULED = auto()
    APPLIED = auto()
    PENDING_EFFECTIVE = auto()
    COMPLETED = auto()
    FAILED = auto()
    ROLLED_BACK = auto()
    SUPERSEDED = auto()
    CANCELLED = auto()
    EXPIRED = auto()
    REJECTED = auto()
    EVOLUTION_HOLD = auto()


class RiskLevel(Enum):
    """Deterministic risk-domain classification for an EvolutionRequest.

    Independent of ``ImprovementPriority`` — this enumerates risk
    exposure, not improvement priority.
    """

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class AuthorizationMode(Enum):
    """How an EvolutionAuthorization was granted."""

    EXPLICIT = auto()   # user:cli per-request approval
    POLICY = auto()     # user:policy declarative pre-authorization
    AUTONOMY = auto()   # system:autonomy inside the configured envelope


class RollbackStrategy(Enum):
    """Rollback strategy attached to an applied EvolutionRequest."""

    SNAPSHOT = auto()      # restore a store-level checksummed artifact
    INVERSE_OP = auto()    # execute the deterministic inverse of the change


class TargetKind(Enum):
    """The kind of Atlas state an EvolutionRequest targets."""

    CONFIG = auto()
    MEMORY = auto()
    KNOWLEDGE = auto()
    CAPABILITY = auto()


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionWindow:
    """Time window during which scheduled evolution requests may apply."""

    window_start: datetime
    window_end: datetime


@dataclass(frozen=True, slots=True)
class AutonomyPolicy:
    """Config mirror of the autonomy envelope.

    Immutable once loaded. The running system can never modify it —
    only the user edits the policy configuration.

    Attributes:
        enabled: Master switch. Default False — Phase 15 behavior preserved.
        effective_execution_level: The gateway level set at startup.
            Default ADMINISTRATIVE.
        allowed_scopes: Scopes eligible for system:autonomy.
        max_risk_level: Highest risk level autonomous requests may carry.
        max_requests_per_window: Autonomous request quota per window.
        authorization_ttl_minutes: TTL for authorizations.
        requires_user_approval_scopes: Scopes that always require user:cli.
        hot_reload_allowlist: Config keys eligible for in-session completion.
        window: Optional EvolutionWindow restricting application times.
        version: Policy manifest version; immutable once loaded.
    """

    enabled: bool = False
    effective_execution_level: ExecutionLevel = ExecutionLevel.ADMINISTRATIVE
    allowed_scopes: list[ScopeType] = field(default_factory=list)
    max_risk_level: RiskLevel = RiskLevel.LOW
    max_requests_per_window: int = 0
    authorization_ttl_minutes: int = 60
    requires_user_approval_scopes: list[ScopeType] = field(default_factory=list)
    hot_reload_allowlist: list[str] = field(default_factory=list)
    window: EvolutionWindow | None = None
    version: str = ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Outcome of per-scope payload validation."""

    valid: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_version: str = ""
    validator_version: str = ""


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Deterministic risk assessment for an EvolutionRequest.

    Attributes:
        risk_level: LOW/MEDIUM/HIGH/CRITICAL.
        score: Continuous score in [0.0, 1.0].
        factors: Named factor contributions (scope weight, blast radius, etc).
        requires_user_approval: True for HIGH/CRITICAL or policy-listed scopes.
        requires_rollback: True when a rollback plan is mandatory.
        summary: Human-readable assessment.
    """

    risk_level: RiskLevel
    score: float = 0.0
    factors: dict[str, float] = field(default_factory=dict)
    requires_user_approval: bool = False
    requires_rollback: bool = False
    summary: str = ""


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionAuthorization:
    """Authorization record permitting application of an EvolutionRequest.

    Attributes:
        request_id: The authorized EvolutionRequest ID.
        authorized_by: "user:cli", "user:policy", or "system:autonomy".
        mode: EXPLICIT, POLICY, or AUTONOMY.
        granted_at: When the authorization was granted.
        expires_at: Policy-TTL expiry; expired authorizations cannot apply.
        policy_ref: Optional reference into the AutonomyPolicy.
        comment: Optional human comment.
    """

    request_id: str
    authorized_by: str = ""
    mode: AuthorizationMode = AuthorizationMode.EXPLICIT
    granted_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    policy_ref: str = ""
    comment: str = ""


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionSchedule:
    """Scheduling constraints for an EvolutionRequest.

    Attributes:
        scheduled_at: When the request entered SCHEDULED.
        window_start: Earliest allowed apply time (None = no restriction).
        window_end: Latest allowed apply time (None = no restriction).
        max_attempts: Application attempts allowed. Default 1 — no auto retry.
        cooldown_until: Requests applied before this time are deferred.
        expired_at: Set when the request transitions to EXPIRED.
    """

    scheduled_at: datetime = field(default_factory=datetime.now)
    window_start: datetime | None = None
    window_end: datetime | None = None
    max_attempts: int = 1
    cooldown_until: datetime | None = None
    expired_at: datetime | None = None


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VersionTarget:
    """Version anchor for an EvolutionRequest.

    Attributes:
        target_kind: Kind of Atlas state being changed.
        current_version: Tolerated current version of the target.
        target_version: Intended version after application.
        state_version_at_creation: Optimistic-concurrency anchor — the
            AtlasStateVersion string at request creation time.
    """

    target_kind: TargetKind
    current_version: str = ""
    target_version: str = ""
    state_version_at_creation: str = ""


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """Rollback plan captured before any mutation occurs.

    Attributes:
        strategy: SNAPSHOT or INVERSE_OP.
        snapshot_ref: Reference to the stored snapshot artifact.
        inverse_description: Human-readable description of the inverse op.
        steps: Ordered rollback steps.
        cascade_targets: Dependent request IDs rolled back first (LIFO).
        requires_user_approval: Whether rollback needs explicit user approval.
    """

    strategy: RollbackStrategy = RollbackStrategy.SNAPSHOT
    snapshot_ref: str = ""
    inverse_description: str = ""
    steps: list[str] = field(default_factory=list)
    cascade_targets: list[str] = field(default_factory=list)
    requires_user_approval: bool = False


# ---------------------------------------------------------------------------
# Application receipts and verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeReceipt:
    """Record of an applied mutation, for audit and rollback dispatch."""

    request_id: str
    changed_keys: list[str] = field(default_factory=list)
    before_refs: dict[str, Any] = field(default_factory=dict)
    after_refs: dict[str, Any] = field(default_factory=dict)
    version_delta: str = ""
    target_tags: list[str] = field(default_factory=list)
    applied_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Outcome of a verification probe for an applied request."""

    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    details: str = ""
    scope: ScopeType = ScopeType.UNKNOWN
    verified_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionRequest:
    """The canonical Phase 16 artifact ordering a governed state change.

    Attributes:
        request_id: Unique identifier.
        source: "proposal_id", "goal_id", "scheduler", or "cli".
        target_scope: The ScopeType of the target state.
        change_payload: Schema-validated payload (never AI-authored).
        intended_level: Execution level required.
        status: Current lifecycle status.
        validation: ValidationReport, once validated.
        risk: RiskAssessment, once assessed.
        authorization: EvolutionAuthorization, once authorized.
        schedule: EvolutionSchedule, once scheduled.
        version_target: VersionTarget anchor, once versioned.
        rollback: RollbackPlan, once captured.
        receipt: ChangeReceipt, once applied.
        verification: VerificationResult, once verified.
        outcome: EvolutionOutcomeRecord, once terminal.
        parent_request_ids: Rollback-cascade edges (requests this depends on).
        created_at / updated_at: Timestamps.
        metadata: Optional additional context for audit.
    """

    request_id: str
    source: str
    target_scope: ScopeType
    change_payload: dict[str, Any] = field(default_factory=dict)
    intended_level: ExecutionLevel = ExecutionLevel.ADMINISTRATIVE
    status: EvolutionRequestStatus = EvolutionRequestStatus.DRAFTED
    validation: ValidationReport | None = None
    risk: RiskAssessment | None = None
    authorization: EvolutionAuthorization | None = None
    schedule: EvolutionSchedule | None = None
    version_target: VersionTarget | None = None
    rollback: RollbackPlan | None = None
    receipt: ChangeReceipt | None = None
    verification: VerificationResult | None = None
    outcome: Any = None  # EvolutionOutcomeRecord forward reference
    parent_request_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    scope_fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_scope_fingerprint(self) -> str:
        """Compute a deterministic fingerprint from the change payload.

        The fingerprint is derived from the canonical serialization of
        ``change_payload``, excluding any non-deterministic fields. Same
        payload always produces the same fingerprint; any change to the
        payload produces a different fingerprint.

        Returns:
            A hex string fingerprint. Empty payload yields empty fingerprint.
        """
        import hashlib
        import json

        if not self.change_payload:
            return ""
        # Canonical JSON serialization: sorted keys, no whitespace
        canonical = json.dumps(
            self.change_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# State versioning
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AtlasStateVersion:
    """Immutable state version manifest entry.

    Attributes:
        major: Execution-level advance; user-issued major bump.
        minor: Capability register/enhance, or new scope activation.
        patch: Applied state change or rollback.
        manifest_id: Unique identifier of this manifest entry.
        applied_request_ids: Requests applied to reach this version.
        parent_version: The version this derives from.
        scope_versions: Per-scope version tags (config/memory/knowledge/capability).
        tags: Additional manifest tags (e.g. "rollback").
        created_at: When this version was recorded.
    """

    major: int = 1
    minor: int = 0
    patch: int = 0
    manifest_id: str = ""
    applied_request_ids: list[str] = field(default_factory=list)
    parent_version: str = ""
    scope_versions: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Outcome evidence (Phase 17 contract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionOutcomeRecord:
    """Structured terminal outcome of an EvolutionRequest.

    The Phase 17 evidence contract: mirrors the role of Phase 15's
    ``GoalExecutionRecord``. Phase 16 persists these records only;
    the Phase 13.6 knowledge pipeline consumes them; Phase 16 never
    aggregates.

    Attributes:
        outcome_record_id: Unique identifier.
        request_id: The originating EvolutionRequest.
        scope: The request's ScopeType.
        area: Canonical evolution area derived from the scope.
        risk_level: Risk assessment of the request.
        intended_level: Execution level the request required.
        authorization_mode: How the request was authorized.
        outcome: COMPLETED, ROLLED_BACK, or FAILED.
        verification_passed: Whether verification succeeded.
        rollback_occurred: Whether rollback was triggered.
        effectiveness_proxy: 1.0 on completed, 0.0 otherwise.
        started_at / finished_at: Lifecycle timestamps.
        related_ids: proposal_id, goal_id, tracked_goal_id, evolution_record_id.
        strategy_key / strategy_name / planning_context_version: Evidence
            linkage carried from GoalAuthorization when transcribed.
        metadata: Additional context for later analysis.
    """

    outcome_record_id: str
    request_id: str
    scope: ScopeType
    area: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    intended_level: ExecutionLevel = ExecutionLevel.ADMINISTRATIVE
    authorization_mode: AuthorizationMode = AuthorizationMode.EXPLICIT
    outcome: str = "FAILED"
    verification_passed: bool = False
    rollback_occurred: bool = False
    effectiveness_proxy: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime = field(default_factory=datetime.now)
    related_ids: list[str] = field(default_factory=list)
    strategy_key: str = ""
    strategy_name: str = ""
    planning_context_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Staged config and status report
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StagedConfigEntry:
    """A staged configuration change awaiting boot activation.

    Config changes are NEVER applied live in Phase 16. They are staged,
    validated against schema, and activated at next boot with
    verification. COMPLETED is only reached when the change is effective
    and verified.

    Attributes:
        entry_id: Unique identifier for this staged entry.
        request_id: The originating EvolutionRequest.
        key: Configuration key.
        value: The staged value.
        schema_status: Schema validation status.
        activated_at: When the entry was activated at boot (or None).
        applied_at: When the entry was staged (written).
    """

    entry_id: str
    request_id: str
    key: str
    value: Any = None
    schema_status: str = "pending"
    activated_at: datetime | None = None
    applied_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class EvolutionStatusReport:
    """Typed bound query result for `atlas evolution status`.

    Attributes:
        state_version: Current AtlasStateVersion summary string.
        hold: Whether EVOLUTION_HOLD is active.
        pending_authorizations: Count of PENDING_AUTHORIZATION requests.
        scheduled: List of SCHEDULED request IDs.
        in_flight: List of APPLIED / PENDING_EFFECTIVE request IDs.
        window_quota_used: Autonomous requests applied in the current window.
        envelope: Compact summary of the AutonomyPolicy envelope.
        policy_version: The loaded AutonomyPolicy version.
    """

    state_version: str = ""
    hold: bool = False
    pending_authorizations: int = 0
    scheduled: list[str] = field(default_factory=list)
    in_flight: list[str] = field(default_factory=list)
    window_quota_used: int = 0
    envelope: dict[str, Any] = field(default_factory=dict)
    policy_version: str = ""
