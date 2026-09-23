"""Phase 4.10 — Model-independent reasoning: evidence contract.

Investigation result: the Phase 4 reasoning/planning/execution core is
deterministic and requires no external AI model. No production change was needed.

Verification: (a) static — no provider SDK/network imports on the reasoning,
cognition and orchestration core; (b) runtime — the reasoning pipeline runs with
a raising AI double and still produces a plan.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.cognition.models import PipelineResult, StageStatus, StageType
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PHASE4_MODULES = (
    "atlas/reasoning/controller.py",
    "atlas/reasoning/models.py",
    "atlas/reasoning/outcomes.py",
    "atlas/reasoning/reflection.py",
    "atlas/reasoning/capabilities/analyzer.py",
    "atlas/reasoning/capabilities/models.py",
    "atlas/reasoning/execution/registry.py",
    "atlas/reasoning/execution/routing.py",
    "atlas/reasoning/execution/dispatcher.py",
    "atlas/reasoning/execution/models.py",
    "atlas/reasoning/planning/engine.py",
    "atlas/reasoning/planning/models.py",
    "atlas/cognition/models.py",
    "atlas/cognition/decision.py",
    "atlas/orchestration/target_resolution.py",
    "atlas/orchestration/executor.py",
    "atlas/orchestration/execution_models.py",
)


class _FailingAI:
    def chat(self, *args, **kwargs):
        raise RuntimeError("no external model available")

    def stream_chat(self, *args, **kwargs):
        def _gen():
            raise RuntimeError("no external model available")
            yield ""  # pragma: no cover

        return _gen()

    def complete(self, *args, **kwargs):
        raise RuntimeError("no external model available")


def _coordinator() -> RuntimeCoordinator:
    registry = CapabilityRegistry()
    for name in ("conversation", "knowledge_retrieval"):
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(capability=_n, success=True, output={}),
        )
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        ai_service=_FailingAI(),
    )


class TestPhase410ModelIndependence:
    def test_phase4_core_has_no_provider_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx")
        for relative in _PHASE4_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"

    def test_reasoning_and_planning_run_with_a_failing_provider(self):
        result = _coordinator().process("hello")
        assert isinstance(result, PipelineResult)

        by_stage = {stage.stage: stage for stage in result.stages}
        # REASONING and PLANNING succeed independently of the (failing) provider.
        assert by_stage[StageType.REASONING].status is StageStatus.SUCCESS
        assert by_stage[StageType.PLANNING].status is StageStatus.SUCCESS
        assert by_stage[StageType.REASONING].data["capabilities"]
        assert "steps" in by_stage[StageType.PLANNING].data
