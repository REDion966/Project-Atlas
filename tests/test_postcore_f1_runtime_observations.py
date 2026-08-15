"""Post-Core F1 — Runtime Observation Coverage.

Verifies the existing SelfObservationEngine producers (health, reasoning,
tool, memory) now receive real runtime evidence through the F1 collector
wired into RuntimeCoordinator's EVOLUTION_OBSERVATION stage, while the
runtime-metrics producer and the 15-stage pipeline remain unchanged.
"""

from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.models import ObservationCategory
from atlas.evolution.runtime_observations import collect_runtime_observations
from atlas.evolution.self_observation import SelfObservationEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator


# ---------------------------------------------------------------------------
# Fakes (small seams)
# ---------------------------------------------------------------------------


class StubMetrics:
    def __init__(self, failed_count: int = 0) -> None:
        self.failed_count = failed_count


class StubMemory:
    def __init__(self, results: list | None = None) -> None:
        self._results = results or []

    def search(self, keyword: str):
        return list(self._results)

    def store(self, content: str, source: str = "") -> None:
        return None


class StubEntry:
    def __init__(self, title: str = "mem") -> None:
        self.title = title


class BrokenToolEngine(SelfObservationEngine):
    def observe_tool_usage(self, *args, **kwargs):
        raise RuntimeError("tool producer offline")


class State:
    """Minimal CognitionState-like carrier for the evidence the F1
    collector reads (reasoning_result / tool_result / memories)."""

    def __init__(
        self,
        reasoning: bool = False,
        tool: bool = False,
        memory: bool = False,
    ) -> None:
        self.reasoning_result = None
        self.tool_result = None
        self.memories = None
        self.evolution_observations = []
        if reasoning:
            self.reasoning_result = {
                "capabilities": [
                    {"name": "conversation", "priority": 5, "reason": "r"},
                    {"name": "research.query", "priority": 4, "reason": "r"},
                ],
                "routes": [],
                "results": [
                    {"capability": "conversation", "success": True, "output": {}, "error": ""},
                    {"capability": "research.query", "success": False, "output": {}, "error": "x"},
                ],
            }
        if tool:
            self.tool_result = {
                "tool_name": "read_file",
                "success": False,
                "output": {},
                "error": "boom",
                "execution_time_ms": 3.0,
            }
        if memory:
            self.memories = [StubEntry("one"), StubEntry("two")]


def make_state(reasoning=False, tool=False, memory=False) -> State:
    return State(reasoning=reasoning, tool=tool, memory=memory)


# ---------------------------------------------------------------------------
# 1. Existing runtime-metrics producer preserved
# ---------------------------------------------------------------------------


class TestRuntimeMetricsPreserved:
    def test_runtime_metrics_still_produced(self):
        engine = SelfObservationEngine()
        observations, skipped = collect_runtime_observations(
            engine, None, StubMetrics(failed_count=1), 12.5
        )
        assert ObservationCategory.RUNTIME_METRICS in {o.category for o in observations}
        assert "runtime_metrics" not in skipped

    def test_error_count_propagates(self):
        engine = SelfObservationEngine()
        observations, _ = collect_runtime_observations(engine, None, StubMetrics(failed_count=2), 0.0)
        runtime_obs = next(
            o for o in observations if o.category == ObservationCategory.RUNTIME_METRICS
        )
        assert runtime_obs.value["error_count"] == 2


# ---------------------------------------------------------------------------
# 2-5. health / reasoning / tool / memory producers reached
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_empty_run_produces_runtime_and_health_only(self):
        engine = SelfObservationEngine()
        observations, skipped = collect_runtime_observations(
            engine, None, StubMetrics(), 1.0
        )
        assert {o.category for o in observations} == {
            ObservationCategory.RUNTIME_METRICS,
            ObservationCategory.SYSTEM_HEALTH,
        }
        assert set(skipped) == {"reasoning", "tool", "memory"}

    def test_health_degraded_when_stages_failed(self):
        engine = SelfObservationEngine()
        observations, _ = collect_runtime_observations(
            engine, make_state(reasoning=True, tool=True, memory=True),
            StubMetrics(failed_count=1), 1.0,
        )
        health = next(o for o in observations if o.category == ObservationCategory.SYSTEM_HEALTH)
        assert health.value["status"] == "degraded"

    def test_reasoning_producer_reached(self):
        engine = SelfObservationEngine()
        observations, skipped = collect_runtime_observations(
            engine, make_state(reasoning=True), StubMetrics(), 1.0
        )
        assert "reasoning" not in skipped
        reasoning = next(o for o in observations if o.category == ObservationCategory.REASONING_QUALITY)
        assert reasoning.value["success_rate"] == 0.5
        assert reasoning.value["total_outcomes"] == 2

    def test_tool_producer_reached(self):
        engine = SelfObservationEngine()
        observations, skipped = collect_runtime_observations(
            engine, make_state(tool=True), StubMetrics(), 1.0
        )
        assert "tool" not in skipped
        tool = next(o for o in observations if o.category == ObservationCategory.TOOL_USAGE)
        assert tool.value["tool_name"] == "read_file"
        assert tool.value["success_rate_percent"] == 0.0

    def test_memory_producer_reached(self):
        engine = SelfObservationEngine()
        observations, skipped = collect_runtime_observations(
            engine, make_state(memory=True), StubMetrics(), 1.0
        )
        assert "memory" not in skipped
        memory = next(o for o in observations if o.category == ObservationCategory.MEMORY_QUALITY)
        assert memory.value["total_memories"] == 2


# ---------------------------------------------------------------------------
# 6-7. Multi-category + deterministic ordering
# ---------------------------------------------------------------------------


class TestMultiCategoryAndDeterminism:
    def test_full_run_produces_all_five_categories_in_order(self):
        engine = SelfObservationEngine()
        observations, skipped = collect_runtime_observations(
            engine, make_state(reasoning=True, tool=True, memory=True),
            StubMetrics(), 1.0,
        )
        assert [o.category for o in observations] == [
            ObservationCategory.RUNTIME_METRICS,
            ObservationCategory.SYSTEM_HEALTH,
            ObservationCategory.REASONING_QUALITY,
            ObservationCategory.TOOL_USAGE,
            ObservationCategory.MEMORY_QUALITY,
        ]
        assert skipped == []

    def test_deterministic_across_runs(self):
        state = make_state(reasoning=True, tool=True, memory=True)
        engine_a = SelfObservationEngine()
        engine_b = SelfObservationEngine()
        a, _ = collect_runtime_observations(engine_a, state, StubMetrics(), 1.0)
        b, _ = collect_runtime_observations(engine_b, state, StubMetrics(), 1.0)
        assert [o.category for o in a] == [o.category for o in b]
        assert engine_a.observation_count == engine_b.observation_count == 5


# ---------------------------------------------------------------------------
# 8-9. Failure isolation
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_broken_tool_producer_degrades_only_tool(self):
        engine = BrokenToolEngine()
        observations, skipped = collect_runtime_observations(
            engine, make_state(reasoning=True, tool=True, memory=True),
            StubMetrics(), 1.0,
        )
        categories = {o.category for o in observations}
        assert "tool" in skipped
        assert ObservationCategory.TOOL_USAGE not in categories
        assert ObservationCategory.RUNTIME_METRICS in categories
        assert ObservationCategory.REASONING_QUALITY in categories
        assert ObservationCategory.MEMORY_QUALITY in categories


# ---------------------------------------------------------------------------
# 10. Planner compatibility
# ---------------------------------------------------------------------------


class TestPlannerCompatibility:
    def test_planner_detects_tool_weakness_from_richer_observations(self):
        engine = SelfObservationEngine()
        collect_runtime_observations(
            engine, make_state(reasoning=True, tool=True, memory=True),
            StubMetrics(), 1.0,
        )
        weaknesses = ImprovementPlanner().detect_weaknesses(engine.recent_observations(n=100))
        assert "tools" in {w.area for w in weaknesses}


# ---------------------------------------------------------------------------
# 11-12. Pipeline integrity + real process path
# ---------------------------------------------------------------------------


class TestPipelineIntegrity:
    def test_fifteen_stage_order_unchanged(self):
        from atlas.cognition.models import StageType

        coordinator = RuntimeCoordinator()
        names = [stage for stage, _ in coordinator._build_stage_definitions()]
        assert names == [
            StageType.CONVERSATION_CONTEXT,
            StageType.MEMORY_RETRIEVAL,
            StageType.KNOWLEDGE_RETRIEVAL,
            StageType.UNDERSTANDING,
            StageType.WORLD_MODEL,
            StageType.REASONING,
            StageType.PLANNING,
            StageType.TOOL_DECISION,
            StageType.TOOL_EXECUTION,
            StageType.AI_RESPONSE,
            StageType.REFLECTION,
            StageType.LEARNING,
            StageType.EVOLUTION_OBSERVATION,
            StageType.GOAL_INTELLIGENCE,
            StageType.MEMORY_STORAGE,
        ]
        assert len(names) == 15

    def test_process_reaches_observation_producers(self):
        from atlas.cognition.models import StageStatus, StageType

        engine = SelfObservationEngine()
        coordinator = RuntimeCoordinator(
            evolution_observation_engine=engine,
            memory_service=StubMemory([StubEntry("one"), StubEntry("two")]),
        )
        result = coordinator.process("hello")
        evolution = next(
            s for s in result.stages if s.stage == StageType.EVOLUTION_OBSERVATION
        )
        assert evolution.status == StageStatus.SUCCESS
        assert evolution.data["observations_count"] >= 2
        assert engine.observation_count >= 2

    def test_pipeline_returns_result_when_collector_raises(self):
        # An unhandled exception inside the F1 collector is contained by the
        # coordinator's existing per-stage guard: the EVOLUTION_OBSERVATION
        # stage is recorded FAILED and the caller still receives a
        # PipelineResult (no uncaught exception propagates). Category-level
        # failures never reach this path — the collector absorbs them (see
        # TestFailureIsolation).
        from atlas.cognition.models import StageStatus, StageType

        import atlas.runtime.runtime_coordinator as rc

        engine = SelfObservationEngine()
        coordinator = RuntimeCoordinator(evolution_observation_engine=engine)
        original = rc.collect_runtime_observations

        def boom(*args, **kwargs):
            raise RuntimeError("observation collector exploded")

        rc.collect_runtime_observations = boom
        try:
            result = coordinator.process("hello")
        finally:
            rc.collect_runtime_observations = original

        assert result is not None
        evolution = next(
            s for s in result.stages if s.stage == StageType.EVOLUTION_OBSERVATION
        )
        assert evolution.status == StageStatus.FAILED
        assert "observation collector exploded" in evolution.error
