"""
Atlas Evolution Autonomy — Request Factory Tests — Phase 16.1

Verifies the deterministic constructors (from_proposal, from_goal,
from_goal_record, from_scheduler, from_cli) produce DRAFTED requests
exactly as the approved specification requires:

- Only state scopes are transcribable (protected scopes refused
  structurally with ValueError).
- Goal transcription carries the GoalAuthorization evidence snapshot.
- Requests carry scope-aligned intended levels and version anchors.
- No validation / authorization / scheduling / storage / gateway
  behaviour is performed by the factory.

Pure logic. No infra. No AI.
"""

import unittest
from datetime import datetime

from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    EvolutionRequestStatus,
    TargetKind,
)
from atlas.evolution.autonomy.request_factory import EvolutionRequestFactory
from atlas.evolution.autonomy.scope_classifier import STATE_SCOPES
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import (
    EvolutionProposal,
    ExecutionLevel,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    Weakness,
)
from atlas.goals.execution_models import GoalAuthorization
from atlas.goals.models import (
    GoalCategory,
    GoalPriority,
    GoalStatus,
    ImprovementGoal,
    ImprovementOpportunity,
)


class _ProposalFactory:
    """Builds minimal EvolutionProposals for factory tests."""

    @staticmethod
    def proposal(scope: ScopeType) -> EvolutionProposal:
        components = {
            ScopeType.CONFIG: ["config", "autonomy:config"],
            ScopeType.MEMORY: ["memory", "autonomy:memory"],
            ScopeType.KNOWLEDGE: ["knowledge", "autonomy:knowledge"],
            ScopeType.CAPABILITY: ["capability", "autonomy:capability"],
            ScopeType.UNKNOWN: ["governance:unknown"],
        }[scope]
        weakness = Weakness(
            area="test",
            description="test weakness",
            severity=ImprovementPriority.MEDIUM,
        )
        plan = ImprovementPlan(
            plan_id="plan-test",
            title="Test plan",
            description="Test description",
            priority=ImprovementPriority.MEDIUM,
            weaknesses=[weakness],
            expected_benefit="benefit",
            complexity_estimate="low",
            target_components=components,
        )
        return EvolutionProposal(
            proposal_id="PROP-TEST-1",
            title="Test proposal",
            summary="Test summary",
            rationale="Test rationale",
            expected_benefit="benefit",
            risks="low",
            impact_analysis="none",
            implementation_approach="approach",
            plan=plan,
            status=ProposalStatus.APPROVED,
        )


def _build_opportunity() -> ImprovementOpportunity:
    """Builds a minimal ImprovementOpportunity."""
    return ImprovementOpportunity(
        opportunity_id="OPP-1",
        title="Opportunity",
        description="Description",
        category=GoalCategory.RELIABILITY,
        source_candidates=["c1"],
        confidence=0.5,
        priority_score=0.8,
    )


class _GoalFactory:
    """Builds minimal goals and authorizations for transcription tests."""

    @staticmethod
    def goal(goal_id: str = "GOAL-TEST-1") -> ImprovementGoal:
        return ImprovementGoal(
            goal_id=goal_id,
            title="Test goal",
            description="Goal description",
            category=GoalCategory.EVOLUTION,
            priority=GoalPriority.MEDIUM,
            status=GoalStatus.APPROVED,
            evidence_count=2,
            confidence=0.7,
        )

    @staticmethod
    def authorization(goal_id: str = "GOAL-TEST-1") -> GoalAuthorization:
        return GoalAuthorization(
            goal_id=goal_id,
            authorized_by="user:cli",
            comment="authorized",
            strategy_key="strat-1",
            strategy_name="Strategy One",
            planning_context_version="2026-01-01T00:00:00+00:00",
        )


class TestFromProposal(unittest.TestCase):
    """Proposal-sourced requests classify scope via the closed map."""

    def test_state_scope_request(self):
        factory = EvolutionRequestFactory()
        req = factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG))
        self.assertIsInstance(req, EvolutionRequest)
        self.assertEqual(req.status, EvolutionRequestStatus.DRAFTED)
        self.assertEqual(req.target_scope, ScopeType.CONFIG)
        self.assertEqual(req.source, "PROP-TEST-1")
        self.assertEqual(req.metadata["source_type"], "proposal")

    def test_unknown_scope_request_kept_for_audit(self):
        # UNKNOWN-scope proposals still produce a DRAFTED request so the
        # audit trail is preserved; refusal occurs at translation/gateway.
        factory = EvolutionRequestFactory()
        req = factory.from_proposal(_ProposalFactory.proposal(ScopeType.UNKNOWN))
        self.assertEqual(req.status, EvolutionRequestStatus.DRAFTED)
        self.assertEqual(req.target_scope, ScopeType.UNKNOWN)
        self.assertEqual(req.intended_level, ExecutionLevel.ADMINISTRATIVE)

    def test_scope_aligned_intended_level(self):
        factory = EvolutionRequestFactory()
        config = factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG))
        memory = factory.from_proposal(_ProposalFactory.proposal(ScopeType.MEMORY))
        self.assertEqual(config.intended_level, ExecutionLevel.SELF_CONFIG)
        self.assertEqual(memory.intended_level, ExecutionLevel.INFORMATION)

    def test_unique_request_ids(self):
        factory = EvolutionRequestFactory()
        first = factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG))
        second = factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG))
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertTrue(first.request_id.startswith("AUTORQ-"))

    def test_version_anchor_present(self):
        factory = EvolutionRequestFactory()
        req = factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG))
        self.assertIsNotNone(req.version_target)
        self.assertEqual(req.version_target.target_kind, TargetKind.CONFIG)
        self.assertEqual(req.version_target.state_version_at_creation, "1.0.0")


class TestFromGoal(unittest.TestCase):
    """Goal transcription (Phase 16 Decision D12) carries evidence."""

    def test_goal_transcription(self):
        factory = EvolutionRequestFactory()
        goal = _GoalFactory.goal()
        auth = _GoalFactory.authorization()
        req = factory.from_goal(goal, auth, ScopeType.CONFIG)
        self.assertEqual(req.source, goal.goal_id)
        self.assertEqual(req.target_scope, ScopeType.CONFIG)
        self.assertEqual(req.metadata["source_type"], "goal")
        self.assertEqual(req.metadata["strategy_key"], "strat-1")
        self.assertEqual(req.metadata["strategy_name"], "Strategy One")
        self.assertEqual(
            req.metadata["planning_context_version"],
            "2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(req.metadata["authorized_by"], "user:cli")

    def test_goal_memory_scope_level(self):
        factory = EvolutionRequestFactory()
        req = factory.from_goal(
            _GoalFactory.goal(), _GoalFactory.authorization(), ScopeType.MEMORY
        )
        self.assertEqual(req.intended_level, ExecutionLevel.INFORMATION)

    def test_protected_scope_refused(self):
        factory = EvolutionRequestFactory()
        with self.assertRaises(ValueError):
            factory.from_goal(_GoalFactory.goal(), _GoalFactory.authorization(), ScopeType.IDENTITY)

    def test_code_scope_refused(self):
        factory = EvolutionRequestFactory()
        with self.assertRaises(ValueError):
            factory.from_goal(_GoalFactory.goal(), _GoalFactory.authorization(), ScopeType.CODE)

    def test_all_state_scopes_acceptable(self):
        factory = EvolutionRequestFactory()
        for scope in STATE_SCOPES:
            with self.subTest(scope=scope.name):
                req = factory.from_goal(
                    _GoalFactory.goal(), _GoalFactory.authorization(), scope
                )
                self.assertEqual(req.target_scope, scope)


class TestFromGoalRecord(unittest.TestCase):
    """Goal-by-ID transcription uses the injected repository only."""

    def test_missing_repository_returns_none(self):
        factory = EvolutionRequestFactory(goal_repository=None)
        self.assertIsNone(
            factory.from_goal_record(
                "GOAL-X", _GoalFactory.authorization(), ScopeType.CONFIG
            )
        )

    def test_missing_goal_returns_none(self):
        class EmptyRepo:
            def get_goal(self, goal_id):
                return None

        factory = EvolutionRequestFactory(goal_repository=EmptyRepo())
        self.assertIsNone(
            factory.from_goal_record(
                "GOAL-X", _GoalFactory.authorization(), ScopeType.CONFIG
            )
        )

    def test_goal_by_id_transcribed(self):
        class Repo:
            def get_goal(self, goal_id):
                if goal_id == "GOAL-TEST-1":
                    return _GoalFactory.goal()
                return None

        factory = EvolutionRequestFactory(goal_repository=Repo())
        req = factory.from_goal_record(
            "GOAL-TEST-1", _GoalFactory.authorization(), ScopeType.MEMORY
        )
        self.assertIsNotNone(req)
        self.assertEqual(req.source, "GOAL-TEST-1")
        self.assertEqual(req.target_scope, ScopeType.MEMORY)


class TestFromScheduler(unittest.TestCase):
    """Scheduler opportunities require an explicit state scope."""

    def test_scheduler_request(self):
        factory = EvolutionRequestFactory()
        req = factory.from_scheduler(_build_opportunity(), ScopeType.KNOWLEDGE)
        self.assertEqual(req.source, "OPP-1")
        self.assertEqual(req.target_scope, ScopeType.KNOWLEDGE)
        self.assertEqual(req.metadata["source_type"], "scheduler")
        self.assertEqual(req.metadata["priority_score"], "0.8")

    def test_protected_scope_refused(self):
        factory = EvolutionRequestFactory()
        with self.assertRaises(ValueError):
            factory.from_scheduler(_build_opportunity(), ScopeType.CODE)


class TestFromCli(unittest.TestCase):
    """CLI-sourced requests are structured and presentation-only."""

    def test_cli_request_copies_payload(self):
        factory = EvolutionRequestFactory()
        payload = {"title": "CLI change", "value": 42}
        req = factory.from_cli(ScopeType.CONFIG, payload, "cli:user1")
        self.assertEqual(req.source, "cli:user1")
        self.assertEqual(req.target_scope, ScopeType.CONFIG)
        self.assertEqual(req.change_payload, payload)
        self.assertEqual(req.metadata["source_type"], "cli")

    def test_payload_is_copied_not_referenced(self):
        factory = EvolutionRequestFactory()
        payload = {"title": "original"}
        req = factory.from_cli(ScopeType.CONFIG, payload, "cli:user1")
        payload["title"] = "mutated"
        self.assertEqual(req.change_payload["title"], "original")

    def test_protected_scope_refused(self):
        factory = EvolutionRequestFactory()
        with self.assertRaises(ValueError):
            factory.from_cli(ScopeType.IDENTITY, {}, "cli:user1")


class TestFactoryIsPure(unittest.TestCase):
    """The factory constructs drafts only — no lifecycle side effects."""

    def test_requests_always_drafted(self):
        factory = EvolutionRequestFactory()
        requests = [
            factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG)),
            factory.from_goal(
                _GoalFactory.goal(), _GoalFactory.authorization(), ScopeType.MEMORY
            ),
            factory.from_scheduler(_build_opportunity(), ScopeType.KNOWLEDGE),
            factory.from_cli(ScopeType.CAPABILITY, {}, "cli:user1"),
        ]
        for req in requests:
            self.assertEqual(req.status, EvolutionRequestStatus.DRAFTED)

    def test_timestamps_exist(self):
        factory = EvolutionRequestFactory()
        req = factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG))
        self.assertIsInstance(req.created_at, datetime)
        self.assertIsInstance(req.updated_at, datetime)

    def test_no_lifecycle_artifacts_attached(self):
        factory = EvolutionRequestFactory()
        req = factory.from_proposal(_ProposalFactory.proposal(ScopeType.CONFIG))
        self.assertIsNone(req.validation)
        self.assertIsNone(req.risk)
        self.assertIsNone(req.authorization)
        self.assertIsNone(req.schedule)
        self.assertIsNone(req.receipt)
        self.assertIsNone(req.verification)


if __name__ == "__main__":
    unittest.main()
