"""Phase 4.7 — Capability-aware planning: evidence contract.

Investigation result: planning already considers available capabilities and
limitations via the existing capability architecture, so no second registry was
introduced.

* ``CapabilityAnalyzer`` maps plan steps → required capabilities.
* ``CapabilityRouter`` routes only capabilities with a registered handler;
  ``CapabilityDispatcher`` reports a missing capability honestly (no fabrication).
* ``atlas.self_knowledge.capability_model`` reports capability dependency
  (deterministic vs external-model) and availability from component health.
* ``atlas.evolution.development_gap.assess_development_gap`` distinguishes
  already-supported vs missing capability/knowledge.
"""

from __future__ import annotations

from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.self_knowledge.capability_model import (
    CapabilityAvailability,
    CapabilityDependency,
    build_capability_model,
)


class TestPhase47CapabilityAwarePlanning:
    def test_only_available_capabilities_are_routed(self):
        registry = CapabilityRegistry()
        registry.register(
            "conversation", lambda params: None
        )
        plan = ReasoningPlan(
            goal="g",
            steps=[ReasoningStep(action="respond"), ReasoningStep(action="query")],
        )
        capabilities = CapabilityAnalyzer().analyze(plan)
        assert {c.name for c in capabilities} == {"conversation", "knowledge_retrieval"}

        routes = CapabilityRouter(registry).route(capabilities)
        # knowledge_retrieval has no handler → not routable.
        assert [r.capability for r in routes] == ["conversation"]

    def test_missing_capability_is_reported_not_faked(self):
        results = CapabilityDispatcher(CapabilityRegistry()).dispatch(
            [Capability(name="knowledge_retrieval", priority=8)]
        )
        assert results[0].success is False
        assert "No handler" in results[0].error

    def test_capability_model_reports_dependency_and_availability(self):
        registry = ComponentRegistry()
        registry.register(
            ComponentMetadata(
                name="memory_service",
                package="atlas.memory.service",
                module_path="atlas.memory.service.memory_manager_service",
                status=ComponentStatus.HEALTHY,
                provided_capabilities=["memory_search"],
            )
        )
        registry.register(
            ComponentMetadata(
                name="ai_service",
                package="atlas.ai",
                module_path="atlas.ai.ai_manager",
                status=ComponentStatus.HEALTHY,
                provided_capabilities=["ai_chat"],
            )
        )
        entries = {e.name: e for e in build_capability_model(registry).entries}

        assert entries["memory_search"].dependency is CapabilityDependency.DETERMINISTIC
        assert (
            entries["ai_chat"].dependency
            is CapabilityDependency.EXTERNAL_MODEL_DEPENDENT
        )
        assert entries["memory_search"].availability is CapabilityAvailability.AVAILABLE

    def test_development_gap_distinguishes_supported_from_missing(self):
        supported = assess_development_gap(
            "memory search", capability_names=["memory_search"]
        )
        assert supported.kind is DevelopmentGapKind.ALREADY_SUPPORTED
        assert "memory_search" in supported.matched

        missing = assess_development_gap(
            "quantum stabilizer control", capability_names=["memory_search"]
        )
        assert missing.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
