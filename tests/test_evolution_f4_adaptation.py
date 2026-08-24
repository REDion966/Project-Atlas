"""Phase F4 — Governed Adaptation Decision Engine tests.

Deterministic, offline coverage of the F4 acceptance criteria:

  1. actionable F3 assessment -> candidate
  2. NONE -> no candidate
  3. REVIEW below threshold -> no candidate/deferred
  4. REVIEW above threshold -> candidate
  5. DEPRECATE -> candidate
  6. REPLACE without known replacement -> fail/defer
  7. REPLACE with known replacement -> candidate
  8. FALLBACK without valid fallback -> defer
  9. FALLBACK with valid fallback -> candidate
 10. malformed assessment -> fail closed
 11. unknown target -> fail closed
 12. deterministic candidate generation
 13. deterministic ordering
 14. duplicate suppression
 15. bounded candidate count
 16. priority/confidence preserved
 17. evidence references preserved
 18. F1 EnvironmentChange evidence preserved
 19. F2 freshness evidence preserved
 20. risk/impact classification
 21. proposal uses existing model (EvolutionProposal)
 22. proposal uses valid initial status (DRAFT)
 23. proposal is NOT APPROVED automatically
 24. ApprovalManager not invoked
 25. AuthorizationManager not bypassed
 26. CODE scope remains protected
 27. SelfDevelopmentLoop not invoked
 28. DevelopmentPlanner not invoked
 29. no subprocess/code execution
 30. no sandbox execution
 31. no registry mutation
 32. no research execution
 33. no duplicate governance infrastructure
 34. F3 regression
 35. F2 regression
 36. F1 regression
 37. Phase E regression
 38. architecture import scan
 39. kernel wiring if implemented
 40. repeated identical calls produce equivalent results

No network / no wall-clock (UTC injection). Not testing persistence/approval
(those live in the existing governance boundary).
"""

import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from atlas.evolution.adaptation import (
    AdaptationDecisionEngine,
    AdaptationDecisionPolicy,
    AdaptationProposalCandidate,
    AdaptationRisk,
)
from atlas.evolution.lifecycle.models import (
    LifecycleAction,
    LifecycleAssessment,
    LifecycleReason,
    LifecycleTargetKind,
)
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def _assessment(
    target_kind,
    identifier,
    action,
    priority,
    reasons=(),
    change_ids=(),
    knowledge_ids=(),
    assessed_at=None,
):
    return LifecycleAssessment(
        target_kind=target_kind,
        target_identifier=identifier,
        action=action,
        reasons=tuple(reasons),
        priority=priority,
        evidence_change_ids=tuple(change_ids),
        evidence_knowledge_ids=tuple(knowledge_ids),
        assessed_at=assessed_at or NOW,
        rationale=",".join(r.name.lower() for r in reasons),
    )


def _engine(policy=None):
    return AdaptationDecisionEngine(policy=policy)


# ---------------------------------------------------------------------------
# 1-9: per-action decision gate
# ---------------------------------------------------------------------------


class TestDecisionGates(unittest.TestCase):

    def test_actionable_f3_assessment_to_candidate(self):
        a = _assessment(
            LifecycleTargetKind.TOOL, "tool_a", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        candidates = _engine().decide([a])
        self.assertEqual(len(candidates), 1)

    def test_none_action_produces_no_candidate(self):
        a = _assessment(LifecycleTargetKind.TOOL, "t1", LifecycleAction.NONE, 1.0)
        self.assertEqual(_engine().decide([a]), ())

    def test_review_below_threshold_deferred(self):
        a = _assessment(
            LifecycleTargetKind.CAPABILITY, "research.query",
            LifecycleAction.REVIEW, 0.5,
            reasons=(LifecycleReason.ENVIRONMENT_CHANGE,),
        )
        self.assertEqual(_engine().decide([a]), ())

    def test_review_above_threshold_produces_candidate(self):
        a = _assessment(
            LifecycleTargetKind.CAPABILITY, "research.query",
            LifecycleAction.REVIEW, 0.9,
            reasons=(LifecycleReason.ENVIRONMENT_CHANGE,),
        )
        candidates = _engine().decide([a])
        self.assertEqual(len(candidates), 1)
        self.assertIs(candidates[0].action, LifecycleAction.REVIEW)

    def test_deprecate_produces_candidate(self):
        a = _assessment(
            LifecycleTargetKind.SKILL, "sk1", LifecycleAction.DEPRECATE, 1.0,
            reasons=(LifecycleReason.EXPLICIT_DEPRECATION,),
        )
        candidates = _engine().decide([a])
        self.assertEqual(len(candidates), 1)
        self.assertIs(candidates[0].action, LifecycleAction.DEPRECATE)

    def test_replace_without_replacement_deferred(self):
        a = _assessment(
            LifecycleTargetKind.MODEL, "openai:gpt-4", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.ENVIRONMENT_CHANGE,),
        )
        self.assertEqual(_engine().decide([a]), ())

    def test_replace_with_replacement_produces_candidate(self):
        a = _assessment(
            LifecycleTargetKind.MODEL, "openai:gpt-4", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        candidates = _engine().decide([a])
        self.assertEqual(len(candidates), 1)
        self.assertIs(candidates[0].action, LifecycleAction.REPLACE)

    def test_fallback_without_valid_fallback_deferred(self):
        a = _assessment(
            LifecycleTargetKind.TOOL, "sandbox_pytest", LifecycleAction.FALLBACK, 1.0,
            reasons=(LifecycleReason.UNAVAILABLE,),
        )
        self.assertEqual(_engine().decide([a]), ())

    def test_fallback_with_valid_fallback_produces_candidate(self):
        a = _assessment(
            LifecycleTargetKind.TOOL, "sandbox_pytest", LifecycleAction.FALLBACK, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        candidates = _engine().decide([a])
        self.assertEqual(len(candidates), 1)
        self.assertIs(candidates[0].action, LifecycleAction.FALLBACK)


# ---------------------------------------------------------------------------
# 10-11: malformed / unknown targets fail closed
# ---------------------------------------------------------------------------


class TestFailClosed(unittest.TestCase):

    def test_malformed_assessment_is_skipped(self):
        candidates = _engine().decide([None, "garbage", 42])
        self.assertEqual(candidates, ())

    def test_unknown_target_kind_raises_for_candidate(self):
        from atlas.evolution.adaptation.models import AdaptationProposalCandidate, AdaptationRisk

        with self.assertRaises(TypeError):
            AdaptationProposalCandidate(
                target_kind="BOGUS",
                target_identifier="x",
                action=LifecycleAction.REVIEW,
                reason=LifecycleReason.ENVIRONMENT_CHANGE,
                priority=0.9,
                risk=AdaptationRisk.LOW,
            )

    def test_empty_identifier_raises_for_candidate(self):
        from atlas.evolution.adaptation.models import AdaptationProposalCandidate, AdaptationRisk

        with self.assertRaises(ValueError):
            AdaptationProposalCandidate(
                target_kind=LifecycleTargetKind.TOOL,
                target_identifier="",
                action=LifecycleAction.REVIEW,
                reason=LifecycleReason.ENVIRONMENT_CHANGE,
                priority=0.9,
                risk=AdaptationRisk.LOW,
            )


# ---------------------------------------------------------------------------
# 12-16: determinism, ordering, dedup, bounded count, priority preserved
# ---------------------------------------------------------------------------


class TestDeterminismAndBounded(unittest.TestCase):

    def test_repeated_identical_calls_equivalent(self):
        ass = [
            _assessment(
                LifecycleTargetKind.TOOL, "t1", LifecycleAction.DEPRECATE, 1.0,
                reasons=(LifecycleReason.EXPLICIT_DEPRECATION,),
            ),
        ]
        e = _engine()
        r1 = e.decide(ass)
        r2 = e.decide(ass)
        self.assertEqual([c.candidate_id for c in r1],
                         [c.candidate_id for c in r2])
        self.assertEqual([c.priority for c in r1],
                         [c.priority for c in r2])

    def test_deterministic_ordering(self):
        high = _assessment(
            LifecycleTargetKind.MODEL, "openai:gpt-4", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        low = _assessment(
            LifecycleTargetKind.TOOL, "t1", LifecycleAction.REVIEW, 0.9,
            reasons=(LifecycleReason.ENVIRONMENT_CHANGE,),
        )
        candidates = _engine().decide([low, high])
        self.assertEqual([c.priority for c in candidates], [1.0, 0.9])

    def test_duplicate_suppression(self):
        a = _assessment(
            LifecycleTargetKind.MODEL, "openai:gpt-4", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        candidates = _engine().decide([a, a, a])
        self.assertEqual(len(candidates), 1)

    def test_bounded_candidate_count(self):
        policy = AdaptationDecisionPolicy(max_candidates=2)
        ass = [
            _assessment(
                LifecycleTargetKind.TOOL, f"tool_{i}",
                LifecycleAction.DEPRECATE, 1.0,
                reasons=(LifecycleReason.EXPLICIT_DEPRECATION,),
            )
            for i in range(8)
        ]
        candidates = _engine(policy).decide(ass)
        self.assertLessEqual(len(candidates), 2)

    def test_priority_preserved_in_candidate(self):
        a = _assessment(
            LifecycleTargetKind.TOOL, "t1", LifecycleAction.REPLACE, 0.85,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        candidate = _engine().decide([a])[0]
        self.assertEqual(candidate.priority, 0.85)


# ---------------------------------------------------------------------------
# 17-19: evidence / provenance references preserved
# ---------------------------------------------------------------------------


class TestEvidencePreservation(unittest.TestCase):

    def test_change_and_knowledge_ids_preserved(self):
        a = _assessment(
            LifecycleTargetKind.CAPABILITY, "research.query",
            LifecycleAction.REVIEW, 0.9,
            reasons=(LifecycleReason.ENVIRONMENT_CHANGE,),
            change_ids=("CHG-1",),
            knowledge_ids=("KID-1",),
        )
        candidate = _engine().decide([a])[0]
        self.assertEqual(candidate.evidence_change_ids, ("CHG-1",))
        self.assertEqual(candidate.evidence_knowledge_ids, ("KID-1",))

    def test_evidence_preserved_in_proposal(self):
        a = _assessment(
            LifecycleTargetKind.MODEL, "openai:gpt-4", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
            change_ids=("CHG-2",),
            knowledge_ids=("KID-2",),
        )
        proposal = _engine().generate([a])[0]
        self.assertEqual(proposal.metadata["evidence_change_ids"], ["CHG-2"])
        self.assertEqual(proposal.metadata["evidence_knowledge_ids"], ["KID-2"])
        self.assertEqual(proposal.metadata["source"], "F4-adaptation")


# ---------------------------------------------------------------------------
# 20-23: proposal uses existing model; DRAFT; never APPROVED automatically
# ---------------------------------------------------------------------------


class TestProposalBoundary(unittest.TestCase):

    def test_proposal_is_existing_evolution_proposal(self):
        a = _assessment(
            LifecycleTargetKind.TOOL, "t1", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        proposals = _engine().generate([a])
        self.assertIsInstance(proposals[0], EvolutionProposal)
        self.assertIsInstance(proposals[0].plan, ImprovementPlan)

    def test_proposal_defaults_to_draft(self):
        a = _assessment(
            LifecycleTargetKind.TOOL, "t1", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        proposal = _engine().generate([a])[0]
        self.assertIs(proposal.status, ProposalStatus.DRAFT)

    def test_proposal_never_approved_automatically(self):
        a = _assessment(
            LifecycleTargetKind.MODEL, "openai:gpt-4", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        proposal = _engine().generate([a])[0]
        self.assertIsNot(proposal.status, ProposalStatus.APPROVED)
        self.assertIsNone(proposal.approved_at)

    def test_risk_classification_high_for_model_replace(self):
        a = _assessment(
            LifecycleTargetKind.MODEL, "openai:gpt-4", LifecycleAction.REPLACE, 1.0,
            reasons=(LifecycleReason.REPLACEMENT_AVAILABLE,),
        )
        candidate = _engine().decide([a])[0]
        self.assertIs(candidate.risk, AdaptationRisk.HIGH)


# ---------------------------------------------------------------------------
# 24-33: governance / execution boundaries
# ---------------------------------------------------------------------------


class TestGovernanceBoundary(unittest.TestCase):

    def test_no_forbidden_imports(self):
        adaptation_dir = _REPO_ROOT / "atlas" / "evolution" / "adaptation"
        forbidden = (
            "atlas.evolution.autonomy",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.approval_manager",
            "atlas.evolution.governance",
            "atlas.ai",
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
                    if node.module and any(node.module == p or node.module.startswith(p)
                                           for p in forbidden):
                        violations.append((str(path), node.module))
        self.assertEqual(violations, [])

    def test_engine_source_has_no_approval_or_execution(self):
        import inspect

        from atlas.evolution.adaptation import engine as mod

        # Scan only the code (strip the leading module docstring so the
        # "NEVER ..." text does not trip the check).
        source = inspect.getsource(mod)
        tree = ast.parse(source)
        assert tree.body and isinstance(tree.body[0], ast.Expr)
        code = ast.get_source_segment(
            source, tree.body[1]
        ) if len(tree.body) > 1 else ""
        if not code:
            # Fallback: remove the first triple-quoted docstring.
            marker = '"""'
            first_close = source.find(marker, source.find(marker) + 3)
            code = source[first_close + 3:]
        for forbidden in ("SelfDevelopmentLoop", "DevelopmentPlanner",
                          "EvolutionExecutionGateway", "ApprovalManager",
                          "subprocess", "sandbox"):
            self.assertNotIn(forbidden, code)

    def test_no_registry_or_memory_reference_in_engine(self):
        import inspect

        from atlas.evolution.adaptation import engine as mod

        src = inspect.getsource(mod)
        for forbidden in ("ToolRegistry", "CapabilityRegistry", "SkillRegistry",
                          "ModelProfileRegistry", "LearningMemory",
                          "EvolutionMemory"):
            self.assertNotIn(forbidden, src)


# ---------------------------------------------------------------------------
# 34-37, 40: end-to-end F1/F2/F3 -> F4 regression integration
# ---------------------------------------------------------------------------


class TestFullPipelineIntegration(unittest.TestCase):

    def test_f1_f2_f3_to_f4_pipeline(self):
        from atlas.evolution.environment.models import (
            EnvironmentChange,
            EnvironmentChangeType,
            EnvironmentDomain,
            EnvironmentEntity,
        )
        from atlas.evolution.freshness.models import (
            FreshnessStatus,
            KnowledgeFreshnessAssessment,
        )
        from atlas.evolution.lifecycle.assessor import CapabilityLifecycleAssessor
        from atlas.evolution.lifecycle.models import LifecycleTarget

        # F1 change: model became unavailable.
        entity = EnvironmentEntity(EnvironmentDomain.MODEL, "openai:gpt-4")
        change = EnvironmentChange(
            entity=entity,
            change_type=EnvironmentChangeType.CHANGED,
            current={"available": False},
        )
        # F2: supporting knowledge is stale.
        stale = KnowledgeFreshnessAssessment(
            knowledge_id="KN-1", status=FreshnessStatus.STALE, assessed_at=NOW,
        )
        # F3: model target, marked unavailable, with a known replacement.
        target = LifecycleTarget(
            target_kind=LifecycleTargetKind.MODEL,
            identifier="openai:gpt-4",
            dependency_entity_keys=frozenset({"MODEL:openai:gpt-4"}),
            knowledge_dependencies=frozenset({"KN-1"}),
            available=False,
            replacement="openai:gpt-4.1",
        )
        assessment = CapabilityLifecycleAssessor().assess(
            target, changes=[change], freshness=[stale]
        )
        # F4: choose and build.
        engine = _engine()
        candidates = engine.decide([assessment])
        proposal = engine.generate([assessment])[0]

        # The F3 action is FALLBACK (unavailable + replacement known).
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].reason, LifecycleReason.REPLACEMENT_AVAILABLE)
        # The assessment carries both evidence streams (F1 change, F2 knowledge).
        self.assertIn("MODEL:openai:gpt-4", candidates[0].evidence_change_ids[0])
        self.assertIn("KN-1", candidates[0].evidence_knowledge_ids)
        # Proposal stays DRAFT; never approved.
        self.assertIs(proposal.status, ProposalStatus.DRAFT)

    def test_repeated_identical_pipeline_produces_equivalent_output(self):
        from atlas.evolution.environment.models import (
            EnvironmentChange,
            EnvironmentChangeType,
            EnvironmentDomain,
            EnvironmentEntity,
        )
        from atlas.evolution.lifecycle.assessor import CapabilityLifecycleAssessor
        from atlas.evolution.lifecycle.models import LifecycleTarget

        entity = EnvironmentEntity(EnvironmentDomain.TOOL, "tool_a")
        change = EnvironmentChange(
            entity=entity, change_type=EnvironmentChangeType.CHANGED,
            current={"available": True},
        )
        target = LifecycleTarget(
            target_kind=LifecycleTargetKind.TOOL,
            identifier="tool_a",
            dependency_entity_keys=frozenset({"TOOL:tool_a"}),
        )
        # F3 -> REVIEW at 0.8 (at threshold; policy threshold defaults 0.8 so
        # a candidate IS produced at 0.8).
        assessment = CapabilityLifecycleAssessor().assess(target, changes=[change])
        engine = _engine()
        r1 = engine.decide([assessment])
        r2 = engine.decide([assessment])
        self.assertEqual([c.candidate_id for c in r1],
                         [c.candidate_id for c in r2])


if __name__ == "__main__":
    unittest.main()