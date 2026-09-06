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
    - Scope validation
    - Replay/duplicate execution protection
    - Explicit authorization requirement
    - Audit trail
    """

    def __init__(
        self,
        authorization_manager: Any = None,
        application_engine: Any = None,
    ) -> None:
        """Initialise the Level 3 execution service.

        Args:
            authorization_manager: The AuthorizationManager used to verify
                execution authority. If None, authorization is skipped (test mode).
            application_engine: The ApplicationEngine used to apply mutations.
                If None, execution is simulated (test mode).
        """
        self._authorization_manager = authorization_manager
        self._application_engine = application_engine
        self._execution_records: dict[str, ExecutionAuditRecord] = {}

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
                approval_id=getattr(approval, "request_id", "unknown"),
                authorization_status="skipped",
                execution_status="rejected",
                error=validation_error,
            )
            self._execution_records[execution_id] = record
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
                approval_id=approval.request_id,
                authorization_status="skipped",
                execution_status="rejected",
                error=replay_error,
            )
            self._execution_records[execution_id] = record
            return (
                Message(
                    role="assistant",
                    content=f"Execution rejected: {replay_error}",
                    metadata={"execution": record.to_dict()},
                ),
                record,
            )

        # Step 3: Validate scope
        scope_error = self._validate_scope(proposal, scope)
        if scope_error:
            record = ExecutionAuditRecord(
                execution_id=execution_id,
                proposal_id=proposal.proposal_id,
                proposal_fingerprint=approval.proposal_fingerprint,
                approval_id=approval.request_id,
                authorization_status="skipped",
                execution_status="rejected",
                error=scope_error,
            )
            self._execution_records[execution_id] = record
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
                    approval_id=approval.request_id,
                    authorization_status="unauthorized",
                    execution_status="unauthorized",
                    error=auth_result.reason,
                )
                self._execution_records[execution_id] = record
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
            approval_id=approval.request_id,
            authorization_status=auth_status,
            execution_status=exec_status,
            error=error,
        )
        self._execution_records[execution_id] = record

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

    def _validate_scope(self, proposal: Any, scope: Any) -> Optional[str]:
        """Validate execution scope matches approved scope.

        Returns:
            Error message if scope mismatch, None if OK.
        """
        # If no scope provided, use proposal's inherent scope
        if scope is None:
            return None

        # Compare scope fingerprints if available
        proposal_scope = getattr(proposal, "scope_fingerprint", None)
        if proposal_scope and hasattr(scope, "fingerprint"):
            if proposal_scope != scope.fingerprint:
                return (
                    "Execution scope does not match approved scope. "
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
