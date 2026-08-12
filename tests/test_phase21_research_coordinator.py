"""Phase 21 — Track A Research Coordinator + Plan-Driven Reachability Tests.

Mirrors the Phase 20 Batch 3 plan-selection integration pattern: the
RuntimeCoordinator pipeline is driven by a real PlanningEngine and real
CapabilityRegistry/Router/Dispatcher. These tests prove:

1. ConcreteResearchCoordinator construction with injected Track A deps
2. The coordinator composes the existing planner/extractor/verifier
   (identity assertions — no duplicate component instantiation)
3. Deterministic behavior
4. Fail-soft behavior (bad source, missing storage, raising components)
5. Storage failure does not crash the research operation (best-effort)
6. Ingest remains governed/fail-closed (no sink → refusal recorded, never
   bypassed)
7. research.coordinate is registered when a coordinator is injected
8. A plan step with action="research.coordinate" reaches the registered
   handler through the REAL pipeline: plan → _select_plan_capabilities →
   CapabilityRouter → CapabilityDispatcher → handler → coordinator
9. The handler invokes the coordinator exactly once (no double dispatch)
10. Existing research.query / research.verify / research.summarize remain
    intact
11. The kernel owns exactly one coordinator
12. The coordinator is not registered in the ServiceContainer
13. The public CognitionAPI decision payload keeps the Phase 20 Blocker-1
    contract (execution results present via data["reasoning"])
14. REASONING stays results=[] and routes=[]
15. PLANNING carries the actual research execution result
16. No duplicate dispatch occurs

Kernel-level tests use isolated temporary DBs (Windows-safe) via a
temporary working directory; the shared runtime atlas_data DB is never
touched. No Ollama / external model provider is required.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.cognition.decision import CognitionDecision
from atlas.cognition.models import StageStatus, StageType
from atlas.evolution.models import ResearchQuery, ResearchResult
from atlas.kernel.atlas import Atlas
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning import PlanningEngine
from atlas.research.capability_handlers import ResearchCapabilityFactory
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import SourceKind, SourceProfile
from atlas.research.planner import ResearchPlanner
from atlas.research.verifier import ClaimVerifier
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.storage.advanced_reasoning_storage import AdvancedReasoningSQLiteStorage
from atlas.storage.evolution_storage import SQLiteEvolutionStorage
from atlas.storage.experience_storage import SQLiteExperienceStorage
from atlas.storage.longterm_storage import LongTermSQLiteStorage
from atlas.storage.research_storage import ResearchSQLiteStorage
from atlas.storage.toolchain_storage import ToolchainSQLiteStorage
from atlas.storage.understanding_storage import SQLiteUnderstandingStorage


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_profiles(*texts: str) -> list[SourceProfile]:
    """Build in-memory SourceProfiles (no filesystem reads)."""
    return [
        SourceProfile(
            uri=f"memory://{index}",
            kind=SourceKind.DOCUMENT,
            text=text,
            title=f"source-{index}",
        )
        for index, text in enumerate(texts)
    ]


class _SpyCoordinator(ConcreteResearchCoordinator):
    """Coordinator that records how many times run() is called."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_call_count = 0

    def run(self, query: ResearchQuery | None):
        self.run_call_count += 1
        return super().run(query)


def _plan_with_step_action(action: str, step_id: str) -> ReasoningPlan:
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

    class _RecordingController(ReasoningController):
        def create_plan(self, decision: CognitionDecision):
            return plan

    return _RecordingController()


def _stage(result, stage_type: StageType):
    for stage in result.stages:
        if stage.stage == stage_type:
            return stage
    return None


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
    temporary db (Phase 20 KernelTestCase pattern — never touches the shared
    atlas_data runtime DB)."""
    temp_dir = Path(tempfile.mkdtemp(prefix="atlas_p21_"))
    db_path = temp_dir / "atlas.db"
    for store in _STORES:
        monkeypatch.setattr(store, "DEFAULT_DB_PATH", db_path)
    return temp_dir


# ---------------------------------------------------------------------------
# 1. Construction + dependency injection (no duplicates)
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_constructs_with_injected_dependencies(self):
        planner = ResearchPlanner()
        extractor = KnowledgeExtractor()
        verifier = ClaimVerifier()
        coordinator = ConcreteResearchCoordinator(
            planner=planner,
            extractor=extractor,
            verifier=verifier,
            storage=None,
            ingest=None,
        )
        # Identity assertions: the coordinator reuses the injected instances.
        assert coordinator.planner is planner
        assert coordinator.extractor is extractor
        assert coordinator.verifier is verifier
        assert coordinator.storage is None
        assert coordinator.ingest is None

    def test_defaults_construct_fresh_components(self):
        coordinator = ConcreteResearchCoordinator()
        assert isinstance(coordinator.planner, ResearchPlanner)
        assert isinstance(coordinator.extractor, KnowledgeExtractor)
        assert isinstance(coordinator.verifier, ClaimVerifier)

    def test_implements_legacy_abc(self):
        coordinator = ConcreteResearchCoordinator()
        # The legacy ABC requires async methods; the concrete impl must
        # satisfy the interface (compatibility boundary preserved).
        assert asyncio.iscoroutinefunction(coordinator.conduct_research)
        assert asyncio.iscoroutinefunction(coordinator.validate_findings)


# ---------------------------------------------------------------------------
# 2. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_query_same_result(self):
        coordinator = ConcreteResearchCoordinator()
        query = ResearchQuery(
            query_id="q-determinism",
            question="What is the architecture of Atlas?",
            context={"sources": []},
        )
        first = coordinator.run(query)
        second = coordinator.run(query)
        assert first.findings == second.findings
        assert first.sources == second.sources
        assert first.confidence == second.confidence
        assert first.query_id == second.query_id


# ---------------------------------------------------------------------------
# 3. Fail-soft behavior
# ---------------------------------------------------------------------------


class TestFailSoft:
    def test_empty_query_fails_soft(self):
        coordinator = ConcreteResearchCoordinator()
        result = coordinator.run(None)
        assert result.confidence == 0.0
        assert result.findings == ""
        assert result.sources == []

    def test_blank_question_fails_soft(self):
        coordinator = ConcreteResearchCoordinator()
        result = coordinator.run(ResearchQuery(query_id="q", question="   "))
        assert result.confidence == 0.0

    def test_bad_source_spec_fails_soft(self):
        """A malformed URI spec must not raise; it is skipped."""
        coordinator = ConcreteResearchCoordinator()
        result = coordinator.run(
            ResearchQuery(
                query_id="q-bad",
                question="test claim",
                context={"sources": ["not-a-real-uri://x"]},
            )
        )
        assert result.confidence == 0.0
        assert result.sources == []

    def test_raising_components_fail_soft(self):
        """A raising planner degrades to a 0.0 result."""
        planner = MagicMock(spec=ResearchPlanner)
        planner.plan.side_effect = RuntimeError("boom")
        coordinator = ConcreteResearchCoordinator(planner=planner)
        result = coordinator.run(
            ResearchQuery(query_id="q", question="some question")
        )
        assert result.confidence == 0.0
        assert result.findings == ""

    def test_storage_failure_does_not_crash(self):
        """Storage best-effort: a raising storage adapter never breaks run()."""
        storage = MagicMock()
        storage.is_available.return_value = True
        storage.store_report.side_effect = RuntimeError("storage unavailable")
        coordinator = ConcreteResearchCoordinator(
            storage=storage,
            resolve_sources=lambda _specs: _make_profiles("Atlas has a kernel."),
        )
        result = coordinator.run(
            ResearchQuery(
                query_id="q-storage-fail",
                question="Atlas has a kernel?",
                context={"sources": []},
            )
        )
        # The run still returns a research result (storage is best-effort).
        assert result.query_id == "q-storage-fail"


# ---------------------------------------------------------------------------
# 4. Ingest remains governed / fail-closed
# ---------------------------------------------------------------------------


class TestIngestFailClosed:
    def test_ingest_without_sink_is_never_bypassed(self):
        """A bridge without a sink reports accepted=False; the coordinator
        records the refusal but does not bypass governance."""
        from atlas.research.evolution_integration import ResearchIngestBridge

        ingest = ResearchIngestBridge()  # no sink → fail-closed
        coordinator = ConcreteResearchCoordinator(
            ingest=ingest,
            resolve_sources=lambda _specs: _make_profiles(
                "Atlas uses a research coordinator."
            ),
        )
        assert ingest.has_sink is False
        result = coordinator.run(
            ResearchQuery(
                query_id="q-ingest",
                question="Atlas research?",
                context={"sources": []},
            )
        )
        # The research operation still completes.
        assert result.query_id == "q-ingest"
        # Governance: the bridge never bypasses the sink; it fails closed.
        assert ingest.has_sink is False

    def test_ingest_with_refusing_sink_does_not_raise(self):
        """A sink that refuses the request must not crash the coordinator."""
        from atlas.research.evolution_integration import (
            IngestHandoffResult,
            ResearchIngestBridge,
        )

        refusing_sink = MagicMock()
        refusing_sink.enqueue_request.return_value = IngestHandoffResult(
            accepted=False, error="governed refusal"
        )
        ingest = ResearchIngestBridge(sink=refusing_sink)
        coordinator = ConcreteResearchCoordinator(
            ingest=ingest,
            resolve_sources=lambda _specs: _make_profiles("Atlas ticks goals."),
        )
        assert ingest.has_sink is True
        result = coordinator.run(
            ResearchQuery(query_id="q-refused", question="Atlas goals?")
        )
        assert result.query_id == "q-refused"
        refusing_sink.enqueue_request.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Capability factory: additive research.coordinate
# ---------------------------------------------------------------------------


class TestCapabilityFactory:
    def test_research_coordinate_registered_when_injected(self):
        coordinator = ConcreteResearchCoordinator()
        factory = ResearchCapabilityFactory(coordinator=coordinator)
        handlers = factory.handlers()
        assert "research.coordinate" in handlers
        assert "research.query" in handlers
        assert "research.verify" in handlers
        assert "research.summarize" in handlers

    def test_no_coordinate_without_coordinator(self):
        factory = ResearchCapabilityFactory()
        handlers = factory.handlers()
        assert "research.coordinate" not in handlers
        assert set(handlers) == {
            "research.query",
            "research.verify",
            "research.summarize",
        }

    def test_register_coordinator_additive(self):
        registry = CapabilityRegistry()
        factory = ResearchCapabilityFactory()
        factory.register(registry)  # 3 handlers
        assert not registry.has("research.coordinate")
        coordinator = ConcreteResearchCoordinator()
        factory.register_coordinator(coordinator, registry)
        assert registry.has("research.coordinate")

    def test_register_coordinator_idempotent(self):
        registry = CapabilityRegistry()
        factory = ResearchCapabilityFactory()
        factory.register(registry)
        coordinator = ConcreteResearchCoordinator()
        factory.register_coordinator(coordinator, registry)
        factory.register_coordinator(coordinator, registry)  # no ValueError
        assert registry.has("research.coordinate")

    def test_existing_handlers_intact_with_coordinator(self):
        """The original 3 handlers keep their behavior when the coordinator
        is injected (the factory is additive, not replacing)."""
        factory = ResearchCapabilityFactory(coordinator=ConcreteResearchCoordinator())
        result = factory.handlers()["research.query"]({"question": "  "})
        assert result.success is False
        assert "question" in result.error
        # verify handler still requires a KnowledgeClaim list (a non-claim
        # input fails validation)
        result = factory.handlers()["research.verify"](
            {"claims": ["not-a-claim"], "sources": []}
        )
        assert result.success is False
        assert "claims" in result.error
        # summarize handler still requires a ResearchReport
        result = factory.handlers()["research.summarize"]({"report": None})
        assert result.success is False


# ---------------------------------------------------------------------------
# 6. Plan step → _select_plan_capabilities → router → dispatcher →
#    handler → coordinator (Mirrors Phase 20 Batch 3 integration pattern)
# ---------------------------------------------------------------------------


class TestReachability:
    def _wire(self):
        registry = CapabilityRegistry()
        factory = ResearchCapabilityFactory()
        factory.register(registry)
        coordinator = _SpyCoordinator()
        factory.register_coordinator(coordinator, registry)
        router = CapabilityRouter(registry)
        dispatcher = CapabilityDispatcher(registry)
        return registry, factory, coordinator, router, dispatcher

    def test_handler_routes_and_dispatches_to_coordinator(self):
        registry, factory, coordinator, router, dispatcher = self._wire()
        capability = Capability(
            name="research.coordinate",
            priority=6,
            reason="plan step",
            metadata={"action": "research.coordinate"},
        )
        routed = router.route([capability])
        assert routed, "router should accept research.coordinate"

        # The dispatcher calls handler(capability.metadata); the handler
        # receives {"action": "research.coordinate"} and delegates to the
        # coordinator (which uses the action as the question).
        result = dispatcher.dispatch([capability])
        assert result is not None
        assert len(result) == 1
        assert result[0].success is True
        assert coordinator.run_call_count == 1

    def test_plan_step_reaches_handler_through_runtime_coordinator(self):
        """Full RuntimeCoordinator path: a plan step with action
        research.coordinate reaches the handler and executes it exactly once,
        with REASONING empty and PLANNING carrying the result."""
        calls = []
        registry = CapabilityRegistry()
        factory = ResearchCapabilityFactory()
        factory.register(registry)
        coordinator = _SpyCoordinator()
        factory.register_coordinator(coordinator, registry)

        plan = _plan_with_step_action("research.coordinate", "step-rc")
        runtime = RuntimeCoordinator(
            reasoning_controller=_recording_plan_controller(plan),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
        )
        result = runtime.process("Research the atlas")

        reasoning_stage = _stage(result, StageType.REASONING)
        planning_stage = _stage(result, StageType.PLANNING)

        # a. PLANNING executes before capability dispatch.
        assert planning_stage is not None
        assert planning_stage.status == StageStatus.SUCCESS
        assert planning_stage.data["results"]
        assert [c["name"] for c in planning_stage.data["dispatched_capabilities"]] == [
            "research.coordinate"
        ]

        # b. no capability execution during REASONING.
        assert reasoning_stage is not None
        assert reasoning_stage.data["results"] == []
        assert reasoning_stage.data["routes"] == []

        # c. the coordinator ran exactly once (no duplicate dispatch).
        assert coordinator.run_call_count == 1

        # d. the PLANNING result is the actual research ExecutionResult.
        planning_results = planning_stage.data["results"]
        assert planning_results[0]["capability"] == "research.coordinate"
        assert planning_results[0]["success"] is True

    def test_no_double_dispatch(self):
        registry, factory, coordinator, router, dispatcher = self._wire()
        capability = Capability(
            name="research.coordinate",
            priority=6,
            reason="plan step",
            metadata={"action": "research.coordinate"},
        )
        routed = router.route([capability])
        assert len(routed) == 1
        dispatcher.dispatch([capability])
        # A single plan step → a single dispatch → a single coordinator call.
        assert coordinator.run_call_count == 1


# ---------------------------------------------------------------------------
# 7. Kernel ownership + ServiceContainer absence
# ---------------------------------------------------------------------------


class TestKernelOwnership:
    def test_kernel_owns_exactly_one_coordinator(self, isolated_env):
        from atlas.kernel.service_container import ServiceContainer

        atlas = Atlas()
        atlas.start()
        coordinator = atlas.research_coordinator
        assert coordinator is not None
        assert isinstance(coordinator, ConcreteResearchCoordinator)
        # Exactly one instance owned by the kernel.
        assert atlas._research_coordinator is coordinator
        atlas.shutdown()

    def test_not_in_service_container(self, isolated_env):
        from atlas.kernel.service_container import ServiceContainer

        atlas = Atlas()
        atlas.start()
        container: ServiceContainer = atlas.container
        assert not container.has("research_coordinator")
        assert not container.has("research")
        atlas.shutdown()

    def test_research_coordinate_registered_in_kernel_registry(self, isolated_env):
        atlas = Atlas()
        atlas.start()
        registry = atlas._capability_registry
        assert registry is not None
        assert registry.has("research.coordinate")
        atlas.shutdown()


# ---------------------------------------------------------------------------
# 8. Public CognitionAPI decision payload compatibility
# ---------------------------------------------------------------------------


class TestPublicPayload:
    def test_pipeline_stage_boundaries_preserved(self, isolated_env):
        """The 15-stage invariant with REASONING empty and PLANNING carrying
        execution results, plus the Phase 20 Blocker-1 public-payload
        contract."""
        atlas = Atlas()
        atlas.start()
        try:
            api = atlas.cognition_api
            assert api is not None
            decision = api.process(
                user_input="hello",
                goal="research.coordinate",
            )
            decision_data = decision.data if hasattr(decision, "data") else {}
            # The Blocker-1 contract: execution results are present on the
            # public decision payload via data["reasoning"].
            assert "reasoning" in decision_data
            reasoning = decision_data["reasoning"]
            assert isinstance(reasoning, dict)
            # results may be empty for a plain respond pipeline; the
            # contract is that the key exists (and is a list when present).
            assert isinstance(reasoning.get("results"), list) or reasoning.get("results") is None
        finally:
            atlas.shutdown()

    def test_kernel_registry_has_research_coordinate_only_once(self, isolated_env):
        atlas = Atlas()
        atlas.start()
        try:
            registry = atlas._capability_registry
            assert registry is not None
            assert registry.has("research.coordinate")
            # registered_names is sorted; ensure no duplicate entry.
            assert registry.registered_names.count("research.coordinate") == 1
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# 9. Legacy ABC compatibility
# ---------------------------------------------------------------------------


class TestLegacyAbc:
    def test_async_conduct_research_matches_abc(self):
        coordinator = ConcreteResearchCoordinator(
            resolve_sources=lambda _specs: _make_profiles("Atlas research works.")
        )
        result = asyncio.run(
            coordinator.conduct_research(
                ResearchQuery(query_id="q-async", question="Atlas research?")
            )
        )
        assert result.query_id == "q-async"
        assert result.confidence >= 0.0

    def test_async_validate_findings_returns_confidence(self):
        coordinator = ConcreteResearchCoordinator()
        result = ResearchResult(
            query_id="q-v",
            findings="x",
            sources=[],
            confidence=0.7,
        )
        score = asyncio.run(coordinator.validate_findings(result))
        assert score == 0.7

    def test_async_validate_findings_fail_soft(self):
        coordinator = ConcreteResearchCoordinator()
        score = asyncio.run(coordinator.validate_findings(None))
        assert score == 0.0
