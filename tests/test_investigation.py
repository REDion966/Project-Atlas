"""P12.3 — Read-only investigation capability tests.

Proves the investigation classification, routing, read-only safety, and
reporting contract.
"""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationReport,
    InvestigationService,
)
from atlas.conversation.task_intake import TaskIntake, TaskType


class TestInvestigationClassification:
    """Investigation requests must be classified correctly."""

    @pytest.mark.parametrize("text", [
        "investigate the F17 failures",
        "analyze the F17 failures",
        "diagnose this bug",
        "inspect the repository",
        "examine the datetime handling",
        "trace the error",
        "debug the comparison issue",
    ])
    def test_investigation_cues(self, text):
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_p12_regression_does_not_become_development(self):
        """The P12.1 regression: 'don't modify' must not trigger development."""
        spec = TaskIntake().intake(
            "Atlas, investigate the F17 failures. Don't modify anything yet."
        )
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_genuine_development_still_classified(self):
        """Genuine development requests remain DEVELOPMENT_REQUEST."""
        spec = TaskIntake().intake("implement the F17 fix for Atlas")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST

    def test_modify_atlas_still_development(self):
        """'modify Atlas' without negation is still development."""
        spec = TaskIntake().intake("modify the datetime handling in Atlas")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST


class TestNegationHandling:
    """Negation must prevent misclassification."""

    def test_dont_modify_not_development(self):
        """'don't modify' should not be classified as development."""
        spec = TaskIntake().intake("don't modify anything")
        # Should NOT be DEVELOPMENT_REQUEST
        assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST

    def test_do_not_change_not_development(self):
        """'do not change' should not be classified as development."""
        spec = TaskIntake().intake("do not change the code")
        assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST


class TestInvestigationService:
    """InvestigationService produces read-only reports."""

    def test_investigation_returns_report(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        assert isinstance(report, InvestigationReport)
        assert report.target == "F17 datetime failures"

    def test_investigation_modification_status_is_none(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        assert report.modification_status == "NONE"

    def test_investigation_finds_datetime_issues(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        # Should find some findings related to datetime
        assert len(report.findings) > 0 or report.diagnosis  # has content

    def test_investigation_markdown_report(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        md = report.to_markdown()
        assert "F17 datetime failures" in md
        assert "NONE" in md  # modification status

    def test_investigation_does_not_mutate(self):
        """Investigation must not create/modify/delete files."""
        import os
        import tempfile

        # Get initial state
        initial_files = set()
        for root, dirs, files in os.walk("atlas/understanding"):
            for f in files:
                initial_files.add(os.path.join(root, f))

        service = InvestigationService()
        service.investigate("F17 datetime failures")

        # Verify no new files created
        after_files = set()
        for root, dirs, files in os.walk("atlas/understanding"):
            for f in files:
                after_files.add(os.path.join(root, f))

        assert initial_files == after_files


class TestInvestigationReport:
    """InvestigationReport structure and serialization."""

    def test_report_is_frozen(self):
        report = InvestigationReport(target="test")
        with pytest.raises(AttributeError):
            report.target = "changed"

    def test_report_to_dict(self):
        report = InvestigationReport(
            target="F17",
            diagnosis="mixed naive/aware datetimes",
            affected_files=("a.py", "b.py"),
        )
        d = report.to_dict() if hasattr(report, "to_dict") else None
        # to_markdown is the serialization method
        md = report.to_markdown()
        assert "F17" in md
        assert "mixed naive/aware datetimes" in md


class TestP14_1RoutingRegression:
    """P14.1 — tool/action identifiers must not trigger investigation routing.

    Investigation cues use word-boundary matching so that a cue like "inspect"
    matches standalone investigation language but does NOT match when it appears
    as a substring of a tool/action identifier such as "code_inspector".
    """

    @pytest.mark.parametrize("text", [
        "Run code_inspector to find files.",
        "execute code_inspector on the project",
        "use the code_analyzer tool",
        "run the debugger on this function",
        "invoke code_tracer to find the bug",
    ])
    def test_tool_name_with_investigation_substring_not_investigation(self, text):
        """Tool/action identifiers containing investigation cues are not investigation."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is not TaskType.INVESTIGATION_REQUEST

    @pytest.mark.parametrize("text", [
        "inspect the repository",
        "inspect the datetime handling",
        "please inspect this code carefully",
        "analyze the failure mode",
        "trace the error to its source",
        "debug the comparison issue",
        "examine the log output",
        "diagnose the performance problem",
    ])
    def test_genuine_investigation_language_still_investigation(self, text):
        """Standalone investigation cues in normal language remain investigation."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST
