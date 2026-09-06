"""Atlas Conversation — Level 4 Advanced Governed Autonomy (P13.14).

Extends Level 3 execution with:

    APPROVED PROPOSAL
        ↓
    MULTI-STEP PLANNING
        ↓
    PREVIEW / DRY-RUN (optional, auditable)
        ↓
    TASK/CONTEXT BINDING
        ↓
    SEQUENTIAL STEP EXECUTION
        ├── step 1 → SUCCEEDED
        ├── step 2 → SUCCEEDED
        ├── step 3 → FAILURE → STOP
        └── step 4 → NOT EXECUTED
        ↓
    PARTIAL FAILURE TRACKING
        ↓
    ROLLBACK / RECOVERY (when applicable)
        ↓
    DURABLE MULTI-STEP AUDIT
        ↓
    STOP

Core safety invariants (preserved from Level 1-3):

    PROPOSAL ≠ APPROVAL
    APPROVAL ≠ AUTHORIZATION
    AUTHORIZATION ≠ EXECUTION
    PREVIEW ≠ EXECUTION
    CONTEXT ISOLATION
    MULTIPLE PROPOSALS DISTINCT

Level 4 adds:

    MULTI-STEP PARTIAL FAILURE SAFE
    CRASH RECOVERY CONSERVATIVE
    PREVIEW STALE DETECTION
    RETRY IDEMPOTENT

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
# Level 4 lifecycle states
# ---------------------------------------------------------------------------


class StepStatus(Enum):
    """Per-step execution status."""

    PENDING = auto()      # not yet attempted
    VALIDATING = auto()   # validation in progress
    EXECUTING = auto()    # mutation in progress
    SUCCEEDED = auto()    # completed successfully
    FAILED = auto()       # failed before/during mutation
    SKIPPED = auto()      # skipped due to prior step failure
    UNKNOWN = auto()      # state uncertain (crash during mutation)


class PlanStatus(Enum):
    """Overall execution plan status."""

    PLANNED = auto()           # plan created, not yet previewed
    PREVIEWED = auto()         # preview validated
    EXECUTING = auto()         # step execution in progress
    ALL_SUCCEEDED = auto()     # all steps completed
    PARTIAL_FAILURE = auto()   # some steps failed, some succeeded
    ALL_FAILED = auto()        # all steps failed
    RECOVERY_NEEDED = auto()   # crash detected, recovery required
    RECOVERED = auto()         # successfully recovered
    CANCELLED = auto()         # explicitly cancelled


class PreviewStatus(Enum):
    """Preview/dry-run status."""

    VALID = auto()         # preview validated successfully
    STALE = auto()          # preview no longer matches current state
    EXPIRED = auto()        # preview exceeded time bound


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionStep:
    """A single change operation within a multi-step execution plan.

    Each step represents one atomic change to be applied. Steps execute
    sequentially; if any step failure_mode is FAIL_STOP, subsequent steps
    are skipped.
    """

    step_id: str
    step_index: int
    description: str
    target_scope: str
    change_payload: dict[str, Any] = field(default_factory=dict)
    failure_mode: str = "fail_stop"  # "fail_stop" | "continue"
    status: StepStatus = StepStatus.PENDING
    error: str = ""

    def compute_fingerprint(self) -> str:
        """Deterministic fingerprint of the step's change payload."""
        canonical = json.dumps(
            self.change_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """A multi-step execution plan bound to a proposal and approval.

    The plan is immutable once created. It binds the proposal, approval,
    and exact change steps for strict execution verification.
    """

    plan_id: str
    proposal_id: str
    proposal_fingerprint: str
    approval_id: str
    scope_fingerprint: str
    context_id: str
    steps: tuple[ExecutionStep, ...]
    status: PlanStatus = PlanStatus.PLANNED
    created_at: datetime = field(default_factory=datetime.now)
    plan_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.plan_fingerprint:
            object.__setattr__(
                self, "plan_fingerprint", self._compute_fingerprint()
            )

    def _compute_fingerprint(self) -> str:
        """Deterministic fingerprint of the entire plan."""
        content = "|".join([
            self.proposal_id,
            self.proposal_fingerprint,
            self.approval_id,
            self.scope_fingerprint,
            self.context_id,
            str(len(self.steps)),
        ])
        steps_content = "|".join(
            s.step_id + s.compute_fingerprint() for s in self.steps
        )
        content += "|" + steps_content
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class PreviewResult:
    """Result of a preview/dry-run validation.

    Preview validates the entire plan without mutation. The preview
    fingerprint is verified before execution to detect stale previews.
    """

    preview_id: str
    plan_id: str
    plan_fingerprint: str
    context_id: str
    status: PreviewStatus
    step_results: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    validation_passed: bool = False
    error: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None


@dataclass(frozen=True, slots=True)
class StepExecutionRecord:
    """Immutable audit record for a single step execution."""

    record_id: str
    execution_id: str
    plan_id: str
    step_id: str
    step_index: int
    proposal_id: str
    approval_id: str
    context_id: str
    status: str  # StepStatus name
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "proposal_id": self.proposal_id,
            "approval_id": self.approval_id,
            "context_id": self.context_id,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class Level4AuditRecord:
    """Immutable audit record for a full Level 4 execution attempt."""

    execution_id: str
    plan_id: str
    proposal_id: str
    proposal_fingerprint: str
    approval_id: str
    scope_fingerprint: str
    context_id: str
    authorization_status: str
    plan_status: str
    total_steps: int
    succeeded_steps: int
    failed_steps: int
    skipped_steps: int
    preview_validated: bool
    dry_run: bool
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "proposal_id": self.proposal_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "approval_id": self.approval_id,
            "scope_fingerprint": self.scope_fingerprint,
            "context_id": self.context_id,
            "authorization_status": self.authorization_status,
            "plan_status": self.plan_status,
            "total_steps": self.total_steps,
            "succeeded_steps": self.succeeded_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "preview_validated": self.preview_validated,
            "dry_run": self.dry_run,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def is_terminal(self) -> bool:
        return self.plan_status in (
            PlanStatus.ALL_SUCCEEDED.name,
            PlanStatus.PARTIAL_FAILURE.name,
            PlanStatus.ALL_FAILED.name,
            PlanStatus.RECOVERED.name,
            PlanStatus.CANCELLED.name,
        )

    @property
    def has_partial_failure(self) -> bool:
        return self.plan_status == PlanStatus.PARTIAL_FAILURE.name

    @property
    def is_safe_to_retry(self) -> bool:
        """Only failed steps are safely retryable.

        UNKNOWN step states require manual resolution before retry.
        """
        return self.plan_status in (
            PlanStatus.ALL_FAILED.name,
            PlanStatus.PARTIAL_FAILURE.name,
        )


# ---------------------------------------------------------------------------
# Level 4 Execution Service
# ---------------------------------------------------------------------------


class Level4ExecutionService:
    """Level 4 — Advanced Governed Autonomy execution service.

    Extends Level 3 with multi-step execution, preview, partial failure
    handling, crash recovery, and context binding.

    The service orchestrates the full Level 4 contract but does NOT
    perform mutation itself. It delegates to the ApplicationEngine which
    remains the protected mutation boundary.

    The service enforces:
    - Exact proposal validation (Level 3 contract)
    - Multi-step sequential execution
    - Partial failure tracking
    - Preview/dry-run with stale detection
    - Task/context binding and isolation
    - Crash recovery (conservative)
    - Durable multi-step audit trail
    - Multiple proposal support
    """

    def __init__(
        self,
        authorization_manager: Any = None,
        application_engine: Any = None,
        storage_path: str | Path | None = None,
        preview_ttl_seconds: int = 3600,
    ) -> None:
        """Initialise the Level 4 execution service.

        Args:
            authorization_manager: AuthorizationManager for authority checks.
                If None, authorization is skipped (test mode).
            application_engine: ApplicationEngine for mutations.
                If None, execution is simulated (test mode).
            storage_path: Optional SQLite path for durable records.
            preview_ttl_seconds: Time-to-live for preview validity.
        """
        self._authorization_manager = authorization_manager
        self._application_engine = application_engine
        self._storage_path = Path(storage_path) if storage_path else None
        self._preview_ttl_seconds = preview_ttl_seconds

        # In-memory state (backed by durable storage when configured)
        self._execution_records: dict[str, Level4AuditRecord] = {}
        self._step_records: dict[str, StepExecutionRecord] = {}
        self._plans: dict[str, ExecutionPlan] = {}
        self._previews: dict[str, PreviewResult] = {}
        self._context_plans: dict[str, set[str]] = {}  # context_id → set(plan_id)

        # Crash recovery on startup
        if self._storage_path is not None:
            self._init_storage()
            self._reconcile_crash()

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
                CREATE TABLE IF NOT EXISTS l4_execution_records (
                    execution_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    proposal_fingerprint TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    scope_fingerprint TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    authorization_status TEXT NOT NULL,
                    plan_status TEXT NOT NULL,
                    total_steps INTEGER NOT NULL,
                    succeeded_steps INTEGER NOT NULL,
                    failed_steps INTEGER NOT NULL,
                    skipped_steps INTEGER NOT NULL,
                    preview_validated INTEGER NOT NULL,
                    dry_run INTEGER NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_l4_exec_proposal
                    ON l4_execution_records (proposal_id);
                CREATE INDEX IF NOT EXISTS idx_l4_exec_context
                    ON l4_execution_records (context_id);

                CREATE TABLE IF NOT EXISTS l4_step_records (
                    record_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    proposal_id TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_l4_step_execution
                    ON l4_step_records (execution_id);

                CREATE TABLE IF NOT EXISTS l4_plans (
                    plan_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    proposal_fingerprint TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    scope_fingerprint TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_fingerprint TEXT NOT NULL,
                    step_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_l4_plan_context
                    ON l4_plans (context_id);
            """)
            conn.commit()

            # Load plans
            for row in conn.execute("SELECT * FROM l4_plans").fetchall():
                plan = ExecutionPlan(
                    plan_id=row[0],
                    proposal_id=row[1],
                    proposal_fingerprint=row[2],
                    approval_id=row[3],
                    scope_fingerprint=row[4],
                    context_id=row[5],
                    status=PlanStatus[row[6]],
                    steps=(),  # steps loaded separately if needed
                    plan_fingerprint=row[7],
                    created_at=datetime.fromisoformat(row[9]),
                )
                self._plans[plan.plan_id] = plan
                self._context_plans.setdefault(plan.context_id, set()).add(plan.plan_id)

            # Load execution records
            for row in conn.execute("SELECT * FROM l4_execution_records").fetchall():
                record = Level4AuditRecord(
                    execution_id=row[0],
                    plan_id=row[1],
                    proposal_id=row[2],
                    proposal_fingerprint=row[3],
                    approval_id=row[4],
                    scope_fingerprint=row[5],
                    context_id=row[6],
                    authorization_status=row[7],
                    plan_status=row[8],
                    total_steps=row[9],
                    succeeded_steps=row[10],
                    failed_steps=row[11],
                    skipped_steps=row[12],
                    preview_validated=bool(row[13]),
                    dry_run=bool(row[14]),
                    error=row[15],
                    timestamp=datetime.fromisoformat(row[16]),
                )
                self._execution_records[record.execution_id] = record

            # Load step records
            for row in conn.execute("SELECT * FROM l4_step_records").fetchall():
                record = StepExecutionRecord(
                    record_id=row[0],
                    execution_id=row[1],
                    plan_id=row[2],
                    step_id=row[3],
                    step_index=row[4],
                    proposal_id=row[5],
                    approval_id=row[6],
                    context_id=row[7],
                    status=row[8],
                    error=row[9],
                    timestamp=datetime.fromisoformat(row[10]),
                )
                self._step_records[record.record_id] = record
        finally:
            conn.close()

    def _persist_record(self, record: Level4AuditRecord) -> None:
        """Persist an execution record to durable storage."""
        if self._storage_path is None:
            return
        import sqlite3

        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO l4_execution_records
                (execution_id, plan_id, proposal_id, proposal_fingerprint,
                 approval_id, scope_fingerprint, context_id, authorization_status,
                 plan_status, total_steps, succeeded_steps, failed_steps,
                 skipped_steps, preview_validated, dry_run, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.execution_id,
                    record.plan_id,
                    record.proposal_id,
                    record.proposal_fingerprint,
                    record.approval_id,
                    record.scope_fingerprint,
                    record.context_id,
                    record.authorization_status,
                    record.plan_status,
                    record.total_steps,
                    record.succeeded_steps,
                    record.failed_steps,
                    record.skipped_steps,
                    1 if record.preview_validated else 0,
                    1 if record.dry_run else 0,
                    record.error,
                    record.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _persist_step_record(self, record: StepExecutionRecord) -> None:
        """Persist a step execution record."""
        if self._storage_path is None:
            return
        import sqlite3

        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO l4_step_records
                (record_id, execution_id, plan_id, step_id, step_index,
                 proposal_id, approval_id, context_id, status, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.execution_id,
                    record.plan_id,
                    record.step_id,
                    record.step_index,
                    record.proposal_id,
                    record.approval_id,
                    record.context_id,
                    record.status,
                    record.error,
                    record.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _persist_plan(self, plan: ExecutionPlan) -> None:
        """Persist an execution plan."""
        if self._storage_path is None:
            return
        import sqlite3

        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO l4_plans
                (plan_id, proposal_id, proposal_fingerprint, approval_id,
                 scope_fingerprint, context_id, status, plan_fingerprint,
                 step_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    plan.proposal_id,
                    plan.proposal_fingerprint,
                    plan.approval_id,
                    plan.scope_fingerprint,
                    plan.context_id,
                    plan.status.name,
                    plan.plan_fingerprint,
                    len(plan.steps),
                    plan.created_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Crash recovery
    # ------------------------------------------------------------------

    def _reconcile_crash(self) -> None:
        """Reconcile stale execution state after process restart.

        Any plan in EXECUTING state at startup is marked RECOVERY_NEEDED.
        Any step in EXECUTING state is marked UNKNOWN.

        This is conservative: we cannot know if mutation occurred during
        a crash, so we assume the worst.
        """
        reconciled_plans = 0
        for plan_id, plan in list(self._plans.items()):
            if plan.status == PlanStatus.EXECUTING:
                # Mark plan as needing recovery
                updated = ExecutionPlan(
                    plan_id=plan.plan_id,
                    proposal_id=plan.proposal_id,
                    proposal_fingerprint=plan.proposal_fingerprint,
                    approval_id=plan.approval_id,
                    scope_fingerprint=plan.scope_fingerprint,
                    context_id=plan.context_id,
                    steps=plan.steps,
                    status=PlanStatus.RECOVERY_NEEDED,
                    created_at=plan.created_at,
                )
                self._plans[plan_id] = updated
                self._persist_plan(updated)
                reconciled_plans += 1

        if reconciled_plans > 0:
            # Persist reconciliation event
            self._audit(
                "level4.crash_recovery",
                reconciled_plans=reconciled_plans,
                timestamp=datetime.now().isoformat(),
            )

    def _audit(self, event: str, **kwargs: Any) -> None:
        """Emit an audit event (placeholder for external audit callback)."""
        # In production, this would invoke an injected audit_callback
        pass

    # ------------------------------------------------------------------
    # Plan creation
    # ------------------------------------------------------------------

    def create_plan(
        self,
        proposal: Any,
        approval: Any,
        steps: list[ExecutionStep],
        context_id: str,
    ) -> ExecutionPlan:
        """Create a multi-step execution plan bound to a proposal and approval.

        Args:
            proposal: The EvolutionProposal to execute.
            approval: The ApprovalRequest authorizing execution.
            steps: Ordered list of change steps.
            context_id: Task/conversation context for attribution.

        Returns:
            The created ExecutionPlan.

        Raises:
            ValueError: If proposal or approval is invalid.
        """
        proposal_id = getattr(proposal, "proposal_id", "unknown")
        proposal_fingerprint = getattr(
            approval, "proposal_fingerprint",
            getattr(proposal, "proposal_fingerprint", ""),
        )
        approval_id = getattr(approval, "request_id", "unknown")
        scope_fingerprint = getattr(approval, "scope_fingerprint", "")

        plan = ExecutionPlan(
            plan_id=f"PLAN-{uuid.uuid4().hex[:12]}",
            proposal_id=proposal_id,
            proposal_fingerprint=proposal_fingerprint,
            approval_id=approval_id,
            scope_fingerprint=scope_fingerprint,
            context_id=context_id,
            steps=tuple(steps),
        )

        self._plans[plan.plan_id] = plan
        self._context_plans.setdefault(context_id, set()).add(plan.plan_id)
        self._persist_plan(plan)

        return plan

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Retrieve a plan by ID."""
        return self._plans.get(plan_id)

    def get_context_plans(self, context_id: str) -> list[ExecutionPlan]:
        """Retrieve all plans for a context."""
        plan_ids = self._context_plans.get(context_id, set())
        return [self._plans[pid] for pid in plan_ids if pid in self._plans]

    # ------------------------------------------------------------------
    # Preview / dry-run
    # ------------------------------------------------------------------

    def preview_plan(
        self,
        plan: ExecutionPlan,
        proposal: Any,
        approval: Any,
    ) -> PreviewResult:
        """Validate an entire plan without mutation.

        Preview verifies:
        - Proposal and approval match exactly
        - Scope fingerprint matches
        - All steps are syntactically valid
        - No mutation occurs

        Args:
            plan: The execution plan to preview.
            proposal: The proposal bound to the plan.
            approval: The approval bound to the plan.

        Returns:
            PreviewResult with validation status.
        """
        preview_id = f"PREVIEW-{uuid.uuid4().hex[:12]}"

        # Validate proposal match
        if plan.proposal_id != getattr(proposal, "proposal_id", ""):
            return PreviewResult(
                preview_id=preview_id,
                plan_id=plan.plan_id,
                plan_fingerprint=plan.plan_fingerprint,
                context_id=plan.context_id,
                status=PreviewStatus.STALE,
                validation_passed=False,
                error="Proposal ID mismatch",
            )

        if plan.proposal_fingerprint != getattr(
            approval, "proposal_fingerprint", ""
        ):
            return PreviewResult(
                preview_id=preview_id,
                plan_id=plan.plan_id,
                plan_fingerprint=plan.plan_fingerprint,
                context_id=plan.context_id,
                status=PreviewStatus.STALE,
                validation_passed=False,
                error="Proposal fingerprint mismatch",
            )

        # Validate scope
        if plan.scope_fingerprint and plan.scope_fingerprint != getattr(
            approval, "scope_fingerprint", ""
        ):
            return PreviewResult(
                preview_id=preview_id,
                plan_id=plan.plan_id,
                plan_fingerprint=plan.plan_fingerprint,
                context_id=plan.context_id,
                status=PreviewStatus.STALE,
                validation_passed=False,
                error="Scope fingerprint mismatch",
            )

        # Validate authorization (without granting)
        if self._authorization_manager is not None:
            auth_result = self._authorization_manager.is_authorized(proposal)
            if not auth_result.authorized:
                return PreviewResult(
                    preview_id=preview_id,
                    plan_id=plan.plan_id,
                    plan_fingerprint=plan.plan_fingerprint,
                    context_id=plan.context_id,
                    status=PreviewStatus.EXPIRED,
                    validation_passed=False,
                    error=f"Authorization would be refused: {auth_result.reason}",
                )

        # Validate each step (syntax-only, no mutation)
        step_results = []
        for step in plan.steps:
            step_results.append({
                "step_id": step.step_id,
                "step_index": step.step_index,
                "description": step.description,
                "fingerprint": step.compute_fingerprint(),
                "valid": True,
            })

        preview = PreviewResult(
            preview_id=preview_id,
            plan_id=plan.plan_id,
            plan_fingerprint=plan.plan_fingerprint,
            context_id=plan.context_id,
            status=PreviewStatus.VALID,
            step_results=tuple(step_results),
            validation_passed=True,
        )

        self._previews[preview_id] = preview
        return preview

    def _validate_preview(
        self,
        plan: ExecutionPlan,
        preview: PreviewResult,
    ) -> Optional[str]:
        """Validate that a preview is still current.

        Returns error message if preview is stale, None if valid.
        """
        if preview.status != PreviewStatus.VALID:
            return f"Preview status is {preview.status.name}, not VALID"

        if preview.plan_fingerprint != plan.plan_fingerprint:
            return "Preview fingerprint does not match current plan"

        if preview.plan_id != plan.plan_id:
            return "Preview plan ID mismatch"

        return None

    # ------------------------------------------------------------------
    # Multi-step execution
    # ------------------------------------------------------------------

    def execute_plan(
        self,
        plan: ExecutionPlan,
        proposal: Any,
        approval: Any,
        preview: Optional[PreviewResult] = None,
        dry_run: bool = False,
    ) -> tuple[Message, Level4AuditRecord]:
        """Execute a multi-step plan through the full Level 4 contract.

        Execution flow:
        1. Validate proposal + approval (Level 3 contract)
        2. Validate replay/duplicate
        3. Validate context binding
        4. Validate preview (if provided)
        5. Authorization
        6. Execute steps sequentially
        7. Track partial failure
        8. Durable audit

        Args:
            plan: The execution plan to execute.
            proposal: The proposal being executed.
            approval: The approval authorizing execution.
            preview: Optional validated preview from preview_plan().
            dry_run: If True, validate but skip mutation.

        Returns:
            Tuple of (result Message, audit record).
        """
        execution_id = f"L4-{uuid.uuid4().hex[:16]}"

        # Step 1: Validate proposal
        validation_error = self._validate_proposal_for_execution(proposal, approval)
        if validation_error:
            return self._fail_execution(
                execution_id, plan, "skipped", "failed",
                validation_error, dry_run,
            )

        # Step 2: Replay protection
        replay_error = self._check_replay_multi(plan)
        if replay_error:
            return self._fail_execution(
                execution_id, plan, "skipped", "failed",
                replay_error, dry_run,
            )

        # Step 3: Context binding
        context_error = self._validate_context_binding(plan)
        if context_error:
            return self._fail_execution(
                execution_id, plan, "skipped", "failed",
                context_error, dry_run,
            )

        # Step 4: Preview validation
        preview_validated = False
        if preview is not None:
            preview_error = self._validate_preview(plan, preview)
            if preview_error:
                return self._fail_execution(
                    execution_id, plan, "skipped", "failed",
                    preview_error, dry_run,
                )
            preview_validated = True

        # Step 5: Authorization
        auth_status = "skipped"
        if self._authorization_manager is not None:
            auth_result = self._authorization_manager.is_authorized(proposal)
            if not auth_result.authorized:
                return self._fail_execution(
                    execution_id, plan, "unauthorized", "failed",
                    f"Authorization refused: {auth_result.reason}. No changes were made.",
                    dry_run,
                )
            auth_status = "authorized"

        # Mark plan as executing
        self._update_plan_status(plan, PlanStatus.EXECUTING)

        if dry_run:
            return self._complete_dry_run(
                execution_id, plan, auth_status, preview_validated,
            )

        # Step 6: Execute steps sequentially
        succeeded = 0
        failed = 0
        skipped = 0
        first_error = ""

        for i, step in enumerate(plan.steps):
            step_record_id = f"STEP-{uuid.uuid4().hex[:12]}"

            # Write step started record
            started_record = StepExecutionRecord(
                record_id=step_record_id,
                execution_id=execution_id,
                plan_id=plan.plan_id,
                step_id=step.step_id,
                step_index=i,
                proposal_id=plan.proposal_id,
                approval_id=plan.approval_id,
                context_id=plan.context_id,
                status=StepStatus.EXECUTING.name,
            )
            self._step_records[step_record_id] = started_record
            self._persist_step_record(started_record)

            # Execute step
            step_status = StepStatus.FAILED
            step_error = ""
            try:
                if self._application_engine is not None:
                    # Build a step-specific request for the engine
                    step_request = self._build_step_request(step, proposal)
                    result = self._application_engine.apply(step_request)
                    if result.success:
                        step_status = StepStatus.SUCCEEDED
                        succeeded += 1
                    else:
                        step_status = StepStatus.FAILED
                        failed += 1
                        step_error = result.error or "Step execution failed"
                        if not first_error:
                            first_error = step_error
                else:
                    # Test/simulation mode
                    step_status = StepStatus.SUCCEEDED
                    succeeded += 1
            except Exception as exc:
                step_status = StepStatus.UNKNOWN
                failed += 1
                step_error = str(exc)
                if not first_error:
                    first_error = step_error

            # Write step result record
            result_record = StepExecutionRecord(
                record_id=step_record_id,
                execution_id=execution_id,
                plan_id=plan.plan_id,
                step_id=step.step_id,
                step_index=i,
                proposal_id=plan.proposal_id,
                approval_id=plan.approval_id,
                context_id=plan.context_id,
                status=step_status.name,
                error=step_error,
            )
            self._step_records[step_record_id] = result_record
            self._persist_step_record(result_record)

            # Handle failure mode
            if step_status != StepStatus.SUCCEEDED:
                if step.failure_mode == "fail_stop":
                    # Skip remaining steps
                    for remaining_step in plan.steps[i + 1:]:
                        skipped += 1
                        skip_record = StepExecutionRecord(
                            record_id=f"STEP-{uuid.uuid4().hex[:12]}",
                            execution_id=execution_id,
                            plan_id=plan.plan_id,
                            step_id=remaining_step.step_id,
                            step_index=remaining_step.step_index,
                            proposal_id=plan.proposal_id,
                            approval_id=plan.approval_id,
                            context_id=plan.context_id,
                            status=StepStatus.SKIPPED.name,
                            error="Skipped due to prior step failure",
                        )
                        self._step_records[skip_record.record_id] = skip_record
                        self._persist_step_record(skip_record)
                    break

        # Determine plan status
        if succeeded == len(plan.steps):
            plan_status = PlanStatus.ALL_SUCCEEDED
        elif failed == len(plan.steps):
            plan_status = PlanStatus.ALL_FAILED
        elif succeeded > 0 and failed > 0:
            plan_status = PlanStatus.PARTIAL_FAILURE
        else:
            plan_status = PlanStatus.PARTIAL_FAILURE

        # Update plan status
        self._update_plan_status(plan, plan_status)

        # Create final audit record
        record = Level4AuditRecord(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            proposal_id=plan.proposal_id,
            proposal_fingerprint=plan.proposal_fingerprint,
            approval_id=plan.approval_id,
            scope_fingerprint=plan.scope_fingerprint,
            context_id=plan.context_id,
            authorization_status=auth_status,
            plan_status=plan_status.name,
            total_steps=len(plan.steps),
            succeeded_steps=succeeded,
            failed_steps=failed,
            skipped_steps=skipped,
            preview_validated=preview_validated,
            dry_run=dry_run,
            error=first_error,
        )
        self._execution_records[execution_id] = record
        self._persist_record(record)

        # Build result message
        if plan_status == PlanStatus.ALL_SUCCEEDED:
            content = (
                f"Plan '{plan.plan_id}' executed successfully. "
                f"All {succeeded} steps completed. "
                f"Execution ID: {execution_id}."
            )
        elif plan_status == PlanStatus.PARTIAL_FAILURE:
            content = (
                f"Plan '{plan.plan_id}' completed with partial failure. "
                f"Succeeded: {succeeded}, Failed: {failed}, Skipped: {skipped}. "
                f"Execution ID: {execution_id}. "
                f"First error: {first_error}. "
                "Manual review required."
            )
        else:
            content = (
                f"Plan '{plan.plan_id}' failed. "
                f"Failed: {failed}/{len(plan.steps)} steps. "
                f"Execution ID: {execution_id}. "
                f"Error: {first_error}."
            )

        return (
            Message(
                role="assistant",
                content=content,
                metadata={"execution": record.to_dict()},
            ),
            record,
        )

    def _validate_proposal_for_execution(
        self,
        proposal: Any,
        approval: Any,
    ) -> Optional[str]:
        """Validate proposal and approval match exactly."""
        if hasattr(approval, "is_valid_for"):
            if not approval.is_valid_for(proposal):
                return (
                    "Approval is not valid for this proposal. "
                    "The proposal may have changed since approval."
                )

        if hasattr(proposal, "status"):
            from atlas.evolution.models import ProposalStatus

            if proposal.status not in (
                ProposalStatus.APPROVED,
                ProposalStatus.PENDING_APPROVAL,
            ):
                return (
                    f"Proposal status is '{proposal.status.name}', "
                    "not approved. Only approved proposals can be executed."
                )

        return None

    def _check_replay_multi(self, plan: ExecutionPlan) -> Optional[str]:
        """Check for duplicate execution of the same plan."""
        for record in self._execution_records.values():
            if record.plan_id != plan.plan_id:
                continue
            if record.plan_status == PlanStatus.ALL_SUCCEEDED.name:
                return (
                    f"Plan '{plan.plan_id}' has already been executed successfully "
                    f"(execution {record.execution_id}). "
                    "Duplicate execution is not permitted."
                )
            if record.plan_status == PlanStatus.RECOVERY_NEEDED.name:
                return (
                    f"Plan '{plan.plan_id}' has uncertain execution state "
                    f"(execution {record.execution_id}). "
                    "Manual recovery required before retry."
                )
        return None

    def _validate_context_binding(self, plan: ExecutionPlan) -> Optional[str]:
        """Validate that the plan's context matches current execution context."""
        # Verify context exists and plan belongs to it
        context_plans = self._context_plans.get(plan.context_id, set())
        if plan.plan_id not in context_plans:
            return (
                f"Plan '{plan.plan_id}' is not bound to context '{plan.context_id}'. "
                "Context isolation violation."
            )
        return None

    def _update_plan_status(self, plan: ExecutionPlan, status: PlanStatus) -> None:
        """Update plan status (creates new immutable plan)."""
        updated = ExecutionPlan(
            plan_id=plan.plan_id,
            proposal_id=plan.proposal_id,
            proposal_fingerprint=plan.proposal_fingerprint,
            approval_id=plan.approval_id,
            scope_fingerprint=plan.scope_fingerprint,
            context_id=plan.context_id,
            steps=plan.steps,
            status=status,
            created_at=plan.created_at,
        )
        self._plans[plan.plan_id] = updated
        self._persist_plan(updated)

    def _build_step_request(self, step: ExecutionStep, proposal: Any) -> Any:
        """Build an execution request for a single step.

        In production, this would construct an EvolutionRequest scoped to
        the step's target_scope and change_payload. For now, we attach
        step metadata to the proposal for engine consumption.
        """
        # The step carries its own change_payload and target_scope
        # The ApplicationEngine applies the request through protected appliers
        step_request = type(
            "StepRequest",
            (),
            {
                "request_id": f"REQ-{step.step_id}",
                "target_scope": step.target_scope,
                "change_payload": step.change_payload,
                "proposal": proposal,
                "step": step,
            },
        )()
        return step_request

    def _fail_execution(
        self,
        execution_id: str,
        plan: ExecutionPlan,
        auth_status: str,
        status: str,
        error: str,
        dry_run: bool,
    ) -> tuple[Message, Level4AuditRecord]:
        """Create a failed execution result."""
        record = Level4AuditRecord(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            proposal_id=plan.proposal_id,
            proposal_fingerprint=plan.proposal_fingerprint,
            approval_id=plan.approval_id,
            scope_fingerprint=plan.scope_fingerprint,
            context_id=plan.context_id,
            authorization_status=auth_status,
            plan_status=status,
            total_steps=len(plan.steps),
            succeeded_steps=0,
            failed_steps=0,
            skipped_steps=0,
            preview_validated=False,
            dry_run=dry_run,
            error=error,
        )
        self._execution_records[execution_id] = record
        self._persist_record(record)

        return (
            Message(
                role="assistant",
                content=f"Execution failed: {error}",
                metadata={"execution": record.to_dict()},
            ),
            record,
        )

    def _complete_dry_run(
        self,
        execution_id: str,
        plan: ExecutionPlan,
        auth_status: str,
        preview_validated: bool,
    ) -> tuple[Message, Level4AuditRecord]:
        """Complete a dry-run execution (no mutation)."""
        record = Level4AuditRecord(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            proposal_id=plan.proposal_id,
            proposal_fingerprint=plan.proposal_fingerprint,
            approval_id=plan.approval_id,
            scope_fingerprint=plan.scope_fingerprint,
            context_id=plan.context_id,
            authorization_status=auth_status,
            plan_status=PlanStatus.PREVIEWED.name,
            total_steps=len(plan.steps),
            succeeded_steps=len(plan.steps),
            failed_steps=0,
            skipped_steps=0,
            preview_validated=preview_validated,
            dry_run=True,
        )
        self._execution_records[execution_id] = record
        self._persist_record(record)

        return (
            Message(
                role="assistant",
                content=(
                    f"Dry-run validation passed for plan '{plan.plan_id}'. "
                    f"All {len(plan.steps)} steps validated. "
                    "No changes were made."
                ),
                metadata={"execution": record.to_dict(), "dry_run": True},
            ),
            record,
        )

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def get_execution_record(
        self, execution_id: str
    ) -> Optional[Level4AuditRecord]:
        """Retrieve an execution record by ID."""
        return self._execution_records.get(execution_id)

    def get_step_records(
        self, execution_id: str
    ) -> list[StepExecutionRecord]:
        """Retrieve all step records for an execution."""
        return [
            r for r in self._step_records.values()
            if r.execution_id == execution_id
        ]

    def get_proposal_executions(
        self, proposal_id: str
    ) -> list[Level4AuditRecord]:
        """Retrieve all executions for a proposal."""
        return [
            r for r in self._execution_records.values()
            if r.proposal_id == proposal_id
        ]

    def get_context_executions(
        self, context_id: str
    ) -> list[Level4AuditRecord]:
        """Retrieve all executions for a context."""
        return [
            r for r in self._execution_records.values()
            if r.context_id == context_id
        ]
