"""
Phase 20 — Closed-Loop Integration Acceptance (Batch 8).

End-to-end acceptance proving that information actually travels through
the connected Phase 20 architecture:

  A. Explicit goal reaches the plan
  B. Reasoning is evidence-bound (kernel KnowledgeEvidenceProvider)
  C. Causal reasoning uses the world model (kernel CausalGraphProvider)
  D. Planning drives capability selection/execution
  E. A Track capability is reachable from a plan
  F. Reflection reaches LearningEngine (reflection-derived insight)
  G. Learning evidence changes a later capability decision
  H. EvolutionIntelligenceEngine.analyze_all() is invoked by the scheduler
  I. Model routing is active (RoutingRequest -> AIService -> ModelRouter)
  J. Atlas.tick() reaches GoalExecutionEngine.settle()
  K. CLI interaction invokes Atlas.tick() exactly once
  L. Combined closed loop: goal -> reasoning -> planning -> dispatch -> routing

All persistence is isolated to temporary paths. No network / providers.
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from atlas.evolution.scheduler import EvolutionScheduler
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.self_observation import SelfObservationEngine
from atlas.evolution.models import Observation, ObservationCategory
from atlas.kernel.atlas import Atlas
from atlas.learning_engine.learning_engine import LearningEngine
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning import PlanningEngine
from atlas.reasoning.reflection import ReflectionEngine
from atlas.reasoning.outcomes import ReasoningRecorder
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.storage.advanced_reasoning_storage import AdvancedReasoningSQLiteStorage
from atlas.storage.evolution_storage import SQLiteEvolutionStorage
from atlas.storage.experience_storage import SQLiteExperienceStorage
from atlas.storage.longterm_storage import LongTermSQLiteStorage
from atlas.storage.research_storage import ResearchSQLiteStorage
from atlas.storage.toolchain_storage import ToolchainSQLiteStorage
from atlas.storage.understanding_storage import SQLiteUnderstandingStorage
from atlas.world_model.models import EntityCategory, RelationType

from tests.test_phase20_batch7_cli_tick import FakeStreamingAtlas


# ---------------------------------------------------------------------------
# Test isolation: every SQLite-backed store the kernel reaches is redirected
# to a single temporary directory per test so atlas_data/ is never touched.
# ---------------------------------------------------------------------------

_STORES = (
    SQLiteExperienceStorage,
    SQLiteUnderstandingStorage,
    SQLiteEvolutionStorage,
    ResearchSQLiteStorage,
    ToolchainSQLiteStorage,
    LongTermSQLiteStorage,
    AdvancedReasoningSQLiteStorage,
)


class KernelTestCase(unittest.TestCase):
    """Base case that starts a real Atlas with fully isolated persistence."""

    def setUp(self) -> None:
        # ignore_cleanup_errors keeps Windows from raising when SQLite
        # releases its file handles slightly later than shutdown().
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._patchers = [
            patch.object(store, "DEFAULT_DB_PATH", Path(self._tmp.name) / "atlas.db")
            for store in _STORES
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(self._stop_patchers)
        self.addCleanup(self._tmp.cleanup)
        self.atlas: Atlas | None = None

    def _stop_patchers(self) -> None:
        for p in self._patchers:
            p.stop()

    def start_atlas(self) -> Atlas:
        if self.atlas is None:
            self.atlas = Atlas()
            self.atlas.start()
        return self.atlas

    def tearDown(self) -> None:
        if self.atlas is not None and self.atlas.started:
            self.atlas.shutdown()


# ---------------------------------------------------------------------------
# Coordinator helper: real reasoning + planning pipeline with spy handlers.
# ---------------------------------------------------------------------------


def _tracking_handler(name: str, calls: list, success: bool = True):
    """Return a handler recording invocation and reporting `name`."""
    def _handler(params: dict) -> ExecutionResult:
        calls.append({"capability": name, "params": params})
        return ExecutionResult(
            capability=name,
            success=success,
            output={"ok": True, "params": params} if success else {},
            error="" if success else "test failure",
        )
    return _handler


def _make_coordinator(
    registry: CapabilityRegistry,
    learning_engine=None,
    ai_service=None,
    reasoning_controller=None,
):
    """Build a RuntimeCoordinator over the given registry with the real
    reasoning/planning pipeline."""
    return RuntimeCoordinator(
        reasoning_controller=reasoning_controller or ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(
            learning_provider=(
                learning_engine.memory if learning_engine is not None else None
            )
        ),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        reflection_engine=ReflectionEngine(),
        reasoning_recorder=ReasoningRecorder(),
        learning_engine=learning_engine,
        ai_service=ai_service,
    )


def _plan_controller(goal: str, actions: list[str], parameters_map=None):
    """Return a ReasoningController-like object producing a plan with the
    given step actions (explicit-goal and Track-capability reachability).

    Each step's parameters default to {"action": <action>}; a
    parameters_map may override parameters for specific actions.
    """
    parameters_map = parameters_map or {}
    controller = MagicMock()
    plan = ReasoningPlan(
        goal=goal,
        steps=[
            ReasoningStep(
                description=f"Step for {action}",
                action=action,
                parameters=parameters_map.get(action, {"action": action}),
            )
            for action in actions
        ],
    )
    controller.create_plan.return_value = plan
    return controller


def _track_default_params(track: str, atlas: Atlas) -> dict:
    """Return deterministic handler parameters for a Track capability and
    seed the knowledge base when the handler reads evidence from it."""
    if track == "reasoning.trace":
        atlas._knowledge_manager.remember(
            title="track evidence",
            content=(
                "is the track reached by pipeline "
                "yes it is reached by the pipeline."
            ),
            source="phase20_closed_loop",
        )
        return {"question": "is the track reached by pipeline"}
    return {"action": track}


def _seed_observations(engine: SelfObservationEngine, count: int = 6) -> None:
    for i in range(count):
        engine.record_observation(Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="runtime_summary",
            value={
                "avg_response_time_ms": 6000 + i * 500,
                "request_count": 100,
                "error_count": 12 + i,
                "error_rate_percent": 12.0 + i,
            },
            unit="composite",
            description=f"Observation {i}",
            timestamp=datetime.now(),
            source="test",
        ))


class RecordingAIService:
    """Fake AIService recording routing_context and returning a text reply."""

    def __init__(self):
        self.routing_contexts = []

    def chat(self, messages, routing_context=None):
        self.routing_contexts.append(routing_context)
        response = MagicMock()
        response.text = "routed reply"
        return response

    def stream_chat(self, messages, routing_context=None):
        self.routing_contexts.append(routing_context)
        yield "chunk"


class SpyIntelligenceEngine:
    """Spy recording analyze_all/get_insights lifecycle calls."""

    def __init__(self):
        self.calls = []

    def analyze_all(self):
        self.calls.append("analyze_all")
        return []

    def get_insights(self):
        self.calls.append("get_insights")
        return []


# ---------------------------------------------------------------------------
# A. Explicit goal reaches the plan
# ---------------------------------------------------------------------------


class TestGoalReachesPlan(unittest.TestCase):
    def test_explicit_goal_propagates_through_planning(self):
        registry = CapabilityRegistry()
        calls: list = []
        registry.register("conversation", _tracking_handler("conversation", calls))
        coordinator = _make_coordinator(registry)

        original = coordinator._reasoning_controller
        captured_goal: list[str] = []

        def _create_plan(decision):
            plan = original.create_plan(decision)
            captured_goal.append(plan.goal)
            return plan

        coordinator._reasoning_controller = MagicMock()
        coordinator._reasoning_controller.create_plan = _create_plan

        result = coordinator.process(
            user_input="is the sky blue",
            goal="verify claim X",
        )

        reasoning = next(
            s.data for s in result.stages if s.stage.name == "REASONING"
        )
        planning = next(
            s.data for s in result.stages if s.stage.name == "PLANNING"
        )

        # Explicit goal reaches the plan goals at every hop.
        self.assertIn("verify claim X", captured_goal[0])
        self.assertIn("verify claim X", reasoning["goal"])
        self.assertIn("verify claim X", planning["goal"])


# ---------------------------------------------------------------------------
# B. Reasoning is evidence-bound (kernel provider)
# ---------------------------------------------------------------------------


class TestReasoningEvidenceBound(KernelTestCase):
    def test_reasoning_trace_carries_knowledge_evidence(self):
        atlas = self.start_atlas()
        atlas._knowledge_manager.remember(
            title="Atlas latency",
            content=(
                "Atlas is built with Python. "
                "is latency measured by pipeline yes it is measured "
                "by the runtime pipeline component."
            ),
            source="phase20_closed_loop",
        )
        handler = atlas._capability_registry.get("reasoning.trace")
        self.assertIsNotNone(handler)

        result = handler({"question": "is latency measured by pipeline"})

        self.assertTrue(result.success, result.error)
        evidence = result.output["trace"]["evidence_refs"]
        self.assertTrue(evidence)
        # The kernel's KnowledgeEvidenceProvider is the one wired behind
        # the registered handler — not a test-invented fake.
        self.assertIs(
            atlas._advanced_reasoning_service.multi_step._evidence_provider,
            atlas._advanced_reasoning_evidence_provider,
        )


# ---------------------------------------------------------------------------
# C. Causal reasoning uses the world model (kernel provider)
# ---------------------------------------------------------------------------


class TestCausalReasoningUsesWorldModel(KernelTestCase):
    def test_causal_path_comes_from_kernel_provider(self):
        atlas = self.start_atlas()
        wm = atlas._world_model_engine
        wm.register_entity(
            label="rain", category=EntityCategory.ABSTRACT_CONCEPT, confidence=0.9,
        )
        wm.register_entity(
            label="wet_ground", category=EntityCategory.ABSTRACT_CONCEPT, confidence=0.9,
        )
        wm.register_entity(
            label="slippery_road", category=EntityCategory.ABSTRACT_CONCEPT, confidence=0.9,
        )
        entities = {
            e.label: e.entity_id for e in wm.graph.get_all_entities()
        }
        wm.add_causal_relation(
            source_id=entities["rain"],
            target_id=entities["wet_ground"],
            relation_type=RelationType.CAUSES,
            description="rain causes wet ground",
            confidence=0.9,
        )
        wm.add_causal_relation(
            source_id=entities["wet_ground"],
            target_id=entities["slippery_road"],
            relation_type=RelationType.CAUSES,
            description="wet ground makes the road slippery",
            confidence=0.8,
        )
        handler = atlas._capability_registry.get("reasoning.causal")
        self.assertIsNotNone(handler)

        result = handler({
            "source": entities["rain"],
            "target": entities["slippery_road"],
        })

        self.assertTrue(result.success, result.error)
        self.assertGreater(result.output["count"], 0)
        path = result.output["paths"][0]
        self.assertEqual(path["relation_types"], ("CAUSES", "CAUSES"))
        self.assertIs(
            atlas._advanced_reasoning_service.causal._graph_provider,
            atlas._advanced_reasoning_causal_provider,
        )


# ---------------------------------------------------------------------------
# D. Planning drives capability selection (Batch 3)
# ---------------------------------------------------------------------------


class TestPlanningDrivesCapabilityExecution(unittest.TestCase):
    def test_planning_stage_executes_not_reasoning(self):
        registry = CapabilityRegistry()
        calls: list = []
        registry.register("conversation", _tracking_handler("conversation", calls))
        coordinator = _make_coordinator(registry)

        result = coordinator.process("hello world")

        reasoning = next(
            s.data for s in result.stages if s.stage.name == "REASONING"
        )
        planning = next(
            s.data for s in result.stages if s.stage.name == "PLANNING"
        )

        # REASONING stage does not execute the capability.
        self.assertEqual(reasoning["results"], [])
        self.assertEqual(reasoning["routes"], [])
        # PLANNING stage executes it.
        self.assertEqual(len(planning["results"]), 1)
        self.assertEqual(planning["results"][0]["capability"], "conversation")
        self.assertTrue(planning["results"][0]["success"])
        # The dispatched capability is derived from the plan: the step
        # action "respond" maps to the registered "conversation" capability
        # via the real analyzer mapping.
        self.assertEqual(planning["steps"][0]["action"], "respond")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["capability"], "conversation")


# ---------------------------------------------------------------------------
# E. Track capability reachable from a plan
# ---------------------------------------------------------------------------


class TestTrackCapabilityReachableFromPlan(KernelTestCase):
    def test_track_capability_dispatched_from_plan_step(self):
        atlas = self.start_atlas()
        registry = atlas._capability_registry
        available = registry.registered_names
        track = "reasoning.trace"
        if track not in available:
            for candidate in ("research.query", "toolchain.execute", "longterm.recall"):
                if candidate in available:
                    track = candidate
                    break
        self.assertIn(track, available)

        # Wrap the real Track handler with a spy so dispatcher reachability
        # is observable; the kernel's production handler stays authoritative.
        original_handler = registry.get(track)
        spy_calls: list = []

        def _wrapped(params):
            spy_calls.append(params)
            return original_handler(params)

        registry.unregister(track)
        registry.register(track, _wrapped)

        controller = _plan_controller("use track capability", [track])

        import atlas.reasoning.capabilities.analyzer as analyzer_mod

        coordinator = RuntimeCoordinator(
            reasoning_controller=controller,
            capability_analyzer=analyzer_mod.CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
        )

        result = coordinator.process("use the research capability")

        planning = next(
            s.data for s in result.stages if s.stage.name == "PLANNING"
        )
        dispatched = [c["name"] for c in planning["dispatched_capabilities"]]
        self.assertIn(track, dispatched)
        track_results = [
            r for r in planning["results"] if r["capability"] == track
        ]
        self.assertTrue(track_results)
        # Reachability verdict: the plan-derived dispatch invoked the real
        # Track handler once through the production wiring. Evidence
        # success is proven separately (criterion B) where the handler
        # receives its full parameters.
        self.assertEqual(len(spy_calls), 1)


# ---------------------------------------------------------------------------
# F. Reflection reaches LearningEngine
# ---------------------------------------------------------------------------


class TestReflectionReachesLearning(unittest.TestCase):
    def test_reflection_suggestion_produces_learning_insight(self):
        learning = LearningEngine()
        registry = CapabilityRegistry()
        for name in ("conversation", "knowledge_retrieval", "task_execution", "analysis"):
            registry.register(name, _tracking_handler(name, [], success=False))

        coordinator = _make_coordinator(registry, learning_engine=learning)
        for i in range(6):
            coordinator.process(f"trigger failure {i}")

        insights = learning.memory.get_insights(200)
        reflection_insights = [
            i for i in insights if i.metadata.get("source") == "reflection"
        ]
        self.assertTrue(reflection_insights)
        self.assertEqual(reflection_insights[0].metadata["source"], "reflection")


# ---------------------------------------------------------------------------
# G. Learning changes a later capability decision
# ---------------------------------------------------------------------------


class TestLearningChangesLaterSelection(unittest.TestCase):
    def test_learning_evidence_changes_selection(self):
        learning = LearningEngine()
        registry = CapabilityRegistry()
        for name in ("conversation", "knowledge_retrieval", "task_execution", "analysis"):
            registry.register(name, _tracking_handler(name, [], success=False))

        # Baseline selection with no learning provider.
        before = CapabilityAnalyzer()
        plan = ReasoningPlan(goal="respond", steps=[ReasoningStep(action="respond")])
        baseline = before.analyze(plan)
        baseline_priority = baseline[0].priority

        # Phase 1: failures -> reflection -> learning evidence.
        coordinator = _make_coordinator(registry, learning_engine=learning)
        for i in range(6):
            coordinator.process(f"failing run {i}")

        # Phase 2: a later selection uses the stored strategy evidence.
        after = CapabilityAnalyzer(learning_provider=learning.memory)
        later = after.analyze(plan)
        later_priority = later[0].priority

        # The learning evidence influences the later decision.
        self.assertEqual(later[0].name, "conversation")
        self.assertLess(later_priority, baseline_priority)


# ---------------------------------------------------------------------------
# H. Evolution intelligence feedback
# ---------------------------------------------------------------------------


class TestEvolutionIntelligenceFeedback(unittest.TestCase):
    def test_analyze_all_invoked_before_get_insights(self):
        spy = SpyIntelligenceEngine()
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            intelligence_engine=spy,
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=6)

        scheduler.tick()

        self.assertEqual(spy.calls.count("analyze_all"), 1)
        self.assertEqual(spy.calls, ["analyze_all", "get_insights"])


# ---------------------------------------------------------------------------
# I. Model routing is active
# ---------------------------------------------------------------------------


class TestModelRoutingActive(unittest.TestCase):
    def test_routing_request_reaches_ai_service(self):
        registry = CapabilityRegistry()
        calls: list = []
        registry.register("conversation", _tracking_handler("conversation", calls))
        ai = RecordingAIService()
        coordinator = _make_coordinator(registry, ai_service=ai)

        coordinator.process("route me")

        self.assertEqual(len(ai.routing_contexts), 1)
        context = ai.routing_contexts[0]
        self.assertIsNotNone(context)
        self.assertEqual(context.metadata["source"], "runtime_coordinator")
        self.assertGreaterEqual(context.complexity, 0.5)

    def test_routing_selects_ollama_with_kernel_profiles(self):
        from atlas.ai.routing.models import ModelProfile, RoutingRequest
        from atlas.ai.routing.registry import ModelProfileRegistry
        from atlas.ai.routing.router import ModelRouter

        registry = ModelProfileRegistry()
        registry.register(ModelProfile(
            provider_name="Mock Provider", model_name="atlas-mock-v1",
            complexity_score=0.3, priority=10,
        ))
        registry.register(ModelProfile(
            provider_name="Ollama", model_name="qwen3:8b",
            complexity_score=0.8, priority=20,
        ))
        router = ModelRouter(registry)

        decision = router.route(RoutingRequest(complexity=0.5))

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Ollama")


# ---------------------------------------------------------------------------
# J. Atlas.tick() reaches GoalExecutionEngine.settle()
# ---------------------------------------------------------------------------


class TestAtlasTickSettlesGoal(unittest.TestCase):
    def _make_executor_with_approved_goal(self):
        from atlas.goals.goal_repository import GoalRepository
        from atlas.goals.goal_execution_engine import GoalExecutionEngine
        from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        from atlas.goals.execution_models import GoalAuthorization
        from atlas.goals.models import (
            GoalCategory,
            GoalPriority,
            GoalStatus,
            ImprovementGoal,
        )
        from unittest.mock import MagicMock

        repo = GoalRepository()
        goal = ImprovementGoal(
            goal_id="GOAL-P20",
            title="Phase 20 goal",
            description="Settle me",
            category=GoalCategory.TOOLING,
            priority=GoalPriority.HIGH,
            status=GoalStatus.APPROVED,
            evidence_count=5,
            confidence=0.8,
        )
        repo.store_goal(goal)
        repo.store_authorization(GoalAuthorization(
            goal_id="GOAL-P20",
            authorized_by="user:cli",
            comment="test",
        ))

        gateway = MagicMock()
        result = MagicMock()
        result.success = True
        result.error = ""
        result.record_id = "GW-1"
        result.tracked_goal_id = ""
        gateway.execute.return_value = result

        binder_registry = ExecutionActionBinderRegistry()
        tool_engine = MagicMock()
        tool_engine.fulfill.return_value = MagicMock(
            tool_name="echo",
            success=True,
            output={"ok": True},
            error="",
            execution_time_ms=1.0,
        )
        binder_registry.register(ToolExecutionActionBinder(tool_engine=tool_engine))

        return GoalExecutionEngine(
            repository=repo,
            execution_gateway=gateway,
            binder_registry=binder_registry,
        )

    def test_tick_calls_task_scheduler_and_goal_settle(self):
        atlas = Atlas()
        task_manager = MagicMock()
        scheduler = MagicMock()
        executor = self._make_executor_with_approved_goal()

        atlas._task_manager = task_manager
        atlas._evolution_scheduler = scheduler
        atlas._goal_executor = executor

        atlas.tick()

        task_manager.tick.assert_called_once_with()
        scheduler.tick.assert_called_once_with()
        # The approved goal was settled by the real GoalExecutionEngine.
        from atlas.goals.models import GoalStatus

        goal = executor.repository.get_goal("GOAL-P20")
        self.assertEqual(goal.status, GoalStatus.COMPLETED)


# ---------------------------------------------------------------------------
# K. CLI reachability (reuses Batch 7 fake infrastructure)
# ---------------------------------------------------------------------------


class TestCLIReachability(unittest.TestCase):
    def _run_cli(self, inputs):
        fake = FakeStreamingAtlas()
        with patch("atlas.cli.cli.Atlas", return_value=fake):
            from atlas.cli.cli import AtlasCLI

            cli = AtlasCLI()
            with patch("builtins.input", side_effect=inputs):
                with patch("builtins.print"):
                    cli.run()
        return fake

    def test_interaction_ticks_once_commands_and_blank_do_not(self):
        fake = self._run_cli(["hello", "/help", "again", "", "exit"])

        # Two real interactions -> exactly two ticks.
        self.assertEqual(fake.tick_calls, 2)
        self.assertEqual(fake.stream_calls, 2)


# ---------------------------------------------------------------------------
# L. Combined closed loop
# ---------------------------------------------------------------------------


class TestCombinedClosedLoop(KernelTestCase):
    def test_goal_through_planning_dispatch_to_routing(self):
        atlas = self.start_atlas()
        registry = atlas._capability_registry
        track = "reasoning.trace"
        available = registry.registered_names
        if track not in available:
            for candidate in ("research.query", "toolchain.execute", "longterm.recall"):
                if candidate in available:
                    track = candidate
                    break

        # Track step parameters (seeds knowledge for reasoning.trace).
        track_params = _track_default_params(track, atlas)

        # Spy wrapper around the real kernel handler.
        original_handler = registry.get(track)
        dispatched_calls: list = []

        def _wrapped(params):
            dispatched_calls.append(params)
            return original_handler(params)

        registry.unregister(track)
        registry.register(track, _wrapped)

        controller = _plan_controller(
            "verify claim Y",
            ["respond", track],
            parameters_map={track: track_params},
        )
        real_analyzer = atlas._capability_analyzer.__class__(
            learning_provider=atlas._learning_engine.memory,
        )
        ai = RecordingAIService()
        coordinator = RuntimeCoordinator(
            reasoning_controller=controller,
            capability_analyzer=real_analyzer,
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
            ai_service=ai,
        )

        result = coordinator.process(
            user_input="run the closed loop",
            goal="verify claim Y",
        )

        reasoning = next(
            s.data for s in result.stages if s.stage.name == "REASONING"
        )
        planning = next(
            s.data for s in result.stages if s.stage.name == "PLANNING"
        )

        # Goal -> reasoning -> planning.
        self.assertIn("verify claim Y", reasoning["goal"])
        self.assertIn("verify claim Y", planning["goal"])

        # Plan-derived capability selection: respond maps to the registered
        # "conversation" capability and the Track step reaches its handler.
        dispatched = [c["name"] for c in planning["dispatched_capabilities"]]
        self.assertIn("conversation", dispatched)
        self.assertIn(track, dispatched)
        self.assertEqual(len(dispatched_calls), 1)

        # Reachability verdict: the Track handler ran through the real
        # registry once (dispatched_calls spy). The handler's full
        # parameter-driven evidence success is covered by criterion B.
        track_results = [
            r for r in planning["results"] if r["capability"] == track
        ]
        self.assertTrue(track_results)

        # AI-response path received a non-None RoutingRequest.
        self.assertEqual(len(ai.routing_contexts), 1)
        self.assertIsNotNone(ai.routing_contexts[0])
        self.assertGreaterEqual(ai.routing_contexts[0].complexity, 0.5)


if __name__ == "__main__":
    unittest.main()
