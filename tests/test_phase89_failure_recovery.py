"""Phase 8.9 — Failure, rollback, and recovery: evidence contract.

Investigation result: the existing sandbox/promotion architecture already
provides isolation and fail-closed behavior, so no second rollback framework was
introduced. A failed acquisition never leaves Atlas believing the capability
exists.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlas.evolution.capability_activation import (
    CapabilityActivationError,
    CapabilityActivator,
)
from atlas.evolution.capability_acquisition import (
    AcquisitionMechanism,
    AcquisitionNeed,
    determine_acquisition_strategy,
    validate_internalized_capability,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.reasoning.execution.registry import CapabilityRegistry

_FAIL_TEST = "def test_visible():\n    assert False\n"


def _proposal(status, test_body):
    plan = ImprovementPlan(
        plan_id="IMP-P89",
        title="t",
        description="d",
        priority=ImprovementPriority.MEDIUM,
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-P89",
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
            "code_changes": [{"path": "atlas/x.py", "content": "V = 1\n"}],
            "test_files": {"tests/test_x.py": test_body},
        },
    )


class TestPhase89FailureRecovery:
    def test_unauthorized_and_blocked_needs_fail_closed(self):
        unauthorized = determine_acquisition_strategy(
            AcquisitionNeed(
                request="acquire x.y",
                target_capability="x.y",
                authorized=False,
                knowledge_available=True,
            )
        )
        assert unauthorized.mechanism is AcquisitionMechanism.NONE

        blocked = determine_acquisition_strategy(
            AcquisitionNeed(
                request="acquire x.y",
                target_capability="x.y",
                required_dependencies=("libx",),
                available_dependencies=(),
            )
        )
        assert blocked.mechanism is AcquisitionMechanism.NONE
        assert blocked.failure_conditions

    def test_validation_failure_leaves_capability_absent(self):
        registry = CapabilityRegistry()
        validation = validate_internalized_capability(
            "x.y", capability_registry=registry
        )
        assert validation.ok is False
        assert registry.registered_names == []

    def test_failed_activation_leaves_registry_unchanged(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "bad.py").write_text('CAPABILITY_NAME = "x.y"\n', encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": "bad.py", "content": 'CAPABILITY_NAME = "x.y"\n'}],
            proposal_id="P",
            repo_root=root,
        )
        registry = CapabilityRegistry()
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, registry).activate(artifact)
        assert registry.registered_names == []

    def test_failed_tests_do_not_report_success(self):
        result = SelfDevelopmentLoop().run(
            _proposal(ProposalStatus.APPROVED, _FAIL_TEST), max_iterations=1
        )
        assert result.status is not DevelopmentOutcomeStatus.SUCCESS
        assert result.outcomes[0].verification_passed is False

    def test_unapproved_execution_is_governance_denied(self):
        result = SelfDevelopmentLoop().run(
            _proposal(ProposalStatus.DRAFT, "def test_x():\n    assert True\n"),
            max_iterations=1,
        )
        assert result.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
