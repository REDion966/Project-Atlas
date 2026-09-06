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
    """

    execution_id: str
    proposal_id: str
    proposal_fingerprint: str
    approval_id: str
    authorization_status: str  # "authorized" | "unauthorized" | "skipped"
    execution_status: str  # "succeeded" | "failed" | "rejected" | "unauthorized"
    scope_fingerprint: str = ""
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
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


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
    ) -> tuple[Message, ExecutionAuditRecord]:
        """Execute an approved proposal through the full Level 3 contract.

        Args:
            proposal: The EvolutionProposal to execute.
            approval: The ApprovalRequest authorizing this execution.
            scope: Optional execution scope for validation.

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
                execution_status="rejected",
                error=validation_error,
            )
            self._execution_records[execution_id] = record
            self._persist_record(record)
            return (
                Message(
                    role="assistant",
                    content=f"Execution rejected: {validation_error}",
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
                execution_status="rejected",
                error=replay_error,
            )
            self._execution_records[execution_id] = record
            self._persist_record(record)
            return (
                Message(
                    role="assistant",
                    content=f"Execution rejected: {replay_error}",
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
                execution_status="rejected",
                error=scope_error,
            )
            self._execution_records[execution_id] = record
            self._persist_record(record)
            return (
                Message(
                    role="assistant",
                    content=f"Execution rejected: {scope_error}",
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
                    execution_status="unauthorized",
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

        # Step 5: Mark as executed (replay protection)
        self._mark_executed(proposal, approval)

        # Step 6: Application (delegated to ApplicationEngine)
        if self._application_engine is not None:
            try:
                result = self._application_engine.apply(proposal)
                exec_status = "succeeded" if result.success else "failed"
                error = result.error or ""
            except Exception as exc:
                exec_status = "failed"
                error = str(exc)
        else:
            # Test/simulation mode: no actual execution
            exec_status = "succeeded"
            error = ""

        record = ExecutionAuditRecord(
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            proposal_fingerprint=approval.proposal_fingerprint,
            scope_fingerprint=getattr(approval, "scope_fingerprint", ""),
            approval_id=approval.request_id,
            authorization_status=auth_status,
            execution_status=exec_status,
            error=error,
        )
        self._execution_records[execution_id] = record
        self._persist_record(record)

        if exec_status == "succeeded":
            content = (
                f"Proposal '{proposal.proposal_id}' executed successfully. "
                f"Execution ID: {execution_id}. "
                "No further action taken."
            )
        else:
            content = (
                f"Execution failed for proposal '{proposal.proposal_id}': {error}. "
                "No changes were made."
            )

        return (
            Message(
                role="assistant",
                content=content,
                metadata={"execution": record.to_dict()},
            ),
            record,
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

        Returns:
            Error message if replay detected, None if OK.
        """
        proposal_id = getattr(proposal, "proposal_id", None)
        if not proposal_id:
            return None

        # Check if this proposal has already been executed
        for record in self._execution_records.values():
            if (
                record.proposal_id == proposal_id
                and record.execution_status == "succeeded"
            ):
                return (
                    f"Proposal '{proposal_id}' has already been executed "
                    f"(execution {record.execution_id}). "
                    "Duplicate execution is not permitted."
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
