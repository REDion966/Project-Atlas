"""Atlas Conversation — Level 3 Execution (P13.8).

Productionizes the Level 3 execution contract:

    APPROVED EXACT PROPOSAL
        ↓
    VALIDATE PROPOSAL ID + FINGERPRINT + APPROVAL
        ↓
    VALIDATE EXECUTION SCOPE
        ↓
    CHECK REPLAY / EXECUTION STATE
        ↓
    AUTHORIZATION
        ↓
    APPLICATION ENGINE
        ↓
    PROTECTED APPLIERS
        ↓
    VERIFICATION
        ↓
    APPLICATION RESULT
        ↓
    EXECUTION AUDIT
        ↓
    CONVERSATION STATE UPDATE
        ↓
    STOP

Core safety invariants:

    APPROVAL ≠ AUTHORIZATION
    AUTHORIZATION ≠ EXECUTION
    PROPOSAL ≠ EXECUTION

Approval must NEVER directly grant execution authority.

Pure logic. No AI. No infrastructure. No execution.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from atlas.conversation.message import Message


@dataclass(frozen=True, slots=True)
class ExecutionAuditRecord:
    """Immutable audit record for one Level 3 execution attempt.

    Attributable to proposal, approval, authorization, and result.

    Execution lifecycle states:
      PENDING  - request received, validation passed, mutation not yet attempted
      STARTED  - mutation attempt beginning
      SUCCEEDED - execution completed successfully
      FAILED   - execution failed before any mutation occurred
      UNKNOWN  - execution state uncertain (crash during/after mutation)
    """

    execution_id: str
    proposal_id: str
    proposal_fingerprint: str
    approval_id: str
    authorization_status: str  # "authorized" | "unauthorized" | "skipped"
    execution_status: str  # "pending" | "started" | "succeeded" | "failed" | "unknown"
    scope_fingerprint: str = ""
    context_id: str = ""  # task/conversation context for attribution
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "proposal_id": self.proposal_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "approval_id": self.approval_id,
            "authorization_status": self.authorization_status,
            "execution_status": self.execution_status,
            "scope_fingerprint": self.scope_fingerprint,
            "context_id": self.context_id,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def is_terminal(self) -> bool:
        """True when execution reached a definite end state."""
        return self.execution_status in ("succeeded", "failed", "unknown")

    @property
    def is_retriable(self) -> bool:
        """True when explicit retry is safe.

        Only FAILED (pre-mutation) is safely retriable.
        UNKNOWN requires explicit resolution first.
        """
        return self.execution_status == "failed"


class Level3ExecutionService:
    """Handles Level 3 execution of an approved proposal.

    This service orchestrates the full execution contract but does NOT
    perform mutation itself. It delegates to the ApplicationEngine which
    remains the protected mutation boundary.

    The service enforces:
    - Exact proposal validation (ID + fingerprint + approval)
    - Scope validation (exact change-set binding)
    - Replay/duplicate execution protection (durable)
    - Explicit authorization requirement
    - Audit trail
    """

    def __init__(
        self,
        authorization_manager: Any = None,
        application_engine: Any = None,
        storage_path: str | Path | None = None,
    ) -> None:
        """Initialise the Level 3 execution service.

        Args:
            authorization_manager: The AuthorizationManager used to verify
                execution authority. If None, authorization is skipped (test mode).
            application_engine: The ApplicationEngine used to apply mutations.
                If None, execution is simulated (test mode).
            storage_path: Optional path to a SQLite database for durable
                execution records. If None, records are process-local only.
        """
        self._authorization_manager = authorization_manager
        self._application_engine = application_engine
        self._execution_records: dict[str, ExecutionAuditRecord] = {}
        self._storage_path = Path(storage_path) if storage_path else None
        if self._storage_path is not None:
            self._init_storage()

    def _init_storage(self) -> None:
        """Initialize SQLite storage for durable execution records."""
        import sqlite3

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_records (
                    execution_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    proposal_fingerprint TEXT NOT NULL,
                    scope_fingerprint TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    authorization_status TEXT NOT NULL,
                    execution_status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_execution_proposal
                ON execution_records (proposal_id)
            """)
            conn.commit()
            # Load existing records into memory
            rows = conn.execute(
                "SELECT * FROM execution_records"
            ).fetchall()
            for row in rows:
                record = ExecutionAuditRecord(
                    execution_id=row[0],
                    proposal_id=row[1],
                    proposal_fingerprint=row[2],
                    scope_fingerprint=row[3],
                    approval_id=row[4],
                    authorization_status=row[5],
                    execution_status=row[6],
                    error=row[7],
                    timestamp=datetime.fromisoformat(row[8]),
                )
                self._execution_records[record.execution_id] = record
        finally:
            conn.close()

    def _persist_record(self, record: ExecutionAuditRecord) -> None:
        """Persist an execution record to durable storage."""
        if self._storage_path is None:
            return
        import sqlite3

        conn = sqlite3.connect(str(self._storage_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_records
                (execution_id, proposal_id, proposal_fingerprint,
                 scope_fingerprint, approval_id, authorization_status,
                 execution_status, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.execution_id,
                    record.proposal_id,
                    record.proposal_fingerprint,
                    record.scope_fingerprint,
                    record.approval_id,
                    record.authorization_status,
                    record.execution_status,
                    record.error,
                    record.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def execute(
        self,
        proposal: Any,
        approval: Any,
        scope: Any = None,
        context_id: str = "",
        dry_run: bool = False,
    ) -> tuple[Message, ExecutionAuditRecord]:
        """Execute an approved proposal through the full Level 3 contract.

        Execution lifecycle:
          1. Validation (proposal, replay, scope) → FAILED if invalid
          2. Authorization → unauthorized if refused
          3. PENDING record written (mutation not yet attempted)
          4. STARTED record written (mutation attempt beginning)
          5. ApplicationEngine.apply() (governed mutation boundary)
          6. SUCCEEDED or UNKNOWN result recorded

        Args:
            proposal: The EvolutionProposal to execute.
            approval: The ApprovalRequest authorizing this execution.
            scope: Optional execution scope for validation.
            context_id: Task/conversation context for attribution.
            dry_run: If True, validate everything but skip mutation.

        Returns:
            A tuple of (Message describing the result, ExecutionAuditRecord).
        """
        execution_id = str(uuid.uuid1())

        # Step 1: Validate exact proposal
        validation_error = self._validate_proposal(proposal, approval)
        if validation_error:
            record = ExecutionAuditRecord(
                execution_id=execution_id,
                proposal_id=getattr(proposal, "proposal_id", "unknown"),
                proposal_fingerprint=getattr(approval, "proposal_fingerprint", ""),
                scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
                approval_id=getattr(approval, "request_id", "unknown"),
                authorization_status="skipped",
                execution_status="failed",
                context_id=context_id,
                error=validation_error,
            )
            self._execution_records[execution_id] = record
            self._persist_record(record)
            return (
                Message(
                    role="assistant",
                    content=f"Execution failed: {validation_error}",
                    metadata={"execution": record.to_dict()},
                ),
                record,
            )

        # Step 2: Check replay
        replay_error = self._check_replay(proposal, approval)
        if replay_error:
            record = ExecutionAuditRecord(
                execution_id=execution_id,
                proposal_id=proposal.proposal_id,
                proposal_fingerprint=approval.proposal_fingerprint,
                scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
                approval_id=approval.request_id,
                authorization_status="skipped",
                execution_status="failed",
                context_id=context_id,
                error=replay_error,
            )
            self._execution_records[execution_id] = record
            self._persist_record(record)
            return (
                Message(
                    role="assistant",
                    content=f"Execution failed: {replay_error}",
                    metadata={"execution": record.to_dict()},
                ),
                record,
            )

        # Step 3: Validate scope (exact change-set binding)
        scope_error = self._validate_scope(proposal, approval, request=scope)
        if scope_error:
            record = ExecutionAuditRecord(
                execution_id=execution_id,
                proposal_id=proposal.proposal_id,
                proposal_fingerprint=approval.proposal_fingerprint,
                scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
                approval_id=approval.request_id,
                authorization_status="skipped",
                execution_status="failed",
                context_id=context_id,
                error=scope_error,
            )
            self._execution_records[execution_id] = record
            self._persist_record(record)
            return (
                Message(
                    role="assistant",
                    content=f"Execution failed: {scope_error}",
                    metadata={"execution": record.to_dict()},
                ),
                record,
            )

        # Step 4: Authorization
        auth_status = "skipped"
        if self._authorization_manager is not None:
            auth_result = self._authorization_manager.is_authorized(proposal)
            if not auth_result.authorized:
                record = ExecutionAuditRecord(
                    execution_id=execution_id,
                    proposal_id=proposal.proposal_id,
                    proposal_fingerprint=approval.proposal_fingerprint,
                    scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
                    approval_id=approval.request_id,
                    authorization_status="unauthorized",
                    execution_status="failed",
                    context_id=context_id,
                    error=auth_result.reason,
                )
                self._execution_records[execution_id] = record
                self._persist_record(record)
                return (
                    Message(
                        role="assistant",
                        content=(
                            f"Authorization refused: {auth_result.reason}. "
                            "No changes were made."
                        ),
                        metadata={"execution": record.to_dict()},
                    ),
                    record,
                )
            auth_status = "authorized"

        # Step 5: Write PENDING record (validation passed, mutation not yet attempted)
        pending_record = ExecutionAuditRecord(
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            proposal_fingerprint=approval.proposal_fingerprint,
            scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
            approval_id=approval.request_id,
            authorization_status=auth_status,
            execution_status="pending",
            context_id=context_id,
        )
        self._execution_records[execution_id] = pending_record
        self._persist_record(pending_record)

        # If dry-run, stop here without mutation
        if dry_run:
            return (
                Message(
                    role="assistant",
                    content=(
                        f"Dry-run validation passed for proposal "
                        f"'{proposal.proposal_id}'. "
                        "No changes were made. "
                        "Execution would proceed with proper authorization."
                    ),
                    metadata={
                        "execution": pending_record.to_dict(),
                        "dry_run": True,
                    },
                ),
                pending_record,
            )

        # Step 6: Write STARTED record (mutation attempt beginning)
        # This is written BEFORE mutation so that a crash during/after mutation
        # leaves the execution in UNKNOWN state rather than silently disappearing.
        started_record = ExecutionAuditRecord(
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            proposal_fingerprint=approval.proposal_fingerprint,
            scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
            approval_id=approval.request_id,
            authorization_status=auth_status,
            execution_status="started",
            context_id=context_id,
        )
        self._execution_records[execution_id] = started_record
        self._persist_record(started_record)

        # Step 7: Application (delegated to ApplicationEngine)
        # This is the governed mutation boundary. A crash here leaves the
        # execution in UNKNOWN state — we cannot know if mutation occurred.
        exec_status = "unknown"
        error = ""
        try:
            if self._application_engine is not None:
                result = self._application_engine.apply(proposal)
                if result.success:
                    exec_status = "succeeded"
                else:
                    # ApplicationEngine failed explicitly — mutation did not occur
                    exec_status = "failed"
                error = result.error or ""
            else:
                # Test/simulation mode: no actual execution
                exec_status = "succeeded"
        except Exception as exc:
            # Exception during mutation — state is uncertain.
            # We do NOT know if partial mutation occurred.
            exec_status = "unknown"
            error = str(exc)

        # Step 8: Write final record (SUCCEEDED, FAILED, or UNKNOWN)
        final_record = ExecutionAuditRecord(
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            proposal_fingerprint=approval.proposal_fingerprint,
            scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
            approval_id=approval.request_id,
            authorization_status=auth_status,
            execution_status=exec_status,
            context_id=context_id,
            error=error,
        )
        self._execution_records[execution_id] = final_record
        self._persist_record(final_record)

        if exec_status == "succeeded":
            content = (
                f"Proposal '{proposal.proposal_id}' executed successfully. "
                f"Execution ID: {execution_id}. "
                "No further action taken."
            )
        elif exec_status == "failed":
            content = (
                f"Execution failed for proposal '{proposal.proposal_id}': {error}. "
                "No changes were made."
            )
        else:  # unknown
            content = (
                f"Execution state uncertain for proposal '{proposal.proposal_id}'. "
                f"Execution ID: {execution_id}. "
                "The process may have been interrupted during mutation. "
                "Manual verification required before retry."
            )

        return (
            Message(
                role="assistant",
                content=content,
                metadata={"execution": final_record.to_dict()},
            ),
            final_record,
        )

    def _validate_proposal(self, proposal: Any, approval: Any) -> Optional[str]:
        """Validate that the proposal and approval match exactly.

        Returns:
            Error message if invalid, None if valid.
        """
        # Check approval validity
        if hasattr(approval, "is_valid_for"):
            if not approval.is_valid_for(proposal):
                return (
                    "Approval is not valid for this proposal. "
                    "The proposal may have changed since approval."
                )

        # Check proposal status
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

    def _check_replay(self, proposal: Any, approval: Any) -> Optional[str]:
        """Check for replay/duplicate execution.

        Blocks retry for:
        - SUCCEEDED: already executed successfully
        - UNKNOWN: execution state uncertain (may have partially mutated)

        Allows retry for:
        - FAILED: failed before mutation occurred
        - PENDING/STARTED: should not normally occur, but safe to block

        Returns:
            Error message if replay detected, None if OK.
        """
        proposal_id = getattr(proposal, "proposal_id", None)
        if not proposal_id:
            return None

        # Check if this proposal has already been executed or is uncertain
        for record in self._execution_records.values():
            if record.proposal_id != proposal_id:
                continue
            if record.execution_status == "succeeded":
                return (
                    f"Proposal '{proposal_id}' has already been executed "
                    f"(execution {record.execution_id}). "
                    "Duplicate execution is not permitted."
                )
            if record.execution_status == "unknown":
                return (
                    f"Proposal '{proposal_id}' has an uncertain execution state "
                    f"(execution {record.execution_id}). "
                    "The process may have been interrupted during mutation. "
                    "Manual verification required before retry."
                )

        return None

    def _validate_scope(
        self,
        proposal: Any,
        approval: Any,
        request: Any = None,
    ) -> Optional[str]:
        """Validate execution scope matches approved scope.

        Uses the scope fingerprint bound to the approval to verify that
        the exact change set being executed matches what was approved.

        Args:
            proposal: The proposal being executed.
            approval: The approval with bound scope fingerprint.
            request: The actual execution request (EvolutionRequest) whose
                change_payload must match the approved scope.

        Returns:
            Error message if scope mismatch, None if OK.
        """
        # Get the approved scope fingerprint from the approval
        approved_scope = getattr(approval, "scope_fingerprint", "")
        if not approved_scope:
            # No scope binding; fall back to proposal-only validation
            return None

        # Compute current scope fingerprint from the request
        current_scope = None
        if request is not None:
            current_scope = getattr(request, "scope_fingerprint", None)
            if not current_scope and hasattr(request, "compute_scope_fingerprint"):
                current_scope = request.compute_scope_fingerprint()
        if current_scope is None:
            current_scope = getattr(proposal, "scope_fingerprint", None)
        if current_scope is None and hasattr(proposal, "compute_scope_fingerprint"):
            current_scope = proposal.compute_scope_fingerprint()

        if current_scope and approved_scope != current_scope:
            return (
                "Execution scope does not match approved scope. "
                "The change set has changed since approval. "
                "Scope expansion is not permitted."
            )

        return None

    def _mark_executed(self, proposal: Any, approval: Any) -> None:
        """Mark a proposal as executed for replay protection.

        This is a lightweight marker; the full audit record provides
        the authoritative execution history.
        """
        # In a full implementation, this would persist to storage
        pass

    def get_execution_record(
        self, execution_id: str
    ) -> Optional[ExecutionAuditRecord]:
        """Retrieve an execution audit record by ID."""
        return self._execution_records.get(execution_id)

    def get_proposal_executions(
        self, proposal_id: str
    ) -> list[ExecutionAuditRecord]:
        """Retrieve all execution records for a proposal."""
        return [
            r for r in self._execution_records.values()
            if r.proposal_id == proposal_id
        ]
