"""
Atlas P18/L5 — L5 Controlled Autonomy Integration Tests.

Tests the L5 controlled autonomy implementation (FINAL LEVEL).

Coverage:
- L5 cross-objective coordination
- L5 priority-based scheduling
- L5 dependency management
- L5 boundaries (what L5 CANNOT do)
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

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
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.conversation_state import ConversationState


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


def _make_user_session() -> FakeSessionContext:
    """Create a USER session context."""
    principal = Principal(
        principal_id="user-001",
        name="Test User",
        authority=AuthorityLevel.USER,
    )
    return FakeSessionContext(
        session_id="test-session-002",
        principal=principal,
        authority=AuthorityLevel.USER,
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


def _make_l4_policy() -> AutonomyPolicy:
    """Create an L4 autonomy policy (CRITICAL risk, INFORMATION level)."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.CRITICAL,
        effective_execution_level=ExecutionLevel.INFORMATION,
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
# A. L5 Classification Tests
# ---------------------------------------------------------------------------


class TestL5Classification:
    """Tests for L5_AUTONOMY_REQUEST task classification."""

    def test_l5_cues_classify_correctly(self):
        """L5 autonomy cues classify as L5_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        cues = [
            "coordinate objectives",
            "coordinate across objectives",
            "prioritize objectives",
            "schedule objectives",
            "manage dependencies",
            "cross objective coordination",
            "multi objective orchestration",
            "objective prioritization",
        ]
        for cue in cues:
            spec = intake.intake(cue)
            assert spec.task_type is TaskType.L5_AUTONOMY_REQUEST, f"Failed for: {cue}"

    def test_l1_cues_not_misclassified_as_l5(self):
        """L1 autonomy cues remain AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("proceed autonomously")
        assert spec.task_type is TaskType.AUTONOMY_REQUEST

    def test_l2_cues_not_misclassified_as_l5(self):
        """L2 autonomy cues remain L2_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("chain the workflows")
        assert spec.task_type is TaskType.L2_AUTONOMY_REQUEST

    def test_l3_cues_not_misclassified_as_l5(self):
        """L3 autonomy cues remain L3_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("generate sub plan")
        assert spec.task_type is TaskType.L3_AUTONOMY_REQUEST

    def test_l4_cues_not_misclassified_as_l5(self):
        """L4 autonomy cues remain L4_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("acquire capability")
        assert spec.task_type is TaskType.L4_AUTONOMY_REQUEST


# ---------------------------------------------------------------------------
# B. L5 Cross-Objective Coordination Tests
# ---------------------------------------------------------------------------


class TestL5CrossObjectiveCoordination:
    """Tests for L5 cross-objective coordination capability."""

    def test_l5_can_coordinate_across_objectives(self):
        """L5 can coordinate across multiple approved objectives."""
        from atlas.evolution.models import ProposalStatus

        controller = _make_controller(_make_l5_policy())
        session = _make_owner_session()

        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
        ]

        decision = controller.check_cross_objective_coordination_autonomy(
            objectives, session
        )

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l5_cannot_coordinate_single_objective(self):
        """L5 cannot coordinate with fewer than 2 objectives."""
        controller = _make_controller(_make_l5_policy())
        session = _make_owner_session()

        objectives = [MagicMock(status=MagicMock(name="APPROVED"))]

        decision = controller.check_cross_objective_coordination_autonomy(
            objectives, session
        )

        assert decision.can_proceed is False
        assert "at least 2 objectives" in decision.reason

    def test_l5_cannot_coordinate_unapproved_objectives(self):
        """L5 cannot coordinate objectives that are not APPROVED."""
        controller = _make_controller(_make_l5_policy())
        session = _make_owner_session()

        objectives = [
            MagicMock(status=MagicMock(name="APPROVED")),
            MagicMock(status=MagicMock(name="DRAFT")),
        ]

        decision = controller.check_cross_objective_coordination_autonomy(
            objectives, session
        )

        assert decision.can_proceed is False
        assert "not APPROVED" in decision.reason

    def test_l4_cannot_coordinate_objectives(self):
        """L4 policy cannot coordinate across objectives (AUTONOMOUS level required)."""
        from atlas.evolution.models import ProposalStatus

        controller = _make_controller(_make_l4_policy())
        session = _make_owner_session()

        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
        ]

        decision = controller.check_cross_objective_coordination_autonomy(
            objectives, session
        )

        assert decision.can_proceed is False
        assert "AUTONOMOUS execution level" in decision.reason


# ---------------------------------------------------------------------------
# C. L5 Priority Scheduling Tests
# ---------------------------------------------------------------------------


class TestL5PriorityScheduling:
    """Tests for L5 priority-based scheduling capability."""

    def test_l5_can_prioritize_objectives(self):
        """L5 can prioritize work across objectives."""
        from atlas.evolution.models import ProposalStatus

        controller = _make_controller(_make_l5_policy())
        session = _make_owner_session()

        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
        ]

        decision = controller.check_priority_scheduling_autonomy(
            objectives, session
        )

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l5_cannot_prioritize_single_objective(self):
        """L5 cannot prioritize with fewer than 2 objectives."""
        controller = _make_controller(_make_l5_policy())
        session = _make_owner_session()

        objectives = [MagicMock(status=MagicMock(name="APPROVED"))]

        decision = controller.check_priority_scheduling_autonomy(
            objectives, session
        )

        assert decision.can_proceed is False
        assert "at least 2 objectives" in decision.reason


# ---------------------------------------------------------------------------
# D. L5 Dependency Management Tests
# ---------------------------------------------------------------------------


class TestL5DependencyManagement:
    """Tests for L5 dependency management capability."""

    def test_l5_can_manage_dependencies(self):
        """L5 can manage dependencies between objectives."""
        from atlas.evolution.models import ProposalStatus

        controller = _make_controller(_make_l5_policy())
        session = _make_owner_session()

        objectives = [
            MagicMock(status=ProposalStatus.APPROVED),
            MagicMock(status=ProposalStatus.APPROVED),
        ]

        decision = controller.check_dependency_management_autonomy(
            objectives, session
        )

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l5_cannot_manage_dependencies_single_objective(self):
        """L5 cannot manage dependencies with fewer than 2 objectives."""
        controller = _make_controller(_make_l5_policy())
        session = _make_owner_session()

        objectives = [MagicMock(status=MagicMock(name="APPROVED"))]

        decision = controller.check_dependency_management_autonomy(
            objectives, session
        )

        assert decision.can_proceed is False
        assert "at least 2 objectives" in decision.reason


# ---------------------------------------------------------------------------
# E. L5 ConversationState Tracking Tests
# ---------------------------------------------------------------------------


class TestL5ConversationStateTracking:
    """Tests for L5 tracking in ConversationState."""

    def test_coordinated_objectives_defaults_to_zero(self):
        """coordinated_objectives defaults to 0."""
        state = ConversationState()
        assert state.coordinated_objectives == 0

    def test_last_l5_decision_defaults_to_none(self):
        """last_l5_decision defaults to None."""
        state = ConversationState()
        assert state.last_l5_decision is None

    def test_l5_fields_can_be_updated(self):
        """L5 fields can be updated via ConversationStateManager."""
        from atlas.conversation.conversation_state import ConversationStateManager

        manager = ConversationStateManager()
        manager.update(
            coordinated_objectives=5,
            last_l5_decision="L5 cross-objective coordination permitted",
        )

        assert manager.state.coordinated_objectives == 5
        assert manager.state.last_l5_decision == "L5 cross-objective coordination permitted"

    def test_l5_fields_in_to_dict(self):
        """L5 fields are included in to_dict()."""
        state = ConversationState(
            coordinated_objectives=3,
            last_l5_decision="Test L5 decision",
        )
        d = state.to_dict()

        assert "coordinated_objectives" in d
        assert "last_l5_decision" in d
        assert d["coordinated_objectives"] == 3
        assert d["last_l5_decision"] == "Test L5 decision"


# ---------------------------------------------------------------------------
# F. L5 DevelopmentPlan Objective Tests
# ---------------------------------------------------------------------------


class TestL5DevelopmentPlanObjective:
    """Tests for L5 objective tracking in DevelopmentPlan."""

    def test_objective_id_defaults_to_none(self):
        """objective_id defaults to None."""
        from atlas.evolution.development_models import DevelopmentPlan

        plan = DevelopmentPlan(
            plan_id="PLAN-001",
            proposal_id="PROP-001",
            title="Test",
            summary="Test plan",
        )

        assert plan.objective_id is None

    def test_objective_id_can_be_set(self):
        """objective_id can be set for cross-objective tracking."""
        from atlas.evolution.development_models import DevelopmentPlan

        plan = DevelopmentPlan(
            plan_id="PLAN-001",
            proposal_id="PROP-001",
            title="Test",
            summary="Test plan",
            objective_id="OBJ-001",
        )

        assert plan.objective_id == "OBJ-001"


# ---------------------------------------------------------------------------
# G. L5 DevelopmentOutcome Coordination Tests
# ---------------------------------------------------------------------------


class TestL5DevelopmentOutcomeCoordination:
    """Tests for L5 coordination tracking in DevelopmentOutcome."""

    def test_coordinated_defaults_to_false(self):
        """coordinated defaults to False."""
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-001",
            plan_id="PLAN-001",
            iteration=1,
        )

        assert outcome.coordinated is False

    def test_coordinated_can_be_set_true(self):
        """coordinated can be set to True."""
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-001",
            plan_id="PLAN-001",
            iteration=1,
            coordinated=True,
        )

        assert outcome.coordinated is True


# ---------------------------------------------------------------------------
# H. L5 Report Builder Tests
# ---------------------------------------------------------------------------


class TestL5ReportBuilder:
    """Tests for L5 reporting in DevelopmentLifecycleReport."""

    def test_coordinated_objectives_defaults_to_zero(self):
        """coordinated_objectives defaults to 0."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.coordinated_objectives == 0

    def test_last_l5_decision_defaults_to_none(self):
        """last_l5_decision defaults to None."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.last_l5_decision is None

    def test_l5_fields_can_be_set(self):
        """L5 fields can be set on DevelopmentLifecycleReport."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
            coordinated_objectives=5,
            last_l5_decision="L5 cross-objective coordination permitted",
        )

        assert report.coordinated_objectives == 5
        assert report.last_l5_decision == "L5 cross-objective coordination permitted"


# ---------------------------------------------------------------------------
# I. L1/L2/L3/L4 Regression Tests
# ---------------------------------------------------------------------------


class TestL1L2L3L4RegressionWithL5:
    """Tests that L1-L4 behavior is preserved with L5 implementation."""

    def test_l1_execution_still_works(self):
        """L1 execution autonomy still works."""
        from atlas.evolution.models import ProposalStatus

        l1_policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(l1_policy)
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l2_workflow_chaining_still_works(self):
        """L2 workflow chaining still works."""
        l2_policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.MEDIUM,
            effective_execution_level=ExecutionLevel.CODE_ARTIFACT,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(l2_policy)
        session = _make_owner_session()

        current = MagicMock()
        current.status = MagicMock()
        current.status.name = "APPROVED"

        next_workflow = MagicMock()
        next_workflow.status = MagicMock()
        next_workflow.status.name = "APPROVED"

        decision = controller.check_workflow_chaining_autonomy(
            current, next_workflow, session
        )

        assert decision.can_proceed is True

    def test_l3_recovery_execution_still_works(self):
        """L3 recovery execution still works."""
        l3_policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.HIGH,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(l3_policy)
        session = _make_owner_session()

        recovery = MagicMock()
        recovery.recoverable = True
        recovery.strategy.value = "revise_and_retry"

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_recovery_execution_autonomy(
            recovery, proposal, session
        )

        assert decision.can_proceed is True

    def test_l4_capability_acquisition_still_works(self):
        """L4 capability acquisition still works."""
        controller = _make_controller(_make_l4_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_capability_acquisition_autonomy(
            proposal, "new_capability", session
        )

        assert decision.can_proceed is True
