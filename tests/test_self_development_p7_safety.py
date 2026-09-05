"""M4.2 — Self-Development Safety Regression Hardening.

Pins three safety invariants of the governed self-development pipeline:

A. Failed/partial development outcomes remain explicitly represented as
   failures in learning and are never recorded as successful/trusted.

B. Approval replay is rejected: a consumed approval cannot be applied twice.

C. Sandbox path confinement rejects traversal, absolute paths, Windows drive
   prefixes, and attempts to escape the sandbox root.

No production behavior is changed; these tests prove the existing contract.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.autonomy.code_sandbox import (
    CodeChangeSet,
    CodeSandbox,
    SandboxPathError,
)
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import build_learning_insight
from atlas.learning_engine.models import (
    InsightImportance,
    LearningCategory,
    LearningInsight,
)


# ---------------------------------------------------------------------------
# Invariant A — Failed development must remain failed in learning.
# ---------------------------------------------------------------------------


def _failed_outcome(proposal_id: str = "DEV-FAIL-1") -> DevelopmentOutcome:
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.FAILED,
        proposal_id=proposal_id,
        plan_id="PLAN-1",
        iteration=1,
        message="implementation failed in sandbox",
        verification_passed=False,
        rollback_occurred=True,
        test_outcome="failed",
        effectiveness_proxy=0.0,
    )


def _success_outcome(proposal_id: str = "DEV-OK-1") -> DevelopmentOutcome:
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id=proposal_id,
        plan_id="PLAN-2",
        iteration=1,
        message="development iteration succeeded in sandbox.",
        changed_files=["atlas/new_module.py"],
        verification_passed=True,
        test_outcome="passed",
        effectiveness_proxy=1.0,
    )


class TestFailedDevelopmentRemainsFailed:
    """A failed iteration must never be recorded as successful learning."""

    def test_failed_outcome_produces_failure_learning(self) -> None:
        insight = build_learning_insight(_failed_outcome())
        assert isinstance(insight, LearningInsight)

    def test_failed_outcome_preserves_failure_category(self) -> None:
        insight = build_learning_insight(_failed_outcome())
        assert insight.category == LearningCategory.FAILURE_AVOIDANCE

    def test_failed_outcome_is_not_marked_success(self) -> None:
        insight = build_learning_insight(_failed_outcome())
        # The title must not claim success for a failed iteration.
        assert "failed" in insight.title.lower()
        assert "succeeded" not in insight.title.lower()

    def test_failed_outcome_metadata_preserves_status(self) -> None:
        insight = build_learning_insight(_failed_outcome())
        assert insight.metadata["outcome"] == "FAILED"
        assert insight.metadata["verification_passed"] is False

    def test_failed_outcome_has_lower_confidence_than_success(self) -> None:
        failed = build_learning_insight(_failed_outcome())
        success = build_learning_insight(_success_outcome())
        # Failure insights must be strictly less confident than success.
        assert failed.confidence < success.confidence
        assert failed.importance == InsightImportance.MEDIUM
        assert success.importance == InsightImportance.LOW

    def test_success_outcome_still_records_success(self) -> None:
        """Regression guard: success path must remain unchanged."""
        insight = build_learning_insight(_success_outcome())
        assert insight.category == LearningCategory.TOOL_USAGE
        assert "succeeded" in insight.title.lower()
        assert insight.metadata["outcome"] == "SUCCESS"


# ---------------------------------------------------------------------------
# Invariant B — Approval replay must be rejected.
# ---------------------------------------------------------------------------


def _pending_request(proposal_id: str = "DEV-REPLAY-1") -> ApprovalRequest:
    return ApprovalRequest(
        request_id="APPR-1",
        proposal_id=proposal_id,
        title="Add feature X",
        description="Implementation details.",
        rationale="Improves test coverage.",
        risks="Low",
        expected_benefit="Better coverage.",
    )


class TestApprovalReplayRejected:
    """A consumed approval cannot be applied a second time."""

    def test_first_approval_succeeds(self) -> None:
        manager = ApprovalManager()
        request = _pending_request()
        manager.approve(request, comment="looks good")
        assert request.decision == ApprovalDecision.APPROVED
        assert request.decision_comment == "looks good"

    def test_second_approval_raises(self) -> None:
        manager = ApprovalManager()
        request = _pending_request()
        manager.approve(request)
        with pytest.raises(ValueError):
            manager.approve(request)

    def test_replay_does_not_mutate_state(self) -> None:
        manager = ApprovalManager()
        request = _pending_request()
        manager.approve(request, comment="first")
        with pytest.raises(ValueError):
            manager.approve(request, comment="replay")
        # The first approval stands; the replay is rejected cleanly.
        assert request.decision == ApprovalDecision.APPROVED
        assert request.decision_comment == "first"

    def test_reject_after_approval_also_raises(self) -> None:
        manager = ApprovalManager()
        request = _pending_request()
        manager.approve(request)
        with pytest.raises(ValueError):
            manager.reject(request, reason="changed my mind")

    def test_cannot_approve_without_pending_decision(self) -> None:
        request = _pending_request()
        request.decision = ApprovalDecision.REJECTED
        with pytest.raises(ValueError):
            ApprovalManager().approve(request)


# ---------------------------------------------------------------------------
# Invariant C — Sandbox path confinement.
# ---------------------------------------------------------------------------


class TestSandboxPathConfinement:
    """Unsafe paths must be rejected before any filesystem access."""

    @pytest.mark.parametrize(
        "bad_path",
        [
            "../outside",
            "../../outside",
            "foo/../../outside",
            "subdir/../../../etc/passwd",
        ],
    )
    def test_rejects_parent_traversal(self, bad_path: str) -> None:
        with pytest.raises(SandboxPathError):
            CodeChangeSet.validate_path(bad_path)

    @pytest.mark.parametrize(
        "bad_path",
        [
            "/etc/passwd",
            "/absolute/path",
            "\\windows\\system32",
        ],
    )
    def test_rejects_absolute_paths(self, bad_path: str) -> None:
        with pytest.raises(SandboxPathError):
            CodeChangeSet.validate_path(bad_path)

    @pytest.mark.parametrize(
        "bad_path",
        [
            "C:\\outside",
            "D:\\data\\file.txt",
            "c:/mixed/path",
        ],
    )
    def test_rejects_windows_drive_prefixes(self, bad_path: str) -> None:
        with pytest.raises(SandboxPathError):
            CodeChangeSet.validate_path(bad_path)

    def test_rejects_dot_segments(self) -> None:
        with pytest.raises(SandboxPathError):
            CodeChangeSet.validate_path("foo/./etc")

    def test_rejects_empty_and_blank_segments(self) -> None:
        with pytest.raises(SandboxPathError):
            CodeChangeSet.validate_path("foo//bar")
        with pytest.raises(SandboxPathError):
            CodeChangeSet.validate_path("")

    def test_accepts_safe_relative_paths(self) -> None:
        for good in ("atlas/new_module.py", "tests/test_x.py", "a/b/c.txt"):
            CodeChangeSet.validate_path(good)  # must not raise

    def test_rejected_path_does_not_escape_to_filesystem(self) -> None:
        """A rejected traversal must not create files outside the sandbox."""
        with tempfile.TemporaryDirectory() as base:
            sandbox = CodeSandbox(base_dir=base)
            try:
                with pytest.raises(SandboxPathError):
                    sandbox.resolve("../escape.txt")
                # No file should exist outside the root.
                parent = pathlib.Path(base).resolve().parent
                assert not (parent / "escape.txt").exists()
            finally:
                sandbox.cleanup()

    def test_symlink_escape_is_rejected(self) -> None:
        """Symlink-based escapes are rejected where symlinks are creatable."""
        with tempfile.TemporaryDirectory() as base:
            sandbox = CodeSandbox(base_dir=base)
            try:
                outside = pathlib.Path(base).resolve().parent / "secret.txt"
                outside.write_text("secret", encoding="utf-8")
                try:
                    link = pathlib.Path(sandbox.root) / "link"
                    try:
                        link.symlink_to(outside)
                    except (OSError, NotImplementedError):
                        # Symlink creation requires privileges on some Windows
                        # configurations; skip rather than weaken the check.
                        pytest.skip("symlinks not creatable in this environment")
                    with pytest.raises(SandboxPathError):
                        sandbox.resolve("link")
                finally:
                    if outside.exists():
                        outside.unlink()
            finally:
                sandbox.cleanup()
