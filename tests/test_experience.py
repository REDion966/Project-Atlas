"""
Phase 9.0 — Experience & Self-Model Tests

Comprehensive tests for:
- Experience models
- ExperienceRepository bounded storage
- ExperienceAccumulator
- TrendAnalyzer
- OutcomeTracker
- SelfModelEngine
- RuntimeCoordinator integration
- Architecture boundaries (pure logic, no infrastructure imports)
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from atlas.cognition.models import CognitionState, PipelineMetrics, PipelineResult, StageResult, StageStatus, StageType
from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    SelfModelSnapshot,
    StructuredExperience,
    TrackedGoal,
    TrendAnalysis,
)
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.experience_accumulator import ExperienceAccumulator
from atlas.experience.trend_analyzer import TrendAnalyzer
from atlas.experience.outcome_tracker import OutcomeTracker
from atlas.experience.self_model_engine import SelfModelEngine


class TestExperienceModels(unittest.TestCase):
    """Immutable dataclass models."""

    def test_structured_experience_defaults(self):
        e = StructuredExperience(
            experience_id="EXP-00000001",
            timestamp=datetime.now(),
            duration_ms=100.0,
            pipeline_path=["understanding", "reasoning"],
            outcome=ExperienceOutcome.SUCCESS,
        )
        self.assertEqual(e.experience_id, "EXP-00000001")
        self.assertEqual(e.user_input, "")
        self.assertEqual(e.outcome, ExperienceOutcome.SUCCESS)

    def test_frozen_model_rejects_modification(self):
        e = StructuredExperience(
            experience_id="EXP-00000001",
            timestamp=datetime.now(),
            duration_ms=100.0,
            pipeline_path=[],
            outcome=ExperienceOutcome.SUCCESS,
        )
        with self.assertRaises(Exception):
            e.user_input = "modified"

    def test_goal_outcome_enum_values(self):
        self.assertEqual(GoalOutcome.ACCEPTED.name, "ACCEPTED")
        self.assertEqual(ExperienceOutcome.FAILURE.name, "FAILURE")


class TestExperienceRepository(unittest.TestCase):
    """Bounded storage for experiences, analyses, and tracked goals."""

    def setUp(self):
        self.repo = ExperienceRepository(max_experiences=5)

    def tearDown(self):
        self.repo.clear()

    def test_store_and_retrieve_experience(self):
        exp = self._make_exp("EXP-00000001")
        self.repo.store_experience(exp)
        self.assertEqual(self.repo.experience_count, 1)
        self.assertEqual(self.repo.get_experience("EXP-00000001"), exp)

    def test_bounded_eviction(self):
        for i in range(7):
            self.repo.store_experience(self._make_exp(f"EXP-{i:08d}"))
        self.assertEqual(self.repo.experience_count, 5)
        self.assertIsNone(self.repo.get_experience("EXP-00000000"))

    def test_get_window(self):
        for i in range(5):
            self.repo.store_experience(self._make_exp(f"EXP-{i:08d}"))
        window = self.repo.get_window(3)
        self.assertEqual(len(window), 3)
        self.assertEqual(window[0].experience_id, "EXP-00000004")
        self.assertEqual(window[-1].experience_id, "EXP-00000002")

    def test_get_experiences_by_outcome(self):
        self.repo.store_experience(self._make_exp("EXP-00000001", ExperienceOutcome.SUCCESS))
        self.repo.store_experience(self._make_exp("EXP-00000002", ExperienceOutcome.FAILURE))
        failures = self.repo.get_experiences_by_outcome(ExperienceOutcome.FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].experience_id, "EXP-00000002")

    def test_store_and_retrieve_tracked_goal(self):
        goal = TrackedGoal(goal_id="G1", goal_title="Improve reasoning")
        self.repo.store_tracked_goal(goal)
        self.assertEqual(len(self.repo.get_tracked_goals()), 1)
        self.assertEqual(self.repo.get_tracked_goal("G1").goal_title, "Improve reasoning")

    def test_summary(self):
        self.repo.store_experience(self._make_exp("EXP-00000001"))
        summary = self.repo.summary()
        self.assertEqual(summary["experience_count"], 1)
        self.assertEqual(summary["analysis_count"], 0)

    def test_invalid_limits_raise(self):
        with self.assertRaises(ValueError):
            ExperienceRepository(max_experiences=0)

    @staticmethod
    def _make_exp(exp_id: str, outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS) -> StructuredExperience:
        return StructuredExperience(
            experience_id=exp_id,
            timestamp=datetime.now(),
            duration_ms=10.0,
            pipeline_path=[],
            outcome=outcome,
        )


class TestExperienceAccumulator(unittest.TestCase):
    """Convert CognitionState + PipelineResult into StructuredExperience."""

    def setUp(self):
        self.repo = ExperienceRepository()
        self.acc = ExperienceAccumulator(repository=self.repo)

    def tearDown(self):
        self.repo.clear()

    def test_record_valid_state_and_result(self):
        state = CognitionState(user_input="hello")
        state.understanding_insights = [MagicMock(), MagicMock()]
        state.concepts = [MagicMock(label="concept1")]
        state.reasoning_result = {
            "goal": "respond",
            "capabilities": [{"name": "conversation"}],
            "results": [{"success": True}],
        }
        state.planning_result = {"goal": "respond", "steps": [{}, {}], "validation_errors": []}
        state.tool_result = {"tool_name": "echo", "tool_success": True}
        state.learning_engine_result = {"insights_count": 3}
        state.reflection_suggestions = [MagicMock()]
        state.goal_intelligence_report = MagicMock(total_recommendations=2)

        metrics = PipelineMetrics(completed_at=datetime.now(), total_duration_ms=150.0)
        result = PipelineResult(success=True, metrics=metrics)

        exp = self.acc.record(state, result)

        self.assertIsNotNone(exp)
        self.assertEqual(exp.user_input, "hello")
        self.assertEqual(exp.understanding_insights_count, 2)
        self.assertEqual(exp.concepts_extracted, ["concept1"])
        self.assertEqual(exp.reasoning_goal, "respond")
        self.assertEqual(exp.reasoning_capabilities, ["conversation"])
        self.assertEqual(exp.reasoning_success_count, 1)
        self.assertEqual(exp.planning_step_count, 2)
        self.assertEqual(exp.tool_name, "echo")
        self.assertTrue(exp.tool_success)
        self.assertEqual(exp.learning_insights_count, 3)
        self.assertEqual(exp.goal_recommendations_count, 2)
        self.assertEqual(self.acc.recorded_count, 1)

    def test_record_none_inputs_returns_none(self):
        self.assertIsNone(self.acc.record(None, None))

    def test_derive_outcome_success(self):
        metrics = PipelineMetrics(completed_at=datetime.now())
        stages = [
            StageResult(stage=StageType.UNDERSTANDING, status=StageStatus.SUCCESS),
            StageResult(stage=StageType.REASONING, status=StageStatus.SUCCESS),
        ]
        result = PipelineResult(success=True, metrics=metrics, stages=stages)
        exp = self.acc.record(CognitionState(), result)
        self.assertEqual(exp.outcome, ExperienceOutcome.SUCCESS)

    def test_derive_outcome_partial(self):
        metrics = PipelineMetrics(completed_at=datetime.now())
        stages = [
            StageResult(stage=StageType.UNDERSTANDING, status=StageStatus.SUCCESS),
            StageResult(stage=StageType.REASONING, status=StageStatus.FAILED),
        ]
        result = PipelineResult(success=True, metrics=metrics, stages=stages)
        exp = self.acc.record(CognitionState(), result)
        self.assertEqual(exp.outcome, ExperienceOutcome.PARTIAL)

    def test_derive_outcome_failure(self):
        metrics = PipelineMetrics(completed_at=datetime.now())
        stages = [
            StageResult(stage=StageType.UNDERSTANDING, status=StageStatus.FAILED),
            StageResult(stage=StageType.REASONING, status=StageStatus.FAILED),
        ]
        result = PipelineResult(success=False, metrics=metrics, stages=stages)
        exp = self.acc.record(CognitionState(), result)
        self.assertEqual(exp.outcome, ExperienceOutcome.FAILURE)


class TestTrendAnalyzer(unittest.TestCase):
    """Directional trend detection over experience windows."""

    def setUp(self):
        self.analyzer = TrendAnalyzer(threshold=0.1)

    def test_empty_window_returns_default(self):
        analysis = self.analyzer.analyze([])
        self.assertEqual(analysis.window_size, 0)
        self.assertEqual(analysis.success_rate_trend, "stable")

    def test_single_experience_returns_stable(self):
        exps = [self._make_exp(outcome=ExperienceOutcome.SUCCESS)]
        analysis = self.analyzer.analyze(exps)
        self.assertEqual(analysis.window_size, 1)
        self.assertEqual(analysis.success_rate_trend, "stable")

    def test_improving_success_rate(self):
        exps = (
            [self._make_exp(outcome=ExperienceOutcome.FAILURE) for _ in range(5)]
            + [self._make_exp(outcome=ExperienceOutcome.SUCCESS) for _ in range(5)]
        )
        analysis = self.analyzer.analyze(exps)
        self.assertEqual(analysis.success_rate_trend, "improving")

    def test_declining_success_rate(self):
        exps = (
            [self._make_exp(outcome=ExperienceOutcome.SUCCESS) for _ in range(5)]
            + [self._make_exp(outcome=ExperienceOutcome.FAILURE) for _ in range(5)]
        )
        analysis = self.analyzer.analyze(exps)
        self.assertEqual(analysis.success_rate_trend, "declining")

    def test_planning_trend_inverted(self):
        exps = (
            [self._make_exp(planning_errors=3) for _ in range(5)]
            + [self._make_exp(planning_errors=0) for _ in range(5)]
        )
        analysis = self.analyzer.analyze(exps)
        self.assertEqual(analysis.planning_trend, "improving")

    def test_capability_trends(self):
        exps = (
            [self._make_exp(caps=["reasoning"], outcome=ExperienceOutcome.FAILURE) for _ in range(5)]
            + [self._make_exp(caps=["reasoning"], outcome=ExperienceOutcome.SUCCESS) for _ in range(5)]
        )
        analysis = self.analyzer.analyze(exps)
        self.assertEqual(analysis.capability_trends.get("reasoning"), "improving")

    def test_invalid_threshold_raises(self):
        with self.assertRaises(ValueError):
            TrendAnalyzer(threshold=1.5)

    @staticmethod
    def _make_exp(
        outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
        planning_errors: int = 0,
        caps: list[str] | None = None,
    ) -> StructuredExperience:
        return StructuredExperience(
            experience_id="EXP-00000000",
            timestamp=datetime.now(),
            duration_ms=10.0,
            pipeline_path=[],
            outcome=outcome,
            planning_validation_errors=planning_errors,
            reasoning_capabilities=caps or [],
            reasoning_total_count=1,
        )


class TestOutcomeTracker(unittest.TestCase):
    """Track whether recommendations produce observable outcomes."""

    def setUp(self):
        self.repo = ExperienceRepository()
        self.tracker = OutcomeTracker(repository=self.repo)

    def tearDown(self):
        self.repo.clear()

    def test_track_recommendation(self):
        rec = MagicMock()
        rec.item_id = "REC-0001"
        rec.problem = "Improve reasoning pipeline"
        goal = self.tracker.track_recommendation(rec)
        self.assertIsNotNone(goal)
        self.assertEqual(goal.goal_id, "REC-0001")
        self.assertEqual(goal.outcome, GoalOutcome.PENDING)

    def test_evaluate_implemented(self):
        rec = MagicMock()
        rec.item_id = "REC-0001"
        rec.problem = "Improve reasoning pipeline"
        self.tracker.track_recommendation(rec)

        for i in range(3):
            exp = StructuredExperience(
                experience_id=f"EXP-{i:08d}",
                timestamp=datetime.now(),
                duration_ms=10.0,
                pipeline_path=[],
                outcome=ExperienceOutcome.SUCCESS,
                user_input="",
                reasoning_goal="Improve reasoning pipeline",
            )
            self.repo.store_experience(exp)

        updated = self.tracker.evaluate_outcomes()
        self.assertEqual(updated[0].outcome, GoalOutcome.IMPLEMENTED)

    def test_evaluate_obsolete(self):
        rec = MagicMock()
        rec.item_id = "REC-0001"
        rec.problem = "Improve quantum computing support"
        self.tracker.track_recommendation(rec)

        for i in range(50):
            exp = StructuredExperience(
                experience_id=f"EXP-{i:08d}",
                timestamp=datetime.now(),
                duration_ms=10.0,
                pipeline_path=[],
                outcome=ExperienceOutcome.SUCCESS,
                user_input="hello",
            )
            self.repo.store_experience(exp)

        updated = self.tracker.evaluate_outcomes()
        self.assertEqual(updated[0].outcome, GoalOutcome.OBSOLETE)

    def test_outcome_summary(self):
        rec = MagicMock()
        rec.item_id = "REC-0001"
        rec.problem = "Improve reasoning"
        self.tracker.track_recommendation(rec)
        summary = self.tracker.get_outcome_summary()
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["by_outcome"].get("pending"), 1)


class TestSelfModelEngine(unittest.TestCase):
    """Orchestrate experience analysis and produce self-model snapshots."""

    def setUp(self):
        self.repo = ExperienceRepository()
        self.engine = SelfModelEngine(
            repository=self.repo,
            update_interval=1,
            window_size=4,
        )

    def tearDown(self):
        self.repo.clear()

    def test_update_interval_respected(self):
        self.repo.store_experience(StructuredExperience(
            experience_id="EXP-00000000",
            timestamp=datetime.now(),
            duration_ms=10.0,
            pipeline_path=[],
            outcome=ExperienceOutcome.SUCCESS,
        ))
        self.assertIsNotNone(self.engine.update())  # counter = 1, runs
        self.assertIsNotNone(self.engine.get_snapshot())
        self.assertIsNotNone(self.engine.update())  # counter = 2, runs

    def test_update_interval_skip(self):
        engine = SelfModelEngine(repository=self.repo, update_interval=2)
        self.assertIsNone(engine.update())  # counter = 1, skipped
        self.assertIsNone(engine.get_snapshot())

    def test_produces_snapshot(self):
        for i in range(4):
            self.repo.store_experience(StructuredExperience(
                experience_id=f"EXP-{i:08d}",
                timestamp=datetime.now(),
                duration_ms=10.0,
                pipeline_path=[],
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_capabilities=["conversation"],
                reasoning_total_count=1,
            ))
        snapshot = self.engine.update()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.total_experiences, 4)
        self.assertEqual(snapshot.overall_success_rate, 1.0)
        self.assertIn("conversation", snapshot.capability_assessments)

    def test_identity_evidence_fed(self):
        identity = MagicMock()
        belief_manager = MagicMock()
        belief_manager.beliefs = {
            "I am continuously improving through experience.": MagicMock(confidence=0.5),
        }
        identity.belief_manager = belief_manager
        identity.capability_profiler = MagicMock()
        identity.decision_style_manager = MagicMock()

        engine = SelfModelEngine(
            repository=self.repo,
            identity_engine=identity,
            update_interval=1,
            window_size=10,
        )

        # First half failures, second half successes -> success_rate_trend = improving
        for i in range(5):
            self.repo.store_experience(StructuredExperience(
                experience_id=f"EXP-{i:08d}",
                timestamp=datetime.now() - timedelta(minutes=10 - i),
                duration_ms=10.0,
                pipeline_path=[],
                outcome=ExperienceOutcome.FAILURE,
                reasoning_total_count=1,
                reasoning_success_count=0,
            ))
        for i in range(5, 10):
            self.repo.store_experience(StructuredExperience(
                experience_id=f"EXP-{i:08d}",
                timestamp=datetime.now() - timedelta(minutes=10 - i),
                duration_ms=10.0,
                pipeline_path=[],
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_total_count=1,
                reasoning_success_count=1,
            ))

        engine.update()
        self.assertTrue(
            belief_manager.strengthen_belief.called or belief_manager.weaken_belief.called,
            "Expected identity belief manager to receive evidence",
        )

    def test_feeds_self_understanding(self):
        understanding = MagicMock()
        engine = SelfModelEngine(
            repository=self.repo,
            understanding_engine=understanding,
            update_interval=1,
            window_size=2,
        )
        for i in range(2):
            self.repo.store_experience(StructuredExperience(
                experience_id=f"EXP-{i:08d}",
                timestamp=datetime.now(),
                duration_ms=10.0,
                pipeline_path=[],
                outcome=ExperienceOutcome.SUCCESS,
            ))
        engine.update()
        understanding.process_text.assert_called_once()
        args = understanding.process_text.call_args
        self.assertIn("Self-observation", args.kwargs["text"])
        self.assertEqual(args.kwargs["source"], "self_model_engine")

    def test_feeds_goal_intelligence(self):
        goal_engine = MagicMock()
        engine = SelfModelEngine(
            repository=self.repo,
            goal_intelligence_engine=goal_engine,
            update_interval=1,
            window_size=2,
        )
        for i in range(2):
            self.repo.store_experience(StructuredExperience(
                experience_id=f"EXP-{i:08d}",
                timestamp=datetime.now(),
                duration_ms=10.0,
                pipeline_path=[],
                outcome=ExperienceOutcome.SUCCESS,
            ))
        engine.update()
        goal_engine.analyze.assert_called_once()


class TestArchitectureBoundaries(unittest.TestCase):
    """Ensure Phase 9.0 remains pure logic."""

    def test_no_infrastructure_imports(self):
        """Experience package must not import infrastructure modules."""
        import atlas.experience.experience_repository as repo_mod
        import atlas.experience.experience_accumulator as acc_mod
        import atlas.experience.trend_analyzer as trend_mod
        import atlas.experience.outcome_tracker as outcome_mod
        import atlas.experience.self_model_engine as self_mod

        forbidden = {"atlas.events", "atlas.storage", "atlas.config", "atlas.state"}
        for mod in (repo_mod, acc_mod, trend_mod, outcome_mod, self_mod):
            source = mod.__doc__ or ""
            source += "\n".join(str(v) for v in mod.__dict__.values())
            for f in forbidden:
                self.assertNotIn(f, source, f"{mod.__name__} imports {f}")


class TestRuntimeCoordinatorIntegration(unittest.TestCase):
    """RuntimeCoordinator records experiences and updates self-model."""

    def setUp(self):
        from atlas.runtime.runtime_coordinator import RuntimeCoordinator

        self.coordinator = RuntimeCoordinator()
        self.repo = ExperienceRepository()
        self.acc = ExperienceAccumulator(repository=self.repo)
        self.engine = SelfModelEngine(
            repository=self.repo,
            update_interval=1,
            window_size=2,
        )
        self.coordinator.set_experience_accumulator(self.acc)
        self.coordinator.set_self_model_engine(self.engine)

    def tearDown(self):
        self.repo.clear()

    def test_process_records_experience(self):
        result = self.coordinator.process("hello")
        self.assertTrue(result.success)
        self.assertEqual(self.repo.experience_count, 1)
        exp = self.repo.get_experiences(1)[0]
        self.assertEqual(exp.user_input, "hello")

    def test_process_updates_self_model(self):
        self.coordinator.process("hello")
        self.coordinator.process("world")
        snapshot = self.engine.get_snapshot()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.total_experiences, 2)

    def test_optional_dependencies_backward_compatible(self):
        from atlas.runtime.runtime_coordinator import RuntimeCoordinator

        coord = RuntimeCoordinator()
        result = coord.process("hello")
        self.assertTrue(result.success)
        self.assertIsNone(coord.experience_accumulator)
        self.assertIsNone(coord.self_model_engine)


if __name__ == "__main__":
    unittest.main()
