"""Phase 4.2 — Governed self-development lifecycle focused tests.

Covers the four Phase 4.2 workstreams:

* WS1 — failure -> diagnosis -> bounded retest/recovery inside the loop.
* WS2 — objective verification attached to the execution path.
* WS3a — deterministic relevant-test selection (and its loop wiring).
* WS5 — lifecycle evidence persisted onto the proposal metadata.

No external model is contacted anywhere in this module.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.development_test_selection import select_relevant_tests
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import (
    DevelopmentRunResult,
    SelfDevelopmentLoop,
)

OK_CHANGES = [{"path": "mod.py", "content": "VALUE = 1\n"}]
OK_TESTS = {"test_mod.py": "def test_value():\n    assert True\n"}
FAIL_TESTS = {"test_mod.py": "def test_value():\n    assert 1 == 2\n"}


def _approved(metadata=None) -> EvolutionProposal:
    plan = ImprovementPlan(
        plan_id="IMP-P42-001",
        title="Add a value",
        description="Introduce a module value.",
        priority=ImprovementPriority.HIGH,
        expected_benefit="A module value exists.",
        complexity_estimate="low",
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-P42-001",
        title="Add a value",
        summary="Introduce a module value.",
        rationale="Modules should export a value.",
        expected_benefit="A module value exists.",
        risks="Low.",
        impact_analysis="Modifies mod.py.",
        implementation_approach="Add a constant and a test.",
        plan=plan,
        status=ProposalStatus.APPROVED,
        metadata=metadata or {},
    )


def _workload(test_files, code_changes=None, verify_target="test_mod.py"):
    return {
        "code_changes": code_changes or OK_CHANGES,
        "test_files": test_files,
        **({"verify_target": verify_target} if verify_target else {}),
    }


# ---------------------------------------------------------------------------
# WS1 — failure -> diagnosis -> bounded retest/recovery
# ---------------------------------------------------------------------------


class TestCorrectionLoop:
    def test_persistent_failure_consumes_budget_and_records_evidence(self):
        loop = SelfDevelopmentLoop()
        result = loop.run(
            _approved(_workload(FAIL_TESTS)), max_iterations=3
        )
        assert result.status == DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED
        assert result.iterations_used == 3
        assert len(result.outcomes) == 3
        # Read-only diagnosis + recovery decision recorded on the run.
        assert result.diagnosis is not None
        assert result.recovery is not None
        assert result.diagnosis.failure_class.value == "verification"
        # The diagnosis/recovery evidence rides on the outcome (and history).
        last = result.outcomes[-1]
        assert last.metadata["diagnosis"]["failure_class"] == "verification"
        assert last.metadata["recovery"]["strategy"] == "no_recovery"

    def test_failure_diagnosis_is_fed_to_the_supplier(self):
        seen: list[list[str]] = []

        def supplier(proposal, history):
            seen.append(
                [
                    (o.metadata.get("recovery") or {}).get("strategy", "")
                    for o in history
                ]
            )
            if history:  # after the first failure, supply a corrected workload
                return _stub_workload(OK_TESTS)
            return _stub_workload(FAIL_TESTS)

        loop = SelfDevelopmentLoop(change_supplier=supplier)
        result = loop.run(_approved(), max_iterations=3)

        assert result.status == DevelopmentOutcomeStatus.SUCCESS
        assert result.iterations_used == 2
        # First call saw no history; the retry saw the prior diagnosis.
        assert seen[0] == []
        assert seen[1] == ["no_recovery"]

    def test_non_retryable_class_stops_early(self):
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )
        from atlas.evolution.development_recovery import DevelopmentRecovery

        class _GovernanceLoop(SelfDevelopmentLoop):
            def _diagnose_and_decide(self, plan, outcomes, iteration):  # noqa: D102
                diagnostic = DevelopmentDiagnostic().diagnose(
                    type(
                        "_R",
                        (),
                        {
                            "status": SimpleNamespace(name="GOVERNANCE_DENIED"),
                            "outcomes": [],
                            "message": "denied",
                        },
                    )()
                )
                return diagnostic, DevelopmentRecovery().decide(
                    SimpleNamespace(outcomes=[]), diagnostic
                )

        loop = _GovernanceLoop()
        result = loop.run(_approved(_workload(FAIL_TESTS)), max_iterations=3)
        assert result.status == DevelopmentOutcomeStatus.FAILED
        assert result.iterations_used == 1  # stopped early; budget not burned
        assert result.diagnosis.failure_class == DiagnosticFailureClass.GOVERNANCE

    def test_is_non_retryable_classification(self):
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        def diag(cls):
            return SimpleNamespace(
                failure_class=cls, confidence=DiagnosticConfidence.KNOWN
            )

        assert SelfDevelopmentLoop._is_non_retryable(
            diag(DiagnosticFailureClass.GOVERNANCE)
        )
        assert SelfDevelopmentLoop._is_non_retryable(
            diag(DiagnosticFailureClass.OBJECTIVE)
        )
        assert SelfDevelopmentLoop._is_non_retryable(
            diag(DiagnosticFailureClass.CAPABILITY)
        )
        assert not SelfDevelopmentLoop._is_non_retryable(
            diag(DiagnosticFailureClass.VERIFICATION)
        )
        assert not SelfDevelopmentLoop._is_non_retryable(
            diag(DiagnosticFailureClass.IMPLEMENTATION)
        )
        assert not SelfDevelopmentLoop._is_non_retryable(
            diag(DiagnosticFailureClass.UNKNOWN)
        )
        assert DevelopmentDiagnostic is not None


class TestFailClosedContractPreserved:
    """The read-only recovery decision must stay fail-closed for ambiguous
    evidence (the boundary pinned by test_investigation)."""

    def test_exhausted_verification_failure_is_not_recoverable(self):
        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.FAILED,
            proposal_id="P",
            plan_id="PL",
            iteration=1,
            verification_passed=False,
            test_outcome="failed",
        )
        result = DevelopmentRunResult(
            status=DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED,
            outcomes=[outcome],
            iterations_used=1,
            message="exhausted",
        )
        diagnostic = DevelopmentDiagnostic().diagnose(result)
        assert diagnostic.failure_class.value == "verification"
        assert diagnostic.recoverable is None
        decision = DevelopmentRecovery().decide(result, diagnostic)
        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.NO_RECOVERY


# ---------------------------------------------------------------------------
# WS2 — verification integrated into the execution path
# ---------------------------------------------------------------------------


class TestVerificationIntegration:
    def test_run_development_execution_attaches_verification(self):
        from atlas.kernel.atlas import Atlas

        memory = SimpleNamespace(
            get_proposal=lambda pid: SimpleNamespace(
                status=SimpleNamespace(name="APPROVED")
            )
        )
        success_outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-P42-001",
            plan_id="PLAN",
            iteration=1,
            verification_passed=True,
            test_outcome="passed",
            effectiveness_proxy=1.0,
        )
        canned = DevelopmentRunResult(
            status=DevelopmentOutcomeStatus.SUCCESS,
            plan=None,
            outcomes=[success_outcome],
            iterations_used=1,
            message="ok",
        )
        fake_self = SimpleNamespace(
            _evolution_memory=memory,
            _development_planner=SimpleNamespace(plan=lambda p: None),
            _self_development_loop=SimpleNamespace(run=lambda p: canned),
        )
        fake_self._require_development_authority = lambda sc, action, **kwargs: None

        result = Atlas.run_development_execution(fake_self, None, "PROP-P42-001")

        assert result.verification is not None
        assert result.verification.status.value == "verified"


# ---------------------------------------------------------------------------
# WS3a — deterministic relevant-test selection + loop wiring
# ---------------------------------------------------------------------------


class TestRelevantTestSelection:
    def test_matches_convention_prefix(self):
        assert select_relevant_tests(
            ["mod.py"], ["test_mod.py", "test_other.py"]
        ) == ("test_mod.py",)

    def test_matches_suffixed_convention(self):
        assert select_relevant_tests(
            ["atlas/evolution/self_development_loop.py"],
            ["tests/test_evolution_self_development_loop.py"],
        ) == ("tests/test_evolution_self_development_loop.py",)

    def test_empty_when_nothing_related(self):
        assert select_relevant_tests(["mod.py"], ["test_other.py"]) == ()

    def test_deterministic_sorted_and_bounded(self):
        available = [f"test_x_{i}.py" for i in range(50)]
        first = select_relevant_tests(["x.py"], available, max_tests=5)
        assert len(first) == 5
        assert list(first) == sorted(first)
        assert select_relevant_tests(["x.py"], available, max_tests=5) == first

    def test_malformed_input_never_raises(self):
        assert select_relevant_tests([], ["test_x.py"]) == ()
        assert select_relevant_tests([None, 1, ""], ["test_x.py"]) == ()
        assert select_relevant_tests(["x.py"], ["test_x.txt"]) == ()
        assert select_relevant_tests(["x.py"], ["test_x.py"], max_tests=0) == ()

    def test_loop_uses_selected_test_as_default_target(self):
        """With no explicit verify_target, only the relevant test runs.

        The unrelated failing test proves the selector narrowed the target:
        running the whole workspace would fail.
        """
        proposal = _approved(
            {
                "code_changes": OK_CHANGES,
                "test_files": {
                    "test_mod.py": "def test_value():\n    assert True\n",
                    "test_unrelated.py": "def test_bad():\n    assert False\n",
                },
                # deliberately no verify_target
            }
        )
        result = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert result.status == DevelopmentOutcomeStatus.SUCCESS
        assert result.outcomes[0].test_outcome == "passed"


# ---------------------------------------------------------------------------
# WS5 — lifecycle evidence persistence
# ---------------------------------------------------------------------------


class TestEvidencePersistence:
    def test_persist_evidence_includes_verification_and_recovery(self):
        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
        from atlas.evolution.development_recovery import DevelopmentRecovery
        from atlas.evolution.development_verification import DevelopmentVerification
        from atlas.kernel.atlas import Atlas

        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.FAILED,
            proposal_id="PROP-P42-001",
            plan_id="PLAN",
            iteration=1,
            verification_passed=False,
            test_outcome="failed",
        )
        result = DevelopmentRunResult(
            status=DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED,
            outcomes=[outcome],
            iterations_used=1,
            message="exhausted",
        )
        result.verification = DevelopmentVerification().verify(result)
        result.diagnosis = DevelopmentDiagnostic().diagnose(result)
        result.recovery = DevelopmentRecovery().decide(result, result.diagnosis)

        proposal = SimpleNamespace(metadata={})
        Atlas._persist_development_evidence(proposal, result)

        metadata = proposal.metadata
        assert metadata["execution"]["result_status"] == "ITERATIONS_EXHAUSTED"
        assert metadata["verification"]["status"] in (
            "unverified",
            "partial",
            "unverifiable",
        )
        assert metadata["diagnosis"]["failure_class"] == "verification"
        assert metadata["recovery"]["strategy"] == "no_recovery"


def _stub_workload(test_files):
    from atlas.evolution.development_models import SandboxWorkload

    return SandboxWorkload(
        code_changes=tuple(OK_CHANGES),
        test_files=dict(test_files),
        verify_target="test_mod.py",
    )
