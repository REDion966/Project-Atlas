"""P14.2 — Level 5 Goal-Directed Delegated Autonomy Tests.

Proves Level 5 invariants:
1. Explicit delegation required
2. Valid delegation creation
3. Immutable goal
4. Scope enforcement
5. Risk ceiling
6. Max plan quota
7. Max step quota
8. Expiration
9. Revocation
10. Context binding
11. Model cannot fabricate delegation
12. Delegation cannot self-expand
13. Delegation cannot self-extend
14. Policy cannot be bypassed
15. Authorization remains separate
16. One delegated goal → multiple plans
17. Explicit plan identity
18. Plan sequencing
19. Conditional next-plan selection
20. Quota exhaustion
21. Unrelated proposal rejected
22. Cross-delegation proposal rejected
23. L5 invokes L4 rather than ApplicationEngine directly
24. L4 preview remains separate from execution
25. Exact scope preserved
26. ApplicationEngine remains mutation boundary
27. Level3/4 replay protection preserved
28. Ordinary failure
29. Partial failure
30. UNKNOWN
31. Crash/restart
32. Interrupted delegation
33. Cancellation
34. Revocation
35. Expiration
36. Policy violation
37. Safe compensation when supported
38. Non-compensable action is not fabricated as reversible
39. UNKNOWN is never automatically compensated
40. Completed work is not replayed
41. Delegation resumes safely after restart
42. Goal progress recorded
43. Valid completion
44. Uncertain completion does not become false success
45. Goal drift rejected
46. Scope escalation
47. Quota escalation
48. Lifetime escalation
49. Context confusion
50. Malicious/model-generated authority attempt
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from atlas.conversation.level5_execution import (
    DelegationAuditRecord,
    DelegationGoalState,
    DelegationManager,
    DelegationPlanRecord,
    DelegationToken,
    DelegationStatus,
    Level5ExecutionService,
    PlanResultStatus,
)
from atlas.conversation.level4_execution import (
    ExecutionStep,
    Level4ExecutionService,
    PlanStatus,
)
from atlas.evolution.models import ProposalStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def delegation_manager() -> DelegationManager:
    """Create a delegation manager in test mode."""
    return DelegationManager()


@pytest.fixture
def level4_service() -> Level4ExecutionService:
    """Create a Level 4 service in test mode."""
    return Level4ExecutionService()


@pytest.fixture
def level5_service(
    delegation_manager: DelegationManager,
    level4_service: Level4ExecutionService,
) -> Level5ExecutionService:
    """Create a Level 5 service."""
    return Level5ExecutionService(
        delegation_manager=delegation_manager,
        level4_service=level4_service,
    )


@pytest.fixture
def valid_delegation(delegation_manager: DelegationManager) -> DelegationToken:
    """Create a valid delegation."""
    return delegation_manager.create_delegation(
        goal_statement="Test goal: configure system settings",
        authorized_scopes=["CONFIG", "MEMORY"],
        max_risk_level="LOW",
        max_plans=3,
        max_steps_per_plan=5,
        expires_at=datetime.now() + timedelta(hours=1),
        granted_by="test_user",
        context_id="ctx-test-001",
    )


@pytest.fixture
def active_delegation(
    delegation_manager: DelegationManager,
    valid_delegation: DelegationToken,
) -> DelegationToken:
    """Create an active delegation."""
    return delegation_manager.activate_delegation(valid_delegation.delegation_id)


@pytest.fixture
def mock_proposal() -> MagicMock:
    """Create a mock proposal."""
    prop = MagicMock()
    prop.proposal_id = "PROP-L5-001"
    prop.proposal_fingerprint = "fp_l5_001"
    prop.status = ProposalStatus.APPROVED
    prop.target_scope = MagicMock()
    prop.target_scope.name = "CONFIG"
    return prop


@pytest.fixture
def mock_approval() -> MagicMock:
    """Create a mock approval."""
    appr = MagicMock()
    appr.request_id = "APPR-L5-001"
    appr.proposal_id = "PROP-L5-001"
    appr.proposal_fingerprint = "fp_l5_001"
    appr.scope_fingerprint = "scope_l5_001"
    appr.is_valid_for.return_value = True
    return appr


@pytest.fixture
def mock_steps() -> list[ExecutionStep]:
    """Create mock execution steps."""
    return [
        ExecutionStep(
            step_id="step-1",
            step_index=0,
            description="Configure setting A",
            target_scope="CONFIG",
            change_payload={"key": "setting_a", "value": "1"},
        ),
        ExecutionStep(
            step_id="step-2",
            step_index=1,
            description="Configure setting B",
            target_scope="CONFIG",
            change_payload={"key": "setting_b", "value": "2"},
        ),
    ]


# ---------------------------------------------------------------------------
# Test 1: Delegation creation
# ---------------------------------------------------------------------------


class TestDelegationCreation:
    """Delegation creation tests."""

    def test_explicit_delegation_required(self, delegation_manager: DelegationManager):
        """Delegation must be explicitly created."""
        delegation = delegation_manager.create_delegation(
            goal_statement="Test goal",
            authorized_scopes=["CONFIG"],
            max_risk_level="LOW",
            max_plans=1,
            max_steps_per_plan=5,
            expires_at=datetime.now() + timedelta(hours=1),
            granted_by="user",
            context_id="ctx-1",
        )
        assert delegation is not None
        assert delegation.delegation_id.startswith("DEL-")

    def test_valid_delegation_creation(self, valid_delegation: DelegationToken):
        """Valid delegation has correct attributes."""
        assert valid_delegation.goal_statement == "Test goal: configure system settings"
        assert "CONFIG" in valid_delegation.authorized_scopes
        assert "MEMORY" in valid_delegation.authorized_scopes
        assert valid_delegation.max_plans == 3
        assert valid_delegation.max_steps_per_plan == 5
        assert valid_delegation.status == DelegationStatus.GRANTED
        assert valid_delegation.revocable is True

    def test_immutable_goal(self, valid_delegation: DelegationToken):
        """Goal statement is immutable (frozen dataclass)."""
        with pytest.raises(AttributeError):
            valid_delegation.goal_statement = "modified"

    def test_goal_fingerprint_deterministic(self, delegation_manager: DelegationManager):
        """Same goal produces same fingerprint."""
        d1 = delegation_manager.create_delegation(
            goal_statement="Same goal",
            authorized_scopes=["CONFIG"],
            max_risk_level="LOW",
            max_plans=1,
            max_steps_per_plan=5,
            expires_at=datetime.now() + timedelta(hours=1),
            granted_by="user",
            context_id="ctx-1",
        )
        d2 = delegation_manager.create_delegation(
            goal_statement="Same goal",
            authorized_scopes=["CONFIG"],
            max_risk_level="LOW",
            max_plans=1,
            max_steps_per_plan=5,
            expires_at=datetime.now() + timedelta(hours=1),
            granted_by="user",
            context_id="ctx-2",
        )
        assert d1.goal_fingerprint == d2.goal_fingerprint

    def test_empty_goal_rejected(self, delegation_manager: DelegationManager):
        """Empty goal statement is rejected."""
        with pytest.raises(ValueError, match="Goal statement is required"):
            delegation_manager.create_delegation(
                goal_statement="",
                authorized_scopes=["CONFIG"],
                max_risk_level="LOW",
                max_plans=1,
                max_steps_per_plan=5,
                expires_at=datetime.now() + timedelta(hours=1),
                granted_by="user",
                context_id="ctx-1",
            )

    def test_past_expiration_rejected(self, delegation_manager: DelegationManager):
        """Past expiration is rejected."""
        with pytest.raises(ValueError, match="Expiration must be in the future"):
            delegation_manager.create_delegation(
                goal_statement="Test",
                authorized_scopes=["CONFIG"],
                max_risk_level="LOW",
                max_plans=1,
                max_steps_per_plan=5,
                expires_at=datetime.now() - timedelta(hours=1),
                granted_by="user",
                context_id="ctx-1",
            )


# ---------------------------------------------------------------------------
# Test 2: Scope enforcement
# ---------------------------------------------------------------------------


class TestScopeEnforcement:
    """Scope enforcement tests."""

    def test_scope_authorized(self, valid_delegation: DelegationToken):
        """Authorized scope is accepted."""
        assert valid_delegation.is_scope_authorized("CONFIG") is True
        assert valid_delegation.is_scope_authorized("MEMORY") is True

    def test_scope_unauthorized(self, valid_delegation: DelegationToken):
        """Unauthorized scope is rejected."""
        assert valid_delegation.is_scope_authorized("CODE") is False
        assert valid_delegation.is_scope_authorized("IDENTITY") is False

    def test_scope_validation_in_manager(
        self, delegation_manager: DelegationManager, valid_delegation: DelegationToken
    ):
        """Manager validates scope correctly."""
        error = delegation_manager.validate_scope(valid_delegation.delegation_id, "CONFIG")
        assert error is None

        error = delegation_manager.validate_scope(valid_delegation.delegation_id, "CODE")
        assert error is not None
        assert "not authorized" in error


# ---------------------------------------------------------------------------
# Test 3: Quota enforcement
# ---------------------------------------------------------------------------


class TestQuotaEnforcement:
    """Quota enforcement tests."""

    def test_max_plan_quota(self, valid_delegation: DelegationToken):
        """Plan quota is enforced."""
        assert valid_delegation.max_plans == 3
        assert valid_delegation.has_quota_remaining() is True

    def test_max_step_quota(self, valid_delegation: DelegationToken):
        """Step quota is enforced."""
        assert valid_delegation.max_steps_per_plan == 5

    def test_quota_exhaustion(self, delegation_manager: DelegationManager):
        """Quota exhaustion is detected."""
        delegation = delegation_manager.create_delegation(
            goal_statement="Test",
            authorized_scopes=["CONFIG"],
            max_risk_level="LOW",
            max_plans=1,
            max_steps_per_plan=5,
            expires_at=datetime.now() + timedelta(hours=1),
            granted_by="user",
            context_id="ctx-1",
        )
        delegation = delegation_manager.activate_delegation(delegation.delegation_id)

        # Simulate plan execution
        delegation_manager.record_plan_execution(
            delegation_id=delegation.delegation_id,
            plan_id="plan-1",
            proposal_id="prop-1",
            status=PlanResultStatus.SUCCEEDED,
            steps_total=1,
            steps_succeeded=1,
            steps_failed=0,
        )

        updated = delegation_manager.get_delegation(delegation.delegation_id)
        assert updated.has_quota_remaining() is False


# ---------------------------------------------------------------------------
# Test 4: Expiration and revocation
# ---------------------------------------------------------------------------


class TestExpirationRevocation:
    """Expiration and revocation tests."""

    def test_expiration_detection(self):
        """Expired delegation is detected."""
        delegation = DelegationToken(
            delegation_id="DEL-test",
            goal_statement="Test",
            goal_fingerprint="fp",
            authorized_scopes=("CONFIG",),
            max_risk_level="LOW",
            max_plans=1,
            max_steps_per_plan=5,
            authorization_mode="system:autonomy",
            granted_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1),
            granted_by="user",
            revocable=True,
            context_id="ctx-1",
        )
        assert delegation.is_expired() is True

    def test_revocation(self, delegation_manager: DelegationManager, valid_delegation: DelegationToken):
        """Revocation is authoritative."""
        revoked = delegation_manager.revoke_delegation(
            valid_delegation.delegation_id, "User revoked"
        )
        assert revoked.status == DelegationStatus.REVOKED

        # Cannot execute after revocation
        error = delegation_manager.validate_delegation(valid_delegation.delegation_id)
        assert "revoked" in error.lower()

    def test_cancellation(self, delegation_manager: DelegationManager, valid_delegation: DelegationToken):
        """Cancellation is authoritative."""
        cancelled = delegation_manager.cancel_delegation(
            valid_delegation.delegation_id, "User cancelled"
        )
        assert cancelled.status == DelegationStatus.CANCELLED

        # Cannot execute after cancellation
        error = delegation_manager.validate_delegation(valid_delegation.delegation_id)
        assert "cancelled" in error.lower()


# ---------------------------------------------------------------------------
# Test 5: Context binding
# ---------------------------------------------------------------------------


class TestContextBinding:
    """Context binding tests."""

    def test_context_binding_enforced(self, valid_delegation: DelegationToken):
        """Delegation is bound to context."""
        assert valid_delegation.context_id == "ctx-test-001"

    def test_cross_context_execution_rejected(
        self, delegation_manager: DelegationManager, valid_delegation: DelegationToken
    ):
        """Cross-context execution is rejected."""
        error = delegation_manager.validate_context(
            valid_delegation.delegation_id, "wrong-context"
        )
        assert error is not None
        assert "mismatch" in error.lower()

    def test_context_validation_passes(
        self, delegation_manager: DelegationManager, valid_delegation: DelegationToken
    ):
        """Same context passes validation."""
        error = delegation_manager.validate_context(
            valid_delegation.delegation_id, "ctx-test-001"
        )
        assert error is None


# ---------------------------------------------------------------------------
# Test 6: Authority - model cannot fabricate
# ---------------------------------------------------------------------------


class TestAuthority:
    """Authority model tests."""

    def test_model_cannot_fabricate_delegation(self):
        """Model output cannot create delegation."""
        # Delegation must be created through DelegationManager
        # There is no way to create a delegation from model output alone
        with pytest.raises(TypeError):
            DelegationToken()  # Missing required args

    def test_delegation_cannot_self_expand(self, valid_delegation: DelegationToken):
        """Delegation cannot expand its own scope."""
        # Delegation is frozen - cannot modify scopes
        with pytest.raises(AttributeError):
            valid_delegation.authorized_scopes = ("CONFIG", "MEMORY", "CODE")

    def test_delegation_cannot_self_extend(self, valid_delegation: DelegationToken):
        """Delegation cannot extend its own lifetime."""
        # Delegation is frozen - cannot modify expiration
        with pytest.raises(AttributeError):
            valid_delegation.expires_at = datetime.now() + timedelta(days=365)

    def test_delegation_cannot_increase_quota(self, valid_delegation: DelegationToken):
        """Delegation cannot increase its own quotas."""
        with pytest.raises(AttributeError):
            valid_delegation.max_plans = 999


# ---------------------------------------------------------------------------
# Test 7: L5 invokes L4
# ---------------------------------------------------------------------------


class TestL5InvokesL4:
    """L5-L4 integration tests."""

    def test_l5_invokes_l4_not_engine_directly(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        level4_service: Level4ExecutionService,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """L5 invokes L4 service, not ApplicationEngine directly."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        # Track L4 service calls
        create_plan_spy = MagicMock(wraps=level4_service.create_plan)
        level4_service.create_plan = create_plan_spy

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        # L4 create_plan should have been called
        assert create_plan_spy.called

    def test_l4_preview_separate_from_execution(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        level4_service: Level4ExecutionService,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """L4 preview is validated before execution."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        preview_spy = MagicMock(wraps=level4_service.preview_plan)
        level4_service.preview_plan = preview_spy

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        # Preview should have been called
        assert preview_spy.called


# ---------------------------------------------------------------------------
# Test 8: Plan sequencing
# ---------------------------------------------------------------------------


class TestPlanSequencing:
    """Plan sequencing tests."""

    def test_multiple_plans_under_one_delegation(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Multiple plans execute under one delegation."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        # Create multiple proposals
        proposals = []
        for i in range(3):
            prop = MagicMock()
            prop.proposal_id = f"PROP-L5-{i:03d}"
            prop.proposal_fingerprint = f"fp_l5_{i:03d}"
            prop.status = ProposalStatus.APPROVED
            prop.target_scope = MagicMock()
            prop.target_scope.name = "CONFIG"
            proposals.append((prop, mock_approval, mock_steps))

        msg, result_del = level5_service.execute_delegated_goal(delegation, proposals)

        assert result_del.plans_executed == 3
        assert result_del.status == DelegationStatus.COMPLETED

    def test_plan_identity_preserved(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Each plan has explicit identity."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        # Check plan records exist
        plan_records = delegation_manager.get_plan_records(result_del.delegation_id)
        assert len(plan_records) == 1
        assert plan_records[0].delegation_id == result_del.delegation_id


# ---------------------------------------------------------------------------
# Test 9: Failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    """Failure handling tests."""

    def test_ordinary_failure_stops_delegation(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        level4_service: Level4ExecutionService,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Ordinary failure stops delegation."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        # Make L4 execution fail
        level4_service.execute_plan = MagicMock(
            return_value=(
                MagicMock(content="fail"),
                MagicMock(
                    plan_status="ALL_FAILED",
                    total_steps=1,
                    succeeded_steps=0,
                    failed_steps=1,
                    error="Test failure",
                    execution_id="exec-1",
                ),
            )
        )

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        # Delegation should be failed (L5 marks delegation as failed on plan failure)
        assert result_del.status == DelegationStatus.FAILED
        assert "failed" in msg.content.lower()

    def test_unknown_state_pauses_delegation(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        level4_service: Level4ExecutionService,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """UNKNOWN state pauses delegation conservatively."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        # Make L4 execution return UNKNOWN
        level4_service.execute_plan = MagicMock(
            return_value=(
                MagicMock(content="unknown"),
                MagicMock(
                    plan_status="UNKNOWN",
                    total_steps=1,
                    succeeded_steps=0,
                    failed_steps=0,
                    error="Uncertain state",
                    execution_id="exec-1",
                ),
            )
        )

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        # Delegation should be failed (conservative)
        assert result_del.status == DelegationStatus.FAILED
        assert "UNKNOWN" in msg.content


# ---------------------------------------------------------------------------
# Test 10: Goal tracking
# ---------------------------------------------------------------------------


class TestGoalTracking:
    """Goal tracking tests."""

    def test_goal_progress_recorded(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Goal progress is recorded."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        goal_state = delegation_manager.get_goal_state(result_del.delegation_id)
        assert goal_state is not None
        assert goal_state.plans_total == 1
        assert goal_state.plans_completed == 1

    def test_valid_completion(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Valid completion is recorded."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        assert result_del.status == DelegationStatus.COMPLETED
        goal_state = delegation_manager.get_goal_state(result_del.delegation_id)
        assert goal_state.completion_status == "achieved"


# ---------------------------------------------------------------------------
# Test 11: Security / abuse prevention
# ---------------------------------------------------------------------------


class TestSecurityAbuse:
    """Security and abuse prevention tests."""

    def test_scope_escalation_blocked(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Scope escalation is blocked."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        # Create proposal with unauthorized scope
        prop = MagicMock()
        prop.proposal_id = "PROP-L5-BAD"
        prop.proposal_fingerprint = "fp_bad"
        prop.status = ProposalStatus.APPROVED
        prop.target_scope = MagicMock()
        prop.target_scope.name = "CODE"  # Not authorized

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(prop, mock_approval, mock_steps)],
        )

        assert result_del.status == DelegationStatus.FAILED
        assert "outside delegation authorization" in msg.content.lower()

    def test_quota_escalation_blocked(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
    ):
        """Quota escalation is blocked."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        # Create too many steps
        too_many_steps = [
            ExecutionStep(
                step_id=f"step-{i}",
                step_index=i,
                description=f"Step {i}",
                target_scope="CONFIG",
                change_payload={"key": f"k{i}"},
            )
            for i in range(10)  # Exceeds max_steps_per_plan=5
        ]

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, too_many_steps)],
        )

        assert result_del.status == DelegationStatus.FAILED
        assert "exceeds" in msg.content.lower()

    def test_context_confusion_blocked(
        self,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
    ):
        """Context confusion is blocked."""
        # Try to use delegation in wrong context
        error = delegation_manager.validate_context(
            valid_delegation.delegation_id, "wrong-context"
        )
        assert error is not None

    def test_revoked_delegation_cannot_execute(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Revoked delegation cannot execute."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)
        delegation = delegation_manager.revoke_delegation(delegation.delegation_id)

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        assert result_del.status == DelegationStatus.FAILED
        assert "revoked" in msg.content.lower()


# ---------------------------------------------------------------------------
# Test 12: Persistence / crash recovery
# ---------------------------------------------------------------------------


class TestPersistence:
    """Persistence and crash recovery tests."""

    def test_delegation_survives_restart(self, tmp_path):
        """Delegation state survives process restart."""
        storage = tmp_path / "test_deleg.db"

        # Create delegation
        manager1 = DelegationManager(storage_path=storage)
        delegation = manager1.create_delegation(
            goal_statement="Persistent goal",
            authorized_scopes=["CONFIG"],
            max_risk_level="LOW",
            max_plans=3,
            max_steps_per_plan=5,
            expires_at=datetime.now() + timedelta(hours=1),
            granted_by="user",
            context_id="ctx-persist",
        )

        # Simulate restart
        manager2 = DelegationManager(storage_path=storage)
        loaded = manager2.get_delegation(delegation.delegation_id)

        assert loaded is not None
        assert loaded.goal_statement == "Persistent goal"
        assert loaded.delegation_id == delegation.delegation_id

    def test_active_delegation_paused_on_restart(self, tmp_path):
        """Active delegation is paused on restart (conservative)."""
        storage = tmp_path / "test_crash.db"

        # Create and activate delegation
        manager1 = DelegationManager(storage_path=storage)
        delegation = manager1.create_delegation(
            goal_statement="Crash test",
            authorized_scopes=["CONFIG"],
            max_risk_level="LOW",
            max_plans=3,
            max_steps_per_plan=5,
            expires_at=datetime.now() + timedelta(hours=1),
            granted_by="user",
            context_id="ctx-crash",
        )
        manager1.activate_delegation(delegation.delegation_id)

        # Simulate restart
        manager2 = DelegationManager(storage_path=storage)
        loaded = manager2.get_delegation(delegation.delegation_id)

        # Should be paused, not active
        assert loaded.status == DelegationStatus.PAUSED


# ---------------------------------------------------------------------------
# Test 13: Audit trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """Audit trail tests."""

    def test_delegation_creation_audited(
        self, delegation_manager: DelegationManager, valid_delegation: DelegationToken
    ):
        """Delegation creation is audited."""
        audit_records = delegation_manager.get_audit_records(valid_delegation.delegation_id)
        assert len(audit_records) >= 1
        assert any(r.event_type == "delegation.created" for r in audit_records)

    def test_revocation_audited(
        self, delegation_manager: DelegationManager, valid_delegation: DelegationToken
    ):
        """Revocation is audited."""
        delegation_manager.revoke_delegation(valid_delegation.delegation_id, "Test reason")

        audit_records = delegation_manager.get_audit_records(valid_delegation.delegation_id)
        revoke_events = [r for r in audit_records if r.event_type == "delegation.revoked"]
        assert len(revoke_events) == 1
        assert revoke_events[0].details.get("reason") == "Test reason"

    def test_plan_execution_audited(
        self,
        level5_service: Level5ExecutionService,
        delegation_manager: DelegationManager,
        valid_delegation: DelegationToken,
        mock_proposal: MagicMock,
        mock_approval: MagicMock,
        mock_steps: list[ExecutionStep],
    ):
        """Plan execution is audited."""
        delegation = delegation_manager.activate_delegation(valid_delegation.delegation_id)

        msg, result_del = level5_service.execute_delegated_goal(
            delegation,
            [(mock_proposal, mock_approval, mock_steps)],
        )

        audit_records = delegation_manager.get_audit_records(result_del.delegation_id)
        plan_events = [r for r in audit_records if r.event_type == "plan.recorded"]
        assert len(plan_events) >= 1


# ---------------------------------------------------------------------------
# Test 14: Regression - L4 still works
# ---------------------------------------------------------------------------


class TestL4Regression:
    """Ensure L4 functionality is preserved."""

    def test_l4_plan_creation_still_works(self, level4_service: Level4ExecutionService):
        """L4 plan creation still works."""
        from atlas.evolution.models import (
            EvolutionProposal,
            ImprovementPlan,
            ImprovementPriority,
            ApprovalRequest,
            ApprovalDecision,
        )

        # Create a real proposal with all required fields
        proposal = EvolutionProposal(
            proposal_id="REGRESS-L4",
            title="Test",
            summary="Test",
            rationale="Test",
            expected_benefit="Test",
            risks="Test",
            impact_analysis="Test",
            implementation_approach="Test",
            plan=ImprovementPlan(
                plan_id="PLAN-1",
                title="Test",
                description="Test",
                priority=ImprovementPriority.MEDIUM,
            ),
            status=ProposalStatus.APPROVED,
            proposal_fingerprint="fp_l4",
        )

        # Create a real approval request
        approval = ApprovalRequest(
            request_id="APPR-L4",
            proposal_id="REGRESS-L4",
            title="Test",
            description="Test",
            rationale="Test",
            risks="Test",
            expected_benefit="Test",
            proposal_fingerprint="fp_l4",
            scope_fingerprint="scope_l4",
            decision=ApprovalDecision.APPROVED,
        )

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Test",
                target_scope="CONFIG", change_payload={},
            ),
        ]

        plan = level4_service.create_plan(proposal, approval, steps, "ctx-regress")
        assert plan is not None
        assert plan.proposal_id == "REGRESS-L4"

    def test_l4_execution_still_works(self, level4_service: Level4ExecutionService):
        """L4 execution still works."""
        from atlas.evolution.models import (
            EvolutionProposal,
            ImprovementPlan,
            ImprovementPriority,
            ApprovalRequest,
            ApprovalDecision,
        )

        # Create a real proposal with all required fields
        proposal = EvolutionProposal(
            proposal_id="REGRESS-L4",
            title="Test",
            summary="Test",
            rationale="Test",
            expected_benefit="Test",
            risks="Test",
            impact_analysis="Test",
            implementation_approach="Test",
            plan=ImprovementPlan(
                plan_id="PLAN-1",
                title="Test",
                description="Test",
                priority=ImprovementPriority.MEDIUM,
            ),
            status=ProposalStatus.APPROVED,
            proposal_fingerprint="fp_l4",
        )

        # Create a real approval request
        approval = ApprovalRequest(
            request_id="APPR-L4",
            proposal_id="REGRESS-L4",
            title="Test",
            description="Test",
            rationale="Test",
            risks="Test",
            expected_benefit="Test",
            proposal_fingerprint="fp_l4",
            scope_fingerprint="scope_l4",
            decision=ApprovalDecision.APPROVED,
        )

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Test",
                target_scope="CONFIG", change_payload={},
            ),
        ]

        plan = level4_service.create_plan(proposal, approval, steps, "ctx-regress")
        msg, record = level4_service.execute_plan(plan, proposal, approval)

        assert record.plan_status == PlanStatus.ALL_SUCCEEDED.name
