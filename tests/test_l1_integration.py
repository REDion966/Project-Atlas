"""
Atlas P18/L1 — L1 Controlled Autonomy Integration Tests.

Tests the integration of L1 autonomy with the conversation service,
task intake, and reporting components.

Coverage:
- AUTONOMY_REQUEST classification
- Conversation state tracking
- Reporting integration
- End-to-end autonomy flow
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.conversation_state import ConversationState


# ---------------------------------------------------------------------------
# A. AUTONOMY_REQUEST Classification Tests
# ---------------------------------------------------------------------------


class TestAutonomyClassification:
    """Tests for AUTONOMY_REQUEST task classification."""

    def test_autonomy_cues_classify_correctly(self):
        """Autonomy cues classify as AUTONOMY_REQUEST."""
        intake = TaskIntake()
        # Note: Some phrases may be classified as other types because
        # execution/approval cues are checked first. We test phrases
        # that are unique to autonomy classification.
        cues = [
            "proceed autonomously",
            "continue autonomously",
            "continue with the development",
            "continue the development",
            "run autonomously",
        ]
        for cue in cues:
            spec = intake.intake(cue)
            assert spec.task_type is TaskType.AUTONOMY_REQUEST, f"Failed for: {cue}"

    def test_execution_not_misclassified_as_autonomy(self):
        """Execution cues remain EXECUTION_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("execute the approved proposal")
        assert spec.task_type is TaskType.EXECUTION_REQUEST

    def test_report_not_misclassified_as_autonomy(self):
        """Report cues remain REPORT_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("report on the development")
        assert spec.task_type is TaskType.REPORT_REQUEST

    def test_recovery_not_misclassified_as_autonomy(self):
        """Recovery cues remain RECOVERY_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("recover from the failure")
        assert spec.task_type is TaskType.RECOVERY_REQUEST

    def test_verification_not_misclassified_as_autonomy(self):
        """Verification cues remain VERIFICATION_REQUEST."""
        intake = TaskIntake()
        spec = intake.intake("verify the development")
        assert spec.task_type is TaskType.VERIFICATION_REQUEST


# ---------------------------------------------------------------------------
# B. ConversationState L1 Tracking Tests
# ---------------------------------------------------------------------------


class TestConversationStateL1Tracking:
    """Tests for L1 autonomy tracking in ConversationState."""

    def test_autonomous_steps_executed_defaults_to_zero(self):
        """autonomous_steps_executed defaults to 0."""
        state = ConversationState()
        assert state.autonomous_steps_executed == 0

    def test_last_autonomy_decision_defaults_to_none(self):
        """last_autonomy_decision defaults to None."""
        state = ConversationState()
        assert state.last_autonomy_decision is None

    def test_autonomous_steps_can_be_updated(self):
        """autonomous_steps_executed can be updated via ConversationStateManager."""
        from atlas.conversation.conversation_state import ConversationStateManager

        manager = ConversationStateManager()
        manager.update(autonomous_steps_executed=5)

        assert manager.state.autonomous_steps_executed == 5

    def test_last_autonomy_decision_can_be_updated(self):
        """last_autonomy_decision can be updated via ConversationStateManager."""
        from atlas.conversation.conversation_state import ConversationStateManager

        manager = ConversationStateManager()
        manager.update(last_autonomy_decision="L1 autonomous execution permitted")

        assert manager.state.last_autonomy_decision == "L1 autonomous execution permitted"

    def test_l1_fields_in_to_dict(self):
        """L1 fields are included in to_dict()."""
        state = ConversationState(
            autonomous_steps_executed=3,
            last_autonomy_decision="Test decision",
        )
        d = state.to_dict()

        assert "autonomous_steps_executed" in d
        assert "last_autonomy_decision" in d
        assert d["autonomous_steps_executed"] == 3
        assert d["last_autonomy_decision"] == "Test decision"

    def test_l1_fields_preserved_across_updates(self):
        """L1 fields are preserved when other fields are updated."""
        from atlas.conversation.conversation_state import ConversationStateManager

        manager = ConversationStateManager()
        manager.update(
            autonomous_steps_executed=2,
            last_autonomy_decision="Test",
        )
        manager.update(current_subject="New topic")

        assert manager.state.autonomous_steps_executed == 2
        assert manager.state.last_autonomy_decision == "Test"


# ---------------------------------------------------------------------------
# C. DevelopmentOutcome Autonomous Flag Tests
# ---------------------------------------------------------------------------


class TestDevelopmentOutcomeAutonomousFlag:
    """Tests for the autonomous flag on DevelopmentOutcome."""

    def test_autonomous_defaults_to_false(self):
        """autonomous flag defaults to False."""
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

        assert outcome.autonomous is False

    def test_autonomous_can_be_set_true(self):
        """autonomous flag can be set to True."""
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-001",
            plan_id="PLAN-001",
            iteration=1,
            autonomous=True,
        )

        assert outcome.autonomous is True


# ---------------------------------------------------------------------------
# D. DevelopmentLifecycleReport L1 Fields Tests
# ---------------------------------------------------------------------------


class TestDevelopmentLifecycleReportL1Fields:
    """Tests for L1 fields on DevelopmentLifecycleReport."""

    def test_autonomous_steps_defaults_to_zero(self):
        """autonomous_steps defaults to 0."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.autonomous_steps == 0

    def test_last_autonomy_decision_defaults_to_none(self):
        """last_autonomy_decision defaults to None."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        assert report.last_autonomy_decision is None

    def test_l1_fields_can_be_set(self):
        """L1 fields can be set on DevelopmentLifecycleReport."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
            autonomous_steps=5,
            last_autonomy_decision="L1 execution permitted",
        )

        assert report.autonomous_steps == 5
        assert report.last_autonomy_decision == "L1 execution permitted"

    def test_report_is_immutable(self):
        """DevelopmentLifecycleReport is frozen."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="Test",
        )

        with pytest.raises(AttributeError):
            report.autonomous_steps = 10


# ---------------------------------------------------------------------------
# E. AutonomyController Integration Tests
# ---------------------------------------------------------------------------


class TestAutonomyControllerIntegration:
    """Integration tests for AutonomyController with existing components."""

    def test_controller_composes_diagnostic_and_recovery(self):
        """AutonomyController can compose DevelopmentDiagnostic and DevelopmentRecovery."""
        from atlas.evolution.autonomy.autonomy_controller import AutonomyController
        from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
        from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
        from atlas.evolution.autonomy.models import AutonomyPolicy, RiskLevel
        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
        from atlas.evolution.development_recovery import DevelopmentRecovery
        from atlas.evolution.governance.models import ScopeType
        from atlas.evolution.models import ExecutionLevel

        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = AutonomyController(
            authorization_manager=AuthorizationManager(policy=policy),
            policy_engine=AutonomyPolicyEngine(policy=policy),
        )

        # Create a failed result
        result = MagicMock()
        result.status = MagicMock()
        result.status.name = "FAILED"
        result.outcomes = []
        result.iterations_used = 1
        result.message = "Test failure"

        # Diagnose the failure
        diagnostic = DevelopmentDiagnostic().diagnose(result)

        # Make recovery decision
        recovery = DevelopmentRecovery().decide(result, diagnostic)

        # Check autonomy for recovery
        decision = controller.check_recovery_autonomy(diagnostic, recovery)

        # Decision should be deterministic
        assert isinstance(decision.can_proceed, bool)
        assert isinstance(decision.reason, str)

    def test_controller_with_successful_result(self):
        """AutonomyController handles successful results correctly."""
        from atlas.evolution.autonomy.autonomy_controller import AutonomyController
        from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
        from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
        from atlas.evolution.autonomy.models import AutonomyPolicy, AuthorizationMode, RiskLevel
        from atlas.evolution.governance.models import ScopeType
        from atlas.evolution.models import ExecutionLevel

        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = AutonomyController(
            authorization_manager=AuthorizationManager(policy=policy),
            policy_engine=AutonomyPolicyEngine(policy=policy),
        )

        # Create a successful result
        result = MagicMock()
        result.status = MagicMock()
        result.status.name = "SUCCESS"

        # Check verification autonomy
        decision = controller.check_verification_autonomy(result)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY


# ---------------------------------------------------------------------------
# F. Security Boundary Tests
# ---------------------------------------------------------------------------


class TestL1SecurityBoundaries:
    """Tests for L1 security and governance boundaries."""

    def test_l1_cannot_bypass_approval_requirement(self):
        """L1 cannot bypass the approval requirement."""
        from atlas.evolution.autonomy.autonomy_controller import AutonomyController
        from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
        from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
        from atlas.evolution.autonomy.models import AutonomyPolicy, RiskLevel
        from atlas.evolution.governance.models import ScopeType
        from atlas.evolution.models import ExecutionLevel, ProposalStatus

        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = AutonomyController(
            authorization_manager=AuthorizationManager(policy=policy),
            policy_engine=AutonomyPolicyEngine(policy=policy),
        )

        # Create an unapproved proposal
        proposal = MagicMock()
        proposal.status = ProposalStatus.DRAFT  # Not APPROVED

        session = MagicMock()
        session.is_owner = True
        session.authority.value = "owner"

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "not APPROVED" in decision.reason

    def test_l1_cannot_expand_own_scope(self):
        """L1 cannot expand its own scope beyond policy."""
        from atlas.evolution.autonomy.autonomy_controller import AutonomyController
        from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
        from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
        from atlas.evolution.autonomy.models import AutonomyPolicy, RiskLevel
        from atlas.evolution.governance.models import ScopeType
        from atlas.evolution.models import ExecutionLevel, ProposalStatus

        # Policy only allows MEMORY scope
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.MEMORY],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = AutonomyController(
            authorization_manager=AuthorizationManager(policy=policy),
            policy_engine=AutonomyPolicyEngine(policy=policy),
        )

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        session = MagicMock()
        session.is_owner = True
        session.authority.value = "owner"

        decision = controller.check_execution_autonomy(proposal, session)

        # Should be denied because CODE scope is not in allowed_scopes
        assert decision.can_proceed is False
        assert decision.escalation_required is True

    def test_l1_requires_owner_for_execution(self):
        """L1 requires OWNER authority for execution."""
        from atlas.evolution.autonomy.autonomy_controller import AutonomyController
        from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
        from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
        from atlas.evolution.autonomy.models import AutonomyPolicy, RiskLevel
        from atlas.evolution.governance.models import ScopeType
        from atlas.evolution.models import ExecutionLevel, ProposalStatus

        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = AutonomyController(
            authorization_manager=AuthorizationManager(policy=policy),
            policy_engine=AutonomyPolicyEngine(policy=policy),
        )

        proposal = MagicMock()
        proposal.status = ProposalStatus.APPROVED

        # USER session (not OWNER)
        session = MagicMock()
        session.is_owner = False
        session.authority.value = "user"

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "OWNER" in decision.reason
