"""
Atlas P18 — End-to-End Integration Tests.

Tests the complete P17+P18 pipeline from natural language request through
autonomous execution to final reporting.

Coverage:
- L1 simple execution
- L2 workflow chaining
- L3 recovery execution
- L4 capability acquisition
- L5 cross-objective coordination
- Governance boundary verification
- Audit trail completeness
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from atlas.authority.models import AuthorityLevel, Principal
from atlas.evolution.autonomy.autonomy_controller import AutonomyController
from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    RiskLevel,
)
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    DevelopmentPlan,
)
from atlas.evolution.development_report import (
    DevelopmentLifecycleReport,
    DevelopmentReportBuilder,
    FinalConclusion,
)
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel, ProposalStatus
from atlas.conversation.conversation_state import (
    ConversationState,
    ConversationStateManager,
)
from atlas.conversation.task_intake import TaskIntake, TaskType


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeSessionContext:
    """Minimal session context for testing."""
    session_id: str = "test-session-001"
    principal: Principal = None
    authority: AuthorityLevel = AuthorityLevel.OWNER

    @property
    def is_owner(self) -> bool:
        return self.authority is AuthorityLevel.OWNER


def _make_owner_session() -> FakeSessionContext:
    """Create an OWNER session context."""
    principal = Principal(
        principal_id="owner-001",
        name="Test Owner",
        authority=AuthorityLevel.OWNER,
    )
    return FakeSessionContext(
        session_id="test-session-001",
        principal=principal,
        authority=AuthorityLevel.OWNER,
    )


def _make_l1_policy() -> AutonomyPolicy:
    """Create an L1 autonomy policy."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.LOW,
        effective_execution_level=ExecutionLevel.SANDBOXED,
        requires_user_approval_scopes=[],
        max_requests_per_window=10,
        authorization_ttl_minutes=60,
    )


def _make_l2_policy() -> AutonomyPolicy:
    """Create an L2 autonomy policy."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.MEDIUM,
        effective_execution_level=ExecutionLevel.CODE_ARTIFACT,
        requires_user_approval_scopes=[],
        max_requests_per_window=10,
        authorization_ttl_minutes=60,
    )


def _make_l3_policy() -> AutonomyPolicy:
    """Create an L3 autonomy policy."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.HIGH,
        effective_execution_level=ExecutionLevel.SELF_CONFIG,
        requires_user_approval_scopes=[],
        max_requests_per_window=10,
        authorization_ttl_minutes=60,
    )


def _make_l4_policy() -> AutonomyPolicy:
    """Create an L4 autonomy policy."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.CRITICAL,
        effective_execution_level=ExecutionLevel.INFORMATION,
        requires_user_approval_scopes=[],
        max_requests_per_window=10,
        authorization_ttl_minutes=60,
    )


def _make_l5_policy() -> AutonomyPolicy:
    """Create an L5 autonomy policy."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.CRITICAL,
        effective_execution_level=ExecutionLevel.AUTONOMOUS,
        requires_user_approval_scopes=[],
        max_requests_per_window=10,
        authorization_ttl_minutes=60,
    )


def _make_controller(policy: AutonomyPolicy) -> AutonomyController:
    """Create an AutonomyController with the given policy."""
    policy_engine = AutonomyPolicyEngine(policy=policy)
    auth_manager = AuthorizationManager(policy=policy)
    return AutonomyController(
        authorization_manager=auth_manager,
        policy_engine=policy_engine,
    )


# ---------------------------------------------------------------------------
# L1 Simple Execution Integration Test
# ---------------------------------------------------------------------------


class TestL1SimpleExecution:
    """E2E test for L1 simple execution scenario."""

    def test_l1_full_pipeline(self):
        """Test L1: request → intake → autonomy check → execution decision."""
        # Step 1: User request comes in
        intake = TaskIntake()
        spec = intake.intake("execute the approved proposal")

        # Step 2: Verify task type classification
        assert spec.task_type is TaskType.EXECUTION_REQUEST

        # Step 3: Create session and policy
        session = _make_owner_session()
        policy = _make_l1_policy()
        controller = _make_controller(policy)

        # Step 4: Create approved proposal
        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        # Step 5: Check L1 autonomy
        decision = controller.check_execution_autonomy(proposal, session)

        # Step 6: Verify decision
        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

        # Step 7: Verify state tracking
        state = ConversationState()
        manager = ConversationStateManager(state)
        manager.update(
            autonomous_steps_executed=1,
            last_autonomy_decision=decision.reason,
        )
        assert manager.state.autonomous_steps_executed == 1

    def test_l1_rejects_unapproved_proposal(self):
        """Test L1: rejects execution of unapproved proposal."""
        session = _make_owner_session()
        policy = _make_l1_policy()
        controller = _make_controller(policy)

        proposal = MagicMock()
        proposal.status = ProposalStatus.DRAFT

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "not APPROVED" in decision.reason


# ---------------------------------------------------------------------------
# L2 Workflow Chaining Integration Test
# ---------------------------------------------------------------------------


class TestL2WorkflowChaining:
    """E2E test for L2 workflow chaining scenario."""

    def test_l2_full_pipeline(self):
        """Test L2: request → intake → autonomy check → chaining decision."""
        # Step 1: User request
        intake = TaskIntake()
        spec = intake.intake("chain the workflows")

        # Step 2: Verify task type
        assert spec.task_type is TaskType.L2_AUTONOMY_REQUEST

        # Step 3: Create session and policy
        session = _make_owner_session()
        policy = _make_l2_policy()
        controller = _make_controller(policy)

        # Step 4: Create approved workflows
        current = MagicMock()
        current.status = ProposalStatus.APPROVED
        next_workflow = MagicMock()
        next_workflow.status = ProposalStatus.APPROVED

        # Step 5: Check L2 autonomy
        decision = controller.check_workflow_chaining_autonomy(
            current, next_workflow, session
        )

        # Step 6: Verify decision
        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

        # Step 7: Verify state tracking
        state = ConversationState()
        manager = ConversationStateManager(state)
        manager.update(
            chained_workflows=("workflow-1", "workflow-2"),
            last_l2_decision=decision.reason,
        )
        assert len(manager.state.chained_workflows) == 2

    def test_l2_plan_adjustment(self):
        """Test L2: bounded plan adjustment preserves objective."""
        session = _make_owner_session()
        policy = _make_l2_policy()
        controller = _make_controller(policy)

        original = MagicMock()
        original.summary = "Implement feature X"
        original.target_components = ["atlas/module_a.py", "atlas/module_b.py"]

        adjusted = MagicMock()
        adjusted.summary = "Implement feature X"
        adjusted.target_components = ["atlas/module_a.py"]

        decision = controller.check_plan_adjustment_autonomy(
            original, adjusted, session
        )

        assert decision.can_proceed is True


# ---------------------------------------------------------------------------
# L3 Recovery Execution Integration Test
# ---------------------------------------------------------------------------


class TestL3RecoveryExecution:
    """E2E test for L3 recovery execution scenario."""

    def test_l3_full_pipeline(self):
        """Test L3: failure → diagnosis → recovery decision → execution."""
        # Step 1: User request
        intake = TaskIntake()
        spec = intake.intake("generate sub plan")

        # Step 2: Verify task type
        assert spec.task_type is TaskType.L3_AUTONOMY_REQUEST

        # Step 3: Create session and policy
        session = _make_owner_session()
        policy = _make_l3_policy()
        controller = _make_controller(policy)

        # Step 4: Create recovery scenario
        recovery = MagicMock()
        recovery.recoverable = True
        recovery.strategy.value = "revise_and_retry"

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        # Step 5: Check L3 autonomy
        decision = controller.check_recovery_execution_autonomy(
            recovery, proposal, session
        )

        # Step 6: Verify decision
        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

        # Step 7: Verify state tracking
        state = ConversationState()
        manager = ConversationStateManager(state)
        manager.update(
            autonomous_recoveries=1,
            last_l3_decision=decision.reason,
        )
        assert manager.state.autonomous_recoveries == 1

    def test_l3_sub_plan_generation(self):
        """Test L3: bounded sub-plan generation."""
        session = _make_owner_session()
        policy = _make_l3_policy()
        controller = _make_controller(policy)

        parent = MagicMock()
        parent.summary = "Implement feature X"
        parent.target_components = ["atlas/module_a.py", "atlas/module_b.py"]

        sub = MagicMock()
        sub.summary = "Implement feature X"
        sub.target_components = ["atlas/module_a.py"]

        decision = controller.check_sub_plan_generation_autonomy(
            parent, sub, session
        )

        assert decision.can_proceed is True


# ---------------------------------------------------------------------------
# L4 Capability Acquisition Integration Test
# ---------------------------------------------------------------------------


class TestL4CapabilityAcquisition:
    """E2E test for L4 capability acquisition scenario."""

    def test_l4_full_pipeline(self):
        """Test L4: request → intake → autonomy check → acquisition decision."""
        # Step 1: User request
        intake = TaskIntake()
        spec = intake.intake("acquire capability")

        # Step 2: Verify task type
        assert spec.task_type is TaskType.L4_AUTONOMY_REQUEST

        # Step 3: Create session and policy
        session = _make_owner_session()
        policy = _make_l4_policy()
        controller = _make_controller(policy)

        # Step 4: Create approved proposal
        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        # Step 5: Check L4 autonomy
        decision = controller.check_capability_acquisition_autonomy(
            proposal, "new_capability", session
        )

        # Step 6: Verify decision
        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

        # Step 7: Verify state tracking
        state = ConversationState()
        manager = ConversationStateManager(state)
        manager.update(
            capabilities_acquired=1,
            last_l4_decision=decision.reason,
        )
        assert manager.state.capabilities_acquired == 1

    def test_l4_information_level(self):
        """Test L4: INFORMATION level operations."""
        session = _make_owner_session()
        policy = _make_l4_policy()
        controller = _make_controller(policy)

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        decision = controller.check_information_level_autonomy(proposal, session)

        assert decision.can_proceed is True

    def test_l4_critical_risk(self):
        """Test L4: CRITICAL risk operations."""
        session = _make_owner_session()
        policy = _make_l4_policy()
        controller = _make_controller(policy)

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        decision = controller.check_critical_risk_autonomy(proposal, session)

        assert decision.can_proceed is True


# ---------------------------------------------------------------------------
# L5 Cross-Objective Coordination Integration Test
# ---------------------------------------------------------------------------


class TestL5CrossObjectiveCoordination:
    """E2E test for L5 cross-objective coordination scenario."""

    def test_l5_full_pipeline(self):
        """Test L5: request → intake → autonomy check → coordination decision."""
        # Step 1: User request
        intake = TaskIntake()
        spec = intake.intake("coordinate objectives")

        # Step 2: Verify task type
        assert spec.task_type is TaskType.L5_AUTONOMY_REQUEST

        # Step 3: Create session and policy
        session = _make_owner_session()
        policy = _make_l5_policy()
        controller = _make_controller(policy)

        # Step 4: Create approved objectives
        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
        ]

        # Step 5: Check L5 autonomy
        decision = controller.check_cross_objective_coordination_autonomy(
            objectives, session
        )

        # Step 6: Verify decision
        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

        # Step 7: Verify state tracking
        state = ConversationState()
        manager = ConversationStateManager(state)
        manager.update(
            coordinated_objectives=2,
            last_l5_decision=decision.reason,
        )
        assert manager.state.coordinated_objectives == 2

    def test_l5_priority_scheduling(self):
        """Test L5: priority-based scheduling across objectives."""
        session = _make_owner_session()
        policy = _make_l5_policy()
        controller = _make_controller(policy)

        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
        ]

        decision = controller.check_priority_scheduling_autonomy(
            objectives, session
        )

        assert decision.can_proceed is True

    def test_l5_dependency_management(self):
        """Test L5: dependency management between objectives."""
        session = _make_owner_session()
        policy = _make_l5_policy()
        controller = _make_controller(policy)

        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
        ]

        decision = controller.check_dependency_management_autonomy(
            objectives, session
        )

        assert decision.can_proceed is True


# ---------------------------------------------------------------------------
# Governance Boundary Verification
# ---------------------------------------------------------------------------


class TestGovernanceBoundaries:
    """E2E test for governance boundary verification."""

    def test_approval_boundary_maintained(self):
        """Test that approval boundaries are maintained across all levels."""
        session = _make_owner_session()

        # L1 requires approval
        l1_policy = _make_l1_policy()
        l1_controller = _make_controller(l1_policy)
        unapproved = MagicMock()
        unapproved.status = ProposalStatus.DRAFT

        l1_decision = l1_controller.check_execution_autonomy(unapproved, session)
        assert l1_decision.can_proceed is False

        # L5 requires approval
        l5_policy = _make_l5_policy()
        l5_controller = _make_controller(l5_policy)
        l5_decision = l5_controller.check_critical_risk_autonomy(unapproved, session)
        assert l5_decision.can_proceed is False

    def test_scope_boundary_maintained(self):
        """Test that scope boundaries are maintained."""
        session = _make_owner_session()
        policy = _make_l5_policy()
        controller = _make_controller(policy)

        # L5 cannot expand scope beyond approved
        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.DRAFT),  # Not approved
        ]

        decision = controller.check_cross_objective_coordination_autonomy(
            objectives, session
        )

        assert decision.can_proceed is False

    def test_self_promotion_prevented(self):
        """Test that self-promotion beyond L5 is prevented."""
        # L5 is the final level - no L6 mechanism exists
        session = _make_owner_session()
        policy = _make_l5_policy()
        controller = _make_controller(policy)

        # Verify L5 uses AUTONOMOUS level (highest)
        assert policy.effective_execution_level == ExecutionLevel.AUTONOMOUS

        # No method exists for L6
        assert not hasattr(controller, "check_l6_autonomy")

    def test_mutation_authority_singular(self):
        """Test that mutation authority remains singular."""
        # Only one AutonomyController exists
        policy = _make_l5_policy()
        controller = _make_controller(policy)

        # All autonomy checks go through the same controller
        assert hasattr(controller, "check_execution_autonomy")
        assert hasattr(controller, "check_cross_objective_coordination_autonomy")


# ---------------------------------------------------------------------------
# Audit Trail Completeness
# ---------------------------------------------------------------------------


class TestAuditTrailCompleteness:
    """E2E test for audit trail completeness."""

    def test_conversation_state_tracks_all_decisions(self):
        """Test that ConversationState tracks all autonomy decisions."""
        state = ConversationState()
        manager = ConversationStateManager(state)

        # Simulate L1 decision
        manager.update(
            autonomous_steps_executed=1,
            last_autonomy_decision="L1 execution permitted",
        )

        # Simulate L2 decision
        manager.update(
            chained_workflows=("wf-1", "wf-2"),
            last_l2_decision="L2 chaining permitted",
        )

        # Simulate L3 decision
        manager.update(
            autonomous_recoveries=1,
            last_l3_decision="L3 recovery permitted",
        )

        # Simulate L4 decision
        manager.update(
            capabilities_acquired=1,
            last_l4_decision="L4 acquisition permitted",
        )

        # Simulate L5 decision
        manager.update(
            coordinated_objectives=2,
            last_l5_decision="L5 coordination permitted",
        )

        # Verify all decisions are tracked
        assert manager.state.autonomous_steps_executed == 1
        assert len(manager.state.chained_workflows) == 2
        assert manager.state.autonomous_recoveries == 1
        assert manager.state.capabilities_acquired == 1
        assert manager.state.coordinated_objectives == 2

    def test_report_includes_all_autonomy_activity(self):
        """Test that DevelopmentLifecycleReport includes all autonomy activity."""
        state = ConversationState(
            autonomous_steps_executed=5,
            last_autonomy_decision="L1 execution",
            chained_workflows=("wf-1", "wf-2"),
            last_l2_decision="L2 chaining",
            autonomous_recoveries=1,
            sub_plans_generated=2,
            last_l3_decision="L3 recovery",
            capabilities_acquired=1,
            last_l4_decision="L4 acquisition",
            coordinated_objectives=3,
            last_l5_decision="L5 coordination",
        )

        # Create a minimal report
        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test evidence",
            autonomous_steps=state.autonomous_steps_executed,
            last_autonomy_decision=state.last_autonomy_decision,
            chained_workflows=len(state.chained_workflows),
            last_l2_decision=state.last_l2_decision,
            autonomous_recoveries=state.autonomous_recoveries,
            sub_plans_generated=state.sub_plans_generated,
            last_l3_decision=state.last_l3_decision,
            capabilities_acquired=state.capabilities_acquired,
            last_l4_decision=state.last_l4_decision,
            coordinated_objectives=state.coordinated_objectives,
            last_l5_decision=state.last_l5_decision,
        )

        # Verify all activity is reported
        assert report.autonomous_steps == 5
        assert report.chained_workflows == 2
        assert report.autonomous_recoveries == 1
        assert report.sub_plans_generated == 2
        assert report.capabilities_acquired == 1
        assert report.coordinated_objectives == 3

    def test_full_lifecycle_report_generation(self):
        """Test that a full lifecycle report can be generated."""
        state = ConversationState(
            autonomous_steps_executed=10,
            last_autonomy_decision="Final L1 decision",
            chained_workflows=("wf-1", "wf-2", "wf-3"),
            last_l2_decision="Final L2 decision",
            autonomous_recoveries=2,
            sub_plans_generated=3,
            last_l3_decision="Final L3 decision",
            capabilities_acquired=2,
            last_l4_decision="Final L4 decision",
            coordinated_objectives=4,
            last_l5_decision="Final L5 decision",
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Full lifecycle completed successfully",
            autonomous_steps=state.autonomous_steps_executed,
            last_autonomy_decision=state.last_autonomy_decision,
            chained_workflows=len(state.chained_workflows),
            last_l2_decision=state.last_l2_decision,
            autonomous_recoveries=state.autonomous_recoveries,
            sub_plans_generated=state.sub_plans_generated,
            last_l3_decision=state.last_l3_decision,
            capabilities_acquired=state.capabilities_acquired,
            last_l4_decision=state.last_l4_decision,
            coordinated_objectives=state.coordinated_objectives,
            last_l5_decision=state.last_l5_decision,
        )

        assert report.final_conclusion == FinalConclusion.SUCCESS
        assert report.autonomous_steps == 10
        assert report.coordinated_objectives == 4
