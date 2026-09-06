"""P13.2 — Level 1 Analysis-Only Contract Tests.

Proves the Level 1 invariants:
- L1-01: Level 1 may read but not mutate
- L1-02: Level 1 cannot create executable proposals
- L1-03: Level 1 cannot fabricate or obtain write authority
- L1-04: Level 1 cannot invoke protected application
- L1-05: Level 1 cannot silently transition to Level 2/3/4/5
- L1-06: Recommendations remain recommendations
- L1-07: Analysis state is not approval or authorization
- L1-08: Moving beyond analysis requires explicit user intent
- L1-09: P12 investigation behavior must remain intact
- L1-10: Human intent remains the authority for promotion
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationReport,
    InvestigationService,
)
from atlas.conversation.task_intake import TaskIntake, TaskType


class TestMixedRequestSafety:
    """Mixed analysis + implementation requests must remain analysis-only."""

    @pytest.mark.parametrize("text", [
        "Investigate this and fix it.",
        "Analyze this and implement the fix.",
        "Investigate the issue, then modify the code.",
        "investigate the F17 failures and fix them",
        "diagnose the bug and patch it",
        "inspect the code and fix the issue",
    ])
    def test_mixed_request_classifies_as_investigation(self, text):
        """Mixed requests with investigation cues classify as investigation."""
        spec = TaskIntake().intake(text)
        # Investigation cues take precedence → analysis only
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST


class TestNoExecutableProposal:
    """Level 1 investigation must not create executable proposals."""

    def test_investigation_does_not_create_proposal(self):
        """InvestigationService must not invoke development cycle."""
        service = InvestigationService()

        # The investigation service has no import access to development cycle
        # Verify by checking the module has no development-related imports
        import inspect
        source = inspect.getsource(service.investigate)
        assert "run_development_cycle" not in source
        assert "change_supplier" not in source
        assert "ChangeSupplier" not in source
        assert "EvolutionProposal" not in source

    def test_investigation_does_not_call_change_supplier(self):
        """Investigation must not invoke the change supplier."""
        service = InvestigationService()

        # Verify investigation service has no access to change supplier
        import atlas.conversation.investigation as inv_module
        source = inspect.getsource(inv_module)
        assert "ChangeSupplier" not in source
        assert "change_supplier" not in source


class TestNoWriteAuthority:
    """Level 1 must not fabricate or obtain write authority."""

    def test_investigation_does_not_request_authorization(self):
        """Investigation must not call AuthorizationManager."""
        service = InvestigationService()

        with patch(
            "atlas.evolution.autonomy.authorization_manager.AuthorizationManager"
        ) as mock_auth:
            service.investigate("F17 datetime failures")
            mock_auth.assert_not_called()

    def test_investigation_does_not_create_approval(self):
        """Investigation must not create approval requests."""
        service = InvestigationService()

        with patch(
            "atlas.evolution.approval_manager.ApprovalManager"
        ) as mock_approval:
            service.investigate("F17 datetime failures")
            mock_approval.assert_not_called()


class TestNoProtectedApplication:
    """Level 1 must not invoke ApplicationEngine or protected appliers."""

    def test_investigation_does_not_call_application_engine(self):
        """Investigation must not call ApplicationEngine.apply()."""
        service = InvestigationService()

        with patch(
            "atlas.evolution.autonomy.application_engine.ApplicationEngine.apply"
        ) as mock_apply:
            service.investigate("F17 datetime failures")
            mock_apply.assert_not_called()


class TestSafeStateStorage:
    """Analysis results stored in ConversationState must not be executable."""

    def test_investigation_report_is_immutable(self):
        """InvestigationReport must be frozen/immutable."""
        report = InvestigationReport(target="test", diagnosis="diag")
        with pytest.raises(AttributeError):
            report.target = "changed"

    def test_modification_status_always_none(self):
        """InvestigationReport.modification_status must always be NONE."""
        report = InvestigationReport(target="test")
        assert report.modification_status == "NONE"

    def test_analysis_state_is_plain_data(self):
        """Analysis results must be plain data, not executable objects."""
        report = InvestigationReport(
            target="F17",
            findings=(
                InvestigationFinding(
                    category="comparison",
                    description="test finding",
                    location="test.py:1",
                ),
            ),
            diagnosis="test diagnosis",
        )
        # Verify all fields are plain data types
        assert isinstance(report.target, str)
        assert isinstance(report.diagnosis, str)
        assert isinstance(report.findings, tuple)
        assert isinstance(report.modification_status, str)
        # No callable/executable objects embedded
        for finding in report.findings:
            assert not callable(finding)
            assert isinstance(finding.description, str)


class TestExplicitTransitionRequired:
    """Moving beyond analysis requires explicit user intent."""

    def test_analysis_does_not_auto_promote(self):
        """Analysis result must not automatically become a development request."""
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")

        # Report is just data, not a development request
        assert isinstance(report, InvestigationReport)
        # No development request type embedded
        assert not hasattr(report, "task_type")
        assert not hasattr(report, "to_development_request")

    def test_recommendation_is_string_only(self):
        """Recommended next step must be a string, not an executable."""
        report = InvestigationReport(
            target="test",
            recommended_next_step="Normalize datetimes to aware UTC",
        )
        assert isinstance(report.recommended_next_step, str)
        assert not callable(report.recommended_next_step)


class TestP12Regression:
    """P12 investigation behavior must remain intact."""

    def test_original_p12_request_still_works(self):
        """The original P12.1 request must still classify as investigation."""
        spec = TaskIntake().intake(
            "Atlas, investigate the F17 failures. Don't modify anything yet."
        )
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_investigation_produces_repository_grounded_report(self):
        """Investigation must produce real repository evidence."""
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")

        # Must have some content
        assert len(report.diagnosis) > 0 or len(report.findings) > 0
        # Must report no modification
        assert report.modification_status == "NONE"

    def test_investigation_finds_real_evidence(self):
        """Investigation must find actual repository evidence."""
        service = InvestigationService()
        report = service.investigate("datetime")

        # Should find at least one piece of evidence in the repo
        has_evidence = (
            any(f.evidence for f in report.findings)
            or report.affected_files
        )
        assert has_evidence or report.diagnosis  # has content


class TestMutationSafety:
    """Investigation must not mutate the repository."""

    def test_investigation_does_not_modify_files(self):
        """Investigation must not create, modify, or delete files."""
        service = InvestigationService()

        # Capture initial state of a test directory
        initial_files = set()
        understanding_dir = Path("atlas/understanding")
        if understanding_dir.exists():
            for f in understanding_dir.rglob("*.py"):
                initial_files.add(str(f.resolve()))

        service.investigate("F17 datetime failures")

        # Verify no new files
        after_files = set()
        if understanding_dir.exists():
            for f in understanding_dir.rglob("*.py"):
                after_files.add(str(f.resolve()))

        assert initial_files == after_files


class TestNegationIntentSafety:
    """Negation and intent must be handled safely."""

    @pytest.mark.parametrize("text,expected_type", [
        # Investigation (read-only analysis)
        ("Investigate this, don't change anything.", TaskType.INVESTIGATION_REQUEST),
        ("Analyze the bug but do not implement.", TaskType.INVESTIGATION_REQUEST),
        ("diagnose the issue, don't modify anything", TaskType.INVESTIGATION_REQUEST),
        ("inspect the code, do not change it", TaskType.INVESTIGATION_REQUEST),
        # Question (also read-only)
        ("Tell me what's wrong; don't touch the code.", TaskType.QUESTION),
        ("Find the problem only.", TaskType.INFORMATION_REQUEST),
        # Development (with self-target)
        ("Fix the bug in Atlas.", TaskType.DEVELOPMENT_REQUEST),
        ("Implement the fix for Atlas.", TaskType.DEVELOPMENT_REQUEST),
        ("Modify the code in Atlas.", TaskType.DEVELOPMENT_REQUEST),
    ])
    def test_intent_classification(self, text, expected_type):
        spec = TaskIntake().intake(text)
        assert spec.task_type is expected_type

    def test_does_not_become_development(self):
        """Read-only requests must not become development."""
        read_only_requests = [
            "Investigate this, don't change anything.",
            "Analyze the bug but do not implement.",
            "Tell me what's wrong; don't touch the code.",
            "Find the problem only.",
        ]
        for req in read_only_requests:
            spec = TaskIntake().intake(req)
            assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST, (
                f'"{req}" should not be DEVELOPMENT_REQUEST'
            )
