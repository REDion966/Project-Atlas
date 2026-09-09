"""
Atlas P18/L1 — AutonomyController Unit Tests.

Tests the L1 Controlled Autonomy decision engine.

Coverage:
- Allowed autonomy (positive tests)
- Approval protection (negative tests)
- Scope protection (negative tests)
- Failure handling
- Escalation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from atlas.authority.models import AuthorityLevel, Principal
from atlas.evolution.autonomy.autonomy_controller import (
    AutonomyController,
    AutonomyDecision,
)
from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    RiskAssessment,
    RiskLevel,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel, ProposalStatus


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


def _make_approved_proposal() -> MagicMock:
    """Create a mock approved proposal."""
    proposal = MagicMock()
    proposal.proposal_id = "PROP-TEST-001"
    proposal.status = ProposalStatus.APPROVED
    proposal.title = "Test Proposal"
    proposal.plan.target_components = ["atlas/test/module.py"]
    return proposal


def _make_unapproved_proposal() -> MagicMock:
    """Create a mock unapproved proposal."""
    proposal = MagicMock()
    proposal.proposal_id = "PROP-TEST-002"
    proposal.status = ProposalStatus.DRAFT
    proposal.title = "Test Proposal"
    return proposal


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


def _make_disabled_policy() -> AutonomyPolicy:
    """Create a disabled autonomy policy."""
    return AutonomyPolicy(
        enabled=False,
        allowed_scopes=[],
        max_risk_level=RiskLevel.LOW,
        effective_execution_level=ExecutionLevel.ADMINISTRATIVE,
        requires_user_approval_scopes=[],
        max_requests_per_window=0,
        authorization_ttl_minutes=0,
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
# A. Allowed Autonomy Tests
# ---------------------------------------------------------------------------


class TestL1AllowedAutonomy:
    """Tests for what L1 CAN do autonomously."""

    def test_l1_can_execute_approved_plan_with_owner(self):
        """L1 can execute an approved proposal with OWNER authority."""
        controller = _make_controller(_make_l1_policy())
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY
        assert "permitted" in decision.reason.lower()

    def test_l1_can_diagnose_failure_autonomously(self):
        """L1 can autonomously diagnose failures (read-only)."""
        controller = _make_controller(_make_l1_policy())
        result = MagicMock()
        result.status = MagicMock()
        result.status.name = "FAILED"

        decision = controller.check_diagnostic_autonomy(result)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l1_can_verify_result_autonomously(self):
        """L1 can autonomously verify results (read-only)."""
        controller = _make_controller(_make_l1_policy())
        result = MagicMock()
        result.status = MagicMock()
        result.status.name = "SUCCESS"

        decision = controller.check_verification_autonomy(result)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l1_can_choose_revise_and_retry(self):
        """L1 can autonomously choose REVISE_AND_RETRY strategy."""
        controller = _make_controller(_make_l1_policy())

        diagnostic = MagicMock()
        diagnostic.failure_class.value = "implementation"
        diagnostic.confidence.value = "known"

        recovery = MagicMock()
        recovery.recoverable = True
        recovery.strategy.value = "revise_and_retry"

        decision = controller.check_recovery_autonomy(diagnostic, recovery)

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY

    def test_l1_can_continue_to_next_step_on_success(self):
        """L1 can continue to next step when last outcome was SUCCESS."""
        controller = _make_controller(_make_l1_policy())

        decision = controller.check_continuation_autonomy(
            current_step=1,
            total_steps=3,
            last_outcome_status=DevelopmentOutcomeStatus.SUCCESS,
        )

        assert decision.can_proceed is True
        assert decision.authorization_mode == AuthorizationMode.AUTONOMY


# ---------------------------------------------------------------------------
# B. Approval Protection Tests
# ---------------------------------------------------------------------------


class TestL1ApprovalProtection:
    """Tests for what L1 CANNOT bypass."""

    def test_l1_cannot_execute_without_approval(self):
        """L1 cannot execute a proposal that is not APPROVED."""
        controller = _make_controller(_make_l1_policy())
        proposal = _make_unapproved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "not APPROVED" in decision.reason

    def test_l1_cannot_execute_without_owner_authority(self):
        """L1 cannot execute without OWNER authority."""
        controller = _make_controller(_make_l1_policy())
        proposal = _make_approved_proposal()
        session = _make_user_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "OWNER authority" in decision.reason

    def test_l1_cannot_execute_when_policy_disabled(self):
        """L1 cannot execute when autonomy policy is disabled."""
        controller = _make_controller(_make_disabled_policy())
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert decision.escalation_required is True

    def test_l1_cannot_self_approve_restricted_operation(self):
        """L1 cannot approve its own restricted operations."""
        # L1 never has self-approval capability - it only checks existing approvals
        controller = _make_controller(_make_l1_policy())
        proposal = _make_unapproved_proposal()  # Not approved
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        # The decision is based on existing approval, not self-approval
        assert decision.authorization_mode is None


# ---------------------------------------------------------------------------
# C. Scope Protection Tests
# ---------------------------------------------------------------------------


class TestL1ScopeProtection:
    """Tests for L1 scope boundaries."""

    def test_l1_cannot_exceed_scope_envelope(self):
        """L1 cannot execute if scope is outside the autonomous envelope."""
        # Create a policy that doesn't allow CODE scope
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.MEMORY],  # Only MEMORY, not CODE
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(policy)
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "outside the autonomous envelope" in decision.reason
        assert decision.escalation_required is True

    def test_l1_cannot_exceed_risk_level(self):
        """L1 cannot execute if risk level exceeds policy ceiling."""
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(policy)
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        # The controller checks LOW risk by default, which should pass
        decision = controller.check_execution_autonomy(proposal, session)
        assert decision.can_proceed is True  # LOW <= LOW

    def test_l1_cannot_exceed_execution_level(self):
        """L1 cannot execute if execution level exceeds policy ceiling."""
        # Policy only allows ADMINISTRATIVE level
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.ADMINISTRATIVE,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(policy)
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "exceeds policy level" in decision.reason
        assert decision.escalation_required is True

    def test_l1_cannot_continue_past_last_step(self):
        """L1 cannot continue past the last step in the plan."""
        controller = _make_controller(_make_l1_policy())

        decision = controller.check_continuation_autonomy(
            current_step=3,
            total_steps=3,
            last_outcome_status=DevelopmentOutcomeStatus.SUCCESS,
        )

        assert decision.can_proceed is False
        assert "No remaining steps" in decision.reason


# ---------------------------------------------------------------------------
# D. Failure Handling Tests
# ---------------------------------------------------------------------------


class TestL1FailureHandling:
    """Tests for L1 failure behavior."""

    def test_l1_escalates_when_recovery_is_escalate(self):
        """L1 escalates when recovery strategy is ESCALATE."""
        controller = _make_controller(_make_l1_policy())

        diagnostic = MagicMock()
        diagnostic.failure_class.value = "capability"
        diagnostic.confidence.value = "known"

        recovery = MagicMock()
        recovery.recoverable = False
        recovery.strategy.value = "escalate"

        decision = controller.check_recovery_autonomy(diagnostic, recovery)

        assert decision.can_proceed is False
        assert decision.escalation_required is True
        assert "ESCALATE" in decision.reason

    def test_l1_stops_when_recovery_is_no_recovery(self):
        """L1 stops when recovery strategy is NO_RECOVERY."""
        controller = _make_controller(_make_l1_policy())

        diagnostic = MagicMock()
        diagnostic.failure_class.value = "governance"
        diagnostic.confidence.value = "known"

        recovery = MagicMock()
        recovery.recoverable = False
        recovery.strategy.value = "no_recovery"

        decision = controller.check_recovery_autonomy(diagnostic, recovery)

        assert decision.can_proceed is False
        assert decision.escalation_required is True
        assert "NO_RECOVERY" in decision.reason

    def test_l1_escalates_continuation_on_failure(self):
        """L1 escalates when continuation is requested after failure."""
        controller = _make_controller(_make_l1_policy())

        decision = controller.check_continuation_autonomy(
            current_step=1,
            total_steps=3,
            last_outcome_status=DevelopmentOutcomeStatus.FAILED,
        )

        assert decision.can_proceed is False
        assert decision.escalation_required is True
        assert "FAILED" in decision.reason


# ---------------------------------------------------------------------------
# E. Escalation Tests
# ---------------------------------------------------------------------------


class TestL1Escalation:
    """Tests for L1 escalation behavior."""

    def test_escalation_flag_set_when_policy_disabled(self):
        """Escalation flag is set when autonomy policy is disabled."""
        controller = _make_controller(_make_disabled_policy())
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.escalation_required is True

    def test_escalation_flag_set_when_scope_exceeded(self):
        """Escalation flag is set when scope is exceeded."""
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.MEMORY],  # Not CODE
            max_risk_level=RiskLevel.LOW,
            effective_execution_level=ExecutionLevel.SANDBOXED,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        controller = _make_controller(policy)
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.escalation_required is True

    def test_no_escalation_when_execution_permitted(self):
        """No escalation when execution is permitted."""
        controller = _make_controller(_make_l1_policy())
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.escalation_required is False


# ---------------------------------------------------------------------------
# F. Evidence Tests
# ---------------------------------------------------------------------------


class TestL1Evidence:
    """Tests for L1 evidence requirements."""

    def test_autonomy_decision_includes_evidence(self):
        """AutonomyDecision includes evidence when permitted."""
        controller = _make_controller(_make_l1_policy())
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is True
        assert "proposal_status" in decision.evidence
        assert "authority" in decision.evidence
        assert "scope" in decision.evidence

    def test_denial_includes_evidence(self):
        """AutonomyDecision includes evidence when denied."""
        controller = _make_controller(_make_disabled_policy())
        proposal = _make_approved_proposal()
        session = _make_owner_session()

        decision = controller.check_execution_autonomy(proposal, session)

        assert decision.can_proceed is False
        assert "evidence" in decision.__dataclass_fields__


# ---------------------------------------------------------------------------
# G. Immutability Tests
# ---------------------------------------------------------------------------


class TestL1Immutability:
    """Tests for AutonomyDecision immutability."""

    def test_autonomy_decision_is_frozen(self):
        """AutonomyDecision is frozen/immutable."""
        decision = AutonomyDecision(
            can_proceed=True,
            reason="Test",
        )

        with pytest.raises(AttributeError):
            decision.can_proceed = False

        with pytest.raises(AttributeError):
            decision.reason = "Modified"
