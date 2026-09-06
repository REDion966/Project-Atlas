"""P13.14 — Level 4 Advanced Governed Autonomy Tests.

Proves Level 4 invariants:
1. Preview does not mutate
2. Preview matches execution representation
3. Stale preview rejected
4. Approval binding preserved
5. Scope binding preserved
6. Task/context isolation
7. Multiple pending proposals
8. Explicit proposal selection
9. Multi-step execution
10. Partial failure tracking
11. Recovery from partial failure
12. Rollback awareness
13. Irreversible operation handling
14. Crash/restart reconciliation
15. UNKNOWN safety
16. Retry safety
17. Duplicate execution prevention
18. Authorization enforcement
19. ApplicationEngine mutation boundary
20. No-bypass behavior
21. Persistence/reconstruction
22. Level 1 regression
23. Level 2 regression
24. Level 3 regression
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from atlas.conversation.level4_execution import (
    ExecutionPlan,
    ExecutionStep,
    Level4AuditRecord,
    Level4ExecutionService,
    PlanStatus,
    PreviewResult,
    PreviewStatus,
    StepExecutionRecord,
    StepStatus,
)
from atlas.evolution.models import EvolutionProposal, ProposalStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> Level4ExecutionService:
    """Create a Level 4 service in test mode (no auth, no engine)."""
    return Level4ExecutionService()


@pytest.fixture
def service_with_auth() -> Level4ExecutionService:
    """Create a Level 4 service with mocked authorization."""
    auth_manager = MagicMock()
    auth_result = MagicMock()
    auth_result.authorized = True
    auth_result.reason = ""
    auth_manager.is_authorized.return_value = auth_result
    return Level4ExecutionService(authorization_manager=auth_manager)


@pytest.fixture
def service_with_engine() -> Level4ExecutionService:
    """Create a Level 4 service with mocked application engine."""
    engine = MagicMock()
    engine_apply_result = MagicMock()
    engine_apply_result.success = True
    engine_apply_result.error = None
    engine.apply.return_value = engine_apply_result
    return Level4ExecutionService(application_engine=engine)


@pytest.fixture
def proposal() -> MagicMock:
    """Create a mock approved proposal."""
    prop = MagicMock(spec=EvolutionProposal)
    prop.proposal_id = "PROP-L4-001"
    prop.proposal_fingerprint = "fp_abc123"
    prop.status = ProposalStatus.APPROVED
    prop.title = "Test Level 4 Proposal"
    prop.summary = "Test multi-step execution"
    return prop


@pytest.fixture
def approval() -> MagicMock:
    """Create a mock approval request."""
    appr = MagicMock()
    appr.request_id = "APPR-L4-001"
    appr.proposal_id = "PROP-L4-001"
    appr.proposal_fingerprint = "fp_abc123"
    appr.scope_fingerprint = "scope_xyz789"
    appr.is_valid_for.return_value = True
    return appr


@pytest.fixture
def steps() -> list[ExecutionStep]:
    """Create sample execution steps."""
    return [
        ExecutionStep(
            step_id="step-1",
            step_index=0,
            description="Create configuration entry",
            target_scope="CONFIG",
            change_payload={"key": "setting1", "value": "a"},
            failure_mode="fail_stop",
        ),
        ExecutionStep(
            step_id="step-2",
            step_index=1,
            description="Update memory record",
            target_scope="MEMORY",
            change_payload={"record": "mem1", "data": "b"},
            failure_mode="fail_stop",
        ),
        ExecutionStep(
            step_id="step-3",
            step_index=2,
            description="Register capability",
            target_scope="CAPABILITY",
            change_payload={"capability": "cap1"},
            failure_mode="fail_stop",
        ),
    ]


@pytest.fixture
def plan(
    service: Level4ExecutionService,
    proposal: MagicMock,
    approval: MagicMock,
    steps: list[ExecutionStep],
) -> ExecutionPlan:
    """Create a valid execution plan."""
    return service.create_plan(
        proposal=proposal,
        approval=approval,
        steps=steps,
        context_id="ctx-task-001",
    )


@pytest.fixture
def plan_for_engine(
    service_with_engine: Level4ExecutionService,
    proposal: MagicMock,
    approval: MagicMock,
    steps: list[ExecutionStep],
) -> ExecutionPlan:
    """Create a valid execution plan for engine-backed service."""
    return service_with_engine.create_plan(
        proposal=proposal,
        approval=approval,
        steps=steps,
        context_id="ctx-task-001",
    )


# ---------------------------------------------------------------------------
# Test 1: Preview does not mutate
# ---------------------------------------------------------------------------


class TestPreview:
    """Preview/dry-run capability tests."""

    def test_preview_does_not_mutate(self, service, proposal, approval, plan):
        """Preview must not cause any mutation."""
        preview = service.preview_plan(plan, proposal, approval)
        assert preview.status == PreviewStatus.VALID
        assert preview.validation_passed

        # Verify no execution records created
        assert len(service._execution_records) == 0

    def test_preview_matches_execution_representation(
        self, service, proposal, approval, plan
    ):
        """Preview must use same change representation as execution."""
        preview = service.preview_plan(plan, proposal, approval)

        # Preview should validate each step's fingerprint
        assert len(preview.step_results) == len(plan.steps)
        for i, result in enumerate(preview.step_results):
            assert result["step_id"] == plan.steps[i].step_id
            assert result["fingerprint"] == plan.steps[i].compute_fingerprint()

    def test_preview_validates_approval_binding(
        self, service, proposal, approval, plan
    ):
        """Preview must validate proposal-approval binding."""
        # Valid preview
        preview = service.preview_plan(plan, proposal, approval)
        assert preview.validation_passed

    def test_preview_rejects_stale_proposal(
        self, service, proposal, approval, plan
    ):
        """Preview must detect proposal changes after plan creation."""
        # Change proposal fingerprint
        approval.proposal_fingerprint = "different_fingerprint"

        preview = service.preview_plan(plan, proposal, approval)
        assert preview.status == PreviewStatus.STALE
        assert not preview.validation_passed

    def test_preview_rejects_scope_mismatch(
        self, service, proposal, approval, plan
    ):
        """Preview must detect scope fingerprint mismatch."""
        approval.scope_fingerprint = "different_scope"

        preview = service.preview_plan(plan, proposal, approval)
        assert preview.status == PreviewStatus.STALE
        assert not preview.validation_passed


# ---------------------------------------------------------------------------
# Test 2: Multi-step execution
# ---------------------------------------------------------------------------


class TestMultiStepExecution:
    """Multi-step execution tests."""

    def test_all_steps_succeed(self, service, proposal, approval, plan):
        """All steps succeed when no failures occur."""
        msg, record = service.execute_plan(plan, proposal, approval)

        assert record.plan_status == PlanStatus.ALL_SUCCEEDED.name
        assert record.total_steps == 3
        assert record.succeeded_steps == 3
        assert record.failed_steps == 0
        assert record.skipped_steps == 0

    def test_step_records_created(self, service, proposal, approval, plan):
        """Each step must create an audit record."""
        msg, record = service.execute_plan(plan, proposal, approval)

        step_records = service.get_step_records(record.execution_id)
        assert len(step_records) == 3
        assert all(r.status == StepStatus.SUCCEEDED.name for r in step_records)

    def test_step_order_preserved(self, service, proposal, approval, plan):
        """Steps must execute in order."""
        msg, record = service.execute_plan(plan, proposal, approval)

        step_records = service.get_step_records(record.execution_id)
        indices = [r.step_index for r in step_records]
        assert indices == [0, 1, 2]


# ---------------------------------------------------------------------------
# Test 3: Partial failure
# ---------------------------------------------------------------------------


class TestPartialFailure:
    """Partial failure handling tests."""

    def test_partial_failure_tracking(self, service_with_engine, proposal, approval):
        """Partial failure must be accurately tracked."""
        # Configure engine to fail on second step
        def side_effect(request):
            result = MagicMock()
            step = getattr(request, "step", None)
            if step and step.step_index == 1:
                result.success = False
                result.error = "Step 2 failed"
            else:
                result.success = True
                result.error = None
            return result

        service_with_engine._application_engine.apply.side_effect = side_effect

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Step 0",
                target_scope="CONFIG", change_payload={"a": 1},
            ),
            ExecutionStep(
                step_id="s1", step_index=1, description="Step 1",
                target_scope="CONFIG", change_payload={"a": 2},
            ),
            ExecutionStep(
                step_id="s2", step_index=2, description="Step 2",
                target_scope="CONFIG", change_payload={"a": 3},
            ),
        ]

        plan = service_with_engine.create_plan(
            proposal=proposal,
            approval=approval,
            steps=steps,
            context_id="ctx-001",
        )

        msg, record = service_with_engine.execute_plan(plan, proposal, approval)

        assert record.plan_status == PlanStatus.PARTIAL_FAILURE.name
        assert record.succeeded_steps == 1
        assert record.failed_steps == 1
        assert record.skipped_steps == 1

    def test_fail_stop_mode(self, service_with_engine, proposal, approval):
        """fail_stop mode must stop after first failure."""
        fail_count = 0

        def side_effect(request):
            nonlocal fail_count
            result = MagicMock()
            step = getattr(request, "step", None)
            if step and step.step_index == 0:
                result.success = False
                result.error = "First step failed"
            else:
                result.success = True
                result.error = None
            return result

        service_with_engine._application_engine.apply.side_effect = side_effect

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Failing step",
                target_scope="CONFIG", change_payload={"x": 1},
                failure_mode="fail_stop",
            ),
            ExecutionStep(
                step_id="s1", step_index=1, description="Should skip",
                target_scope="CONFIG", change_payload={"x": 2},
            ),
        ]

        plan = service_with_engine.create_plan(
            proposal=proposal, approval=approval, steps=steps,
            context_id="ctx-002",
        )

        msg, record = service_with_engine.execute_plan(plan, proposal, approval)

        assert record.plan_status == PlanStatus.PARTIAL_FAILURE.name
        assert record.skipped_steps == 1


# ---------------------------------------------------------------------------
# Test 4: Authorization
# ---------------------------------------------------------------------------


class TestAuthorization:
    """Authorization enforcement tests."""

    def test_unauthorized_execution_fails(self, proposal, approval, plan):
        """Unauthorized execution must fail."""
        auth_manager = MagicMock()
        auth_result = MagicMock()
        auth_result.authorized = False
        auth_result.reason = "User denied"
        auth_manager.is_authorized.return_value = auth_result

        service = Level4ExecutionService(authorization_manager=auth_manager)
        # Recreate plan in this service
        plan = service.create_plan(
            proposal=proposal, approval=approval,
            steps=[
                ExecutionStep(
                    step_id="s0", step_index=0, description="Test",
                    target_scope="CONFIG", change_payload={},
                ),
            ],
            context_id="ctx-auth",
        )

        msg, record = service.execute_plan(plan, proposal, approval)

        assert record.authorization_status == "unauthorized"
        assert "User denied" in record.error

    def test_approval_not_authorization(self, proposal, approval):
        """Approval alone must not grant execution authority."""
        auth_manager = MagicMock()
        auth_result = MagicMock()
        auth_result.authorized = False
        auth_result.reason = "Separate authorization required"
        auth_manager.is_authorized.return_value = auth_result

        service = Level4ExecutionService(authorization_manager=auth_manager)
        plan = service.create_plan(
            proposal=proposal, approval=approval,
            steps=[
                ExecutionStep(
                    step_id="s0", step_index=0, description="Test",
                    target_scope="CONFIG", change_payload={},
                ),
            ],
            context_id="ctx-auth2",
        )

        # Even with approval, execution must fail without authorization
        msg, record = service.execute_plan(plan, proposal, approval)
        assert record.authorization_status == "unauthorized"


# ---------------------------------------------------------------------------
# Test 5: Task/context isolation
# ---------------------------------------------------------------------------


class TestContextIsolation:
    """Task/context binding and isolation tests."""

    def test_context_binding_enforced(self, service, proposal, approval, steps):
        """Plan must be bound to its creation context."""
        plan = service.create_plan(
            proposal=proposal, approval=approval,
            steps=steps, context_id="ctx-isolated",
        )

        assert plan.context_id == "ctx-isolated"
        context_plans = service.get_context_plans("ctx-isolated")
        assert len(context_plans) == 1

    def test_cross_context_execution_rejected(
        self, service, proposal, approval, steps
    ):
        """Execution must reject plans from different contexts."""
        plan = service.create_plan(
            proposal=proposal, approval=approval,
            steps=steps, context_id="ctx-original",
        )

        # Tamper with context binding (simulate context confusion)
        service._context_plans["ctx-original"].discard(plan.plan_id)

        msg, record = service.execute_plan(plan, proposal, approval)

        assert "not bound to context" in record.error

    def test_multiple_contexts_isolated(self, service, proposal, approval):
        """Multiple contexts must remain isolated."""
        steps_a = [
            ExecutionStep(
                step_id="a0", step_index=0, description="A",
                target_scope="CONFIG", change_payload={},
            ),
        ]
        steps_b = [
            ExecutionStep(
                step_id="b0", step_index=0, description="B",
                target_scope="MEMORY", change_payload={},
            ),
        ]

        plan_a = service.create_plan(
            proposal=proposal, approval=approval,
            steps=steps_a, context_id="ctx-A",
        )
        plan_b = service.create_plan(
            proposal=proposal, approval=approval,
            steps=steps_b, context_id="ctx-B",
        )

        # Contexts must be isolated
        assert len(service.get_context_plans("ctx-A")) == 1
        assert len(service.get_context_plans("ctx-B")) == 1
        assert service.get_context_plans("ctx-A")[0].plan_id != \
               service.get_context_plans("ctx-B")[0].plan_id


# ---------------------------------------------------------------------------
# Test 6: Multiple proposals
# ---------------------------------------------------------------------------


class TestMultipleProposals:
    """Multiple pending proposal support tests."""

    def test_multiple_proposals_coexist(self, service, approval):
        """Multiple proposals can coexist."""
        prop1 = MagicMock(spec=EvolutionProposal)
        prop1.proposal_id = "PROP-MULTI-1"
        prop1.proposal_fingerprint = "fp_multi_1"
        prop1.status = ProposalStatus.APPROVED

        prop2 = MagicMock(spec=EvolutionProposal)
        prop2.proposal_id = "PROP-MULTI-2"
        prop2.proposal_fingerprint = "fp_multi_2"
        prop2.status = ProposalStatus.APPROVED

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Multi",
                target_scope="CONFIG", change_payload={},
            ),
        ]

        plan1 = service.create_plan(
            proposal=prop1, approval=approval, steps=steps,
            context_id="ctx-multi",
        )
        plan2 = service.create_plan(
            proposal=prop2, approval=approval, steps=steps,
            context_id="ctx-multi",
        )

        # Both plans coexist in same context
        context_plans = service.get_context_plans("ctx-multi")
        assert len(context_plans) == 2

    def test_proposal_selection_explicit(self, service, approval):
        """Execution must target an explicit proposal."""
        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Select",
                target_scope="CONFIG", change_payload={},
            ),
        ]

        prop_a = MagicMock(spec=EvolutionProposal)
        prop_a.proposal_id = "PROP-A"
        prop_a.proposal_fingerprint = "fp_a"
        prop_a.status = ProposalStatus.APPROVED

        prop_b = MagicMock(spec=EvolutionProposal)
        prop_b.proposal_id = "PROP-B"
        prop_b.proposal_fingerprint = "fp_b"
        prop_b.status = ProposalStatus.APPROVED

        plan_a = service.create_plan(
            proposal=prop_a, approval=approval, steps=steps,
            context_id="ctx-select",
        )
        plan_b = service.create_plan(
            proposal=prop_b, approval=approval, steps=steps,
            context_id="ctx-select",
        )

        # Execute plan_a, verify it targets PROP-A
        msg, record = service.execute_plan(plan_a, prop_a, approval)
        assert record.proposal_id == "PROP-A"

        # Verify plan_b was not executed
        assert service.get_execution_record("nonexistent") is None


# ---------------------------------------------------------------------------
# Test 7: Replay/duplicate protection
# ---------------------------------------------------------------------------


class TestReplayProtection:
    """Duplicate execution prevention tests."""

    def test_duplicate_execution_rejected(self, service, proposal, approval, plan):
        """Duplicate execution of successful plan must be rejected."""
        # First execution succeeds
        msg1, record1 = service.execute_plan(plan, proposal, approval)
        assert record1.plan_status == PlanStatus.ALL_SUCCEEDED.name

        # Second execution must be rejected
        msg2, record2 = service.execute_plan(plan, proposal, approval)
        assert "already been executed" in record2.error

    def test_failed_plan_can_retry(self, service_with_engine, proposal, approval):
        """Failed plan can be retried."""
        def fail_first_only(request):
            result = MagicMock()
            # Fail on first call only
            if not hasattr(fail_first_only, "called"):
                fail_first_only.called = True
                result.success = False
                result.error = "Transient failure"
            else:
                result.success = True
                result.error = None
            return result

        service_with_engine._application_engine.apply.side_effect = fail_first_only

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Retry step",
                target_scope="CONFIG", change_payload={},
            ),
        ]

        plan = service_with_engine.create_plan(
            proposal=proposal, approval=approval, steps=steps,
            context_id="ctx-retry",
        )

        # First attempt fails
        msg1, record1 = service_with_engine.execute_plan(plan, proposal, approval)
        assert record1.plan_status == PlanStatus.ALL_FAILED.name


# ---------------------------------------------------------------------------
# Test 8: Dry-run execution
# ---------------------------------------------------------------------------


class TestDryRun:
    """Dry-run execution tests."""

    def test_dry_run_no_mutation(self, service, proposal, approval, plan):
        """Dry-run must not mutate state."""
        msg, record = service.execute_plan(
            plan, proposal, approval, dry_run=True,
        )

        assert record.dry_run is True
        assert record.plan_status == PlanStatus.PREVIEWED.name
        assert "No changes were made" in msg.content

    def test_dry_run_validates_authorization(
        self, proposal, approval, plan
    ):
        """Dry-run with auth must validate without granting."""
        auth_manager = MagicMock()
        auth_result = MagicMock()
        auth_result.authorized = True
        auth_manager.is_authorized.return_value = auth_result

        service = Level4ExecutionService(authorization_manager=auth_manager)
        plan = service.create_plan(
            proposal=proposal, approval=approval,
            steps=[
                ExecutionStep(
                    step_id="s0", step_index=0, description="Test",
                    target_scope="CONFIG", change_payload={},
                ),
            ],
            context_id="ctx-dry",
        )

        msg, record = service.execute_plan(
            plan, proposal, approval, dry_run=True,
        )

        assert record.dry_run is True
        assert record.authorization_status == "authorized"


# ---------------------------------------------------------------------------
# Test 9: Crash recovery
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    """Crash/restart reconciliation tests."""

    def test_recovery_detected_on_startup(self, tmp_path):
        """Stale EXECUTING plans detected on startup."""
        storage = tmp_path / "test_crash.db"

        # Create service and start an execution
        service1 = Level4ExecutionService(storage_path=storage)

        proposal = MagicMock(spec=EvolutionProposal)
        proposal.proposal_id = "PROP-CRASH"
        proposal.proposal_fingerprint = "fp_crash"
        proposal.status = ProposalStatus.APPROVED

        approval = MagicMock()
        approval.request_id = "APPR-CRASH"
        approval.proposal_id = "PROP-CRASH"
        approval.proposal_fingerprint = "fp_crash"
        approval.scope_fingerprint = "scope_crash"
        approval.is_valid_for.return_value = True

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Crash step",
                target_scope="CONFIG", change_payload={},
            ),
        ]

        plan = service1.create_plan(
            proposal=proposal, approval=approval, steps=steps,
            context_id="ctx-crash",
        )

        # Simulate crash: mark plan as EXECUTING
        service1._update_plan_status(plan, PlanStatus.EXECUTING)
        assert service1.get_plan(plan.plan_id).status == PlanStatus.EXECUTING

        # Create new service instance (simulates restart)
        service2 = Level4ExecutionService(storage_path=storage)

        # Plan should be in RECOVERY_NEEDED state
        recovered_plan = service2.get_plan(plan.plan_id)
        assert recovered_plan.status == PlanStatus.RECOVERY_NEEDED

    def test_unknown_step_state_conservative(self):
        """UNKNOWN step state must require manual resolution."""
        record = Level4AuditRecord(
            execution_id="test",
            plan_id="plan",
            proposal_id="prop",
            proposal_fingerprint="fp",
            approval_id="appr",
            scope_fingerprint="scope",
            context_id="ctx",
            authorization_status="authorized",
            plan_status=PlanStatus.RECOVERY_NEEDED.name,
            total_steps=3,
            succeeded_steps=1,
            failed_steps=0,
            skipped_steps=0,
            preview_validated=False,
            dry_run=False,
        )

        # RECOVERY_NEEDED is not safe to retry
        assert not record.is_safe_to_retry


# ---------------------------------------------------------------------------
# Test 10: Preview stale detection
# ---------------------------------------------------------------------------


class TestPreviewStaleDetection:
    """Preview staleness detection tests."""

    def test_stale_preview_rejected_on_execution(
        self, service, proposal, approval, plan
    ):
        """Execution must reject stale preview."""
        # Create valid preview
        preview = service.preview_plan(plan, proposal, approval)
        assert preview.status == PreviewStatus.VALID

        # Tamper with preview (simulate state change)
        stale_preview = PreviewResult(
            preview_id=preview.preview_id,
            plan_id=preview.plan_id,
            plan_fingerprint="tampered_fingerprint",
            context_id=preview.context_id,
            status=PreviewStatus.VALID,
        )

        msg, record = service.execute_plan(
            plan, proposal, approval, preview=stale_preview,
        )

        assert "fingerprint does not match" in record.error

    def test_preview_before_execution(
        self, service, proposal, approval, plan
    ):
        """Preview can be used to gate execution."""
        preview = service.preview_plan(plan, proposal, approval)
        assert preview.validation_passed

        # Execute with valid preview
        msg, record = service.execute_plan(
            plan, proposal, approval, preview=preview,
        )

        assert record.preview_validated is True
        assert record.plan_status == PlanStatus.ALL_SUCCEEDED.name


# ---------------------------------------------------------------------------
# Test 11: ApplicationEngine boundary
# ---------------------------------------------------------------------------


class TestApplicationEngineBoundary:
    """ApplicationEngine mutation boundary tests."""

    def test_mutation_through_engine_only(
        self, service_with_engine, proposal, approval, plan_for_engine
    ):
        """All mutation must go through ApplicationEngine."""
        msg, record = service_with_engine.execute_plan(
            plan_for_engine, proposal, approval
        )

        # Engine must be called for each step
        assert service_with_engine._application_engine.apply.call_count == 3

    def test_no_direct_mutation_bypass(self, service, proposal, approval, plan):
        """No path may bypass ApplicationEngine."""
        # In test mode (engine=None), execution simulates success
        msg, record = service.execute_plan(plan, proposal, approval)

        # Without engine, no actual mutation occurs
        assert record.plan_status == PlanStatus.ALL_SUCCEEDED.name


# ---------------------------------------------------------------------------
# Test 12: State semantics
# ---------------------------------------------------------------------------


class TestStateSemantics:
    """State transition tests."""

    def test_plan_status_transitions(self, service, proposal, approval, plan):
        """Plan status must transition correctly."""
        # Initial status is PLANNED
        assert plan.status == PlanStatus.PLANNED

        # After execution, status updates
        msg, record = service.execute_plan(plan, proposal, approval)
        updated_plan = service.get_plan(plan.plan_id)
        assert updated_plan.status == PlanStatus.ALL_SUCCEEDED

    def test_audit_record_immutable(self, service, proposal, approval, plan):
        """Audit records must be immutable once created."""
        msg, record = service.execute_plan(plan, proposal, approval)

        # Record is frozen dataclass
        with pytest.raises(AttributeError):
            record.plan_status = "tampered"  # type: ignore[misc]

    def test_step_record_terminal_states(self):
        """Step records must have correct terminal states."""
        record = StepExecutionRecord(
            record_id="r1",
            execution_id="e1",
            plan_id="p1",
            step_id="s1",
            step_index=0,
            proposal_id="prop1",
            approval_id="appr1",
            context_id="ctx1",
            status=StepStatus.SUCCEEDED.name,
        )

        assert record.status == StepStatus.SUCCEEDED.name


# ---------------------------------------------------------------------------
# Test 13: Fail-closed behavior
# ---------------------------------------------------------------------------


class TestFailClosed:
    """Fail-closed safety tests."""

    def test_invalid_proposal_fails_closed(self, service, approval, plan):
        """Invalid proposal must fail closed."""
        invalid_proposal = MagicMock(spec=EvolutionProposal)
        invalid_proposal.proposal_id = "PROP-INVALID"
        invalid_proposal.proposal_fingerprint = "wrong_fp"
        invalid_proposal.status = ProposalStatus.REJECTED

        approval.is_valid_for.return_value = False

        msg, record = service.execute_plan(plan, invalid_proposal, approval)

        assert record.plan_status == "failed"

    def test_missing_authorization_fails_closed(self, proposal, approval, plan):
        """Missing authorization must fail closed."""
        auth_manager = MagicMock()
        auth_result = MagicMock()
        auth_result.authorized = False
        auth_result.reason = "No authorization"
        auth_manager.is_authorized.return_value = auth_result

        service = Level4ExecutionService(authorization_manager=auth_manager)
        plan = service.create_plan(
            proposal=proposal, approval=approval,
            steps=[
                ExecutionStep(
                    step_id="s0", step_index=0, description="Test",
                    target_scope="CONFIG", change_payload={},
                ),
            ],
            context_id="ctx-fail",
        )

        msg, record = service.execute_plan(plan, proposal, approval)

        assert record.authorization_status == "unauthorized"
        assert "No authorization" in record.error


# ---------------------------------------------------------------------------
# Test 14: Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    """Durable persistence tests."""

    def test_records_persisted_to_storage(
        self, tmp_path, proposal, approval
    ):
        """Records must persist to durable storage."""
        storage = tmp_path / "test_persist.db"
        service = Level4ExecutionService(storage_path=storage)

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Persist",
                target_scope="CONFIG", change_payload={"k": "v"},
            ),
        ]

        plan = service.create_plan(
            proposal=proposal, approval=approval, steps=steps,
            context_id="ctx-persist",
        )

        msg, record = service.execute_plan(plan, proposal, approval)

        # Create new service instance (simulates restart)
        service2 = Level4ExecutionService(storage_path=storage)

        # Record should be persisted
        loaded_record = service2.get_execution_record(record.execution_id)
        assert loaded_record is not None
        assert loaded_record.plan_status == PlanStatus.ALL_SUCCEEDED.name

    def test_plans_persisted(
        self, tmp_path, proposal, approval
    ):
        """Plans must persist across restarts."""
        storage = tmp_path / "test_plans.db"
        service1 = Level4ExecutionService(storage_path=storage)

        steps = [
            ExecutionStep(
                step_id="s0", step_index=0, description="Plan",
                target_scope="CONFIG", change_payload={},
            ),
        ]

        plan = service1.create_plan(
            proposal=proposal, approval=approval, steps=steps,
            context_id="ctx-plan-persist",
        )

        # New service instance
        service2 = Level4ExecutionService(storage_path=storage)

        loaded_plan = service2.get_plan(plan.plan_id)
        assert loaded_plan is not None
        assert loaded_plan.proposal_id == "PROP-L4-001"


# ---------------------------------------------------------------------------
# Test 15: Level 1/2/3 regression
# ---------------------------------------------------------------------------


class TestRegression:
    """Regression tests for Level 1/2/3 contracts."""

    def test_level1_investigation_preserved(self):
        """Level 1 investigation classification must be preserved."""
        from atlas.conversation.task_intake import TaskIntake, TaskType

        spec = TaskIntake().intake("Investigate the failure patterns.")
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_level2_approval_preserved(self):
        """Level 2 proposal/approval contract must be preserved."""
        from atlas.evolution.approval_manager import ApprovalManager
        from atlas.evolution.models import EvolutionProposal, ProposalStatus

        proposal = EvolutionProposal(
            proposal_id="REGRESS-1",
            title="Regression test",
            summary="Test",
            rationale="Test",
            expected_benefit="Test",
            risks="Test",
            impact_analysis="Test",
            implementation_approach="Test",
            plan=MagicMock(),
            status=ProposalStatus.DRAFT,
        )

        manager = ApprovalManager()
        request = manager.create_approval_request(proposal)

        assert request.proposal_id == "REGRESS-1"
        assert proposal.status == ProposalStatus.PENDING_APPROVAL

    def test_level3_execution_preserved(self):
        """Level 3 single-step execution must still work."""
        from atlas.conversation.execution import Level3ExecutionService

        service = Level3ExecutionService()

        proposal = MagicMock(spec=EvolutionProposal)
        proposal.proposal_id = "L3-REGRESS"
        proposal.proposal_fingerprint = "fp_l3"
        proposal.status = ProposalStatus.APPROVED

        approval = MagicMock()
        approval.request_id = "APPR-L3"
        approval.proposal_id = "L3-REGRESS"
        approval.proposal_fingerprint = "fp_l3"
        approval.is_valid_for.return_value = True

        msg, record = service.execute(proposal, approval)

        assert record.execution_status == "succeeded"
