"""
Phase 20 Batch 4 — Reflection → Learning → Selection feedback.

Integration + unit tests proving:
  A. Reflection suggestions reach the LearningEngine via the
     RuntimeCoordinator pipeline.
  B. The LearningEngine consumes reflection suggestions and produces a
     reflection-derived learning insight (plus capability-keyed strategy
     evidence).
  C. A fake/minimal learning provider shows strategy-performance evidence
     changing CapabilityAnalyzer priority/order.
  D. The no-learning-provider case preserves existing analyzer behavior.
  E. Learning evidence affects a later capability-selection decision
     through the real kernel-owned LearningMemory instance.

Deterministic evidence only — no external model/provider calls.
"""

import unittest

from atlas.learning_engine.learning_engine import LearningEngine
from atlas.learning_engine.models import (
    LearningCategory,
    StrategyPerformance,
)
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.outcomes import ReasoningRecorder
from atlas.reasoning.planning import PlanningEngine
from atlas.reasoning.reflection import ReflectionEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator


_CAPABILITY_NAMES = (
    "conversation",
    "knowledge_retrieval",
    "task_execution",
    "analysis",
)


def _capability_handler(name: str, success: bool):
    """Build a handler that reports the registered capability name.

    Mirrors the DEFAULT_HANDLERS contract: each handler returns the
    capability it is registered under (not the plan-step action), so
    reflection evidence is keyed by the real capability name.
    """
    def _handler(params: dict) -> ExecutionResult:
        return ExecutionResult(
            capability=name,
            success=success,
            output={} if success else {"received": params},
            error="" if success else "test failure",
        )
    return _handler


def _make_coordinator(learning_engine=None, fail=True):
    """Build a full RuntimeCoordinator with reasoning + reflection + learning."""
    registry = CapabilityRegistry()
    for name in _CAPABILITY_NAMES:
        registry.register(name, _capability_handler(name, success=not fail))

    analyzer = CapabilityAnalyzer(
        learning_provider=learning_engine.memory if learning_engine else None
    )

    coordinator = RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=analyzer,
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        reflection_engine=ReflectionEngine(),
        reasoning_recorder=ReasoningRecorder(),
        learning_engine=learning_engine,
    )
    return coordinator


class TestReflectionReachesLearningEngine(unittest.TestCase):
    """A: reflection output flows into the LearningEngine through the pipeline."""

    def test_reflection_suggestions_reach_learning_engine(self):
        learning = LearningEngine()
        coordinator = _make_coordinator(
            learning_engine=learning,
            fail=True,
        )

        # Frequent-failure reflection needs >= 3 uses of a capability with
        # >= 50% failure rate. Run 6 failing processes.
        for i in range(6):
            coordinator.process(f"trigger failure {i}")

        # Reflection must have been recorded and consumed by learning.
        reflection_insights = [
            i for i in learning.memory.get_insights(200)
            if i.metadata.get("source") == "reflection"
        ]
        self.assertTrue(
            reflection_insights,
            "No reflection-derived insight stored in LearningMemory",
        )
        self.assertEqual(
            reflection_insights[0].category,
            LearningCategory.OPTIMIZATION,
        )
        self.assertEqual(
            reflection_insights[0].metadata["source"],
            "reflection",
        )


class TestLearningEngineConsumesReflection(unittest.TestCase):
    """B: LearningEngine turns reflection suggestions into learning evidence."""

    def test_reflection_suggestion_produces_insight_and_evidence(self):
        engine = LearningEngine()
        data = {
            "success": True,
            "has_reasoning": True,
            "has_planning": True,
            "has_tool_result": False,
            "understanding_insights_count": 0,
            "reflection_suggestions": [
                {
                    "pattern": "frequent_failures",
                    "description": "Capability 'conversation' has a 100% failure rate "
                                   "across 6 uses (6 failures).",
                    "suggestion": "Review handler for capability 'conversation'.",
                    "confidence": 1.0,
                    "target_area": "capability_selection",
                    "affected_outcomes_count": 6,
                }
            ],
        }

        insights = engine.learn_from_pipeline(data)

        reflection_insights = [
            i for i in insights
            if i.metadata.get("source") == "reflection"
        ]
        self.assertEqual(len(reflection_insights), 1)
        self.assertEqual(
            reflection_insights[0].title,
            "Reflection: frequent_failures",
        )

        # Capability-keyed strategy evidence must exist for the analyzer.
        performance = engine.memory.get_strategy_by_name("conversation")
        self.assertIsNotNone(performance)
        self.assertGreaterEqual(performance.total_uses, 6)
        # 100% failure rate with 6 uses → success rate 0.0
        self.assertEqual(performance.success_rate, 0.0)

    def test_no_reflection_suggestions_no_reflection_insight(self):
        engine = LearningEngine()
        data = {
            "success": True,
            "has_reasoning": True,
            "has_planning": True,
            "has_tool_result": False,
            "understanding_insights_count": 1,
        }

        insights = engine.learn_from_pipeline(data)

        reflection_insights = [
            i for i in insights
            if i.metadata.get("source") == "reflection"
        ]
        self.assertEqual(reflection_insights, [])
        # Understanding insight still generated (backward compatibility).
        self.assertTrue(
            any(i.category == LearningCategory.UNDERSTANDING_STRATEGY for i in insights)
        )


class TestAnalyzerWithLearningProvider(unittest.TestCase):
    """C: strategy-performance evidence changes priority/order."""

    def test_provider_evidence_reorders_capabilities(self):
        # Fake provider: task_execution has a proven effective history.
        class FakeProvider:
            def get_strategy_by_name(self, name):
                if name == "task_execution":
                    return StrategyPerformance(
                        strategy_id="S-E",
                        strategy_name="task_execution",
                        strategy_type="capability",
                        total_uses=10,
                        success_count=10,
                        failure_count=0,
                    )
                return None

        analyzer = CapabilityAnalyzer(learning_provider=FakeProvider())

        from atlas.reasoning.models import ReasoningPlan, ReasoningStep

        plan = ReasoningPlan(
            goal="query then execute",
            steps=[
                ReasoningStep(action="query"),
                ReasoningStep(action="execute"),
            ],
        )

        capabilities = analyzer.analyze(plan)
        names = [c.name for c in capabilities]

        # Baseline order: knowledge_retrieval(8), task_execution(7).
        # With evidence, task_execution(7+2=9) overtakes knowledge_retrieval(8).
        self.assertEqual(names, ["task_execution", "knowledge_retrieval"])
        self.assertEqual(
            next(c for c in capabilities if c.name == "task_execution").priority,
            9,
        )
        self.assertEqual(
            next(c for c in capabilities if c.name == "knowledge_retrieval").priority,
            8,
        )

    def test_low_evidence_uses_ignored(self):
        # A record with fewer than MIN_EVIDENCE_USES uses must not influence.
        class FakeProvider:
            def get_strategy_by_name(self, name):
                if name == "task_execution":
                    return StrategyPerformance(
                        strategy_id="S-E",
                        strategy_name="task_execution",
                        total_uses=1,
                        success_count=1,
                        failure_count=0,
                    )
                return None

        analyzer = CapabilityAnalyzer(learning_provider=FakeProvider())

        from atlas.reasoning.models import ReasoningPlan, ReasoningStep

        plan = ReasoningPlan(
            goal="execute",
            steps=[ReasoningStep(action="execute")],
        )
        capabilities = analyzer.analyze(plan)

        self.assertEqual(capabilities[0].priority, 7)


class TestAnalyzerWithoutProvider(unittest.TestCase):
    """D: no learning provider → existing static behavior unchanged."""

    def test_priorities_unchanged_without_provider(self):
        analyzer = CapabilityAnalyzer()

        from atlas.reasoning.models import ReasoningPlan, ReasoningStep

        plan = ReasoningPlan(
            goal="multi",
            steps=[
                ReasoningStep(action="respond"),
                ReasoningStep(action="query"),
                ReasoningStep(action="execute"),
            ],
        )

        capabilities = analyzer.analyze(plan)
        names = [c.name for c in capabilities]

        self.assertEqual(
            names,
            ["conversation", "knowledge_retrieval", "task_execution"],
        )
        priorities = {c.name: c.priority for c in capabilities}
        self.assertEqual(priorities["conversation"], 10)
        self.assertEqual(priorities["knowledge_retrieval"], 8)
        self.assertEqual(priorities["task_execution"], 7)

    def test_provider_none_constructor_is_equivalent(self):
        self.assertIsNone(CapabilityAnalyzer()._learning_provider)
        self.assertIsNone(CapabilityAnalyzer(learning_provider=None)._learning_provider)


class TestLearningAffectsLaterSelection(unittest.TestCase):
    """E: learning evidence changes a later capability-selection decision."""

    def test_reflection_evidence_changes_subsequent_selection(self):
        learning = LearningEngine()

        # Phase 1: stream of failures → reflection → learning evidence.
        coordinator = _make_coordinator(
            learning_engine=learning,
            fail=True,
        )
        for i in range(6):
            coordinator.process(f"failing run {i}")

        performance = learning.memory.get_strategy_by_name("conversation")
        self.assertIsNotNone(performance)
        self.assertLess(performance.success_rate, 0.5)

        # Phase 2: a later selection is influenced by the stored evidence.
        # The same LearningMemory instance feeds the analyzer.
        second_analyzer = CapabilityAnalyzer(
            learning_provider=learning.memory,
        )
        from atlas.reasoning.models import ReasoningPlan, ReasoningStep

        plan = ReasoningPlan(
            goal="respond",
            steps=[ReasoningStep(action="respond")],
        )
        capabilities = second_analyzer.analyze(plan)

        # Baseline conversation priority is 10; the failure evidence must
        # lower it (deterministic bounded adjustment).
        self.assertEqual(capabilities[0].name, "conversation")
        self.assertLess(capabilities[0].priority, 10)

    def test_no_evidence_no_selection_change(self):
        # A fresh learning engine (no reflection evidence) must not change
        # the analyzer's selection.
        learning = LearningEngine()

        # One successful run only: no failure evidence recorded.
        coordinator = _make_coordinator(
            learning_engine=learning,
            fail=False,
        )
        coordinator.process("single success")

        self.assertIsNone(learning.memory.get_strategy_by_name("conversation"))

        analyzer = CapabilityAnalyzer(learning_provider=learning.memory)
        from atlas.reasoning.models import ReasoningPlan, ReasoningStep

        plan = ReasoningPlan(
            goal="respond",
            steps=[ReasoningStep(action="respond")],
        )
        capabilities = analyzer.analyze(plan)
        self.assertEqual(capabilities[0].priority, 10)


if __name__ == "__main__":
    unittest.main()
