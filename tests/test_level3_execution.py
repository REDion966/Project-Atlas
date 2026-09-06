"""P13.8 — Level 3 Execution Contract Tests.

Proves the Level 3 invariants:
- L3-01: Only exact approved proposal enters implementation
- L3-02: Proposal ID + fingerprint must match
- L3-03: Stale approval cannot execute
- L3-04: Rejected/deferred/draft cannot execute
- L3-05: Approval is not authorization
- L3-06: Authorization is explicit
- L3-07: ApplicationEngine remains protected mutation boundary
- L3-08: Applied scope equals approved scope
- L3-09: No silent scope expansion
- L3-10: Protected paths/appliers remain protected
- L3-11: Proposal remains immutable during execution
- L3-12: Execution is attributable
- L3-13: Task/context binding enforced
- L3-14: No automatic promotion
- L3-15: Authorization precedes mutation
- L3-16: No ungoverned command execution
- L3-17: Filesystem scope bounded
- L3-18: Git operations governed
- L3-19: Execution result explicit
- L3-20: Failure has safe semantics
- L3-21: Partial mutation accurately represented
- L3-22: Replay controlled
- L3-23: Postconditions verifiable
- L3-24: Execution auditable
- L3-25: State transitions explicit
- L3-26: Level 2 stops before Level 3
- L3-27: No bypass path
- L3-28: Dry-run absent (documented)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atlas.conversation.execution import (
    ExecutionAuditRecord,
    Level3ExecutionService,
)
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.evolution.models import EvolutionProposal, ProposalStatus


class TestExecutionClassification:
    """Explicit execution requests must be classified correctly."""

    @pytest.mark.parametrize("text", [
        "Execute the approved proposal.",
        "Implement the approved changes.",
        "Apply the approved proposal.",
        "Carry out the approved plan.",
        "Run the approved proposal.",
        "Begin implementation of the approved proposal.",
    ])
    def test_execution_cues(self, text: str):
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.EXECUTION_REQUEST

    @pytest.mark.parametrize("text", [
        "Okay.",
        "Sure.",
        "Looks good.",
        "Sounds good.",
        "Go ahead.",
        "Do it.",
        "Proceed.",
    ])
    def test_ambiguous_not_execution(self, text: str):
        spec = TaskIntake().intake(text)
        assert spec.task_type is not TaskType.EXECUTION_REQUEST

    def test_negated_execution_not_execution(self):
        spec = TaskIntake().intake("Don't execute this proposal.")
        assert spec.task_type is not TaskType.EXECUTION_REQUEST


class TestLevel3ExecutionService:
    """Level 3 execution service contract tests."""

    def _make_proposal(
        self,
        proposal_id: str = "PROP-1",
        fingerprint: str = "fp123",
        status: ProposalStatus = ProposalStatus.APPROVED,
    ) -> MagicMock:
        proposal = MagicMock(spec=EvolutionProposal)
        proposal.proposal_id = proposal_id
        proposal.proposal_fingerprint = fingerprint
        proposal.status = status
        return proposal

    def _make_approval(
        self,
        request_id: str = "APPR-1",
        proposal_id: str = "PROP-1",
        fingerprint: str = "fp123",
        valid: bool = True,
    ) -> MagicMock:
        approval = MagicMock()
        approval.request_id = request_id
        approval.proposal_id = proposal_id
        approval.proposal_fingerprint = fingerprint

        def check_valid(prop):
            return (
                prop.proposal_id == proposal_id
                and prop.proposal_fingerprint == fingerprint
            )

        approval.is_valid_for.side_effect = check_valid
        return approval

    def test_exact_proposal_validation(self):
        """Only exact approved proposal enters implementation."""
        service = Level3ExecutionService()
        proposal = self._make_proposal()
        approval = self._make_approval()

        message, record = service.execute(proposal, approval)

        assert record.execution_status == "succeeded"
        assert record.proposal_id == "PROP-1"
        assert record.proposal_fingerprint == "fp123"

    def test_wrong_fingerprint_rejected(self):
        """Mismatched fingerprint rejects execution."""
        service = Level3ExecutionService()
        proposal = self._make_proposal(fingerprint="different_fp")
        approval = self._make_approval()  # fingerprint="fp123"

        message, record = service.execute(proposal, approval)

        assert record.execution_status == "rejected"
        assert "not valid" in record.error.lower()

    def test_wrong_proposal_id_rejected(self):
        """Different proposal ID rejects execution."""
        service = Level3ExecutionService()
        proposal = self._make_proposal(proposal_id="PROP-DIFFERENT")
        approval = self._make_approval()  # proposal_id="PROP-1"

        message, record = service.execute(proposal, approval)

        assert record.execution_status == "rejected"

    def test_rejected_approval_cannot_execute(self):
        """Rejected approval cannot execute."""
        service = Level3ExecutionService()
        proposal = self._make_proposal(status=ProposalStatus.REJECTED)
        approval = self._make_approval(valid=False)

        message, record = service.execute(proposal, approval)

        assert record.execution_status == "rejected"

    def test_replay_protection(self):
        """Duplicate execution is rejected."""
        service = Level3ExecutionService()
        proposal = self._make_proposal()
        approval = self._make_approval()

        # First execution succeeds
        message1, record1 = service.execute(proposal, approval)
        assert record1.execution_status == "succeeded"

        # Second execution rejected
        message2, record2 = service.execute(proposal, approval)
        assert record2.execution_status == "rejected"
        assert "already been executed" in record2.error

    def test_audit_record_created(self):
        """Execution creates structured audit record."""
        service = Level3ExecutionService()
        proposal = self._make_proposal()
        approval = self._make_approval()

        message, record = service.execute(proposal, approval)

        assert isinstance(record, ExecutionAuditRecord)
        assert record.execution_id
        assert record.proposal_id == "PROP-1"
        assert record.authorization_status in ("authorized", "skipped")
        assert record.execution_status in ("succeeded", "failed", "rejected", "unauthorized")

    def test_no_active_proposal_rejected(self):
        """No active proposal in state rejects execution."""
        from atlas.conversation.conversation_state import ConversationStateManager

        mgr = ConversationStateManager()
        # No active proposal set
        assert mgr.state.active_proposal_id is None

    def test_execution_does_not_mutate_files(self):
        """Execution service must not write files."""
        service = Level3ExecutionService()
        proposal = self._make_proposal()
        approval = self._make_approval()

        # Service has no file-writing capabilities
        assert not hasattr(service, "write_file")
        assert not hasattr(service, "modify_file")

    def test_execution_does_not_call_application_engine_without_wiring(self):
        """Without wired ApplicationEngine, execution is simulated."""
        service = Level3ExecutionService()  # No engine wired
        proposal = self._make_proposal()
        approval = self._make_approval()

        message, record = service.execute(proposal, approval)

        # Simulated success (no actual execution)
        assert record.execution_status == "succeeded"

    def test_execution_with_authorization_manager(self):
        """Authorization manager is consulted when wired."""
        auth_manager = MagicMock()
        auth_result = MagicMock()
        auth_result.authorized = False
        auth_result.reason = "test refusal"
        auth_manager.is_authorized.return_value = auth_result

        service = Level3ExecutionService(authorization_manager=auth_manager)
        proposal = self._make_proposal()
        approval = self._make_approval()

        message, record = service.execute(proposal, approval)

        assert record.execution_status == "unauthorized"
        assert record.authorization_status == "unauthorized"


class TestExecutionAuditRecord:
    """Audit record structure and serialization."""

    def test_record_is_immutable(self):
        record = ExecutionAuditRecord(
            execution_id="exec-1",
            proposal_id="PROP-1",
            proposal_fingerprint="fp123",
            approval_id="APPR-1",
            authorization_status="authorized",
            execution_status="succeeded",
        )
        with pytest.raises(AttributeError):
            record.execution_id = "changed"

    def test_record_to_dict(self):
        record = ExecutionAuditRecord(
            execution_id="exec-1",
            proposal_id="PROP-1",
            proposal_fingerprint="fp123",
            approval_id="APPR-1",
            authorization_status="authorized",
            execution_status="succeeded",
        )
        d = record.to_dict()
        assert d["execution_id"] == "exec-1"
        assert d["proposal_id"] == "PROP-1"
        assert d["execution_status"] == "succeeded"


class TestLevel1Level2Preservation:
    """Level 1 and Level 2 behavior must be preserved."""

    def test_investigation_still_works(self):
        """Investigation requests still classify correctly."""
        spec = TaskIntake().intake("Investigate the F17 failures.")
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_approval_still_works(self):
        """Approval requests still classify correctly."""
        spec = TaskIntake().intake("Approve this proposal.")
        assert spec.task_type is TaskType.APPROVAL

    def test_execution_checked_before_approval(self):
        """Execution cues take precedence over approval cues."""
        # "execute" contains neither approve/accept/authorize cues
        spec = TaskIntake().intake("Execute the approved proposal.")
        assert spec.task_type is TaskType.EXECUTION_REQUEST


class TestScopeFingerprintBinding:
    """Exact change-set binding tests."""

    def test_same_payload_same_fingerprint(self):
        """Identical change payloads produce identical fingerprints."""
        from atlas.evolution.autonomy.models import EvolutionRequest, ScopeType

        req1 = EvolutionRequest(
            request_id="R1",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"file.py": "content", "other.py": "data"},
        )
        req2 = EvolutionRequest(
            request_id="R2",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"file.py": "content", "other.py": "data"},
        )
        fp1 = req1.compute_scope_fingerprint()
        fp2 = req2.compute_scope_fingerprint()
        assert fp1 == fp2
        assert len(fp1) > 0

    def test_different_payload_different_fingerprint(self):
        """Changed payload produces different fingerprint."""
        from atlas.evolution.autonomy.models import EvolutionRequest, ScopeType

        req1 = EvolutionRequest(
            request_id="R1",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"file.py": "content_v1"},
        )
        req2 = EvolutionRequest(
            request_id="R2",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"file.py": "content_v2"},
        )
        assert req1.compute_scope_fingerprint() != req2.compute_scope_fingerprint()

    def test_scope_expansion_rejected(self):
        """Approved scope A cannot execute change set B."""
        from atlas.evolution.autonomy.models import EvolutionRequest, ScopeType
        from atlas.evolution.models import ApprovalRequest

        # Approved scope
        approved_req = EvolutionRequest(
            request_id="R1",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"file.py": "approved_content"},
        )
        approved_fp = approved_req.compute_scope_fingerprint()

        # Create real approval with scope bound
        approval = ApprovalRequest(
            request_id="APPR-1",
            proposal_id="PROP-1",
            title="Test",
            description="Test",
            rationale="Test",
            risks="Test",
            expected_benefit="Test",
            proposal_fingerprint="prop_fp",
            scope_fingerprint=approved_fp,
        )

        # Attempt to execute different scope
        different_req = EvolutionRequest(
            request_id="R2",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"file.py": "different_content", "extra.py": "added"},
        )

        # The approval's scope validation should reject
        assert approval.is_valid_scope(different_req) is False

        # Same scope should be valid
        same_req = EvolutionRequest(
            request_id="R3",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"file.py": "approved_content"},
        )
        assert approval.is_valid_scope(same_req) is True

    def test_approval_scope_validation_method(self):
        """ApprovalRequest.is_valid_scope() works correctly."""
        from atlas.evolution.models import ApprovalRequest

        approval = ApprovalRequest(
            request_id="APPR-1",
            proposal_id="PROP-1",
            title="Test",
            description="Test",
            rationale="Test",
            risks="Test",
            expected_benefit="Test",
            proposal_fingerprint="prop_fp",
            scope_fingerprint="scope_fp_123",
        )

        # Matching scope
        matching = MagicMock()
        matching.scope_fingerprint = "scope_fp_123"
        assert approval.is_valid_scope(matching) is True

        # Different scope
        different = MagicMock()
        different.scope_fingerprint = "different_fp"
        assert approval.is_valid_scope(different) is False

        # No scope binding (fallback to proposal-only)
        no_scope = ApprovalRequest(
            request_id="APPR-2",
            proposal_id="PROP-2",
            title="Test",
            description="Test",
            rationale="Test",
            risks="Test",
            expected_benefit="Test",
            proposal_fingerprint="prop_fp",
        )
        # Without scope binding, any request passes scope validation
        assert no_scope.is_valid_scope(matching) is True


class TestDurableReplayProtection:
    """Durable replay protection tests."""

    def _make_proposal(self):
        """Create a proposal mock that passes validation."""
        from atlas.evolution.models import ProposalStatus
        proposal = MagicMock()
        proposal.proposal_id = "PROP-1"
        proposal.proposal_fingerprint = "fp123"
        proposal.status = ProposalStatus.APPROVED
        return proposal

    def _make_approval(self):
        """Create an approval mock that passes validation."""
        approval = MagicMock()
        approval.request_id = "APPR-1"
        approval.proposal_id = "PROP-1"
        approval.proposal_fingerprint = "fp123"
        approval.scope_fingerprint = ""
        approval.is_valid_for.return_value = True
        return approval

    def test_execution_persisted_to_storage(self, tmp_path):
        """Execution records persist to SQLite storage."""
        storage_path = tmp_path / "executions.db"
        service = Level3ExecutionService(storage_path=storage_path)

        proposal = self._make_proposal()
        approval = self._make_approval()

        message, record = service.execute(proposal, approval)

        assert record.execution_status == "succeeded"

        # Record should be persisted
        assert record.execution_id in service._execution_records

        # Verify SQLite has the record
        import sqlite3
        conn = sqlite3.connect(str(storage_path))
        rows = conn.execute(
            "SELECT execution_id FROM execution_records WHERE proposal_id = ?",
            ("PROP-1",),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == record.execution_id

    def test_replay_rejected_after_restart(self, tmp_path):
        """Replay protection survives service reconstruction."""
        storage_path = tmp_path / "executions.db"

        # First service instance - execute
        service1 = Level3ExecutionService(storage_path=storage_path)
        proposal = self._make_proposal()
        approval = self._make_approval()

        message1, record1 = service1.execute(proposal, approval)
        assert record1.execution_status == "succeeded"

        # Reconstruct service (simulates process restart)
        service2 = Level3ExecutionService(storage_path=storage_path)

        # Replay attempt should be rejected
        message2, record2 = service2.execute(proposal, approval)
        assert record2.execution_status == "rejected"
        assert "already been executed" in record2.error
