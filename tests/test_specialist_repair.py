"""The specialist repair path — bounded corrective change via ACTIVE ``code.generate``.

Proves that ``RepairChangeSupplier`` authors a corrective change through the SAME
Atlas-owned specialist seam used for initial generation, that the correction is
strictly bounded (one file, the SAME authorized target, and genuinely different
from the failing content), and that every deviation fails closed to the baseline
workload. No authority, no promotion, no new provider/author is introduced.
"""

from __future__ import annotations

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    SandboxWorkload,
)
from atlas.evolution.development_repair import RepairChangeSupplier
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.specialists import CODE_GENERATE, CODE_REVIEW, SpecialistProposal

TARGET = "mod.py"
BAD = "VALUE = 1\n"
GOOD = "VALUE = 2\n"
TESTS = {"test_mod.py": "def test_value():\n    assert True\n"}


def _proposal() -> EvolutionProposal:
    plan = ImprovementPlan(
        plan_id="IMP-REPAIR-S",
        title="Add a value",
        description="Introduce a module value.",
        priority=ImprovementPriority.HIGH,
        expected_benefit="A module value exists.",
        complexity_estimate="low",
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-REPAIR-S",
        title="Add a value",
        summary="Introduce a module value.",
        rationale="Modules should export a value.",
        expected_benefit="A module value exists.",
        risks="Low.",
        impact_analysis="Modifies mod.py.",
        implementation_approach="Add a constant.",
        plan=plan,
        status=ProposalStatus.APPROVED,
        metadata={
            "code_changes": [{"path": TARGET, "content": BAD}],
            "test_files": dict(TESTS),
        },
    )


def _baseline(proposal=None, history=None) -> SandboxWorkload:
    return SandboxWorkload(
        code_changes=({"path": TARGET, "content": BAD},),
        test_files=dict(TESTS),
        verify_target="test_mod.py",
    )


def _failed(**over) -> DevelopmentOutcome:
    base = dict(
        outcome=DevelopmentOutcomeStatus.FAILED,
        proposal_id="PROP-REPAIR-S",
        plan_id="IMP-REPAIR-S",
        iteration=1,
        message="tests failed",
        changed_files=[TARGET],
        verification_passed=False,
        rollback_occurred=False,
        test_outcome="failed",
    )
    base.update(over)
    return DevelopmentOutcome(**base)


class _Author:
    """Duck-typed specialist author (the ``propose`` surface) with a canned reply."""

    def __init__(self, raw=None, *, raises: bool = False) -> None:
        self._raw = raw
        self._raises = raises
        self.calls: list[dict] = []

    def _build_context(self, target):
        """The author's own bounded repository context (mirrors the real author)."""
        return {TARGET: BAD}

    def propose(
        self, need, *, target="", plan=None, verification_tests=(), context=None
    ):
        self.calls.append(
            {
                "need": need,
                "target": target,
                "plan": plan,
                "verification_tests": tuple(verification_tests),
                "context": dict(context or {}),
            }
        )
        if self._raises:
            raise RuntimeError("provider down")
        return self._raw


def _proposal_with(files, *, capability=CODE_GENERATE, provider_id="fake.code"):
    return SpecialistProposal(
        provider_id=provider_id,
        capability=capability,
        payload={"files": dict(files), "paths": sorted(files)},
    )


def _supplier(author):
    return RepairChangeSupplier(baseline=_baseline, repair_author=author)


class TestSpecialistCorrectiveRepair:
    def test_specialist_repair_is_enabled_when_an_author_is_wired(self):
        supplier = _supplier(_Author(_proposal_with({TARGET: GOOD})))
        assert supplier.repair_enabled is True
        assert supplier.specialist_repair_enabled is True

    def test_corrective_change_is_produced_for_the_same_target(self):
        author = _Author(_proposal_with({TARGET: GOOD}))
        workload = _supplier(author)(_proposal(), [_failed()])
        assert workload is not None
        assert workload.code_changes == ({"path": TARGET, "content": GOOD},)
        # The bounded verification requirement is preserved.
        assert workload.test_files == dict(TESTS)
        assert workload.verify_target == "test_mod.py"

    def test_the_author_receives_a_bounded_task_including_the_failure(self):
        author = _Author(_proposal_with({TARGET: GOOD}))
        _supplier(author)(_proposal(), [_failed()])
        call = author.calls[-1]
        assert call["target"] == TARGET
        assert call["verification_tests"] == ("test_mod.py",)
        # Context carries the failing target content AND the test source.
        assert TARGET in call["context"]
        assert "test_mod.py" in call["context"]
        assert "FAILED" in call["need"].summary

    def test_first_attempt_and_success_are_not_repaired(self):
        author = _Author(_proposal_with({TARGET: GOOD}))
        supplier = _supplier(author)
        assert supplier(_proposal(), []) == _baseline()
        assert author.calls == []


class TestFailClosedBoundary:
    def test_identical_correction_is_refused(self):
        """The Command 3C failure mode: a restated failing change is not a repair."""
        author = _Author(_proposal_with({TARGET: BAD}))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_wrong_target_is_refused(self):
        author = _Author(_proposal_with({"other.py": GOOD}))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_multiple_files_are_refused(self):
        author = _Author(_proposal_with({TARGET: GOOD, "other.py": GOOD}))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_traversal_path_is_refused(self):
        author = _Author(_proposal_with({"../evil.py": GOOD}))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_absolute_path_is_refused(self):
        author = _Author(_proposal_with({"/etc/x.py": GOOD}))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_empty_content_is_refused(self):
        author = _Author(_proposal_with({TARGET: "   \n"}))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_malformed_proposal_is_refused(self):
        for raw in ({"files": {TARGET: GOOD}}, object(), "nope"):
            assert _supplier(_Author(raw))(_proposal(), [_failed()]) == _baseline()

    def test_wrong_capability_is_refused(self):
        author = _Author(_proposal_with({TARGET: GOOD}, capability=CODE_REVIEW))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_missing_provider_identity_is_refused(self):
        author = _Author(_proposal_with({TARGET: GOOD}, provider_id="   "))
        assert _supplier(author)(_proposal(), [_failed()]) == _baseline()

    def test_unavailable_author_yields_no_correction(self):
        assert _supplier(_Author(None))(_proposal(), [_failed()]) == _baseline()

    def test_raising_author_fails_closed(self):
        assert _supplier(_Author(raises=True))(_proposal(), [_failed()]) == _baseline()

    def test_repair_is_inert_without_a_specialist_author(self):
        supplier = RepairChangeSupplier(baseline=_baseline)
        assert supplier.repair_enabled is False
        assert supplier(_proposal(), [_failed()]) == _baseline()

    def test_provider_callable_is_resolved_lazily(self):
        """The kernel wires a provider (the supplier is built before the author)."""
        holder: dict = {}
        supplier = RepairChangeSupplier(
            baseline=_baseline, repair_author=lambda: holder.get("author")
        )
        assert supplier.specialist_repair_enabled is False
        assert supplier(_proposal(), [_failed()]) == _baseline()
        holder["author"] = _Author(_proposal_with({TARGET: GOOD}))
        workload = supplier(_proposal(), [_failed()])
        assert workload is not None
        assert workload.code_changes == ({"path": TARGET, "content": GOOD},)

    def test_broken_provider_callable_fails_closed(self):
        def boom():
            raise RuntimeError("no author")

        supplier = RepairChangeSupplier(baseline=_baseline, repair_author=boom)
        assert supplier.specialist_repair_enabled is False
        assert supplier(_proposal(), [_failed()]) == _baseline()


class TestRecoveryEligibility:
    def test_non_verification_failures_are_not_repaired(self):
        author = _Author(_proposal_with({TARGET: GOOD}))
        supplier = _supplier(author)
        # A rollback (change not applied) is not a repair candidate.
        assert supplier(_proposal(), [_failed(rollback_occurred=True)]) == _baseline()
        # An environment timeout is not a repair candidate.
        assert supplier(_proposal(), [_failed(test_outcome="timeout")]) == _baseline()

    def test_errored_targeted_test_is_repaired(self):
        author = _Author(_proposal_with({TARGET: GOOD}))
        workload = _supplier(author)(_proposal(), [_failed(test_outcome="error")])
        assert workload is not None
        assert workload.code_changes == ({"path": TARGET, "content": GOOD},)


class TestNoAuthorityOrSideEffects:
    def test_supplier_has_no_authority_surface(self):
        supplier = _supplier(_Author(_proposal_with({TARGET: GOOD})))
        for banned in ("approve", "promote", "authorize", "activate", "execute"):
            assert not hasattr(supplier, banned)

    def test_inputs_are_not_mutated(self):
        proposal = _proposal()
        history = [_failed()]
        before = dict(proposal.metadata)
        _supplier(_Author(_proposal_with({TARGET: GOOD})))(proposal, history)
        assert proposal.metadata == before
        assert len(history) == 1

    def test_corrective_workload_is_sandbox_data_only(self):
        workload = _supplier(_Author(_proposal_with({TARGET: GOOD})))(
            _proposal(), [_failed()]
        )
        assert isinstance(workload, SandboxWorkload)
