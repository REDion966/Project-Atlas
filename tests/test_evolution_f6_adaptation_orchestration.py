"""Phase F6 — Full Adaptation Engine Orchestration tests.

Deterministic, offline coverage of the F6 acceptance criteria (see module
header): full cycle, environment reach, DRAFT-only proposals, governance
boundary, F5 evaluation, boundedness, fail-closed, determinism, no parallel
infrastructure, kernel bridge, no tick auto-run, import boundaries.

Uses real F1-F5 implementations where practical; only the F1 environment
observer is a tiny deterministic stand-in that returns real
``EnvironmentChange`` models on the real ``EnvironmentObservationResult``
surface.
"""

import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from atlas.evolution.adaptation import AdaptationOrchestrator
from atlas.evolution.adaptation.evaluation import AdaptationFeedbackSignal
from atlas.evolution.environment.models import (
    EnvironmentChange,
    EnvironmentChangeType,
    EnvironmentDomain,
    EnvironmentEntity,
    EnvironmentObservationResult,
    ObservationReliability,
)
from atlas.evolution.freshness.models import KnowledgeRef
from atlas.evolution.lifecycle.models import LifecycleTarget, LifecycleTargetKind
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


class _FixedEnvironmentStub:
    """A tiny F1 stand-in exposing the real EnvironmentObserver surface.

    Returns a real ``EnvironmentObservationResult`` carrying fixed
    ``EnvironmentChange`` records (deterministic, offline).
    """

    def __init__(self, changes, cycle_id="ENV-0001"):
        self._changes = list(changes)
        self._cycle_id = cycle_id

    def observe_cycle(self) -> EnvironmentObservationResult:
        return EnvironmentObservationResult(
            cycle_id=self._cycle_id,
            changes=tuple(self._changes),
            failures=(),
            provider_count=len(self._changes),
            observed_count=len(self._changes),
            success=True,
        )


def _env_change(domain, entity_id, current=None):
    entity = EnvironmentEntity(EnvironmentDomain[domain], entity_id)
    return EnvironmentChange(
        entity=entity,
        change_type=EnvironmentChangeType.CHANGED,
        previous={"available": True},
        current=current if current is not None else {"available": True},
        observed_at=NOW,
        source="fixed_stub",
        reliability=ObservationReliability.HIGH,
    )


def _unavailable_model_change():
    return _env_change("MODEL", "openai:gpt-4", current={"available": False})


def _model_target(identifier="openai:gpt-4", unavailable=False, replacement=""):
    entity_keys = frozenset({f"MODEL:{identifier}"})
    return LifecycleTarget(
        target_kind=LifecycleTargetKind.MODEL,
        identifier=identifier,
        dependency_entity_keys=entity_keys,
        affected_domains=frozenset({"MODEL"}),
        available=not unavailable,
        replacement=replacement,
    )


def _knowledge_ref(identifier="KN-1"):
    return KnowledgeRef(
        knowledge_id=identifier,
        entity_key=f"MODEL:{identifier}",
        affected_domains=frozenset({"MODEL"}),
        source_uris=("http://src/1",),
    )


def _with_f5_proposal_and_outcome():
    proposal = EvolutionProposal(
        proposal_id="P-EVAL-1",
        title="t",
        summary="s",
        rationale="r",
        expected_benefit="e",
        risks="low",
        impact_analysis="i",
        implementation_approach="a",
        plan=ImprovementPlan(
            plan_id="IMP-P-EVAL-1", title="t", description="d",
            priority=ImprovementPriority.HIGH,
            target_components=["MODEL:openai:gpt-4"],
        ),
        status=ProposalStatus.APPROVED,
    )
    outcome = DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id="P-EVAL-1",
        plan_id="PLAN-EVAL-1",
        iteration=1,
        verification_passed=True,
        test_outcome="passed",
        effectiveness_proxy=1.0,
    )
    return proposal, outcome


def _orchestrator(env_stub):
    return AdaptationOrchestrator(
        environment_observer=env_stub,
        freshness_assessor=None,  # fresh F2
        lifecycle_assessor=None,  # fresh F3
        decision_engine=None,     # fresh F4
        evaluator=None,           # fresh F5
        now=lambda: NOW,
    )


class TestFullCycle(unittest.TestCase):
    """1-4: a complete F1->F2->F3->F4 cycle produces DRAFT proposals."""

    def test_one_complete_cycle_produces_draft_proposals(self):
        env = _FixedEnvironmentStub([_unavailable_model_change()])
        target = _model_target(unavailable=True, replacement="openai:gpt-4.1")
        result = _orchestrator(env).run_cycle(
            knowledge_refs=[_knowledge_ref()],
            lifecycle_targets=[target],
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.environment_changes), 1)
        self.assertGreaterEqual(len(result.freshness_assessments), 1)
        self.assertGreaterEqual(len(result.lifecycle_assessments), 1)
        self.assertGreaterEqual(len(result.candidates), 1)
        self.assertGreaterEqual(len(result.proposals), 1)
        for proposal in result.proposals:
            self.assertIs(proposal.status, ProposalStatus.DRAFT)

    def test_environment_changes_reach_freshness(self):
        env = _FixedEnvironmentStub([_unavailable_model_change()])
        result = _orchestrator(env).run_cycle(
            knowledge_refs=[_knowledge_ref("KN-REL")],
        )
        # The observed change reaches F2 (KN-REL declares affected MODEL
        # domain, so it becomes stale/uncertain — the candidate list is
        # non-empty because missing provenance makes it UNCERTAIN).
        self.assertTrue(result.environment_changes)
        self.assertGreaterEqual(len(result.freshness_candidates), 1)


class TestGovernanceBoundary(unittest.TestCase):
    """5-8: no auto-approve, no execution, no sandbox, phase-E untouched."""

    def test_no_proposal_auto_approved(self):
        env = _FixedEnvironmentStub([_unavailable_model_change()])
        result = _orchestrator(env).run_cycle(
            lifecycle_targets=[_model_target(unavailable=True, replacement="x")],
        )
        self.assertGreaterEqual(len(result.proposals), 1)
        for proposal in result.proposals:
            self.assertIs(proposal.status, ProposalStatus.DRAFT)
            self.assertIsNone(proposal.approved_at)

    def test_orchestrator_never_executes_phase_e(self):
        import inspect

        from atlas.evolution.adaptation import orchestrator as mod

        # Scan only the code (strip the module docstring, which describes what
        # F6 does NOT invoke).
        source = inspect.getsource(mod)
        marker = '"""'
        first_close = source.find(marker, source.find(marker) + 3)
        code = source[first_close + 3:]
        for forbidden in ("SelfDevelopmentLoop", "DevelopmentPlanner",
                          "sandbox", "subprocess"):
            self.assertNotIn(forbidden, code)


class TestF5EvaluationAndFeedback(unittest.TestCase):
    """9-10: supplied approved/outcome data flows through F5."""

    def test_f5_evaluation_consumes_supplied_outcome(self):
        proposal, outcome = _with_f5_proposal_and_outcome()
        env = _FixedEnvironmentStub([])
        result = _orchestrator(env).run_cycle(
            lifecycle_targets=[],
            evaluate_pairs=[(proposal, outcome)],
        )
        self.assertEqual(len(result.evaluations), 1)
        self.assertEqual(len(result.feedback), 1)
        self.assertEqual(result.feedback[0].signal, AdaptationFeedbackSignal.RETAIN)
        self.assertTrue(result.feedback[0].retain_adaptation)


class TestDeterminismAndBounds(unittest.TestCase):
    """12-13, 15: deterministic ordering, bounded candidates, no recursion."""

    def test_identical_cycles_are_equivalent(self):
        env_a = _FixedEnvironmentStub([_unavailable_model_change()])
        env_b = _FixedEnvironmentStub([_unavailable_model_change()])
        r1 = _orchestrator(env_a).run_cycle(
            lifecycle_targets=[_model_target(unavailable=True, replacement="x")],
            now=NOW,
        )
        r2 = _orchestrator(env_b).run_cycle(
            lifecycle_targets=[_model_target(unavailable=True, replacement="x")],
            now=NOW,
        )
        self.assertEqual(r1.cycle_id, r2.cycle_id)
        self.assertEqual(
            [p.proposal_id for p in r1.proposals],
            [p.proposal_id for p in r2.proposals],
        )

    def test_bounded_candidates(self):
        env = _FixedEnvironmentStub([])
        many_targets = [
            _model_target(
                identifier=f"openai:gpt-{i}",
                unavailable=True,
                replacement=f"openai:new-{i}",
            )
            for i in range(20)
        ]
        result = _orchestrator(env).run_cycle(
            lifecycle_targets=many_targets,
            max_candidates=3,
        )
        # F4 (bounded via the orchestrator's max_candidates) caps output.
        self.assertLessEqual(len(result.candidates), 3)
        self.assertLessEqual(len(result.proposals), 3)

    def test_truncation_recorded_when_bounds_exceeded(self):
        env = _FixedEnvironmentStub([])
        targets = [
            _model_target(identifier=f"m{i}", unavailable=True, replacement="r")
            for i in range(5)
        ]
        # knowledge max 1 with 3 refs -> the knowledge stage truncates.
        result = _orchestrator(env).run_cycle(
            knowledge_refs=[_knowledge_ref("K1"), _knowledge_ref("K2"),
                            _knowledge_ref("K3")],
            lifecycle_targets=targets,
            max_knowledge=1,
        )
        self.assertIn("knowledge", result.truncated)
        # 5 targets assessed; the orchestrator passes the F4 cap so F4 bounds
        # candidate output; 5 targets is within default lifecycle bound.
        self.assertEqual(len(result.lifecycle_assessments), 5)

    def test_no_infinite_retry_recursion(self):
        env = _FixedEnvironmentStub([_unavailable_model_change()])
        orch = _orchestrator(env)
        orch.run_cycle(lifecycle_targets=[
            _model_target(unavailable=True, replacement="x")
        ])
        orch.run_cycle(lifecycle_targets=[
            _model_target(unavailable=True, replacement="x")
        ])
        self.assertEqual(orch.cycle_count, 2)


class TestFailClosed(unittest.TestCase):
    """14: malformed / invalid input never raises; returns a bounded result."""

    def test_malformed_input_fails_closed(self):
        env = _FixedEnvironmentStub([_unavailable_model_change()])
        result = _orchestrator(env).run_cycle(
            knowledge_refs=["not-a-ref", None],
            lifecycle_targets=["not-a-target", object()],
            evaluate_pairs=[("bad", None), (None, None)],
        )
        self.assertEqual(result.freshness_assessments, ())
        self.assertEqual(result.lifecycle_assessments, ())
        self.assertEqual(result.freshness_candidates, ())
        self.assertGreaterEqual(len(result.failures), 1)
        self.assertIn(result.status, ("partial", "failed"))

    def test_observer_failure_is_bounded(self):
        class _BrokenEnv:
            def observe_cycle(self):
                raise RuntimeError("boom")

        result = _orchestrator(_BrokenEnv()).run_cycle()
        self.assertEqual(result.status, "failed")
        self.assertTrue(
            any(stage == "environment" for stage, _ in result.failures)
        )


class TestNoParallelInfrastructure(unittest.TestCase):
    """16: the orchestrator creates no EventBus/scheduler/memory/registry."""

    def test_orchestrator_creates_no_infrastructure(self):
        import inspect

        from atlas.evolution.adaptation import orchestrator as mod

        source = inspect.getsource(mod)
        marker = '"""'
        first_close = source.find(marker, source.find(marker) + 3)
        code = source[first_close + 3:]
        for forbidden in ("EventBus", "Scheduler", "EvolutionMemory",
                          "LearningMemory", "ToolRegistry", "CapabilityRegistry",
                          "Thread", "daemon"):
            self.assertNotIn(forbidden, code)


class TestKernelBridge(unittest.TestCase):
    """17-19: Atlas bridge works; tick does NOT auto-run; shutdown cleans up."""

    def test_atlas_kernel_bridge_works(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            result = atlas.run_adaptation_cycle(
                supplied_changes=[_unavailable_model_change()],
                lifecycle_targets=[
                    _model_target(unavailable=True, replacement="openai:gpt-4.1")
                ],
            )
            self.assertIsNotNone(result)
            for proposal in result.proposals:
                self.assertIs(proposal.status, ProposalStatus.DRAFT)
        finally:
            atlas.shutdown()

    def test_tick_does_not_auto_invoke_adaptation(self):
        import inspect

        from atlas.kernel.atlas import Atlas

        src = inspect.getsource(Atlas.tick)
        self.assertNotIn("run_adaptation_cycle", src)

    def test_shutdown_cleans_up_orchestrator(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        atlas.shutdown()
        self.assertIsNone(atlas.adaptation_orchestrator)


class TestImportBoundary(unittest.TestCase):
    """20: architecture / import boundaries remain valid."""

    def test_orchestrator_has_no_prohibited_imports(self):
        adaptation_dir = _REPO_ROOT / "atlas" / "evolution" / "adaptation"
        forbidden = (
            "atlas.evolution.autonomy",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.approval_manager",
            "atlas.evolution.authorization_manager",
            "atlas.evolution.governance",
            "self_development_loop",
            "subprocess",
            "requests",
        )
        violations = []
        for path in sorted(adaptation_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p)
                               for p in forbidden):
                            violations.append((str(path), alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module and any(
                        node.module == p or node.module.startswith(p)
                        for p in forbidden
                    ):
                        violations.append((str(path), node.module))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()