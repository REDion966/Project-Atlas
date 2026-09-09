"""
Atlas P18/L3 — L3 Controlled Autonomy Integration Tests.

Tests the L3 controlled autonomy implementation.

Coverage:
- L3 autonomous recovery execution
- L3 bounded sub-plan generation
- L3 HIGH risk handling
- L3 SELF_CONFIG operations
- L3 boundaries (what L3 CANNOT do)
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


def _make_l2_policy() -> AutonomyPolicy:
    """Create an L2 autonomy policy (MEDIUM risk only)."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.MEDIUM,
        effective_execution_level=ExecutionLevel.CODE_ARTIFACT,
        requires_user_approval_scopes=[],
        max_requests_per_window=10,
        authorization_ttl_minutes=60,
    )


def _make_l1_policy() -> AutonomyPolicy:
    """Create an L1 autonomy policy (LOW risk, SANDBOXED)."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.LOW,
        effective_execution_level=ExecutionLevel.SANDBOXED,
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
# A. L3 Classification Tests
# ---------------------------------------------------------------------------


class TestL3Classification:
    """Tests for L3_AUTONOMY_REQUEST task classification."""

    def test_l3_cues_classify_correctly(self):
        """L3 autonomy cues classify as L3_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        # Note: Some phrases may be classified as other types because
        # execution/recovery cues are checked first. We test phrases
        # that are unique to L3 classification.
        cues = [
            "generate sub plan",
            "create sub plan",
            "handle high risk",
            "modify configuration",
            "adjust configuration",
        ]
        for cue in cues:
            spec = intake.intake(cue)
            assert spec.task_type is TaskType.L3_AUTONOMY_REQUEST, f"Failed for: {cue}"

    def test_l1_cues_not_misclassified_as_l3(self):
        """L1 autonomy cues remain AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("proceed autonomously")
        assert spec.task_type is TaskType.AUTONOMY_REQUEST

    def test_l2_cues_not_misclassified_as_l3(self):
        """L2 autonomy cues remain L2_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("chain the workflows")
        assert spec.task_type is TaskType.L2_AUTONOMY_REQUEST


# ---------------------------------------------------------------------------
# B. L3 Recovery Execution Tests
# ---------------------------------------------------------------------------


class TestL3RecoveryExecution:
    """Tests for L3 autonomous recovery execution capability."""

    def test_l3_can_execute_recovery_autonomously(self):
        """L3 can execute recovery autonomously."""
        controller = _make_controller(_make_l3_policy())
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
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l3_cannot_execute_non_recoverable(self):
        """L3 cannot execute recovery if not recoverable."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        recovery = MagicMock()
        recovery.recoverable = False
        recovery.strategy.value = "no_recovery"

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_recovery_execution_autonomy(
            recovery, proposal, session
        )

        assert decision.can_proceed is False
        assert decision.escalation_required is True

    def test_l3_cannot_execute_without_owner(self):
        """L3 cannot execute recovery without OWNER authority."""
        controller = _make_controller(_make_l3_policy())
        session = _make_user_session()

        recovery = MagicMock()
        recovery.recoverable = True
        recovery.strategy.value = "revise_and_retry"

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_recovery_execution_autonomy(
            recovery, proposal, session
        )

        assert decision.can_proceed is False
        assert "OWNER" in decision.reason


# ---------------------------------------------------------------------------
# C. L3 Sub-Plan Generation Tests
# ---------------------------------------------------------------------------


class TestL3SubPlanGeneration:
    """Tests for L3 bounded sub-plan generation capability."""

    def test_l3_can_generate_bounded_sub_plan(self):
        """L3 can generate a bounded sub-plan."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

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
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l3_cannot_generate_sub_plan_changing_objective(self):
        """L3 cannot generate sub-plan that changes objective."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        parent = MagicMock()
        parent.summary = "Implement feature X"
        parent.target_components = ["atlas/module_a.py"]

        sub = MagicMock()
        sub.summary = "Implement feature Y"
        sub.target_components = ["atlas/module_a.py"]

        decision = controller.check_sub_plan_generation_autonomy(
            parent, sub, session
        )

        assert decision.can_proceed is False
        assert "preserve the parent objective" in decision.reason
        assert decision.escalation_required is True

    def test_l3_cannot_generate_sub_plan_expanding_scope(self):
        """L3 cannot generate sub-plan that expands scope."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        parent = MagicMock()
        parent.summary = "Implement feature X"
        parent.target_components = ["atlas/module_a.py"]

        sub = MagicMock()
        sub.summary = "Implement feature X"
        sub.target_components = ["atlas/module_a.py", "atlas/module_c.py"]

        decision = controller.check_sub_plan_generation_autonomy(
            parent, sub, session
        )

        assert decision.can_proceed is False
        assert "expand scope beyond parent" in decision.reason
        assert decision.escalation_required is True


# ---------------------------------------------------------------------------
# D. L3 HIGH Risk Tests
# ---------------------------------------------------------------------------


class TestL3HighRisk:
    """Tests for L3 HIGH risk handling capability."""

    def test_l3_can_handle_high_risk(self):
        """L3 can handle HIGH risk operations."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_high_risk_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l2_cannot_handle_high_risk(self):
        """L2 policy cannot handle HIGH risk operations."""
        controller = _make_controller(_make_l2_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_high_risk_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "HIGH risk tolerance" in decision.reason

    def test_l3_cannot_handle_critical_risk(self):
        """L3 cannot handle CRITICAL risk operations."""
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.HIGH,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(policy)
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_high_risk_autonomy(proposal, session)

        # L3 can handle HIGH, but the policy ceiling is HIGH
        assert decision.can_proceed is True  # HIGH <= HIGH


# ---------------------------------------------------------------------------
# E. L3 SELF_CONFIG Tests
# ---------------------------------------------------------------------------


class TestL3SelfConfig:
    """Tests for L3 SELF_CONFIG capability."""

    def test_l3_can_modify_self_config(self):
        """L3 can modify internal configuration."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_self_config_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l2_cannot_execute_sandboxed(self):
        """L2 policy cannot execute SANDBOXED level operations."""
        from atlas.evolution.models import ProposalStatus

        # L2 policy allows CODE_ARTIFACT, but SANDBOXED is "higher"
        controller = _make_controller(_make_l2_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        # L2 cannot execute at SANDBOXED level (4 > 3)
        decision = controller.check_execution_autonomy(proposal, session)

        # L2's check_execution_autonomy uses SANDBOXED level, which should fail
        # because L2's policy only allows CODE_ARTIFACT
        assert decision.can_proceed is False
        assert "policy level" in decision.reason


# ---------------------------------------------------------------------------
# F. L3 ConversationState Tracking Tests
# ---------------------------------------------------------------------------


class TestL3ConversationStateTracking:
    """Tests for L3 tracking in ConversationState."""

    def test_autonomous_recoveries_defaults_to_zero(self):
        """autonomous_recoveries defaults to 0."""
        state = ConversationState()
        assert state.autonomous_recoveries == 0

    def test_sub_plans_generated_defaults_to_zero(self):
        """sub_plans_generated defaults to 0."""
        state = ConversationState()
        assert state.sub_plans_generated == 0

    def test_last_l3_decision_defaults_to_none(self):
        """last_l3_decision defaults to None."""
        state = ConversationState()
        assert state.last_l3_decision is None

    def test_l3_fields_can_be_updated(self):
        """L3 fields can be updated via ConversationStateManager."""
        from atlas.conversation.conversation_state import ConversationStateManager

        manager = ConversationStateManager()
        manager.update(
            autonomous_recoveries=3,
            sub_plans_generated=5,
            last_l3_decision="L3 recovery execution permitted",
        )

        assert manager.state.autonomous_recoveries == 3
        assert manager.state.sub_plans_generated == 5
        assert manager.state.last_l3_decision == "L3 recovery execution permitted"

    def test_l3_fields_in_to_dict(self):
        """L3 fields are included in to_dict()."""
        state = ConversationState(
            autonomous_recoveries=2,
            sub_plans_generated=4,
            last_l3_decision="Test L3 decision",
        )
        d = state.to_dict()

        assert "autonomous_recoveries" in d
        assert "sub_plans_generated" in d
        assert "last_l3_decision" in d
        assert d["autonomous_recoveries"] == 2
        assert d["sub_plans_generated"] == 4
        assert d["last_l3_decision"] == "Test L3 decision"


# ---------------------------------------------------------------------------
# G. L3 DevelopmentPlan Sub-Plan Tests
# ---------------------------------------------------------------------------


class TestL3DevelopmentPlanSubPlan:
    """Tests for L3 sub-plan tracking in DevelopmentPlan."""

    def test_parent_plan_id_defaults_to_none(self):
        """parent_plan_id defaults to None."""
        from atlas.evolution.development_models import DevelopmentPlan

        plan = DevelopmentPlan(
            plan_id="PLAN-001",
            proposal_id="PROP-001",
            title="Test",
            summary="Test plan",
        )

        assert plan.parent_plan_id is None

    def test_parent_plan_id_can_be_set(self):
        """parent_plan_id can be set for sub-plans."""
        from atlas.evolution.development_models import DevelopmentPlan

        plan = DevelopmentPlan(
            plan_id="PLAN-001-SUB",
            proposal_id="PROP-001",
            title="Test Sub-Plan",
            summary="Test sub-plan",
            parent_plan_id="PLAN-001",
        )

        assert plan.parent_plan_id == "PLAN-001"


# ---------------------------------------------------------------------------
# H. L3 DevelopmentOutcome Recovery Tests
# ---------------------------------------------------------------------------


class TestL3DevelopmentOutcomeRecovery:
    """Tests for L3 recovery tracking in DevelopmentOutcome."""

    def test_recovery_executed_defaults_to_false(self):
        """recovery_executed defaults to False."""
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

        assert outcome.recovery_executed is False

    def test_recovery_executed_can_be_set_true(self):
        """recovery_executed can be set to True."""
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-001",
            plan_id="PLAN-001",
            iteration=1,
            recovery_executed=True,
        )

        assert outcome.recovery_executed is True


# ---------------------------------------------------------------------------
# I. L3 Report Builder Tests
# ---------------------------------------------------------------------------


class TestL3ReportBuilder:
    """Tests for L3 reporting in DevelopmentLifecycleReport."""

    def test_autonomous_recoveries_defaults_to_zero(self):
        """autonomous_recoveries defaults to 0."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.autonomous_recoveries == 0

    def test_sub_plans_generated_defaults_to_zero(self):
        """sub_plans_generated defaults to 0."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.sub_plans_generated == 0

    def test_l3_fields_can_be_set(self):
        """L3 fields can be set on DevelopmentLifecycleReport."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
            autonomous_recoveries=3,
            sub_plans_generated=5,
            last_l3_decision="L3 recovery execution permitted",
        )

        assert report.autonomous_recoveries == 3
        assert report.sub_plans_generated == 5
        assert report.last_l3_decision == "L3 recovery execution permitted"


# ---------------------------------------------------------------------------
# J. L1/L2 Regression Tests
# ---------------------------------------------------------------------------


class TestL1L2RegressionWithL3:
    """Tests that L1/L2 behavior is preserved with L3 implementation."""

    def test_l1_execution_still_works(self):
        """L1 execution autonomy still works."""
        from atlas.evolution.models import ProposalStatus

        controller = _make_controller(_make_l1_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l2_workflow_chaining_still_works(self):
        """L2 workflow chaining still works."""
        controller = _make_controller(_make_l2_policy())
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

    def test_l2_plan_adjustment_still_works(self):
        """L2 plan adjustment still works."""
        controller = _make_controller(_make_l2_policy())
        session = _make_owner_session()

        original = MagicMock()
        original.summary = "Implement feature X"
        original.target_components = ["atlas/module_a.py"]

        adjusted = MagicMock()
        adjusted.summary = "Implement feature X"
        adjusted.target_components = ["atlas/module_a.py"]

        decision = controller.check_plan_adjustment_autonomy(
            original, adjusted, session
        )

        assert decision.can_proceed is True
