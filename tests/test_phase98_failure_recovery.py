"""Phase 9.8 — Failure diagnosis and bounded recovery: evidence contract.

Investigation result: Atlas already diagnoses failures (``DevelopmentDiagnostic``)
and decides bounded recovery (``DevelopmentRecovery``); the loop retries only
within the iteration budget and stops early on non-retryable classes. Failures
are never converted into success.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.development_diagnostic import (
    DevelopmentDiagnostic,
    DiagnosticFailureClass,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.development_recovery import (
    DevelopmentRecovery,
    RecoveryStrategy,
)
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop

_FAIL_TEST = "def test_visible():\n    assert False\n"


def _approved(test_body):
    plan = ImprovementPlan(
        plan_id="IMP-P98",
        title="t",
        description="d",
        priority=ImprovementPriority.MEDIUM,
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-P98",
        title="t",
        summary="s",
        rationale="r",
        expected_benefit="b",
        risks="low",
        impact_analysis="x",
        implementation_approach="y",
        plan=plan,
        status=ProposalStatus.APPROVED,
        metadata={
            "code_changes": [{"path": "atlas/x.py", "content": "VALUE = 1\n"}],
            "test_files": {"tests/test_x.py": test_body},
        },
    )


class TestPhase98FailureRecovery:
    def test_unclear_evidence_diagnoses_unknown_and_no_recovery(self):
        result = SimpleNamespace(
            status=DevelopmentOutcomeStatus.FAILED,
            outcomes=[],
            iterations_used=0,
            message="",
        )
        diagnostic = DevelopmentDiagnostic().diagnose(result)
        assert diagnostic.failure_class is DiagnosticFailureClass.UNKNOWN
        recovery = DevelopmentRecovery().decide(result, diagnostic)
        assert recovery.recoverable is False
        assert recovery.strategy is RecoveryStrategy.NO_RECOVERY

    def test_non_retryable_classes_stop_early(self):
        for cls in ("governance", "objective", "capability"):
            assert (
                SelfDevelopmentLoop._is_non_retryable(
                    SimpleNamespace(failure_class=SimpleNamespace(value=cls))
                )
                is True
            )
        # Implementation/verification failures remain retryable within the budget.
        assert (
            SelfDevelopmentLoop._is_non_retryable(
                SimpleNamespace(failure_class=SimpleNamespace(value="implementation"))
            )
            is False
        )

    def test_retry_is_bounded_and_not_converted_to_success(self):
        result = SelfDevelopmentLoop().run(
            _approved(_FAIL_TEST), max_iterations=2
        )
        assert result.status is DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED
        assert all(o.verification_passed is False for o in result.outcomes)
        assert len(result.outcomes) <= 2  # bounded

    def test_failure_is_not_converted_to_success(self):
        result = SelfDevelopmentLoop().run(_approved(_FAIL_TEST), max_iterations=1)
        assert result.status is not DevelopmentOutcomeStatus.SUCCESS
