"""
Atlas P18/L4 — L4 Controlled Autonomy Integration Tests.

Tests the L4 controlled autonomy implementation.

Coverage:
- L4 capability acquisition
- L4 INFORMATION level operations
- L4 CRITICAL risk handling
- L4 boundaries (what L4 CANNOT do)
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


def _make_l3_policy() -> AutonomyPolicy:
    """Create an L3 autonomy policy (HIGH risk only)."""
    return AutonomyPolicy(
        enabled=True,
        allowed_scopes=[ScopeType.CODE],
        max_risk_level=RiskLevel.HIGH,
        effective_execution_level=ExecutionLevel.SELF_CONFIG,
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
# A. L4 Classification Tests
# ---------------------------------------------------------------------------


class TestL4Classification:
    """Tests for L4_AUTONOMY_REQUEST task classification."""

    def test_l4_cues_classify_correctly(self):
        """L4 autonomy cues classify as L4_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        cues = [
            "acquire capability",
            "acquire new capability",
            "modify memory",
            "modify knowledge",
            "handle critical risk",
            "critical risk operation",
            "information level operation",
            "capability acquisition",
        ]
        for cue in cues:
            spec = intake.intake(cue)
            assert spec.task_type is TaskType.L4_AUTONOMY_REQUEST, f"Failed for: {cue}"

    def test_l1_cues_not_misclassified_as_l4(self):
        """L1 autonomy cues remain AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("proceed autonomously")
        assert spec.task_type is TaskType.AUTONOMY_REQUEST

    def test_l2_cues_not_misclassified_as_l4(self):
        """L2 autonomy cues remain L2_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("chain the workflows")
        assert spec.task_type is TaskType.L2_AUTONOMY_REQUEST

    def test_l3_cues_not_misclassified_as_l4(self):
        """L3 autonomy cues remain L3_AUTONOMY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("generate sub plan")
        assert spec.task_type is TaskType.L3_AUTONOMY_REQUEST


# ---------------------------------------------------------------------------
# B. L4 Capability Acquisition Tests
# ---------------------------------------------------------------------------


class TestL4CapabilityAcquisition:
    """Tests for L4 capability acquisition capability."""

    def test_l4_can_acquire_capability(self):
        """L4 can acquire a new capability."""
        controller = _make_controller(_make_l4_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_capability_acquisition_autonomy(
            proposal, "new_capability", session
        )

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l4_cannot_acquire_without_owner(self):
        """L4 cannot acquire capability without OWNER authority."""
        controller = _make_controller(_make_l4_policy())
        session = _make_user_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_capability_acquisition_autonomy(
            proposal, "new_capability", session
        )

        assert decision.can_proceed is False
        assert "OWNER" in decision.reason

    def test_l3_cannot_acquire_capability(self):
        """L3 policy cannot acquire capabilities (CRITICAL risk required)."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_capability_acquisition_autonomy(
            proposal, "new_capability", session
        )

        assert decision.can_proceed is False
        assert "CRITICAL risk tolerance" in decision.reason


# ---------------------------------------------------------------------------
# C. L4 INFORMATION Level Tests
# ---------------------------------------------------------------------------


class TestL4InformationLevel:
    """Tests for L4 INFORMATION level capability."""

    def test_l4_can_modify_information_level(self):
        """L4 can modify memory/knowledge."""
        controller = _make_controller(_make_l4_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_information_level_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l3_cannot_modify_information_level(self):
        """L3 policy cannot modify INFORMATION level."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_information_level_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "INFORMATION execution level" in decision.reason


# ---------------------------------------------------------------------------
# D. L4 CRITICAL Risk Tests
# ---------------------------------------------------------------------------


class TestL4CriticalRisk:
    """Tests for L4 CRITICAL risk handling capability."""

    def test_l4_can_handle_critical_risk(self):
        """L4 can handle CRITICAL risk operations."""
        controller = _make_controller(_make_l4_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_critical_risk_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l3_cannot_handle_critical_risk(self):
        """L3 policy cannot handle CRITICAL risk operations."""
        controller = _make_controller(_make_l3_policy())
        session = _make_owner_session()

        proposal = MagicMock()
        proposal.status = MagicMock()
        proposal.status.name = "APPROVED"

        decision = controller.check_critical_risk_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "CRITICAL risk tolerance" in decision.reason


# ---------------------------------------------------------------------------
# E. L4 ConversationState Tracking Tests
# ---------------------------------------------------------------------------


class TestL4ConversationStateTracking:
    """Tests for L4 tracking in ConversationState."""

    def test_capabilities_acquired_defaults_to_zero(self):
        """capabilities_acquired defaults to 0."""
        state = ConversationState()
        assert state.capabilities_acquired == 0

    def test_last_l4_decision_defaults_to_none(self):
        """last_l4_decision defaults to None."""
        state = ConversationState()
        assert state.last_l4_decision is None

    def test_l4_fields_can_be_updated(self):
        """L4 fields can be updated via ConversationStateManager."""
        from atlas.conversation.conversation_state import ConversationStateManager

        manager = ConversationStateManager()
        manager.update(
            capabilities_acquired=5,
            last_l4_decision="L4 capability acquisition permitted",
        )

        assert manager.state.capabilities_acquired == 5
        assert manager.state.last_l4_decision == "L4 capability acquisition permitted"

    def test_l4_fields_in_to_dict(self):
        """L4 fields are included in to_dict()."""
        state = ConversationState(
            capabilities_acquired=3,
            last_l4_decision="Test L4 decision",
        )
        d = state.to_dict()

        assert "capabilities_acquired" in d
        assert "last_l4_decision" in d
        assert d["capabilities_acquired"] == 3
        assert d["last_l4_decision"] == "Test L4 decision"


# ---------------------------------------------------------------------------
# F. L4 DevelopmentPlan Capability Tests
# ---------------------------------------------------------------------------


class TestL4DevelopmentPlanCapabilities:
    """Tests for L4 capability tracking in DevelopmentPlan."""

    def test_capabilities_required_defaults_to_empty(self):
        """capabilities_required defaults to empty tuple."""
        from atlas.evolution.development_models import DevelopmentPlan

        plan = DevelopmentPlan(
            plan_id="PLAN-001",
            proposal_id="PROP-001",
            title="Test",
            summary="Test plan",
        )

        assert plan.capabilities_required == ()

    def test_capabilities_required_can_be_set(self):
        """capabilities_required can be set for plans."""
        from atlas.evolution.development_models import DevelopmentPlan

        plan = DevelopmentPlan(
            plan_id="PLAN-001",
            proposal_id="PROP-001",
            title="Test",
            summary="Test plan",
            capabilities_required=("cap_a", "cap_b"),
        )

        assert plan.capabilities_required == ("cap_a", "cap_b")


# ---------------------------------------------------------------------------
# G. L4 DevelopmentOutcome Capability Tests
# ---------------------------------------------------------------------------


class TestL4DevelopmentOutcomeCapability:
    """Tests for L4 capability tracking in DevelopmentOutcome."""

    def test_capability_acquired_defaults_to_none(self):
        """capability_acquired defaults to None."""
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

        assert outcome.capability_acquired is None

    def test_capability_acquired_can_be_set(self):
        """capability_acquired can be set to a capability name."""
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-001",
            plan_id="PLAN-001",
            iteration=1,
            capability_acquired="new_capability",
        )

        assert outcome.capability_acquired == "new_capability"


# ---------------------------------------------------------------------------
# H. L4 Report Builder Tests
# ---------------------------------------------------------------------------


class TestL4ReportBuilder:
    """Tests for L4 reporting in DevelopmentLifecycleReport."""

    def test_capabilities_acquired_defaults_to_zero(self):
        """capabilities_acquired defaults to 0."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.capabilities_acquired == 0

    def test_last_l4_decision_defaults_to_none(self):
        """last_l4_decision defaults to None."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.last_l4_decision is None

    def test_l4_fields_can_be_set(self):
        """L4 fields can be set on DevelopmentLifecycleReport."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
            capabilities_acquired=5,
            last_l4_decision="L4 capability acquisition permitted",
        )

        assert report.capabilities_acquired == 5
        assert report.last_l4_decision == "L4 capability acquisition permitted"


# ---------------------------------------------------------------------------
# I. L1/L2/L3 Regression Tests
# ---------------------------------------------------------------------------


class TestL1L2L3RegressionWithL4:
    """Tests that L1/L2/L3 behavior is preserved with L4 implementation."""

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
