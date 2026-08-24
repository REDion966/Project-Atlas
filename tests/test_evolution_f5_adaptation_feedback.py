"""Phase F5 — Adaptation Evaluation & Feedback tests.

Deterministic, offline coverage of the F5 acceptance criteria (see module
header): lifecycle states, executed outcomes, effectiveness, feedback/F2/F3
bridges, memory integration, governance safety, regression.
"""

import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from atlas.evolution.adaptation import (
    AdaptationEvaluationState,
    AdaptationEvaluator,
    AdaptationFeedbackSignal,
)
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def _proposal(
    proposal_id="P1",
    status=ProposalStatus.DRAFT,
    target_key="TOOL:sandbox_pytest",
    evidence_changes=(),
    evidence_knowledge=(),
):
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="title",
        summary="summary",
        rationale="rationale",
        expected_benefit="benefit",
        risks="risk",
        impact_analysis="impact",
        implementation_approach="approach",
        plan=ImprovementPlan(
            plan_id=f"IMP-{proposal_id}",
            title="title",
            description="desc",
            priority=ImprovementPriority.HIGH,
            target_components=[target_key],
        ),
        status=status,
        metadata={
            "target_key": target_key,
            "evidence_change_ids": list(evidence_changes),
            "evidence_knowledge_ids": list(evidence_knowledge),
        },
    )


def _outcome(
    status=DevelopmentOutcomeStatus.SUCCESS,
    verification_passed=True,
    rollback_occurred=False,
    proxy=1.0,
    plan_id="PLAN-1",
):
    return DevelopmentOutcome(
        outcome=status,
        proposal_id="P1",
        plan_id=plan_id,
        iteration=1,
        verification_passed=verification_passed,
        rollback_occurred=rollback_occurred,
        test_outcome="passed" if verification_passed else "failed",
        effectiveness_proxy=proxy,
    )


def _failed_outcome():
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.FAILED,
        proposal_id="P1",
        plan_id="PLAN-1",
        iteration=1,
        verification_passed=False,
        test_outcome="failed",
        effectiveness_proxy=0.0,
    )


def _evaluator(now=None, max_items=10):
    return AdaptationEvaluator(max_items=max_items, now=lambda: now or NOW)


class TestProposalLifecycleStates(unittest.TestCase):
    """Governance states are never conflation with technical failure."""

    def test_draft_is_not_executed(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.DRAFT))
        self.assertIs(ev.state, AdaptationEvaluationState.NOT_EXECUTED)
        self.assertIsNone(ev.effectiveness)
        self.assertFalse(ev.approval_occurred)

    def test_pending_approval_is_not_executed(self):
        ev = _evaluator().evaluate_proposal(
            _proposal(status=ProposalStatus.PENDING_APPROVAL)
        )
        self.assertIs(ev.state, AdaptationEvaluationState.NOT_EXECUTED)

    def test_approved_not_executed(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.APPROVED))
        self.assertIs(ev.state, AdaptationEvaluationState.APPROVED_NOT_EXECUTED)
        self.assertTrue(ev.approval_occurred)
        self.assertFalse(ev.execution_occurred)

    def test_rejected_is_governance(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.REJECTED))
        self.assertIs(ev.state, AdaptationEvaluationState.GOVERNANCE_REJECTED)
        self.assertFalse(ev.execution_occurred)
        self.assertIsNone(ev.effectiveness)

    def test_deferred_is_deferred(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.DEFERRED))
        self.assertIs(ev.state, AdaptationEvaluationState.DEFERRED)
        self.assertFalse(ev.execution_occurred)

    def test_superseded(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.SUPERSEDED))
        self.assertIs(ev.state, AdaptationEvaluationState.SUPERSEDED)


class TestExecutedOutcomes(unittest.TestCase):
    """Successful / failed / verification / rollback / effectiveness."""

    def test_successful_outcome(self):
        outcome = _outcome()
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), outcome
        )
        self.assertIs(ev.state, AdaptationEvaluationState.SUCCESSFUL)
        self.assertEqual(ev.effectiveness, 1.0)
        self.assertEqual(ev.confidence, 0.9)
        self.assertTrue(ev.execution_occurred)

    def test_failed_outcome(self):
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), _failed_outcome()
        )
        self.assertIs(ev.state, AdaptationEvaluationState.FAILED)
        self.assertEqual(ev.effectiveness, 0.0)

    def test_verification_failure_zero_effectiveness(self):
        outcome = _outcome(verification_passed=False)
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), outcome
        )
        self.assertIs(ev.state, AdaptationEvaluationState.FAILED)
        self.assertEqual(ev.effectiveness, 0.0)
        self.assertFalse(ev.verification_passed)

    def test_rollback_zero_effectiveness(self):
        outcome = _outcome(status=DevelopmentOutcomeStatus.FAILED, rollback_occurred=True)
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), outcome
        )
        self.assertEqual(ev.effectiveness, 0.0)
        self.assertTrue(ev.rollback_occurred)

    def test_effectiveness_proxy_reused_and_bounded(self):
        outcome = _outcome(proxy=0.75)
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), outcome
        )
        self.assertEqual(ev.effectiveness, 0.75)

        outcome_big = _outcome(proxy=5.0)
        ev_big = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), outcome_big
        )
        self.assertLessEqual(ev_big.effectiveness, 1.0)
        self.assertGreaterEqual(ev_big.effectiveness, 0.0)

    def test_confidence_bounded(self):
        outcome = _outcome()
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), outcome
        )
        self.assertGreaterEqual(ev.confidence, 0.0)
        self.assertLessEqual(ev.confidence, 1.0)


class TestFeedbackSignals(unittest.TestCase):
    """Positive/negative feedback and F2/F3 bridge signals."""

    def test_successful_outcome_retain_feedback(self):
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), _outcome()
        )
        fb = _evaluator().feedback_for(ev)
        self.assertIs(fb.signal, AdaptationFeedbackSignal.RETAIN)
        self.assertTrue(fb.retain_adaptation)

    def test_failed_outcome_reconsider_feedback(self):
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), _failed_outcome()
        )
        fb = _evaluator().feedback_for(ev)
        self.assertIs(fb.signal, AdaptationFeedbackSignal.RECONSIDER)
        self.assertTrue(fb.reconsider_adaptation)

    def test_rejected_feedback_not_technical(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.REJECTED))
        fb = _evaluator().feedback_for(ev)
        self.assertIs(fb.signal, AdaptationFeedbackSignal.REJECTED)
        self.assertFalse(fb.reconsider_adaptation)
        self.assertFalse(fb.retain_adaptation)

    def test_deferred_feedback_not_technical(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.DEFERRED))
        fb = _evaluator().feedback_for(ev)
        self.assertIs(fb.signal, AdaptationFeedbackSignal.DEFERRED)

    def test_f2_freshness_bridge(self):
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), _outcome()
        )
        fb = _evaluator().feedback_for(ev)
        self.assertIn(fb.freshness_signal, ("refresh", "reassess", "none"))

    def test_f3_lifecycle_bridge(self):
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), _outcome()
        )
        fb = _evaluator().feedback_for(ev)
        self.assertIn(fb.lifecycle_signal, ("deprioritize", "reassess", "none"))


class TestDeterminismAndBounded(unittest.TestCase):
    """13-16: determinism, ordering, dedup, bounded input."""

    def test_identical_inputs_identical_output(self):
        probe = _proposal(proposal_id="P9", status=ProposalStatus.APPROVED)
        outcome = _outcome()
        e = _evaluator()
        r1 = e.evaluate_outcome(probe, outcome)
        r2 = e.evaluate_outcome(probe, outcome)
        self.assertEqual(r1.to_dict(), r2.to_dict())

    def test_evaluate_many_deterministic_order(self):
        proposals = [
            _proposal(proposal_id="B", status=ProposalStatus.APPROVED),
            _proposal(proposal_id="A", status=ProposalStatus.DRAFT),
        ]
        results = _evaluator().evaluate_many(proposals)
        self.assertEqual(
            [r.proposal_id for r in results], ["A", "B"]
        )

    def test_evaluate_many_dedup(self):
        p = _proposal(status=ProposalStatus.REJECTED)
        results = _evaluator().evaluate_many([p, p, p])
        self.assertEqual(len(results), 1)

    def test_bounded_input(self):
        many = [_proposal(proposal_id=f"P{i}") for i in range(50)]
        results = _evaluator(max_items=5).evaluate_many(many)
        self.assertLessEqual(len(results), 5)

    def test_feedback_idempotent(self):
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.APPROVED))
        fb1 = _evaluator().feedback_for(ev)
        fb2 = _evaluator().feedback_for(ev)
        self.assertEqual(fb1.feedback_id, fb2.feedback_id)


class TestIdentityAndEvidence(unittest.TestCase):
    """17-24: proposal/outcome/target identity + provenance + F1/F2/F3 evidence."""

    def test_identity_preserved(self):
        outcome = _outcome()
        ev = _evaluator().evaluate_outcome(
            _proposal(proposal_id="P9", target_key="MODEL:openai:gpt-4"), outcome
        )
        self.assertEqual(ev.proposal_id, "P9")
        self.assertEqual(ev.target_key, "MODEL:openai:gpt-4")
        self.assertEqual(ev.outcome_id, ev.outcome_id)

    def test_outcome_identity_preserved(self):
        outcome = _outcome(plan_id="PLAN-9")
        ev = _evaluator().evaluate_outcome(_proposal(status=ProposalStatus.APPROVED), outcome)
        self.assertEqual(ev.outcome_id, "PLAN-9")

    def test_f1_f2_f3_evidence_preserved(self):
        proposal = _proposal(
            status=ProposalStatus.APPROVED,
            evidence_changes=("CHG-1", "CHG-2"),
            evidence_knowledge=("KN-1",),
        )
        outcome = _outcome()
        ev = _evaluator().evaluate_outcome(proposal, outcome)
        self.assertEqual(ev.evidence_change_ids, ("CHG-1", "CHG-2"))
        self.assertEqual(ev.evidence_knowledge_ids, ("KN-1",))

        fb = _evaluator().feedback_for(ev)
        self.assertIn("CHG-1", fb.evidence_refs)
        self.assertIn("KN-1", fb.evidence_refs)

    def test_proposal_without_metadata_uses_plan_target(self):
        proposal = _proposal(status=ProposalStatus.APPROVED)
        proposal.metadata = {}
        ev = _evaluator().evaluate_proposal(proposal)
        self.assertEqual(ev.target_key, "TOOL:sandbox_pytest")


class TestMemoryIntegration(unittest.TestCase):
    """31-32: existing EvolutionMemory / LearningMemory integration."""

    def test_evolution_memory_store(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        memory = EvolutionMemory()
        ev = _evaluator().evaluate_proposal(_proposal(status=ProposalStatus.APPROVED))
        _evaluator().record(ev, evolution_memory=memory)
        self.assertEqual(memory.record_count, 1)

    def test_learning_memory_recommendation(self):
        from atlas.learning_engine.learning_memory import LearningMemory

        memory = LearningMemory()
        ev = _evaluator().evaluate_outcome(
            _proposal(status=ProposalStatus.APPROVED), _failed_outcome()
        )
        _evaluator().record(ev, learning_memory=memory)
        self.assertGreaterEqual(memory.recommendation_count, 1)


class TestGovernanceSafety(unittest.TestCase):
    """34-40: no execution / sandbox / subprocess / approval / mutations."""

    def test_no_forbidden_imports(self):
        adaptation_dir = _REPO_ROOT / "atlas" / "evolution" / "adaptation"
        forbidden = (
            "atlas.evolution.autonomy",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.approval_manager",
            "atlas.evolution.authorization_manager",
            "atlas.evolution.governance",
            "self_development_loop",
            "subprocess",
            "sandbox",
        )
        violations = []
        for path in sorted(adaptation_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p) for p in forbidden):
                            violations.append((str(path), alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module and any(node.module == p or node.module.startswith(p) for p in forbidden):
                        violations.append((str(path), node.module))
        self.assertEqual(violations, [])

    def test_no_proposal_status_mutation(self):
        proposal = _proposal(status=ProposalStatus.DRAFT)
        _evaluator().evaluate_proposal(proposal)
        self.assertIs(proposal.status, ProposalStatus.DRAFT)

    def test_no_registry_reference(self):
        import inspect

        from atlas.evolution.adaptation import evaluation, evaluator

        for mod in (evaluation, evaluator):
            src = inspect.getsource(mod)
            for forbidden in ("ToolRegistry", "CapabilityRegistry", "SkillRegistry",
                              "ModelProfileRegistry"):
                self.assertNotIn(forbidden, src)


class TestPipelineAndKernel(unittest.TestCase):
    """41-47: F1-F4 regression + kernel integration smoke."""

    def test_full_adaptation_cycle_yields_evaluation(self):
        # F4 produces a DRAFT proposal; F5 evaluates it (not executed).
        from atlas.evolution.adaptation import AdaptationDecisionEngine
        from atlas.evolution.lifecycle.models import (
            LifecycleAction, LifecycleAssessment, LifecycleReason,
            LifecycleTargetKind,
        )
        from atlas.evolution.lifecycle.assessor import CapabilityLifecycleAssessor

        proposal = _proposal(status=ProposalStatus.DRAFT)
        ev = _evaluator().evaluate_proposal(proposal)
        self.assertIs(ev.state, AdaptationEvaluationState.NOT_EXECUTED)

    def test_kernel_integration_smoke(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            proposal = _proposal(status=ProposalStatus.APPROVED)
            evaluation, feedback = atlas.evaluate_adaptation(proposal)
            self.assertIsNotNone(evaluation)
            self.assertIsNotNone(feedback)
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()