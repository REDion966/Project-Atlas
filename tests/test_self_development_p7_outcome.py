"""P7.5 — Development outcome reporter contract tests.

Pins truthful, idempotent, reporting-only rendering of EXISTING F9 outcome
states, plus the safety/dependency/tick/B4 boundaries.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from atlas.conversation.development_outcome_reporter import (
    DevelopmentOutcomeReporter,
    DevelopmentOutcomeSnapshot,
    DevelopmentOutcomeState,
    snapshot_from_approval_decision,
    snapshot_from_cycle_result,
    snapshot_from_promotion_status,
    snapshot_from_run_result,
)
from atlas.conversation.message import Message

_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def reporter():
    return DevelopmentOutcomeReporter()


# ---------------------------------------------------------------------------
# Fake F9 result objects (duck-typed, mirroring the real shapes)
# ---------------------------------------------------------------------------


class _CycleResult:
    def __init__(self, ok=True, proposal_id="DEV-1", approval_request_id="APPR-1", failures=()):
        self.ok = ok
        self.proposal_id = proposal_id
        self.approval_request_id = approval_request_id
        self.failures = failures


class _ApprovalRequest:
    def __init__(self, decision, proposal_id="DEV-1", request_id="APPR-1"):
        self.decision = decision
        self.proposal_id = proposal_id
        self.request_id = request_id


class _Decision:
    def __init__(self, name):
        self.name = name


class _RunResult:
    def __init__(self, status_name, rollback=False, verification=False, message="", test_outcome="passed", proposal_id="DEV-1"):
        self.status = _Decision(status_name)
        self.plan = type("_Plan", (), {"proposal_id": proposal_id})()
        self.message = message
        self.rollback = rollback
        self.verification = verification
        self.test_outcome = test_outcome
        self.outcomes = [
            type(
                "_Outcome",
                (),
                {
                    "rollback_occurred": rollback,
                    "verification_passed": verification,
                    "test_outcome": test_outcome,
                },
            )()
        ]


# ---------------------------------------------------------------------------
# Truthful outcome rendering
# ---------------------------------------------------------------------------


class TestOutcomeReporting:
    def test_awaiting_approval_from_cycle(self, reporter):
        snap = snapshot_from_cycle_result(_CycleResult(ok=True))
        msg = reporter.report(snap)
        assert "awaiting human approval" in msg.content.lower()
        assert msg.metadata["development_outcome"]["state"] == "awaiting_approval"

    def test_preparation_failure_from_cycle(self, reporter):
        snap = snapshot_from_cycle_result(
            _CycleResult(ok=False, failures=(("supplier", "no changes"),))
        )
        msg = reporter.report(snap)
        assert "failed" in msg.content.lower()
        assert msg.metadata["development_outcome"]["state"] == "preparation_failed"

    def test_approval_rejected(self, reporter):
        snap = snapshot_from_approval_decision(_ApprovalRequest(_Decision("REJECTED")))
        msg = reporter.report(snap)
        assert "denied" in msg.content.lower()
        assert msg.metadata["development_outcome"]["state"] == "approval_rejected"

    def test_approval_deferred(self, reporter):
        snap = snapshot_from_approval_decision(_ApprovalRequest(_Decision("DEFERRED")))
        msg = reporter.report(snap)
        assert "deferred" in msg.content.lower()

    def test_approval_approved(self, reporter):
        snap = snapshot_from_approval_decision(_ApprovalRequest(_Decision("APPROVED")))
        msg = reporter.report(snap)
        assert "ready to proceed" in msg.content.lower()

    def test_execution_success(self, reporter):
        snap = snapshot_from_run_result(
            _RunResult("SUCCESS", rollback=False, verification=True)
        )
        msg = reporter.report(snap)
        assert "completed successfully" in msg.content.lower()

    def test_execution_failure(self, reporter):
        snap = snapshot_from_run_result(
            _RunResult("FAILED", rollback=False, verification=False)
        )
        msg = reporter.report(snap)
        assert "failed" in msg.content.lower()
        assert "success" not in msg.content.lower()

    def test_rollback_reported_truthfully(self, reporter):
        snap = snapshot_from_run_result(
            _RunResult("FAILED", rollback=True, verification=False)
        )
        msg = reporter.report(snap)
        assert "rolled back" in msg.content.lower()

    def test_promotion_pending(self, reporter):
        snap = snapshot_from_promotion_status("pending_review", proposal_id="DEV-1")
        msg = reporter.report(snap)
        assert "awaiting human promotion review" in msg.content.lower()

    def test_promotion_approved_never_claims_repo_change(self, reporter):
        snap = snapshot_from_promotion_status("approved", proposal_id="DEV-1")
        msg = reporter.report(snap)
        assert "ready for human promotion" in msg.content.lower()
        assert "repository has not been modified" in msg.content.lower()

    def test_unknown_state_fails_closed(self, reporter):
        snap = DevelopmentOutcomeSnapshot(state="nonsense")
        msg = reporter.report(snap)
        assert "could not be determined" in msg.content.lower()


# ---------------------------------------------------------------------------
# Key semantic distinctions
# ---------------------------------------------------------------------------


class TestNoStateConflation:
    def test_pending_approval_is_not_success(self, reporter):
        snap = snapshot_from_cycle_result(_CycleResult(ok=True))
        msg = reporter.report(snap)
        assert "success" not in msg.content.lower()
        assert "completed" not in msg.content.lower()

    def test_pending_approval_is_not_execution(self, reporter):
        snap = snapshot_from_cycle_result(_CycleResult(ok=True))
        msg = reporter.report(snap)
        assert "executed" not in msg.content.lower()
        assert "execution" not in msg.content.lower()

    def test_pending_approval_is_not_promotion(self, reporter):
        snap = snapshot_from_cycle_result(_CycleResult(ok=True))
        msg = reporter.report(snap)
        assert "promotion" not in msg.content.lower()
        assert "promoted" not in msg.content.lower()


# ---------------------------------------------------------------------------
# Idempotency / no auto-action / provenance
# ---------------------------------------------------------------------------


class TestIdempotencyAndSafety:
    def test_repeated_reporting_is_idempotent(self, reporter):
        snap = snapshot_from_run_result(_RunResult("SUCCESS"))
        a = reporter.report(snap)
        b = reporter.report(snap)
        assert a.content == b.content
        # Stateless: repeated reporting never creates requests/retries.
        assert a.metadata == b.metadata

    def test_provenance_preserved(self, reporter):
        snap = snapshot_from_run_result(
            _RunResult("SUCCESS"),
            session_id="sess-1",
            principal_id="alice",
            authority="user",
        )
        msg = reporter.report(snap)
        assert msg.metadata["session_id"] == "sess-1"
        assert msg.metadata["principal_id"] == "alice"
        assert msg.metadata["authority"] == "user"

    def test_user_authority_not_elevated(self, reporter):
        snap = snapshot_from_run_result(
            _RunResult("SUCCESS"),
            principal_id="alice",
            authority="user",
        )
        assert reporter.report(snap).metadata["authority"] == "user"


# ---------------------------------------------------------------------------
# Reporting-only: no approval/execute/promote bypass
# ---------------------------------------------------------------------------


class TestReportingOnly:
    def test_reporter_has_no_execution_surface(self, reporter):
        for attr in (
            "approve",
            "reject",
            "execute",
            "promote",
            "approval_manager",
            "development_controller",
            "planner",
            "self_development_loop",
            "execution_gateway",
            "promotion_gate",
            "tick",
        ):
            assert not hasattr(reporter, attr), f"reporter has {attr}"

    def test_reporter_module_imports_no_evolution_machinery(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_outcome_reporter.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="development_outcome_reporter.py")
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and module.startswith("atlas.evolution"):
                raise AssertionError(f"reporter imports {module}")

    def test_reporter_imports_no_forbidden_packages(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_outcome_reporter.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="development_outcome_reporter.py")
        forbidden = (
            "atlas.kernel",
            "atlas.runtime",
            "atlas.storage",
            "atlas.orchestration",
            "atlas.advisory",
        )
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and any(
                module == p or module.startswith(p + ".") for p in forbidden
            ):
                raise AssertionError(f"reporter imports {module}")


# ---------------------------------------------------------------------------
# Tick + B4 safety
# ---------------------------------------------------------------------------


class TestTickAndB4:
    def test_tick_remains_development_execution_free(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        for marker in (
            "run_development_cycle",
            "run_development_execution",
            "confirm_development_approval",
            "submit_development_for_promotion_review",
        ):
            assert marker not in tick_src

    def test_reporter_has_no_b4_references(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_outcome_reporter.py"
        ).read_text(encoding="utf-8")
        assert "ModelAssistedChangeSupplier" not in source
        assert "model_assisted_authoring" not in source
