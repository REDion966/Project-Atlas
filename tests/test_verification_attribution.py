"""Command 4 — verification attribution (bounded pre/post test-status).

Covers the pure classification, its real integration in the bounded development
loop (a genuine pre-change baseline probe inside the disposable sandbox), and its
use in repair eligibility. No external model is contacted.
"""

from __future__ import annotations

import pytest

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    SandboxWorkload,
)
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.evolution.verification_attribution import (
    BASELINE_METADATA_KEY,
    VerificationTransition,
    baseline_of,
    classify_transition,
    is_attributable,
    is_recoverable,
    transition_of,
)

ORIGINAL = "VALUE = 1\n"
BROKEN = "VALUE = 2\n"
ALREADY_BROKEN = "VALUE = 9\n"
TEST = "from mod import VALUE\n\n\ndef test_value():\n    assert VALUE == 1\n"


# ---------------------------------------------------------------------------
# Pure classification
# ---------------------------------------------------------------------------


class TestClassification:
    @pytest.mark.parametrize(
        "baseline, after, expected",
        [
            (True, True, VerificationTransition.STILL_PASSING),
            (True, False, VerificationTransition.REGRESSION),
            (False, True, VerificationTransition.FIXED),
            (False, False, VerificationTransition.ALREADY_FAILING),
        ],
    )
    def test_transitions(self, baseline, after, expected):
        assert classify_transition(baseline, after) is expected

    @pytest.mark.parametrize(
        "baseline, after", [(None, False), (True, None), ("x", False), (1, 0)]
    )
    def test_non_boolean_status_is_unknown(self, baseline, after):
        assert classify_transition(baseline, after) is VerificationTransition.UNKNOWN

    def test_only_regression_is_attributable_and_recoverable(self):
        assert is_attributable(VerificationTransition.REGRESSION) is True
        assert is_recoverable(VerificationTransition.REGRESSION) is True
        for transition in (
            VerificationTransition.ALREADY_FAILING,
            VerificationTransition.FIXED,
            VerificationTransition.STILL_PASSING,
            VerificationTransition.UNKNOWN,
        ):
            assert is_attributable(transition) is False
            assert is_recoverable(transition) is False

    def test_outcome_baseline_reader(self):
        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.FAILED,
            proposal_id="P",
            plan_id="PL",
            iteration=1,
            verification_passed=False,
            metadata={BASELINE_METADATA_KEY: False},
        )
        assert baseline_of(outcome) is False
        assert transition_of(outcome) is VerificationTransition.ALREADY_FAILING
        # Absent baseline -> UNKNOWN (never asserts attributability).
        assert baseline_of(DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.FAILED, proposal_id="P",
            plan_id="PL", iteration=1,
        )) is None


# ---------------------------------------------------------------------------
# Real loop integration — a genuine pre-change baseline probe
# ---------------------------------------------------------------------------


def _approved() -> EvolutionProposal:
    plan = ImprovementPlan(
        plan_id="IMP-C4-001",
        title="Set a value",
        description="Introduce a module value.",
        priority=ImprovementPriority.MEDIUM,
        expected_benefit="A module value exists.",
        complexity_estimate="low",
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-C4-001",
        title="Set a value",
        summary="Introduce a module value.",
        rationale="Modules should export a value.",
        expected_benefit="A module value exists.",
        risks="Low.",
        impact_analysis="Modifies mod.py.",
        implementation_approach="Set a constant.",
        plan=plan,
        status=ProposalStatus.APPROVED,
    )


def _workload(original: str, change: str) -> SandboxWorkload:
    return SandboxWorkload(
        code_changes=({"path": "mod.py", "content": change},),
        test_files={"test_mod.py": TEST},
        repository_context={"mod.py": original},
        verify_target="test_mod.py",
    )


class TestBaselineProbe:
    def test_a_change_that_breaks_a_passing_test_is_attributable(self):
        loop = SelfDevelopmentLoop(
            change_supplier=lambda p, h: _workload(ORIGINAL, BROKEN)
        )
        result = loop.run(_approved(), max_iterations=1)

        assert result.status == DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED
        outcome = result.outcomes[-1]
        # The targeted test passed WITHOUT the change and fails WITH it.
        assert baseline_of(outcome) is True
        assert transition_of(outcome) is VerificationTransition.REGRESSION
        assert is_attributable(transition_of(outcome)) is True

    def test_a_pre_existing_failure_is_not_attributable(self):
        loop = SelfDevelopmentLoop(
            change_supplier=lambda p, h: _workload(ALREADY_BROKEN, BROKEN)
        )
        result = loop.run(_approved(), max_iterations=1)

        assert result.status == DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED
        outcome = result.outcomes[-1]
        # The targeted test already failed WITHOUT the change.
        assert baseline_of(outcome) is False
        assert transition_of(outcome) is VerificationTransition.ALREADY_FAILING
        assert is_attributable(transition_of(outcome)) is False

    def test_a_passing_change_reports_a_pass_to_pass_transition(self):
        loop = SelfDevelopmentLoop(
            change_supplier=lambda p, h: _workload(ORIGINAL, ORIGINAL)
        )
        result = loop.run(_approved(), max_iterations=1)

        assert result.status == DevelopmentOutcomeStatus.SUCCESS
        outcome = result.outcomes[-1]
        assert baseline_of(outcome) is True
        assert transition_of(outcome) is VerificationTransition.STILL_PASSING


# ---------------------------------------------------------------------------
# Repair eligibility uses attribution
# ---------------------------------------------------------------------------


class _Author:
    def propose(self, need, **kwargs):
        from atlas.specialists import CODE_GENERATE, SpecialistProposal

        return SpecialistProposal(
            provider_id="fake.code",
            capability=CODE_GENERATE,
            payload={"files": {"mod.py": BROKEN}, "paths": ["mod.py"]},
        )


def _failed(**metadata) -> DevelopmentOutcome:
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.FAILED,
        proposal_id="P",
        plan_id="PL",
        iteration=1,
        message="failed",
        changed_files=["mod.py"],
        verification_passed=False,
        test_outcome="failed",
        metadata=dict(metadata),
    )


def _proposal() -> EvolutionProposal:
    proposal = _approved()
    proposal.metadata.update(
        {"code_changes": [{"path": "mod.py", "content": "VALUE = 3\n"}]}
    )
    return proposal


def _repair_supplier():
    from atlas.evolution.development_repair import RepairChangeSupplier

    def baseline(proposal, history):
        return SandboxWorkload(
            code_changes=({"path": "mod.py", "content": "VALUE = 3\n"},),
            test_files={"test_mod.py": TEST},
            verify_target="test_mod.py",
        )

    return RepairChangeSupplier(baseline=baseline, repair_author=_Author())


class TestRepairEligibility:
    def test_regression_is_repaired(self):
        supplier = _repair_supplier()
        workload = supplier(_proposal(), [_failed(**{BASELINE_METADATA_KEY: True})])
        assert workload is not None
        assert workload.code_changes == ({"path": "mod.py", "content": BROKEN},)

    def test_pre_existing_failure_is_not_repaired(self):
        supplier = _repair_supplier()
        workload = supplier(_proposal(), [_failed(**{BASELINE_METADATA_KEY: False})])
        assert workload is not None
        # No corrective change: the baseline workload is returned unchanged.
        assert workload.code_changes == ({"path": "mod.py", "content": "VALUE = 3\n"},)

    def test_unknown_baseline_preserves_the_legacy_heuristic(self):
        supplier = _repair_supplier()
        workload = supplier(_proposal(), [_failed()])
        assert workload.code_changes == ({"path": "mod.py", "content": BROKEN},)
