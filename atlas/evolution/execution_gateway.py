"""
Atlas Evolution Execution Gateway — Phase 13.4

The constitutional execution gate for evolution proposals.

The gateway is the ONLY future entry point for self-modification.
It sits between the approval workflow and EvolutionExecutionEngine:

    Approved proposal → ExecutionGateway → RuleEngine.evaluate()
                                              │
                            approved?        │
                            ├─ yes ──▶ EvolutionExecutionEngine.execute()
                            └─ no  ──▶ refusal EvolutionRecord

The gateway does NOT add any execution capability of its own. Atlas
still cannot modify itself. Execution remains ADMINISTRATIVE: approved
proposals are recorded as implemented, refused proposals are recorded
for audit, and nothing is ever changed, written, or executed.

Guarantees:
  - Never mutates proposal status on refusal.
  - Never calls EvolutionExecutionEngine when governance denies execution.
  - Fails CLOSED: a missing RuleEngine always refuses execution.
  - Fully deterministic: the same proposal and level always produce
    the same result.
  - Pure logic. No threading. No async. No AI. No infrastructure.

Phase 13.4 — Evolution Execution Gateway.
"""

from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import (
    EvolutionProposal,
    EvolutionRecord,
    ExecutionLevel,
    GatewayExecutionResult,
    ProposalStatus,
)

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestExecutionResult:
    """Outcome of ``execute_request()`` — the request-oriented gateway path.

    Unlike the proposal-oriented ``GatewayExecutionResult``, this carries the
    (possibly updated) ``EvolutionRequest`` produced by ``application_engine``.

    Attributes:
        request: The request after the apply attempt. On success this carries
            COMPLETED / PENDING_EFFECTIVE plus receipt, verification and
            rollback fields. On a governance refusal it is the unchanged input.
        success: True only when ``application_engine.apply`` succeeded.
        terminal_status: COMPLETED, PENDING_EFFECTIVE, FAILED, or REFUSED.
        governance_decision: The RuleEngine decision (None if not evaluated).
        error: Human-readable error when success is False.
    """

    request: EvolutionRequest
    success: bool
    terminal_status: str = "FAILED"
    governance_decision: Any = None
    error: str = ""


class EvolutionExecutionGateway:
    """
    Constitutional gate for evolution proposal execution.

    Wraps EvolutionExecutionEngine and validates every execution
    against governance rules before delegation. The gateway is the
    single choke point that future self-modification phases must
    pass through.

    Dependencies are injected via constructor:
      - rule_engine: Required. Evaluates proposals against governance
        constraints. Missing RuleEngine fails CLOSED.
      - execution_engine: Required. Performs the actual (currently
        administrative) execution for governance-approved proposals.
      - evolution_memory: Optional. Stores refusal records for audit.
        Missing memory degrades gracefully — execution results are
        still returned, only persistence is skipped.
      - current_execution_level: The engine's capability level.
        Defaults to ADMINISTRATIVE. Future phases raise this bar.
      - application_engine: Optional (Batch 13). Required for the governed
        ``execute_request()`` path; missing ⇒ fail-closed refusal. Injected
        here, NOT held by the autonomy package (Phase 16 D15).
      - autonomy_request_adapter: Optional (Batch 13). Translates an
        ``EvolutionRequest`` into the scope-pinned ``EvolutionProposal`` the
        RuleEngine requires. Missing ⇒ fail-closed refusal.

    Pure logic. No side effects beyond the injected dependencies.
    """

    def __init__(
        self,
        execution_engine: Any,
        rule_engine: Any = None,
        evolution_memory: Any = None,
        current_execution_level: ExecutionLevel = ExecutionLevel.ADMINISTRATIVE,
        application_engine: Any = None,
        autonomy_request_adapter: Any = None,
    ):
        """
        Initialise the execution gateway.

        Args:
            execution_engine: An EvolutionExecutionEngine instance
                that performs the actual execution once governance
                approves it. Required.
            rule_engine: A RuleEngine instance evaluating proposals
                against governance constraints. Required — a missing
                engine fails CLOSED.
            evolution_memory: An EvolutionMemory instance for storing
                refusal audit records. Optional — if None, refusals
                are returned without persistence.
            current_execution_level: The current ExecutionLevel.
                Phase 13.4 uses ADMINISTRATIVE.
            application_engine: Optional ApplicationEngine reached only via
                ``execute_request()`` (Phase 16 D3/D15).
            autonomy_request_adapter: Optional ``AutonomyRequestAdapter``
                translating an ``EvolutionRequest`` into an ``EvolutionProposal``.
        """
        self._execution_engine = execution_engine
        self._rule_engine = rule_engine
        self._evolution_memory = evolution_memory
        self._current_execution_level = current_execution_level
        self._application_engine = application_engine
        self._autonomy_request_adapter = autonomy_request_adapter
        self._record_counter = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def execution_engine(self):
        """Return the injected EvolutionExecutionEngine, or None."""
        return self._execution_engine

    @property
    def rule_engine(self):
        """Return the injected RuleEngine, or None."""
        return self._rule_engine

    @property
    def evolution_memory(self):
        """Return the injected EvolutionMemory, or None."""
        return self._evolution_memory

    @property
    def application_engine(self) -> Any:
        """Return the injected ApplicationEngine, or None."""
        return self._application_engine

    @property
    def autonomy_request_adapter(self) -> Any:
        """Return the injected AutonomyRequestAdapter, or None."""
        return self._autonomy_request_adapter

    @property
    def execution_level(self) -> ExecutionLevel:
        """Return the current execution capability level."""
        return self._current_execution_level

    def set_execution_level(self, level: ExecutionLevel) -> None:
        """Raise or lower the current execution capability level.

        Future phases raise this bar to unlock additional scopes.
        The level is an explicit, auditable configuration — never
        derived from behavior.
        """
        self._current_execution_level = level

    # ------------------------------------------------------------------
    # Evaluation (side-effect free)
    # ------------------------------------------------------------------

    def evaluate(self, proposal: EvolutionProposal) -> Any:
        """
        Evaluate a proposal against governance constraints.

        This is a pure query: it never mutates the proposal and never
        executes anything. Used to inspect whether a proposal would be
        executable at the current level.

        Args:
            proposal: The EvolutionProposal to evaluate.

        Returns:
            A GovernanceDecision. If no RuleEngine is available, a
            fail-closed rejection decision is returned.
        """
        if self._rule_engine is None:
            from atlas.evolution.governance.models import GovernanceDecision

            return GovernanceDecision(
                approved=False,
                reason=(
                    "RuleEngine is not available. Execution gateway "
                    "fails closed — no proposal can be executed."
                ),
                violated_rules=["GATEWAY-FAIL-CLOSED"],
            )

        return self._rule_engine.evaluate(
            proposal=proposal,
            current_level=self._current_execution_level,
        )

    # ------------------------------------------------------------------
    # Gated execution
    # ------------------------------------------------------------------

    def execute(
        self,
        proposal: EvolutionProposal,
        latest_experience_id: str = "",
    ) -> GatewayExecutionResult:
        """
        Execute an approved proposal through the governance gate.

        The gate sequence:
          1. Fail CLOSED if the RuleEngine is missing.
          2. Return an error if the EvolutionExecutionEngine is missing.
          3. Validate that the proposal is APPROVED.
          4. Evaluate governance. If rejected:
               - store a refusal audit record (if memory available)
               - return a refusal result — the proposal is NOT mutated
                 and the execution engine is NOT called.
          5. If approved: delegate to EvolutionExecutionEngine.execute()
             and pass through its result.

        Args:
            proposal: An EvolutionProposal with status APPROVED.
            latest_experience_id: Optional ID of the latest experience
                for outcome tracking linkage.

        Returns:
            A GatewayExecutionResult describing the outcome.
        """
        # Fail closed: no rule engine → no execution, ever.
        if self._rule_engine is None:
            return GatewayExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                status="REFUSED",
                error=(
                    "RuleEngine is not available. Execution gateway "
                    "fails closed — execution is refused."
                ),
            )

        if self._execution_engine is None:
            return GatewayExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                status="",
                error="EvolutionExecutionEngine is not available.",
            )

        if proposal.status != ProposalStatus.APPROVED:
            return GatewayExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                status="",
                error=(
                    f"Cannot execute proposal '{proposal.proposal_id}' "
                    f"with status '{proposal.status.name}'. "
                    f"Proposal must be APPROVED."
                ),
            )

        decision = self._rule_engine.evaluate(
            proposal=proposal,
            current_level=self._current_execution_level,
        )

        # Governance denied → refusal audit record, no execution.
        if not decision.approved:
            record_id = self._store_refusal_record(proposal, decision)
            return GatewayExecutionResult(
                success=False,
                proposal_id=proposal.proposal_id,
                status="REFUSED",
                governance_decision=decision,
                record_id=record_id,
                error=(
                    f"Governance denied execution: {decision.reason}"
                ),
            )

        # Governance approved → delegate unchanged to the engine.
        result = self._execution_engine.execute(
            proposal=proposal,
            latest_experience_id=latest_experience_id,
        )

        return GatewayExecutionResult(
            success=result.success,
            proposal_id=result.proposal_id,
            status=result.status,
            governance_decision=decision,
            record_id=result.record_id,
            tracked_goal_id=result.tracked_goal_id,
            error=result.error,
        )

    def execute_request(self, request: EvolutionRequest) -> RequestExecutionResult:
        """Execute an already-authorized ``EvolutionRequest`` governed request.

        Sole applied-evolution path (Phase 16 D3/D10). The gate sequence:

          1. Fail CLOSED if either ``application_engine`` or
             ``autonomy_request_adapter`` is missing.
          2. UNKNOWN-close invariant: refuse UNKNOWN / IDENTITY / CODE scopes
             unconditionally, regardless of level.
          3. Fail CLOSED if the RuleEngine is missing.
          4. Translate the request into a scope-pinned ``EvolutionProposal``
             (status APPROVED) via ``AutonomyRequestAdapter`` (closed map).
          5. Evaluate governance at the current execution level. If rejected,
             store a refusal audit record (if memory available) and return a
             refusal — the engine is never called.
          6. If approved, delegate to ``application_engine.apply(request)``.

        ``execute(proposal)`` (the administrative proposal path) is unchanged.

        Args:
            request: The governed request to apply.

        Returns:
            A RequestExecutionResult carrying the updated request.
        """
        # Fail closed — required request-execution dependencies missing.
        if self._application_engine is None:
            return RequestExecutionResult(
                request=request,
                success=False,
                terminal_status="REFUSED",
                error="ApplicationEngine is not available for request execution.",
            )
        if self._autonomy_request_adapter is None:
            return RequestExecutionResult(
                request=request,
                success=False,
                terminal_status="REFUSED",
                error=(
                    "AutonomyRequestAdapter is not available for request "
                    "execution."
                ),
            )
        if self._rule_engine is None:
            return RequestExecutionResult(
                request=request,
                success=False,
                terminal_status="REFUSED",
                error=(
                    "RuleEngine is not available. Execution gateway fails "
                    "closed — no request can be executed."
                ),
            )

        # UNKNOWN-close invariant — refuse constitutionally protected scopes
        # regardless of execution level.
        if request.target_scope in {
            ScopeType.UNKNOWN,
            ScopeType.IDENTITY,
            ScopeType.CODE,
        }:
            return RequestExecutionResult(
                request=request,
                success=False,
                terminal_status="REFUSED",
                error=(
                    f"Scope {request.target_scope.name} is constitutionally "
                    "protected and cannot be executed."
                ),
            )

        # Governed translation → scope-pinned APPROVED proposal (closed map).
        proposal = self._autonomy_request_adapter.to_proposal(request)

        decision = self._rule_engine.evaluate(
            proposal=proposal,
            current_level=self._current_execution_level,
        )

        # Governance denied → refusal audit record, no engine call.
        if not decision.approved:
            record_id = self._store_request_refusal(request, proposal, decision)
            return RequestExecutionResult(
                request=request,
                success=False,
                terminal_status="REFUSED",
                governance_decision=decision,
                error=f"Governance denied request execution: {decision.reason}",
            )

        # Governance approved → delegate to the sole application engine.
        result = self._application_engine.apply(request)
        return RequestExecutionResult(
            request=result.request,
            success=result.success,
            terminal_status=result.terminal_status,
            governance_decision=decision,
            error=result.error,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store_refusal_record(
        self,
        proposal: EvolutionProposal,
        decision: Any,
    ) -> str:
        """
        Store a refusal audit record in EvolutionMemory if available.

        Args:
            proposal: The proposal that was refused.
            decision: The GovernanceDecision that refused it.

        Returns:
            The record ID, or empty string if no record was stored.
        """
        if self._evolution_memory is None:
            return ""

        record = EvolutionRecord(
            record_id=self._next_record_id(),
            event_type="refusal",
            description=(
                f"Refused execution of proposal "
                f"'{proposal.proposal_id}': {proposal.title}. "
                f"Reason: {decision.reason}"
            ),
            related_ids=[proposal.proposal_id],
            metadata={
                "execution_level": self._current_execution_level.name,
                "proposal_title": proposal.title,
                "violated_rules": list(decision.violated_rules),
            },
        )
        self._evolution_memory.store_record(record)
        return record.record_id

    def _store_request_refusal(
        self,
        request: EvolutionRequest,
        proposal: EvolutionProposal,
        decision: Any,
    ) -> str:
        """Store a refusal audit record for a refused governed request.

        Reuses the existing ``EvolutionRecord``/``EvolutionMemory`` audit
        surface so a governance-refused request is recorded, not swallowed.

        Returns:
            The record ID, or empty string if no record was stored.
        """
        if self._evolution_memory is None:
            return ""
        record = EvolutionRecord(
            record_id=self._next_record_id(),
            event_type="refusal",
            description=(
                f"Refused execution of request '{request.request_id}' "
                f"(proposal '{proposal.proposal_id}'). Reason: {decision.reason}"
            ),
            related_ids=[request.request_id, proposal.proposal_id],
            metadata={
                "execution_level": self._current_execution_level.name,
                "target_scope": request.target_scope.name,
                "source_request_id": request.request_id,
                "violated_rules": list(decision.violated_rules),
            },
        )
        self._evolution_memory.store_record(record)
        return record.record_id

    def _next_record_id(self) -> str:
        """Generate a unique evolution record identifier."""
        self._record_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"GWR-{timestamp}-{self._record_counter:04d}"
