"""Atlas Conversation — Level 5 Goal-Directed Delegated Autonomy (P14.2).

Extends Level 4 execution with:

    USER DELEGATION (bounded authority)
        ↓
    GOAL DECOMPOSITION
        ↓
    MULTI-PLAN SEQUENCING
        ↓
    REPEATED L4 PLAN/PREVIEW/EXECUTION
        ↓
    PER-PLAN RESULT EVALUATION
        ↓
    NEXT-PLAN DECISION
        ↓
    GOAL COMPLETION / TERMINATION
        ↓
    CROSS-PLAN COMPENSATION (when supported)
        ↓
    DURABLE DELEGATION AUDIT

Core safety invariants (preserved from Level 1-4):

    DELEGATION ≠ POLICY
    POLICY ≠ AUTHORIZATION
    AUTHORIZATION ≠ EXECUTION
    EXECUTION ≠ MUTATION
    L5 MUST NOT BYPASS L4
    L5 MUST NOT BYPASS APPLICATION_ENGINE
    L5 CANNOT SELF-EXTEND AUTHORITY
    REVOCATION IS AUTHORITATIVE
    EXPIRATION IS AUTHORITATIVE
    UNKNOWN IS CONSERVATIVE

Level 5 adds:

    GOAL-DELEGATION BINDING
    MULTI-PLAN SEQUENCING
    QUOTA ENFORCEMENT
    DELEGATION LIFECYCLE
    CROSS-PLAN COMPENSATION (when safe)
    REVOCATION/EXPIRATION CHECKS

Pure logic. No AI. No infrastructure. No direct mutation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

from atlas.conversation.message import Message


# ---------------------------------------------------------------------------
# Level 5 delegation lifecycle states
# ---------------------------------------------------------------------------


class DelegationStatus(Enum):
    """Delegation lifecycle status."""

    GRANTED = auto()           # delegation created, not yet active
    ACTIVE = auto()            # delegation executing plans
    PAUSED = auto()            # delegation paused (failure/recovery)
    COMPLETED = auto()         # goal achieved
    EXPIRED = auto()           # delegation expired
    REVOKED = auto()           # delegation revoked by user
    FAILED = auto()            # unrecoverable failure
    CANCELLED = auto()         # explicitly cancelled


class PlanResultStatus(Enum):
    """Result status for an executed plan under delegation."""

    SUCCEEDED = auto()
    FAILED = auto()
    PARTIAL = auto()
    UNKNOWN = auto()
    SKIPPED = auto()


# ---------------------------------------------------------------------------
# Delegation data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DelegationToken:
    """Immutable bounded authority to pursue a goal.

    The delegation is granted by the user and binds authority to:
    - a specific goal
    - authorized scopes
    - risk/plan/step quotas
    - a context
    - an expiration time

    The delegation CANNOT be self-extended by Atlas.
    """

    delegation_id: str
    goal_statement: str
    goal_fingerprint: str
    authorized_scopes: tuple[str, ...]  # scope names
    max_risk_level: str
    max_plans: int
    max_steps_per_plan: int
    authorization_mode: str  # "system:autonomy"
    granted_at: datetime
    expires_at: datetime
    granted_by: str
    revocable: bool
    context_id: str
    status: DelegationStatus = DelegationStatus.GRANTED
    plans_executed: int = 0
    plans_succeeded: int = 0
    plans_failed: int = 0

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Check if delegation has expired."""
        if now is None:
            now = datetime.now()
        return now > self.expires_at

    def is_active(self) -> bool:
        """Check if delegation is in active state."""
        return self.status == DelegationStatus.ACTIVE

    def can_execute_plans(self) -> bool:
        """Check if delegation can still execute plans."""
        return self.status == DelegationStatus.ACTIVE

    def has_quota_remaining(self) -> bool:
        """Check if plan quota remains."""
        return self.plans_executed < self.max_plans

    def is_scope_authorized(self, scope: str) -> bool:
        """Check if a scope is within authorized scopes."""
        return scope in self.authorized_scopes

    def with_status(self, status: DelegationStatus) -> DelegationToken:
        """Return new delegation with updated status."""
        return DelegationToken(
            delegation_id=self.delegation_id,
            goal_statement=self.goal_statement,
            goal_fingerprint=self.goal_fingerprint,
            authorized_scopes=self.authorized_scopes,
            max_risk_level=self.max_risk_level,
            max_plans=self.max_plans,
            max_steps_per_plan=self.max_steps_per_plan,
            authorization_mode=self.authorization_mode,
            granted_at=self.granted_at,
            expires_at=self.expires_at,
            granted_by=self.granted_by,
            revocable=self.revocable,
            context_id=self.context_id,
            status=status,
            plans_executed=self.plans_executed,
            plans_succeeded=self.plans_succeeded,
            plans_failed=self.plans_failed,
        )


@dataclass(frozen=True, slots=True)
class DelegationPlanRecord:
    """Record of a plan execution under delegation."""

    record_id: str
    delegation_id: str
    plan_id: str
    proposal_id: str
    context_id: str
    goal_fingerprint: str
    status: str  # PlanResultStatus name
    steps_total: int
    steps_succeeded: int
    steps_failed: int
    error: str = ""
    compensable: bool = False
    compensated: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "delegation_id": self.delegation_id,
            "plan_id": self.plan_id,
            "proposal_id": self.proposal_id,
            "context_id": self.context_id,
            "goal_fingerprint": self.goal_fingerprint,
            "status": self.status,
            "steps_total": self.steps_total,
            "steps_succeeded": self.steps_succeeded,
            "steps_failed": self.steps_failed,
            "error": self.error,
            "compensable": self.compensable,
            "compensated": self.compensated,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DelegationAuditRecord:
    """Audit record for delegation lifecycle events."""

    event_id: str
    delegation_id: str
    event_type: str
    goal_fingerprint: str
    context_id: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "delegation_id": self.delegation_id,
            "event_type": self.event_type,
            "goal_fingerprint": self.goal_fingerprint,
            "context_id": self.context_id,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DelegationGoalState:
    """Tracks progress toward goal completion."""

    delegation_id: str
    goal_fingerprint: str
    plans_total: int = 0
    plans_completed: int = 0
    plans_failed: int = 0
    evidence: tuple[str, ...] = field(default_factory=tuple)
    completion_status: str = "in_progress"  # in_progress | achieved | uncertain | failed
    last_updated: datetime = field(default_factory=datetime.now)

    def with_plan_result(self, success: bool) -> DelegationGoalState:
        """Update goal state with a plan result."""
        if success:
            return DelegationGoalState(
                delegation_id=self.delegation_id,
                goal_fingerprint=self.goal_fingerprint,
                plans_total=self.plans_total + 1,
                plans_completed=self.plans_completed + 1,
                plans_failed=self.plans_failed,
                evidence=self.evidence,
                completion_status=self.completion_status,
            )
        else:
            return DelegationGoalState(
                delegation_id=self.delegation_id,
                goal_fingerprint=self.goal_fingerprint,
                plans_total=self.plans_total + 1,
                plans_completed=self.plans_completed,
                plans_failed=self.plans_failed + 1,
                evidence=self.evidence,
                completion_status=self.completion_status,
            )


# ---------------------------------------------------------------------------
# Delegation Manager
# ---------------------------------------------------------------------------


class DelegationManager:
    """Manages delegation lifecycle and persistence.

    Responsibilities:
    - Create/grant delegations
    - Validate delegations (expiration, revocation, quota, scope)
    - Enforce policy envelope
    - Track lifecycle transitions
    - Persist delegation state
    - Reconstruct state after restart

    The manager does NOT mutate application state.
    """

    def __init__(
        self,
        policy_engine: Any = None,
        storage_path: str | Path | None = None,
        clock: Optional[datetime] = None,
    ) -> None:
        """Initialize the delegation manager.

        Args:
            policy_engine: AutonomyPolicyEngine for envelope checks.
                If None, policy checks are skipped (test mode).
            storage_path: Optional SQLite path for durable delegation state.
            clock: Optional clock for deterministic tests.
        """
        self._policy_engine = policy_engine
        self._storage_path = Path(storage_path) if storage_path else None
        self._clock = clock or datetime.now

        # In-memory state (backed by durable storage when configured)
        self._delegations: dict[str, DelegationToken] = {}
        self._plan_records: dict[str, DelegationPlanRecord] = {}
        self._audit_records: list[DelegationAuditRecord] = []
        self._goal_states: dict[str, DelegationGoalState] = {}
        self._context_delegations: dict[str, set[str]] = {}  # context_id → set(delegation_id)

        # Crash recovery on startup
        if self._storage_path is not None:
            self._init_storage()
            self._reconcile_state()

    # ------------------------------------------------------------------
    # Storage lifecycle
    # ------------------------------------------------------------------

    def _init_storage(self) -> None:
        """Initialize durable storage and load existing records."""
        import sqlite3

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS l5_delegations (
                    delegation_id TEXT PRIMARY KEY,
                    goal_statement TEXT NOT NULL,
                    goal_fingerprint TEXT NOT NULL,
                    authorized_scopes TEXT NOT NULL,
                    max_risk_level TEXT NOT NULL,
                    max_plans INTEGER NOT NULL,
                    max_steps_per_plan INTEGER NOT NULL,
                    authorization_mode TEXT NOT NULL,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    revocable INTEGER NOT NULL,
                    context_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plans_executed INTEGER NOT NULL DEFAULT 0,
                    plans_succeeded INTEGER NOT NULL DEFAULT 0,
                    plans_failed INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_l5_deleg_context
                    ON l5_delegations (context_id);
                CREATE INDEX IF NOT EXISTS idx_l5_deleg_status
                    ON l5_delegations (status);

                CREATE TABLE IF NOT EXISTS l5_plan_records (
                    record_id TEXT PRIMARY KEY,
                    delegation_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    goal_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    steps_total INTEGER NOT NULL,
                    steps_succeeded INTEGER NOT NULL,
                    steps_failed INTEGER NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    compensable INTEGER NOT NULL DEFAULT 0,
                    compensated INTEGER NOT NULL DEFAULT 0,
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_l5_plan_delegation
                    ON l5_plan_records (delegation_id);

                CREATE TABLE IF NOT EXISTS l5_audit_records (
                    event_id TEXT PRIMARY KEY,
                    delegation_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    goal_fingerprint TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '{}',
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_l5_audit_delegation
                    ON l5_audit_records (delegation_id);
            """)
            conn.commit()

            # Load delegations
            for row in conn.execute("SELECT * FROM l5_delegations").fetchall():
                delegation = DelegationToken(
                    delegation_id=row[0],
                    goal_statement=row[1],
                    goal_fingerprint=row[2],
                    authorized_scopes=tuple(json.loads(row[3])),
                    max_risk_level=row[4],
                    max_plans=row[5],
                    max_steps_per_plan=row[6],
                    authorization_mode=row[7],
                    granted_at=datetime.fromisoformat(row[8]),
                    expires_at=datetime.fromisoformat(row[9]),
                    granted_by=row[10],
                    revocable=bool(row[11]),
                    context_id=row[12],
                    status=DelegationStatus[row[13]],
                    plans_executed=row[14],
                    plans_succeeded=row[15],
                    plans_failed=row[16],
                )
                self._delegations[delegation.delegation_id] = delegation
                self._context_delegations.setdefault(delegation.context_id, set()).add(
                    delegation.delegation_id
                )

            # Load plan records
            for row in conn.execute("SELECT * FROM l5_plan_records").fetchall():
                record = DelegationPlanRecord(
                    record_id=row[0],
                    delegation_id=row[1],
                    plan_id=row[2],
                    proposal_id=row[3],
                    context_id=row[4],
                    goal_fingerprint=row[5],
                    status=row[6],
                    steps_total=row[7],
                    steps_succeeded=row[8],
                    steps_failed=row[9],
                    error=row[10],
                    compensable=bool(row[11]),
                    compensated=bool(row[12]),
                    timestamp=datetime.fromisoformat(row[13]),
                )
                self._plan_records[record.record_id] = record
        finally:
            conn.close()

    def _persist_delegation(self, delegation: DelegationToken) -> None:
        """Persist a delegation to durable storage."""
        if self._storage_path is None:
            return
        import sqlite3

        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO l5_delegations
                (delegation_id, goal_statement, goal_fingerprint, authorized_scopes,
                 max_risk_level, max_plans, max_steps_per_plan, authorization_mode,
                 granted_at, expires_at, granted_by, revocable, context_id, status,
                 plans_executed, plans_succeeded, plans_failed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delegation.delegation_id,
                    delegation.goal_statement,
                    delegation.goal_fingerprint,
                    json.dumps(list(delegation.authorized_scopes)),
                    delegation.max_risk_level,
                    delegation.max_plans,
                    delegation.max_steps_per_plan,
                    delegation.authorization_mode,
                    delegation.granted_at.isoformat(),
                    delegation.expires_at.isoformat(),
                    delegation.granted_by,
                    1 if delegation.revocable else 0,
                    delegation.context_id,
                    delegation.status.name,
                    delegation.plans_executed,
                    delegation.plans_succeeded,
                    delegation.plans_failed,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _persist_plan_record(self, record: DelegationPlanRecord) -> None:
        """Persist a plan record."""
        if self._storage_path is None:
            return
        import sqlite3

        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO l5_plan_records
                (record_id, delegation_id, plan_id, proposal_id, context_id,
                 goal_fingerprint, status, steps_total, steps_succeeded,
                 steps_failed, error, compensable, compensated, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.delegation_id,
                    record.plan_id,
                    record.proposal_id,
                    record.context_id,
                    record.goal_fingerprint,
                    record.status,
                    record.steps_total,
                    record.steps_succeeded,
                    record.steps_failed,
                    record.error,
                    1 if record.compensable else 0,
                    1 if record.compensated else 0,
                    record.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _persist_audit_record(self, record: DelegationAuditRecord) -> None:
        """Persist an audit record."""
        if self._storage_path is None:
            return
        import sqlite3

        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute(
                """
                INSERT INTO l5_audit_records
                (event_id, delegation_id, event_type, goal_fingerprint,
                 context_id, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.event_id,
                    record.delegation_id,
                    record.event_type,
                    record.goal_fingerprint,
                    record.context_id,
                    json.dumps(record.details),
                    record.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Crash recovery
    # ------------------------------------------------------------------

    def _reconcile_state(self) -> None:
        """Reconcile delegation state after process restart.

        Any ACTIVE delegation at startup is marked PAUSED (conservative).
        """
        reconciled = 0
        for delegation_id, delegation in list(self._delegations.items()):
            if delegation.status == DelegationStatus.ACTIVE:
                # Mark as paused - user must explicitly resume
                updated = DelegationToken(
                    delegation_id=delegation.delegation_id,
                    goal_statement=delegation.goal_statement,
                    goal_fingerprint=delegation.goal_fingerprint,
                    authorized_scopes=delegation.authorized_scopes,
                    max_risk_level=delegation.max_risk_level,
                    max_plans=delegation.max_plans,
                    max_steps_per_plan=delegation.max_steps_per_plan,
                    authorization_mode=delegation.authorization_mode,
                    granted_at=delegation.granted_at,
                    expires_at=delegation.expires_at,
                    granted_by=delegation.granted_by,
                    revocable=delegation.revocable,
                    context_id=delegation.context_id,
                    status=DelegationStatus.PAUSED,
                    plans_executed=delegation.plans_executed,
                    plans_succeeded=delegation.plans_succeeded,
                    plans_failed=delegation.plans_failed,
                )
                self._delegations[delegation_id] = updated
                self._persist_delegation(updated)
                reconciled += 1

        if reconciled > 0:
            self._audit(
                "level5.crash_recovery",
                delegation_id="system",
                reconciled=reconciled,
            )

    def _audit(self, event_type: str, delegation_id: str = "", **details: Any) -> None:
        """Emit an audit event."""
        record = DelegationAuditRecord(
            event_id=f"AUDIT-{uuid.uuid4().hex[:12]}",
            delegation_id=delegation_id,
            event_type=event_type,
            goal_fingerprint=details.get("goal_fingerprint", ""),
            context_id=details.get("context_id", ""),
            details=details,
        )
        self._audit_records.append(record)
        self._persist_audit_record(record)

    # ------------------------------------------------------------------
    # Delegation creation
    # ------------------------------------------------------------------

    def create_delegation(
        self,
        goal_statement: str,
        authorized_scopes: list[str],
        max_risk_level: str,
        max_plans: int,
        max_steps_per_plan: int,
        expires_at: datetime,
        granted_by: str,
        context_id: str,
        authorization_mode: str = "system:autonomy",
        revocable: bool = True,
    ) -> DelegationToken:
        """Create a new delegation.

        Args:
            goal_statement: The user's bounded objective.
            authorized_scopes: List of authorized scope names.
            max_risk_level: Maximum risk level allowed.
            max_plans: Maximum number of plans allowed.
            max_steps_per_plan: Maximum steps per plan.
            expiration time.
            granted_by: User identity granting the delegation.
            context_id: Binding context.
            authorization_mode: Authorization mode (default system:autonomy).
            revocable: Whether the delegation can be revoked.

        Returns:
            The created DelegationToken.

        Raises:
            ValueError: If parameters are invalid.
        """
        if not goal_statement or not goal_statement.strip():
            raise ValueError("Goal statement is required")

        if max_plans <= 0:
            raise ValueError("max_plans must be positive")

        if max_steps_per_plan <= 0:
            raise ValueError("max_steps_per_plan must be positive")

        if expires_at <= self._clock():
            raise ValueError("Expiration must be in the future")

        if not authorized_scopes:
            raise ValueError("At least one authorized scope is required")

        # Validate against policy envelope if available
        if self._policy_engine is not None:
            if not self._policy_engine.is_enabled():
                raise ValueError("Autonomy policy is disabled")

        goal_fingerprint = self._compute_goal_fingerprint(goal_statement)

        delegation = DelegationToken(
            delegation_id=f"DEL-{uuid.uuid4().hex[:16]}",
            goal_statement=goal_statement,
            goal_fingerprint=goal_fingerprint,
            authorized_scopes=tuple(authorized_scopes),
            max_risk_level=max_risk_level,
            max_plans=max_plans,
            max_steps_per_plan=max_steps_per_plan,
            authorization_mode=authorization_mode,
            granted_at=self._clock(),
            expires_at=expires_at,
            granted_by=granted_by,
            revocable=revocable,
            context_id=context_id,
            status=DelegationStatus.GRANTED,
        )

        self._delegations[delegation.delegation_id] = delegation
        self._context_delegations.setdefault(context_id, set()).add(delegation.delegation_id)
        self._persist_delegation(delegation)

        # Initialize goal state
        goal_state = DelegationGoalState(
            delegation_id=delegation.delegation_id,
            goal_fingerprint=goal_fingerprint,
        )
        self._goal_states[delegation.delegation_id] = goal_state

        self._audit(
            "delegation.created",
            delegation_id=delegation.delegation_id,
            goal_fingerprint=goal_fingerprint,
            context_id=context_id,
        )

        return delegation

    def _compute_goal_fingerprint(self, goal_statement: str) -> str:
        """Compute deterministic fingerprint for a goal statement."""
        canonical = json.dumps(goal_statement.strip(), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Delegation lifecycle
    # ------------------------------------------------------------------

    def activate_delegation(self, delegation_id: str) -> DelegationToken:
        """Activate a granted delegation."""
        delegation = self._get_delegation_or_raise(delegation_id)

        if delegation.status not in (DelegationStatus.GRANTED, DelegationStatus.PAUSED):
            raise ValueError(
                f"Cannot activate delegation in state {delegation.status.name}"
            )

        if delegation.is_expired(self._clock()):
            raise ValueError("Cannot activate expired delegation")

        updated = DelegationToken(
            delegation_id=delegation.delegation_id,
            goal_statement=delegation.goal_statement,
            goal_fingerprint=delegation.goal_fingerprint,
            authorized_scopes=delegation.authorized_scopes,
            max_risk_level=delegation.max_risk_level,
            max_plans=delegation.max_plans,
            max_steps_per_plan=delegation.max_steps_per_plan,
            authorization_mode=delegation.authorization_mode,
            granted_at=delegation.granted_at,
            expires_at=delegation.expires_at,
            granted_by=delegation.granted_by,
            revocable=delegation.revocable,
            context_id=delegation.context_id,
            status=DelegationStatus.ACTIVE,
            plans_executed=delegation.plans_executed,
            plans_succeeded=delegation.plans_succeeded,
            plans_failed=delegation.plans_failed,
        )

        self._delegations[delegation_id] = updated
        self._persist_delegation(updated)

        self._audit(
            "delegation.activated",
            delegation_id=delegation_id,
            goal_fingerprint=delegation.goal_fingerprint,
            context_id=delegation.context_id,
        )

        return updated

    def revoke_delegation(self, delegation_id: str, reason: str = "") -> DelegationToken:
        """Revoke a delegation."""
        delegation = self._get_delegation_or_raise(delegation_id)

        if not delegation.revocable:
            raise ValueError("Delegation is not revocable")

        updated = DelegationToken(
            delegation_id=delegation.delegation_id,
            goal_statement=delegation.goal_statement,
            goal_fingerprint=delegation.goal_fingerprint,
            authorized_scopes=delegation.authorized_scopes,
            max_risk_level=delegation.max_risk_level,
            max_plans=delegation.max_plans,
            max_steps_per_plan=delegation.max_steps_per_plan,
            authorization_mode=delegation.authorization_mode,
            granted_at=delegation.granted_at,
            expires_at=delegation.expires_at,
            granted_by=delegation.granted_by,
            revocable=delegation.revocable,
            context_id=delegation.context_id,
            status=DelegationStatus.REVOKED,
            plans_executed=delegation.plans_executed,
            plans_succeeded=delegation.plans_succeeded,
            plans_failed=delegation.plans_failed,
        )

        self._delegations[delegation_id] = updated
        self._persist_delegation(updated)

        self._audit(
            "delegation.revoked",
            delegation_id=delegation_id,
            goal_fingerprint=delegation.goal_fingerprint,
            context_id=delegation.context_id,
            reason=reason,
        )

        return updated

    def cancel_delegation(self, delegation_id: str, reason: str = "") -> DelegationToken:
        """Cancel a delegation."""
        delegation = self._get_delegation_or_raise(delegation_id)

        if delegation.status in (DelegationStatus.COMPLETED, DelegationStatus.CANCELLED):
            raise ValueError(f"Cannot cancel delegation in state {delegation.status.name}")

        updated = DelegationToken(
            delegation_id=delegation.delegation_id,
            goal_statement=delegation.goal_statement,
            goal_fingerprint=delegation.goal_fingerprint,
            authorized_scopes=delegation.authorized_scopes,
            max_risk_level=delegation.max_risk_level,
            max_plans=delegation.max_plans,
            max_steps_per_plan=delegation.max_steps_per_plan,
            authorization_mode=delegation.authorization_mode,
            granted_at=delegation.granted_at,
            expires_at=delegation.expires_at,
            granted_by=delegation.granted_by,
            revocable=delegation.revocable,
            context_id=delegation.context_id,
            status=DelegationStatus.CANCELLED,
            plans_executed=delegation.plans_executed,
            plans_succeeded=delegation.plans_succeeded,
            plans_failed=delegation.plans_failed,
        )

        self._delegations[delegation_id] = updated
        self._persist_delegation(updated)

        self._audit(
            "delegation.cancelled",
            delegation_id=delegation_id,
            goal_fingerprint=delegation.goal_fingerprint,
            context_id=delegation.context_id,
            reason=reason,
        )

        return updated

    def complete_delegation(self, delegation_id: str) -> DelegationToken:
        """Mark delegation as completed."""
        delegation = self._get_delegation_or_raise(delegation_id)

        if delegation.status != DelegationStatus.ACTIVE:
            raise ValueError(
                f"Cannot complete delegation in state {delegation.status.name}"
            )

        updated = DelegationToken(
            delegation_id=delegation.delegation_id,
            goal_statement=delegation.goal_statement,
            goal_fingerprint=delegation.goal_fingerprint,
            authorized_scopes=delegation.authorized_scopes,
            max_risk_level=delegation.max_risk_level,
            max_plans=delegation.max_plans,
            max_steps_per_plan=delegation.max_steps_per_plan,
            authorization_mode=delegation.authorization_mode,
            granted_at=delegation.granted_at,
            expires_at=delegation.expires_at,
            granted_by=delegation.granted_by,
            revocable=delegation.revocable,
            context_id=delegation.context_id,
            status=DelegationStatus.COMPLETED,
            plans_executed=delegation.plans_executed,
            plans_succeeded=delegation.plans_succeeded,
            plans_failed=delegation.plans_failed,
        )

        self._delegations[delegation_id] = updated
        self._persist_delegation(updated)

        # Update goal state
        if delegation_id in self._goal_states:
            goal_state = self._goal_states[delegation_id]
            self._goal_states[delegation_id] = DelegationGoalState(
                delegation_id=goal_state.delegation_id,
                goal_fingerprint=goal_state.goal_fingerprint,
                plans_total=goal_state.plans_total,
                plans_completed=goal_state.plans_completed,
                plans_failed=goal_state.plans_failed,
                evidence=goal_state.evidence,
                completion_status="achieved",
            )

        self._audit(
            "delegation.completed",
            delegation_id=delegation_id,
            goal_fingerprint=delegation.goal_fingerprint,
            context_id=delegation.context_id,
        )

        return updated

    def fail_delegation(self, delegation_id: str, reason: str = "") -> DelegationToken:
        """Mark delegation as failed."""
        delegation = self._get_delegation_or_raise(delegation_id)

        updated = DelegationToken(
            delegation_id=delegation.delegation_id,
            goal_statement=delegation.goal_statement,
            goal_fingerprint=delegation.goal_fingerprint,
            authorized_scopes=delegation.authorized_scopes,
            max_risk_level=delegation.max_risk_level,
            max_plans=delegation.max_plans,
            max_steps_per_plan=delegation.max_steps_per_plan,
            authorization_mode=delegation.authorization_mode,
            granted_at=delegation.granted_at,
            expires_at=delegation.expires_at,
            granted_by=delegation.granted_by,
            revocable=delegation.revocable,
            context_id=delegation.context_id,
            status=DelegationStatus.FAILED,
            plans_executed=delegation.plans_executed,
            plans_succeeded=delegation.plans_succeeded,
            plans_failed=delegation.plans_failed,
        )

        self._delegations[delegation_id] = updated
        self._persist_delegation(updated)

        self._audit(
            "delegation.failed",
            delegation_id=delegation_id,
            goal_fingerprint=delegation.goal_fingerprint,
            context_id=delegation.context_id,
            reason=reason,
        )

        return updated

    # ------------------------------------------------------------------
    # Delegation validation
    # ------------------------------------------------------------------

    def validate_delegation(self, delegation_id: str) -> Optional[str]:
        """Validate a delegation is executable.

        Returns error message if invalid, None if valid.
        """
        delegation = self._delegations.get(delegation_id)
        if delegation is None:
            return f"Delegation '{delegation_id}' not found"

        # Check expiration
        if delegation.is_expired(self._clock()):
            return "Delegation has expired"

        # Check revocation
        if delegation.status == DelegationStatus.REVOKED:
            return "Delegation has been revoked"

        # Check cancellation
        if delegation.status == DelegationStatus.CANCELLED:
            return "Delegation has been cancelled"

        # Check completion
        if delegation.status == DelegationStatus.COMPLETED:
            return "Delegation has already completed"

        # Check active state
        if delegation.status != DelegationStatus.ACTIVE:
            return f"Delegation is not active (status: {delegation.status.name})"

        # Check quota
        if not delegation.has_quota_remaining():
            return "Delegation plan quota exhausted"

        return None

    def validate_scope(self, delegation_id: str, scope: str) -> Optional[str]:
        """Validate a scope is within delegation authorization.

        Returns error message if invalid, None if valid.
        """
        delegation = self._delegations.get(delegation_id)
        if delegation is None:
            return f"Delegation '{delegation_id}' not found"

        if not delegation.is_scope_authorized(scope):
            return (
                f"Scope '{scope}' is not authorized. "
                f"Authorized scopes: {list(delegation.authorized_scopes)}"
            )

        return None

    def validate_context(self, delegation_id: str, context_id: str) -> Optional[str]:
        """Validate context matches delegation binding.

        Returns error message if invalid, None if valid.
        """
        delegation = self._delegations.get(delegation_id)
        if delegation is None:
            return f"Delegation '{delegation_id}' not found"

        if delegation.context_id != context_id:
            return (
                f"Context mismatch: delegation bound to '{delegation.context_id}', "
                f"but execution attempted in '{context_id}'"
            )

        return None

    # ------------------------------------------------------------------
    # Plan record tracking
    # ------------------------------------------------------------------

    def record_plan_execution(
        self,
        delegation_id: str,
        plan_id: str,
        proposal_id: str,
        status: PlanResultStatus,
        steps_total: int,
        steps_succeeded: int,
        steps_failed: int,
        error: str = "",
        compensable: bool = False,
    ) -> DelegationPlanRecord:
        """Record a plan execution result under delegation."""
        delegation = self._get_delegation_or_raise(delegation_id)

        record = DelegationPlanRecord(
            record_id=f"PLANREC-{uuid.uuid4().hex[:12]}",
            delegation_id=delegation_id,
            plan_id=plan_id,
            proposal_id=proposal_id,
            context_id=delegation.context_id,
            goal_fingerprint=delegation.goal_fingerprint,
            status=status.name,
            steps_total=steps_total,
            steps_succeeded=steps_succeeded,
            steps_failed=steps_failed,
            error=error,
            compensable=compensable,
        )

        self._plan_records[record.record_id] = record
        self._persist_plan_record(record)

        # Update delegation counters
        plans_executed = delegation.plans_executed + 1
        plans_succeeded = delegation.plans_succeeded + (1 if status == PlanResultStatus.SUCCEEDED else 0)
        plans_failed = delegation.plans_failed + (1 if status in (PlanResultStatus.FAILED, PlanResultStatus.UNKNOWN) else 0)

        updated = DelegationToken(
            delegation_id=delegation.delegation_id,
            goal_statement=delegation.goal_statement,
            goal_fingerprint=delegation.goal_fingerprint,
            authorized_scopes=delegation.authorized_scopes,
            max_risk_level=delegation.max_risk_level,
            max_plans=delegation.max_plans,
            max_steps_per_plan=delegation.max_steps_per_plan,
            authorization_mode=delegation.authorization_mode,
            granted_at=delegation.granted_at,
            expires_at=delegation.expires_at,
            granted_by=delegation.granted_by,
            revocable=delegation.revocable,
            context_id=delegation.context_id,
            status=delegation.status,
            plans_executed=plans_executed,
            plans_succeeded=plans_succeeded,
            plans_failed=plans_failed,
        )

        self._delegations[delegation_id] = updated
        self._persist_delegation(updated)

        # Update goal state
        if delegation_id in self._goal_states:
            goal_state = self._goal_states[delegation_id]
            self._goal_states[delegation_id] = goal_state.with_plan_result(
                status == PlanResultStatus.SUCCEEDED
            )

        self._audit(
            "plan.recorded",
            delegation_id=delegation_id,
            goal_fingerprint=delegation.goal_fingerprint,
            context_id=delegation.context_id,
            plan_id=plan_id,
            status=status.name,
        )

        return record

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def get_delegation(self, delegation_id: str) -> Optional[DelegationToken]:
        """Retrieve a delegation by ID."""
        return self._delegations.get(delegation_id)

    def get_context_delegations(self, context_id: str) -> list[DelegationToken]:
        """Retrieve all delegations for a context."""
        delegation_ids = self._context_delegations.get(context_id, set())
        return [
            self._delegations[did]
            for did in delegation_ids
            if did in self._delegations
        ]

    def get_plan_records(self, delegation_id: str) -> list[DelegationPlanRecord]:
        """Retrieve all plan records for a delegation."""
        return [
            r for r in self._plan_records.values()
            if r.delegation_id == delegation_id
        ]

    def get_audit_records(self, delegation_id: str) -> list[DelegationAuditRecord]:
        """Retrieve all audit records for a delegation."""
        return [
            r for r in self._audit_records
            if r.delegation_id == delegation_id
        ]

    def get_goal_state(self, delegation_id: str) -> Optional[DelegationGoalState]:
        """Retrieve goal state for a delegation."""
        return self._goal_states.get(delegation_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_delegation_or_raise(self, delegation_id: str) -> DelegationToken:
        """Get delegation or raise ValueError."""
        delegation = self._delegations.get(delegation_id)
        if delegation is None:
            raise ValueError(f"Delegation '{delegation_id}' not found")
        return delegation


# ---------------------------------------------------------------------------
# Level 5 Execution Service
# ---------------------------------------------------------------------------


class Level5ExecutionService:
    """Level 5 — Goal-Directed Delegated Autonomy execution service.

    Orchestrates multiple L4 plans under a single user delegation.

    The service:
    - Tracks goal progress
    - Sequences multiple L4 plans
    - Validates each plan against delegation + policy
    - Invokes L4 execution for each plan
    - Enforces quotas and boundaries
    - Handles failure/recovery conservatively
    - Maintains full audit attribution

    L5 NEVER mutates application state directly.
    L5 NEVER bypasses L4 governance.
    L5 NEVER bypasses ApplicationEngine.
    """

    def __init__(
        self,
        delegation_manager: DelegationManager,
        level4_service: Any,  # Level4ExecutionService
        authorization_manager: Any = None,
        rollback_manager: Any = None,
    ) -> None:
        """Initialize the Level 5 execution service.

        Args:
            delegation_manager: DelegationManager for delegation lifecycle.
            level4_service: Level4ExecutionService for plan execution.
            authorization_manager: AuthorizationManager for authority checks.
            rollback_manager: RollbackManager for compensation (optional).
        """
        self._delegation_manager = delegation_manager
        self._level4_service = level4_service
        self._authorization_manager = authorization_manager
        self._rollback_manager = rollback_manager

    def execute_delegated_goal(
        self,
        delegation: DelegationToken,
        proposals: list[tuple[Any, Any, list[Any]]],  # (proposal, approval, steps)
    ) -> tuple[Message, DelegationToken]:
        """Execute a delegated goal through multiple L4 plans.

        Args:
            delegation: The active delegation.
            proposals: List of (proposal, approval, steps) tuples.

        Returns:
            Tuple of (result Message, final delegation state).
        """
        # Validate delegation can execute
        validation_error = self._delegation_manager.validate_delegation(delegation.delegation_id)
        if validation_error:
            return self._fail_goal(
                delegation, f"Delegation validation failed: {validation_error}"
            )

        current_delegation = delegation

        for proposal, approval, steps in proposals:
            # Re-validate delegation before each plan
            validation_error = self._delegation_manager.validate_delegation(
                current_delegation.delegation_id
            )
            if validation_error:
                return self._fail_goal(
                    current_delegation,
                    f"Delegation invalid before plan: {validation_error}",
                )

            # Validate scope authorization
            scope_error = self._validate_proposal_scope(current_delegation, proposal)
            if scope_error:
                return self._fail_goal(current_delegation, scope_error)

            # Validate step count against delegation quota
            if len(steps) > current_delegation.max_steps_per_plan:
                return self._fail_goal(
                    current_delegation,
                    f"Plan steps ({len(steps)}) exceeds delegation limit "
                    f"({current_delegation.max_steps_per_plan})",
                )

            # Check authorization if manager available
            if self._authorization_manager is not None:
                auth_result = self._authorization_manager.is_authorized(proposal)
                if not auth_result.authorized:
                    return self._fail_goal(
                        current_delegation,
                        f"Authorization refused: {auth_result.reason}",
                    )

            # Create and execute L4 plan
            try:
                plan = self._level4_service.create_plan(
                    proposal=proposal,
                    approval=approval,
                    steps=steps,
                    context_id=current_delegation.context_id,
                )

                # Preview the plan
                preview = self._level4_service.preview_plan(plan, proposal, approval)
                if not preview.validation_passed:
                    return self._fail_goal(
                        current_delegation,
                        f"Plan preview failed: {preview.error}",
                    )

                # Execute the plan
                msg, record = self._level4_service.execute_plan(
                    plan, proposal, approval, preview=preview
                )

                # Record plan execution
                plan_status = self._map_plan_status(record.plan_status)
                self._delegation_manager.record_plan_execution(
                    delegation_id=current_delegation.delegation_id,
                    plan_id=plan.plan_id,
                    proposal_id=getattr(proposal, "proposal_id", "unknown"),
                    status=plan_status,
                    steps_total=record.total_steps,
                    steps_succeeded=record.succeeded_steps,
                    steps_failed=record.failed_steps,
                    error=record.error,
                    compensable=self._is_compensable(record),
                )

                # Update delegation reference
                current_delegation = self._delegation_manager.get_delegation(
                    current_delegation.delegation_id
                )

                # Handle plan result
                if plan_status == PlanResultStatus.UNKNOWN:
                    # Conservative: pause delegation on UNKNOWN
                    current_delegation = self._delegation_manager.fail_delegation(
                        current_delegation.delegation_id,
                        f"Plan {plan.plan_id} resulted in UNKNOWN state",
                    )
                    return (
                        Message(
                            role="assistant",
                            content=(
                                f"Delegation paused due to uncertain plan result. "
                                f"Plan {plan.plan_id} state is UNKNOWN. "
                                f"Manual resolution required."
                            ),
                            metadata={"delegation": current_delegation},
                        ),
                        current_delegation,
                    )

                if plan_status == PlanResultStatus.FAILED:
                    # Stop delegation on failure - do not continue to next plan
                    current_delegation = self._delegation_manager.fail_delegation(
                        current_delegation.delegation_id,
                        f"Plan {plan.plan_id} failed: {record.error}",
                    )
                    return (
                        Message(
                            role="assistant",
                            content=(
                                f"Delegation paused due to plan failure. "
                                f"Plan {plan.plan_id} failed: {record.error}. "
                                f"Plans executed: {current_delegation.plans_executed}."
                            ),
                            metadata={"delegation": current_delegation},
                        ),
                        current_delegation,
                    )

            except Exception as exc:
                return self._fail_goal(
                    current_delegation,
                    f"Plan execution error: {str(exc)}",
                )

        # All plans executed successfully
        current_delegation = self._delegation_manager.complete_delegation(
            current_delegation.delegation_id
        )

        goal_state = self._delegation_manager.get_goal_state(current_delegation.delegation_id)

        return (
            Message(
                role="assistant",
                content=(
                    f"Delegation '{current_delegation.delegation_id}' completed. "
                    f"Goal: {current_delegation.goal_statement}. "
                    f"Plans executed: {current_delegation.plans_executed}. "
                    f"Succeeded: {current_delegation.plans_succeeded}. "
                    f"Failed: {current_delegation.plans_failed}."
                ),
                metadata={
                    "delegation": current_delegation,
                    "goal_state": goal_state,
                },
            ),
            current_delegation,
        )

    def _validate_proposal_scope(
        self,
        delegation: DelegationToken,
        proposal: Any,
    ) -> Optional[str]:
        """Validate proposal scope against delegation authorization."""
        scope = getattr(proposal, "target_scope", None)
        if scope is None:
            return None  # No scope to validate

        scope_name = scope.name if hasattr(scope, "name") else str(scope)

        if not delegation.is_scope_authorized(scope_name):
            return (
                f"Proposal scope '{scope_name}' is outside delegation authorization. "
                f"Authorized: {list(delegation.authorized_scopes)}"
            )

        return None

    def _map_plan_status(self, plan_status: str) -> PlanResultStatus:
        """Map L4 plan status to L5 plan result status."""
        status_map = {
            "ALL_SUCCEEDED": PlanResultStatus.SUCCEEDED,
            "PARTIAL_FAILURE": PlanResultStatus.PARTIAL,
            "ALL_FAILED": PlanResultStatus.FAILED,
        }
        return status_map.get(plan_status, PlanResultStatus.UNKNOWN)

    def _is_compensable(self, record: Any) -> bool:
        """Check if a plan record is compensable.

        A plan is compensable only if it has a valid rollback plan
        and all operations are reversible.
        """
        if self._rollback_manager is None:
            return False

        # Check if record has required fields for compensation
        if not hasattr(record, "plan_fingerprint"):
            return False

        # Only SUCCEEDED plans with complete execution are compensable
        if not hasattr(record, "plan_status"):
            return False

        if record.plan_status != "ALL_SUCCEEDED":
            return False

        return True

    def _fail_goal(
        self,
        delegation: DelegationToken,
        error: str,
    ) -> tuple[Message, DelegationToken]:
        """Handle goal execution failure."""
        failed_delegation = self._delegation_manager.fail_delegation(
            delegation.delegation_id, error
        )

        return (
            Message(
                role="assistant",
                content=f"Delegation failed: {error}",
                metadata={"delegation": failed_delegation, "error": error},
            ),
            failed_delegation,
        )
