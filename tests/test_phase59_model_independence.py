"""Phase 5.9 — Model-independent capability system: evidence contract.

Investigation result: the Phase 5 capability system is deterministic and
requires no external AI model. No production change was needed.

Verification: (a) static — no provider SDK/network imports on the capability
modules; (b) runtime — capability representation/discovery/availability/gap/
selection/routing all work with a raising AI double.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.cognition.models import StageStatus, StageType
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.self_knowledge.capability_model import build_capability_model

_REPO_ROOT = Path(__file__).resolve().parents[1]

_CAPABILITY_MODULES = (
    "atlas/reasoning/capabilities/analyzer.py",
    "atlas/reasoning/capabilities/models.py",
    "atlas/reasoning/execution/registry.py",
    "atlas/reasoning/execution/routing.py",
    "atlas/reasoning/execution/dispatcher.py",
    "atlas/reasoning/execution/models.py",
    "atlas/reasoning/execution/handlers.py",
    "atlas/self_knowledge/capability_model.py",
    "atlas/tools/registry.py",
    "atlas/tools/selector.py",
    "atlas/tools/executor.py",
    "atlas/tools/models.py",
    "atlas/evolution/development_gap.py",
    "atlas/evolution/capability_activation.py",
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


def _registry(*names):
    registry = CapabilityRegistry()
    for name in names:
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(capability=_n, success=True, output={}),
        )
    return registry


class TestPhase59ModelIndependence:
    def test_capability_modules_have_no_provider_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx")
        for relative in _CAPABILITY_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"

    def test_capability_system_works_with_a_failing_provider(self):
        # Reasoning still discovers capabilities with the provider unavailable.
        coordinator = RuntimeCoordinator(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=_registry("conversation", "knowledge_retrieval"),
            capability_router=CapabilityRouter(_registry("conversation", "knowledge_retrieval")),
            capability_dispatcher=CapabilityDispatcher(
                _registry("conversation", "knowledge_retrieval")
            ),
            planning_engine=PlanningEngine(),
            ai_service=_FailingAI(),
        )
        result = coordinator.process("hello")
        by_stage = {stage.stage: stage for stage in result.stages}
        assert by_stage[StageType.REASONING].status is StageStatus.SUCCESS

        # Representation / availability / gap detection / routing are model-free.
        components = ComponentRegistry()
        components.register(
            ComponentMetadata(
                name="provider",
                package="atlas.example",
                module_path="atlas.example.provider",
                status=ComponentStatus.HEALTHY,
                provided_capabilities=["thing.do"],
            )
        )
        entry = next(
            e for e in build_capability_model(components).entries if e.name == "thing.do"
        )
        assert entry.availability.value == "available"

        assert (
            assess_development_gap("thing do", capability_names=["thing.do"]).kind
            is DevelopmentGapKind.ALREADY_SUPPORTED
        )

        registry = _registry("conversation")
        routes = CapabilityRouter(registry).route([Capability(name="conversation")])
        assert [r.capability for r in routes] == ["conversation"]
        assert CapabilityDispatcher(registry).dispatch([Capability(name="conversation")])[0].success
