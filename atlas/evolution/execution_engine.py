"""
Atlas EvolutionExecutionEngine — Phase 11.0

Orchestrates the execution lifecycle for approved evolution proposals.
Operates at Level 0 (ADMINISTRATIVE) in Phase 11 — record-keeping only.

Delegates approval flow to ApprovalManager, stores execution records in
EvolutionMemory, and creates TrackedGoals via OutcomeTracker for later
outcome verification.

This is a pure logic orchestrator with no infrastructure dependencies.
It receives all dependencies via constructor injection.

Execution capability levels (defined in atlas/evolution/models.py):
  ADMINISTRATIVE = 0   Phase 11: record-keeping only
  SELF_CONFIG     = 1  Phase 12+: modify internal Atlas configuration
  INFORMATION     = 2  Phase 12+: modify memory, knowledge, world model
  CODE_ARTIFACT   = 3  Phase 13+: generate code patches
  SANDBOXED       = 4  Phase 14+: apply changes in sandbox, test, rollback
  AUTONOMOUS      = 5  Future: self-directed improvement

Phase 11 implements ADMINISTRATIVE only.
"""

from datetime import datetime
from typing import Any

from atlas.evolution.models import (
    ApprovalRequest,
    EvolutionProposal,
    EvolutionRecord,
    ExecutionLevel,
    ExecutionResult,
    ProposalStatus,
)


class _TrackableProposal:
    """
    Adapter wrapping an object with .proposal_id and .title for
    OutcomeTracker compatibility.

    OutcomeTracker.track_recommendation() expects .item_id and .problem
    (the protocol of GoalIntelligence RecommendationItem). EvolutionProposal
    uses 'proposal_id' and 'title' with __slots__ so we can't alias.
    This adapter bridges the gap for any duck-typed object with those
    attributes.
    """

    __slots__ = ("_proposal",)

    def __init__(self, proposal: Any) -> None:
        self._proposal = proposal

    @property
    def item_id(self) -> str:
        return self._proposal.proposal_id

    @property
    def problem(self) -> str:
        return self._proposal.title


class EvolutionExecutionEngine:
    """
    Orchestrates the full lifecycle for evolution proposals.

    Dependencies are all optional via injection. Missing dependencies
    cause operations to be skipped gracefully, preserving backward
    compatibility and enabling incremental testing.

    The engine's approval methods (approve_proposal, reject_proposal,
    defer_proposal) delegate to ApprovalManager for the pure logic of
    state transitions. The engine provides the orchestration layer:
    validation, execution, record-keeping, and outcome tracking.

    The execute() method is gated by ExecutionLevel. Phase 11 operates
    at ADMINISTRATIVE — it records the execution and creates a
    TrackedGoal for future verification, but performs no system changes.
    """

    def __init__(
        self,
        approval_manager: Any = None,
        evolution_memory: Any = None,
        outcome_tracker: Any = None,
        execution_level: ExecutionLevel = ExecutionLevel.ADMINISTRATIVE,
        knowledge_pipeline: Any = None,
    ):
        """
        Initialise the execution engine.

        Args:
            approval_manager: An ApprovalManager instance for approval
                workflow logic. Optional — if None, approval methods raise.
            evolution_memory: An EvolutionMemory instance for storing
                execution records. Optional — if None, records are not stored.
            outcome_tracker: An OutcomeTracker instance for creating
                TrackedGoal records. Optional — if None, tracking is skipped.
            execution_level: The capability level for this engine instance.
                Phase 11 uses ADMINISTRATIVE.
            knowledge_pipeline: Optional EvolutionKnowledgePipeline for
                automatic consolidation of execution records.
                Skipped if None.
        """
        self._approval_manager = approval_manager
        self._evolution_memory = evolution_memory
        self._outcome_tracker = outcome_tracker
        self._execution_level = execution_level
        self._knowledge_pipeline = knowledge_pipeline
        self._record_counter = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def execution_level(self) -> ExecutionLevel:
        """Return the current execution capability level."""
        return self._execution_level

    @property
    def approval_manager(self):
        """Return the injected ApprovalManager, or None."""
        return self._approval_manager

    @property
    def evolution_memory(self):
        """Return the injected EvolutionMemory, or None."""
        return self._evolution_memory

    @property
    def outcome_tracker(self):
        """Return the injected OutcomeTracker, or None."""
        return self._outcome_tracker

    # ------------------------------------------------------------------
    # Approval lifecycle
    # ------------------------------------------------------------------

    def approve_proposal(
        self,
        proposal: EvolutionProposal,
        request: ApprovalRequest,
        comment: str = "",
        latest_experience_id: str = "",
    ) -> ExecutionResult:
        """
        Approve a pending proposal and execute it.

        Orchestrates: ApprovalManager.approve() → ApprovalManager
        .update_proposal_from_decision() → execute().

        Args:
            proposal: The EvolutionProposal to approve.
            request: The ApprovalRequest associated with the proposal.
            comment: Optional user comment on the approval.
            latest_experience_id: Optional ID of the latest experience
                for outcome tracking linkage.

        Returns:
            An ExecutionResult describing the outcome.
        """
        if self._approval_manager is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error="ApprovalManager is not available.",
            )

        try:
            self._approval_manager.approve(request, comment=comment)
            self._approval_manager.update_proposal_from_decision(proposal, request)
        except ValueError as exc:
            return ExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error=str(exc),
            )

        # Decision-persistence closure: the decided request must survive a
        # restart, otherwise an executed proposal reappears PENDING_APPROVAL.
        if self._evolution_memory is not None:
            self._evolution_memory.update_approval_request(request)

        return self.execute(
            proposal=proposal,
            latest_experience_id=latest_experience_id,
        )

    def reject_proposal(
        self,
        proposal: EvolutionProposal,
        request: ApprovalRequest,
        reason: str,
        comment: str = "",
    ) -> ExecutionResult:
        """
        Reject a pending proposal without execution.

        Delegates to ApprovalManager.reject() and records the outcome.

        Args:
            proposal: The EvolutionProposal to reject.
            request: The ApprovalRequest associated with the proposal.
            reason: The reason for rejection (required).
            comment: Optional additional user comment.

        Returns:
            An ExecutionResult describing the outcome.
        """
        if self._approval_manager is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error="ApprovalManager is not available.",
            )

        try:
            self._approval_manager.reject(request, reason=reason)
            self._approval_manager.update_proposal_from_decision(proposal, request)
        except ValueError as exc:
            return ExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error=str(exc),
            )

        self._store_rejection_record(proposal, request)

        # Decision-persistence closure: rejected proposals must not fall
        # back to their pre-decision status after a restart.
        if self._evolution_memory is not None:
            self._evolution_memory.store_proposal(proposal)
            self._evolution_memory.update_approval_request(request)

        return ExecutionResult(
            success=True,
            proposal_id=proposal.proposal_id,
            status=ProposalStatus.REJECTED.name,
        )

    def defer_proposal(
        self,
        proposal: EvolutionProposal,
        request: ApprovalRequest,
        reason: str = "",
    ) -> ExecutionResult:
        """
        Defer a pending proposal for later consideration.

        Delegates to ApprovalManager.defer().

        Args:
            proposal: The EvolutionProposal to defer.
            request: The ApprovalRequest associated with the proposal.
            reason: Optional reason for deferring.

        Returns:
            An ExecutionResult describing the outcome.
        """
        if self._approval_manager is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error="ApprovalManager is not available.",
            )

        try:
            self._approval_manager.defer(request, reason=reason)
            self._approval_manager.update_proposal_from_decision(proposal, request)
        except ValueError as exc:
            return ExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error=str(exc),
            )

        # Decision-persistence closure: deferred proposals must not fall
        # back to their pre-decision status after a restart.
        if self._evolution_memory is not None:
            self._evolution_memory.store_proposal(proposal)
            self._evolution_memory.update_approval_request(request)

        return ExecutionResult(
            success=True,
            proposal_id=proposal.proposal_id,
            status=ProposalStatus.DEFERRED.name,
        )

    # ------------------------------------------------------------------
    # Proposal execution (administrative only, Phase 11)
    # ------------------------------------------------------------------

    def execute(
        self,
        proposal: EvolutionProposal,
        latest_experience_id: str = "",
    ) -> ExecutionResult:
        """
        Execute an approved proposal at the configured execution level.

        Phase 11 (ADMINISTRATIVE): Creates an EvolutionRecord, stores it
        in EvolutionMemory, creates a TrackedGoal via OutcomeTracker,
        and updates the proposal status to IMPLEMENTED.

        Args:
            proposal: An EvolutionProposal with status APPROVED.
            latest_experience_id: Optional ID of the latest experience
                for outcome tracking linkage.

        Returns:
            An ExecutionResult describing the outcome.
        """
        # Validate proposal state — a refused governed execution is still an
        # execution outcome and must be recorded, never silently discarded.
        if proposal.status != ProposalStatus.APPROVED:
            error = (
                f"Cannot execute proposal '{proposal.proposal_id}' "
                f"with status '{proposal.status.name}'. "
                f"Proposal must be APPROVED."
            )
            self._store_execution_failure(proposal, error)
            return ExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error=error,
            )

        # Update proposal status to IMPLEMENTED
        proposal.status = ProposalStatus.IMPLEMENTED
        proposal.metadata["executed_at"] = datetime.now().isoformat()

        # Persist the updated proposal so status is not lost on restart
        if self._evolution_memory is not None:
            self._evolution_memory.store_proposal(proposal)

        # Create a TrackedGoal for outcome verification FIRST so the
        # execution record below can carry the tracked_goal_id (F7: a
        # single complete representation of the execution outcome).
        tracked_goal_id = ""
        if self._outcome_tracker is not None:
            try:
                goal = self._outcome_tracker.track_recommendation(
                    recommendation=self._as_trackable(proposal),
                    related_experience_id=latest_experience_id,
                )
                if goal is not None:
                    tracked_goal_id = goal.goal_id
            except Exception:
                # Tracking failures should not block execution
                pass

        # Create and store the execution record with its outcome metadata.
        record = self._create_execution_record(
            proposal,
            success=True,
            error="",
            status=ProposalStatus.IMPLEMENTED.name,
            tracked_goal_id=tracked_goal_id,
        )
        if self._evolution_memory is not None:
            self._evolution_memory.store_record(record)

        # Feed execution record into knowledge pipeline for consolidation
        if self._knowledge_pipeline is not None:
            try:
                self._knowledge_pipeline.consolidate()
            except Exception:
                pass

        return ExecutionResult(
            success=True,
            proposal_id=proposal.proposal_id,
            status=ProposalStatus.IMPLEMENTED.name,
            record_id=record.record_id,
            tracked_goal_id=tracked_goal_id,
        )

    # ------------------------------------------------------------------
    # Convenience methods (for CLI — accept proposal_id strings)
    # ------------------------------------------------------------------

    def approve_proposal_by_id(
        self,
        proposal_id: str,
        comment: str = "",
        latest_experience_id: str = "",
    ) -> ExecutionResult:
        """
        Approve a proposal by its ID. Looks up the proposal and its
        associated approval request from EvolutionMemory.

        Args:
            proposal_id: The ID of the proposal to approve.
            comment: Optional user comment.
            latest_experience_id: Optional experience ID for tracking.

        Returns:
            An ExecutionResult describing the outcome.
        """
        if self._evolution_memory is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error="EvolutionMemory is not available.",
            )

        proposal = self._evolution_memory.get_proposal(proposal_id)
        if proposal is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error=f"Proposal '{proposal_id}' not found.",
            )

        # Find the matching approval request
        request = self._find_approval_request(proposal_id)
        if request is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error=f"No approval request found for proposal '{proposal_id}'.",
            )

        return self.approve_proposal(
            proposal=proposal,
            request=request,
            comment=comment,
            latest_experience_id=latest_experience_id,
        )

    def reject_proposal_by_id(
        self,
        proposal_id: str,
        reason: str,
        comment: str = "",
    ) -> ExecutionResult:
        """
        Reject a proposal by its ID. Looks up the proposal and its
        associated approval request from EvolutionMemory.

        Args:
            proposal_id: The ID of the proposal to reject.
            reason: The reason for rejection.
            comment: Optional additional user comment.

        Returns:
            An ExecutionResult describing the outcome.
        """
        if self._evolution_memory is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error="EvolutionMemory is not available.",
            )

        proposal = self._evolution_memory.get_proposal(proposal_id)
        if proposal is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error=f"Proposal '{proposal_id}' not found.",
            )

        request = self._find_approval_request(proposal_id)
        if request is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error=f"No approval request found for proposal '{proposal_id}'.",
            )

        return self.reject_proposal(
            proposal=proposal,
            request=request,
            reason=reason,
            comment=comment,
        )

    def defer_proposal_by_id(
        self,
        proposal_id: str,
        reason: str = "",
    ) -> ExecutionResult:
        """
        Defer a proposal by its ID. Looks up the proposal and its
        associated approval request from EvolutionMemory.

        Args:
            proposal_id: The ID of the proposal to defer.
            reason: Optional reason for deferring.

        Returns:
            An ExecutionResult describing the outcome.
        """
        if self._evolution_memory is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error="EvolutionMemory is not available.",
            )

        proposal = self._evolution_memory.get_proposal(proposal_id)
        if proposal is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error=f"Proposal '{proposal_id}' not found.",
            )

        request = self._find_approval_request(proposal_id)
        if request is None:
            return ExecutionResult(
                success=False,
                proposal_id=proposal_id,
                error=f"No approval request found for proposal '{proposal_id}'.",
            )

        return self.defer_proposal(
            proposal=proposal,
            request=request,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Query methods (for CLI presentation layer)
    # ------------------------------------------------------------------

    def list_proposals(
        self,
        pending_only: bool = False,
    ) -> list[EvolutionProposal]:
        """
        Return all stored proposals, newest first.

        Args:
            pending_only: If True, return only PENDING_APPROVAL proposals.

        Returns:
            A list of EvolutionProposal instances, or empty list if
            EvolutionMemory is not available.
        """
        if self._evolution_memory is None:
            return []

        if pending_only:
            return self._evolution_memory.get_proposals_by_status(
                ProposalStatus.PENDING_APPROVAL,
            )
        return self._evolution_memory.get_all_proposals()

    def get_proposal(
        self,
        proposal_id: str,
    ) -> EvolutionProposal | None:
        """
        Retrieve a single proposal by its ID.

        Args:
            proposal_id: The proposal identifier.

        Returns:
            The EvolutionProposal, or None if not found.
        """
        if self._evolution_memory is None:
            return None
        return self._evolution_memory.get_proposal(proposal_id)

    # ------------------------------------------------------------------
    # Read-only audit surface (Post-Core F8)
    # ------------------------------------------------------------------

    def get_proposal_audit(self, proposal_id: str) -> dict[str, Any] | None:
        """
        Return a read-only audit projection for a proposal.

        Post-Core F8 — Audit/visibility: combines the proposal's own
        fields with the current approval decision and the execution
        outcome already represented by the F7 EvolutionRecord metadata.
        Never mutates state, never executes, and never touches governance.

        Args:
            proposal_id: The proposal identifier.

        Returns:
            A stable dictionary projection, or None if the proposal is
            unknown.
        """
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            return None

        approval = None
        request = self._find_approval_request(proposal_id)
        if request is not None:
            from atlas.evolution.models import ApprovalDecision

            decision = getattr(request, "decision", ApprovalDecision.PENDING)
            approval = {
                "decision": (
                    decision.name if hasattr(decision, "name") else str(decision)
                ),
                "comment": getattr(request, "decision_comment", ""),
                "decided_at": self._format_timestamp(
                    getattr(request, "decided_at", None)
                ),
            }

        execution = None
        record = self._find_execution_record(proposal_id)
        if record is not None:
            execution = {
                "record_id": record.record_id,
                "success": bool(record.metadata.get("success", True)),
                "error": str(record.metadata.get("error", "")),
                "status": str(record.metadata.get("status", "")),
                "tracked_goal_id": str(record.metadata.get("tracked_goal_id", "")),
            }

        return {
            "proposal_id": proposal.proposal_id,
            "title": proposal.title,
            "status": proposal.status.name,
            "priority": proposal.plan.priority.name,
            "created_at": self._format_timestamp(proposal.created_at),
            "approved_at": self._format_timestamp(proposal.approved_at),
            "rejection_reason": proposal.rejection_reason,
            "approval": approval,
            "execution": execution,
        }

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        """Format a timestamp deterministically for audit output."""
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _find_execution_record(
        self,
        proposal_id: str,
    ) -> EvolutionRecord | None:
        """Find the execution EvolutionRecord for a proposal."""
        if self._evolution_memory is None:
            return None
        for record in self._evolution_memory.get_records_by_type("execution"):
            if proposal_id in record.related_ids:
                return record
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_trackable(proposal: Any) -> Any:
        """
        Wrap an EvolutionProposal so OutcomeTracker can read item_id and problem.

        OutcomeTracker.track_recommendation() expects objects with .item_id
        and .problem attributes (the protocol used by GoalIntelligence
        RecommendationItem). EvolutionProposal uses 'proposal_id' and 'title'
        with __slots__ so we can't add aliases — this adapter bridges the gap.
        """
        return _TrackableProposal(proposal)

    def _find_approval_request(
        self,
        proposal_id: str,
    ) -> ApprovalRequest | None:
        """Find the approval request associated with a proposal."""
        if self._evolution_memory is None:
            return None
        for req in self._evolution_memory.get_all_approval_requests():
            if req.proposal_id == proposal_id:
                return req
        return None

    def _next_record_id(self) -> str:
        """Generate a unique evolution record identifier."""
        self._record_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"EVR-{timestamp}-{self._record_counter:04d}"

    def _create_execution_record(
        self,
        proposal: EvolutionProposal,
        success: bool = True,
        error: str = "",
        status: str = "",
        tracked_goal_id: str = "",
    ) -> EvolutionRecord:
        """
        Create an EvolutionRecord documenting a proposal execution.

        Post-Core F7: the record carries the execution's own outcome
        (``success``, ``error``, ``status``, ``tracked_goal_id``) in
        metadata so EvolutionIntelligenceEngine can deterministically
        classify the execution — including a failed governed execution
        as a failure — without duplicating representation.

        Args:
            proposal: The executed EvolutionProposal.
            success: Whether the execution attempt succeeded.
            error: Error message when the execution failed.
            status: Final status name of the proposal after the attempt.
            tracked_goal_id: ID of the TrackedGoal created for this
                execution (empty when tracking is unavailable).

        Returns:
            An EvolutionRecord with event_type "execution".
        """
        verb = "Executed" if success else "Failed to execute"
        return EvolutionRecord(
            record_id=self._next_record_id(),
            event_type="execution",
            description=(
                f"{verb} proposal '{proposal.proposal_id}': "
                f"{proposal.title}. {proposal.summary[:100]}"
            ),
            related_ids=[proposal.proposal_id],
            metadata={
                "execution_level": self._execution_level.name,
                "proposal_title": proposal.title,
                "proposal_summary": proposal.summary,
                "success": success,
                "error": error,
                "status": status or proposal.status.name,
                "tracked_goal_id": tracked_goal_id,
            },
        )

    def _store_execution_failure(
        self,
        proposal: EvolutionProposal,
        error: str,
    ) -> None:
        """Record a failed execution attempt in EvolutionMemory.

        Post-Core F7: failed governed executions are never silently
        discarded — they become deterministic failure records consumed by
        EvolutionIntelligenceEngine so the next improvement-analysis cycle
        can account for them.
        """
        if self._evolution_memory is None:
            return
        record = self._create_execution_record(
            proposal,
            success=False,
            error=error,
            status=proposal.status.name,
        )
        self._evolution_memory.store_record(record)

    def _store_rejection_record(
        self,
        proposal: EvolutionProposal,
        request: ApprovalRequest,
    ) -> None:
        """Store a rejection record in EvolutionMemory if available."""
        if self._evolution_memory is None:
            return

        record = EvolutionRecord(
            record_id=self._next_record_id(),
            event_type="rejection",
            description=(
                f"Rejected proposal '{proposal.proposal_id}': "
                f"{proposal.title}. Reason: {request.decision_comment}"
            ),
            related_ids=[proposal.proposal_id],
        )
        self._evolution_memory.store_record(record)
