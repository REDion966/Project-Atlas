"""Phase 21 Batch 3 — Research Output → Outcome / Reflection / Learning Feedback.

Closes the research-output feedback boundary using the EXISTING Phase 20
closed loop. No new research-learning subsystem is introduced. These tests
prove that a research execution result becomes a normal reasoning outcome
consumed by the existing outcome → reflection → learning → capability
selection path:

  A. research.coordinate produces a normal ExecutionResult.
  B. A plan step with action="research.coordinate" reaches the real
     coordinator through the existing registry/router/dispatcher.
  C. The research ExecutionResult appears in PLANNING.results.
  D. REASONING.results stays [] and REASONING.routes stays [].
  E. The research execution result reaches the existing outcome-recording
     path (ReasoningRecorder via RuntimeCoordinator._record_outcome).
  F. A ReasoningOutcome/record exists with the research capability identity
     and the execution result information.
  G. ReflectionEngine can consume the resulting outcome using the existing
     pipeline (REFLECTION stage over recorder.recent()).
  H. LearningEngine can consume reflection output using the existing Phase 20
     path (LEARNING stage → reflection-sourced LearningInsight).
  I. A legitimate failure scenario records capability-keyed strategy evidence
     through the existing StrategyPerformance mechanism.
  J. A later CapabilityAnalyzer can consume that evidence (Phase 21 Batch 3
     bridge: plan-step action keys are consulted by the analyzer).
  K. No duplicate dispatch occurs (coordinator invoked exactly once).
  L. Public CognitionAPI decision payload remains compatible:
     decision.data["reasoning"]["results"] contains the research result.
  M. ResearchIngestBridge is wired to the governed sink and is not bypassed.
  N. No additional ResearchCoordinator, LearningEngine, LearningMemory,
     planner, router, or dispatcher instances are accidentally created.

The failure mechanism used in I/J is the same legitimate one used by the
Phase 20 Batch 4 tests: a registry handler reporting a deterministic failed
ExecutionResult. Reflection suggestions are produced by the REAL
ReflectionEngine logic — nothing is manufactured.

Kernel-level tests use isolated temporary DBs; atlas_data/ is never touched.
No Ollama / external HTTP services are required.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from atlas.cognition.api import CognitionAPI
from atlas.cognition.models import StageStatus, StageType
from atlas.evolution.models import ResearchQuery
from atlas.kernel.atlas import Atlas
from atlas.learning_engine.learning_engine import LearningEngine
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.outcomes import ReasoningRecorder
from atlas.reasoning.planning import PlanningEngine
from atlas.reasoning.reflection import ReflectionEngine
from atlas.research.capability_handlers import ResearchCapabilityFactory
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.services.cognition_service import CognitionService
from atlas.storage.advanced_reasoning_storage import AdvancedReasoningSQLiteStorage
from atlas.storage.evolution_storage import SQLiteEvolutionStorage
from atlas.storage.experience_storage import SQLiteExperienceStorage
from atlas.storage.longterm_storage import LongTermSQLiteStorage
from atlas.storage.research_storage import ResearchSQLiteStorage
from atlas.storage.toolchain_storage import ToolchainSQLiteStorage
from atlas.storage.understanding_storage import SQLiteUnderstandingStorage


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class _SpyCoordinator(ConcreteResearchCoordinator):
    """Production coordinator that records how many times run() is called."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_call_count = 0

    def run(self, query: ResearchQuery | None):
        self.run_call_count += 1
        return super().run(query)


def _plan_with_step_action(action: str) -> ReasoningPlan:
    """Build a ReasoningPlan whose single step uses the given action."""
    return ReasoningPlan(
        goal=f"{action}: test",
        steps=[
            ReasoningStep(
                description=f"Step for {action}",
                action=action,
                parameters={"action": action},
            )
        ],
    )


def _recording_plan_controller(plan: ReasoningPlan):
    """ReasoningController substitute returning a fixed plan."""
    from atlas.cognition.decision import CognitionDecision

    class _RecordingController(ReasoningController):
        def create_plan(self, decision: CognitionDecision):
            return plan

    return _RecordingController()


def _stage(result, stage_type: StageType):
    for stage in result.stages:
        if stage.stage == stage_type:
            return stage
    return None


def _wire_research_registry(coordinator) -> tuple[CapabilityRegistry, CapabilityRouter, CapabilityDispatcher]:
    """Production wiring: factory registration + coordinator registration."""
    registry = CapabilityRegistry()
    factory = ResearchCapabilityFactory()
    factory.register(registry)  # research.query / research.verify / research.summarize
    factory.register_coordinator(coordinator, registry)  # research.coordinate
    return registry, CapabilityRouter(registry), CapabilityDispatcher(registry)


def _make_runtime(
    coordinator,
    *,
    recorder=None,
    reflection=None,
    learning=None,
) -> RuntimeCoordinator:
    """Real RuntimeCoordinator over the production registry/router/dispatcher.

    Only the plan origin is a test boundary (recording controller); every
    dispatch/outcome/reflection/learning component is production.
    """
    registry, router, dispatcher = _wire_research_registry(coordinator)
    return RuntimeCoordinator(
        reasoning_controller=_recording_plan_controller(
            _plan_with_step_action("research.coordinate")
        ),
        capability_analyzer=CapabilityAnalyzer(
            learning_provider=learning.memory if learning is not None else None
        ),
        capability_registry=registry,
        capability_router=router,
        capability_dispatcher=dispatcher,
        planning_engine=PlanningEngine(),
        reflection_engine=reflection,
        reasoning_recorder=recorder,
        learning_engine=learning,
    )


_STORES = (
    SQLiteExperienceStorage,
    SQLiteUnderstandingStorage,
    SQLiteEvolutionStorage,
    ResearchSQLiteStorage,
    ToolchainSQLiteStorage,
    LongTermSQLiteStorage,
    AdvancedReasoningSQLiteStorage,
)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every SQLite-backed store the kernel touches to a single
    temporary db — the shared atlas_data runtime DB is never touched."""
    temp_dir = Path(tempfile.mkdtemp(prefix="atlas_p21b3_"))
    db_path = temp_dir / "atlas.db"
    for store in _STORES:
        monkeypatch.setattr(store, "DEFAULT_DB_PATH", db_path)
    return temp_dir


# ---------------------------------------------------------------------------
# A. research.coordinate produces a normal ExecutionResult
# ---------------------------------------------------------------------------


class TestResearchExecutionResult:
    def test_handler_produces_normal_execution_result(self):
        coordinator = ConcreteResearchCoordinator()
        registry, router, dispatcher = _wire_research_registry(coordinator)
        capability = Capability(
            name="research.coordinate",
            priority=6,
            reason="plan step",
            metadata={"action": "research.coordinate"},
        )
        result = dispatcher.dispatch([capability])[0]
        assert isinstance(result, ExecutionResult)
        assert result.capability == "research.coordinate"
        assert result.success is True
        assert "findings" in result.output
        assert "sources" in result.output
        assert "confidence" in result.output
        assert "query_id" in result.output


# ---------------------------------------------------------------------------
# B/C/D/K. Plan step → registry → router → dispatcher → coordinator → PLANNING
# ---------------------------------------------------------------------------


class TestPlanReachability:
    def test_plan_step_reaches_coordinator_through_production_path(self):
        coordinator = _SpyCoordinator()
        recorder = ReasoningRecorder()
        runtime = _make_runtime(coordinator, recorder=recorder)
        result = runtime.process("Research the atlas")

        reasoning_stage = _stage(result, StageType.REASONING)
        planning_stage = _stage(result, StageType.PLANNING)

        # B: the plan step reached the real coordinator once through the
        # production registry/router/dispatcher path.
        assert coordinator.run_call_count == 1
        # K: a single plan step → a single dispatch → a single run.
        assert coordinator.run_call_count == 1

        # C: the research ExecutionResult appears in PLANNING.results.
        assert planning_stage is not None
        assert planning_stage.status == StageStatus.SUCCESS
        planning_results = planning_stage.data["results"]
        assert len(planning_results) == 1
        assert planning_results[0]["capability"] == "research.coordinate"
        assert planning_results[0]["success"] is True
        assert "findings" in planning_results[0]["output"]
        assert [c["name"] for c in planning_stage.data["dispatched_capabilities"]] == [
            "research.coordinate"
        ]

        # D: REASONING stays dispatch-free.
        assert reasoning_stage is not None
        assert reasoning_stage.data["results"] == []
        assert reasoning_stage.data["routes"] == []

    def test_no_duplicate_registration(self):
        coordinator = ConcreteResearchCoordinator()
        registry, _, _ = _wire_research_registry(coordinator)
        assert registry.registered_names.count("research.coordinate") == 1


# ---------------------------------------------------------------------------
# E/F. Outcome recording
# ---------------------------------------------------------------------------


class TestOutcomeRecording:
    def test_research_outcome_recorded_with_capability_identity(self):
        coordinator = _SpyCoordinator()
        recorder = ReasoningRecorder()
        runtime = _make_runtime(coordinator, recorder=recorder)
        runtime.process("Research the atlas")

        # E: the research execution result reached the outcome-recording path.
        assert recorder.count == 1
        outcome = recorder.latest()
        assert outcome is not None

        # F: outcome carries the research capability identity + result info.
        assert outcome.metadata.get("source") == "runtime_coordinator"
        assert outcome.results[0]["capability"] == "research.coordinate"
        assert outcome.results[0]["success"] is True
        assert "findings" in outcome.results[0]["output"]
        assert "confidence" in outcome.results[0]["output"]
        assert outcome.capabilities[0]["name"] == "research.coordinate"
        assert outcome.success is True


# ---------------------------------------------------------------------------
# G/H. Reflection + Learning consume research outcomes via the pipeline
# ---------------------------------------------------------------------------


class TestReflectionAndLearning:
    def test_successful_research_flows_through_reflection_and_learning(self):
        coordinator = ConcreteResearchCoordinator()
        recorder = ReasoningRecorder()
        reflection = ReflectionEngine()
        learning = LearningEngine()
        runtime = _make_runtime(
            coordinator,
            recorder=recorder,
            reflection=reflection,
            learning=learning,
        )

        # Repeated-routing reflection needs >= 5 outcomes. Six successful
        # research-coordinate executions produce a real repeated_routing
        # suggestion (research.coordinate used in 6/6 outcomes).
        final_result = None
        for i in range(6):
            final_result = runtime.process(f"research run {i}")

        assert recorder.count == 6
        for outcome in recorder.recent(6):
            assert outcome.results[0]["capability"] == "research.coordinate"
            assert outcome.results[0]["success"] is True

        # G: the REFLECTION stage consumed the outcomes through the pipeline.
        reflection_stage = _stage(final_result, StageType.REFLECTION)
        assert reflection_stage is not None
        assert reflection_stage.status == StageStatus.SUCCESS
        assert reflection_stage.data["suggestions_count"] >= 1
        suggestions = reflection.analyze(recorder.recent(20))
        assert any(s.pattern == "repeated_routing" for s in suggestions)

        # H: the LEARNING stage consumed reflection output via the existing
        # Phase 20 path (reflection-sourced LearningInsight in LearningMemory).
        learning_stage = _stage(final_result, StageType.LEARNING)
        assert learning_stage is not None
        assert learning_stage.status == StageStatus.SUCCESS
        assert learning_stage.data["insights_count"] >= 1
        reflection_insights = [
            i
            for i in learning.memory.get_insights(200)
            if i.metadata.get("source") == "reflection"
        ]
        assert reflection_insights
        assert any(
            i.title == "Reflection: repeated_routing" for i in reflection_insights
        )


# ---------------------------------------------------------------------------
# I/J. Legitimate failure → capability-keyed evidence → later selection
# ---------------------------------------------------------------------------


def _failing_research_handler(params: dict) -> ExecutionResult:
    """Legitimate deterministic failure (Phase 20 Batch 4 mechanism):
    a registry handler that reports a failed ExecutionResult."""
    return ExecutionResult(
        capability="research.coordinate",
        success=False,
        error="phase21 test regression failure",
        output={"received": params},
    )


def _make_failing_runtime(learning) -> RuntimeCoordinator:
    registry = CapabilityRegistry()
    registry.register("research.coordinate", _failing_research_handler)
    return RuntimeCoordinator(
        reasoning_controller=_recording_plan_controller(
            _plan_with_step_action("research.coordinate")
        ),
        capability_analyzer=CapabilityAnalyzer(
            learning_provider=learning.memory,
        ),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        reflection_engine=ReflectionEngine(),
        reasoning_recorder=ReasoningRecorder(),
        learning_engine=learning,
    )


class TestFailureLearningEvidence:
    def test_failure_evidence_recorded_for_research_capability(self):
        learning = LearningEngine()
        runtime = _make_failing_runtime(learning)
        for i in range(6):
            runtime.process(f"failing research run {i}")

        # I: reflection-derived learning evidence is recorded through the
        # existing capability-keyed StrategyPerformance mechanism.
        performance = learning.memory.get_strategy_by_name("research.coordinate")
        assert performance is not None
        assert performance.total_uses >= 6
        assert performance.success_rate == 0.0

    def test_later_analyzer_consumes_research_evidence(self):
        learning = LearningEngine()
        runtime = _make_failing_runtime(learning)
        for i in range(6):
            runtime.process(f"failing research run {i}")

        performance = learning.memory.get_strategy_by_name("research.coordinate")
        assert performance is not None
        assert performance.total_uses >= 6

        # Baseline: a fresh analyzer with no provider keeps priority 5.
        baseline = CapabilityAnalyzer().analyze(
            _plan_with_step_action("research.coordinate")
        )
        assert baseline[0].name == "general"
        assert baseline[0].priority == 5

        # J: a later CapabilityAnalyzer consuming the same LearningMemory
        # deprioritizes the research action from the failure evidence
        # (bounded deterministic adjustment, semantics unchanged).
        later = CapabilityAnalyzer(learning_provider=learning.memory).analyze(
            _plan_with_step_action("research.coordinate")
        )
        assert later[0].name == "general"
        assert later[0].priority < baseline[0].priority


# ---------------------------------------------------------------------------
# L. Public CognitionAPI payload compatibility
# ---------------------------------------------------------------------------


class TestPublicPayload:
    def test_decision_payload_reasoning_results_contains_research_result(self):
        coordinator = ConcreteResearchCoordinator()
        registry, router, dispatcher = _wire_research_registry(coordinator)
        runtime = RuntimeCoordinator(
            reasoning_controller=_recording_plan_controller(
                _plan_with_step_action("research.coordinate")
            ),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=router,
            capability_dispatcher=dispatcher,
            planning_engine=PlanningEngine(),
        )
        service = CognitionService(runtime_coordinator=runtime)
        service.start()
        api = CognitionAPI(cognition_service=service)

        decision = api.process("Research the atlas")

        assert "reasoning" in decision.data
        results = decision.data["reasoning"]["results"]
        assert results, "executed results must be exposed on the public payload"
        assert results[0]["capability"] == "research.coordinate"
        assert results[0]["success"] is True
        assert "findings" in results[0]["output"]
        service.stop()


# ---------------------------------------------------------------------------
# M. ResearchIngestBridge is wired to the governed sink
# ---------------------------------------------------------------------------


class TestIngestIsGoverned:
    def test_kernel_ingest_bridge_wired_not_bypassed(self, isolated_env):
        atlas = Atlas()
        atlas.start()
        try:
            bridge = atlas._research_ingest_bridge
            coordinator = atlas.research_coordinator
            assert bridge is not None
            assert coordinator is not None
            # The coordinator is wired to the governed bridge; the bridge now
            # holds the kernel's single GovernanceIngestSink (post-governed-
            # sink), so ingestion is routed through the governed evolution
            # path rather than failing closed for lack of a sink (§19).
            assert coordinator.ingest is bridge
            assert bridge.has_sink is True
            assert bridge._sink is atlas._governed_ingest_sink

            # A research run completes normally while the bridge stays
            # governed (never bypasses governance into KnowledgeManager
            # directly).
            result = coordinator.run(
                ResearchQuery(
                    query_id="q-feedback",
                    question="Atlas research feedback?",
                    context={"sources": []},
                )
            )
            assert result.query_id == "q-feedback"
            assert bridge.has_sink is True
            assert bridge._sink is atlas._governed_ingest_sink
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# N. No accidental duplicate instances
# ---------------------------------------------------------------------------


class TestNoDuplicateInstances:
    def test_kernel_single_coordinator_learning_and_execution_instances(self, isolated_env):
        atlas = Atlas()
        atlas.start()
        try:
            research_factory = atlas._research_factory
            learning_engine = atlas._learning_engine
            capability_analyzer = atlas._capability_analyzer
            registry = atlas._capability_registry
            router = atlas._capability_router
            dispatcher = atlas._capability_dispatcher
            runtime = atlas._runtime_coordinator
            planning_engine = atlas._planning_engine
            coordinator = atlas.research_coordinator
            assert research_factory is not None
            assert learning_engine is not None
            assert capability_analyzer is not None
            assert registry is not None
            assert router is not None
            assert dispatcher is not None
            assert runtime is not None
            assert planning_engine is not None
            assert coordinator is not None

            # Exactly one coordinator: the kernel-owned instance is the one
            # bound into the research factory (and therefore the registry).
            assert research_factory.coordinator is coordinator
            assert research_factory.coordinator is atlas._research_coordinator

            # Exactly one LearningEngine / LearningMemory: the analyzer's
            # learning provider wraps the same kernel-owned memory store.
            analyzer_provider = capability_analyzer._learning_provider
            assert analyzer_provider is not None
            assert analyzer_provider._store is learning_engine.memory

            # Exactly one planner / router / dispatcher, all sharing the one
            # registry and injected into the RuntimeCoordinator.
            assert router.registry is registry
            assert dispatcher.registry is registry
            assert runtime._planning_engine is planning_engine
            assert runtime._capability_router is router
            assert runtime._capability_dispatcher is dispatcher
            assert runtime._capability_registry is registry
            assert runtime._capability_analyzer is capability_analyzer

            # research.coordinate is registered exactly once.
            assert registry.registered_names.count("research.coordinate") == 1
        finally:
            atlas.shutdown()
