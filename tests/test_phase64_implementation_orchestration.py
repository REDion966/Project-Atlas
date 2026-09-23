"""Phase 6.4 — Implementation orchestration: evidence contract.

Investigation result: implementation is already orchestrated, governed, and
sandbox-confined, so no new orchestrator or code executor was introduced.

* ``SelfDevelopmentLoop`` — bounded per-iteration lifecycle
  (IMPLEMENT via ``SandboxImplementer``/E2 ``CodeApplier`` → VERIFY via E4
  pytest → ACCEPT) inside a disposable ``CodeSandbox``.
* It consumes an ALREADY-APPROVED (or SANDBOX_AUTHORIZED) proposal and never
  mutates the real repository.
"""

from __future__ import annotations

from pathlib import Path

from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PASS_TEST = "def test_visible():\n    assert True\n"
_FAIL_TEST = "def test_visible():\n    assert False\n"


def _proposal(status=ProposalStatus.APPROVED, test_body=_PASS_TEST, pid="PROP-P64"):
    plan = ImprovementPlan(
        plan_id="IMP-P64",
        title="t",
        description="d",
        priority=ImprovementPriority.HIGH,
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id=pid,
        title="t",
        summary="s",
        rationale="r",
        expected_benefit="b",
        risks="low",
        impact_analysis="x",
        implementation_approach="y",
        plan=plan,
        status=status,
        metadata={
            "code_changes": [
                {"path": "atlas/example/mod.py", "content": "VALUE = 1\n"}
            ],
            "test_files": {"tests/test_mod.py": test_body},
        },
    )


class TestPhase64ImplementationOrchestration:
    def test_unauthorized_implementation_is_rejected(self):
        result = SelfDevelopmentLoop().run(
            _proposal(status=ProposalStatus.DRAFT), max_iterations=1
        )
        assert result.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
        assert result.outcomes == []

    def test_authorized_implementation_succeeds_inside_the_sandbox(self):
        result = SelfDevelopmentLoop().run(_proposal(), max_iterations=1)
        assert result.status is DevelopmentOutcomeStatus.SUCCESS
        outcome = result.outcomes[0]
        assert outcome.verification_passed is True
        assert outcome.test_outcome == "passed"
        assert outcome.changed_files == ["atlas/example/mod.py"]

    def test_failing_implementation_does_not_report_success(self):
        result = SelfDevelopmentLoop().run(
            _proposal(test_body=_FAIL_TEST), max_iterations=1
        )
        # A failing sandbox test never yields SUCCESS.
        assert result.status is not DevelopmentOutcomeStatus.SUCCESS
        assert result.outcomes[0].verification_passed is False

    def test_real_repository_is_never_modified(self):
        SelfDevelopmentLoop().run(_proposal(), max_iterations=1)
        # The sandbox workload path must not exist in the live repository.
        assert not (_REPO_ROOT / "atlas/example/mod.py").exists()
