"""Phase 5.1 — Capability representation: evidence contract.

Investigation result: Atlas already represents capabilities as structured,
Atlas-owned, deterministic concepts across a coherent set of models, so no new
representation was introduced.

* ``atlas/tools/models.py::Tool`` (+``ToolParameter``) — the executable
  capability-with-inputs representation (name, description, typed/required
  parameters, category, handler, tags, metadata).
* ``atlas/reasoning/capabilities/models.py::Capability`` — the reasoning-level
  selection representation (name, priority, reason, metadata).
* ``atlas/self_knowledge/capability_model.py::CapabilityEntry`` — the
  self-knowledge representation (kind, dependency, availability, components,
  sources, health, limitations).
* ``atlas/reasoning/execution/models.py::ExecutionResult`` / ``ExecutionRoute`` —
  the execution contract.
"""

from __future__ import annotations

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.models import ExecutionResult
from atlas.self_knowledge.capability_model import (
    CapabilityKind,
    build_capability_model,
)
from atlas.tools.models import Tool, ToolParameter


class TestPhase51CapabilityRepresentation:
    def test_executable_capability_representation_is_structured(self):
        tool = Tool(
            name="echo",
            description="Echo the given text.",
            category="utility",
            parameters=[
                ToolParameter(
                    name="text",
                    description="Text to echo.",
                    type_hint="string",
                    required=True,
                )
            ],
            handler=lambda params: None,
            tags=["util"],
        )
        assert tool.name == "echo"
        assert tool.category == "utility"
        assert tool.parameters[0].name == "text"
        assert tool.parameters[0].required is True
        assert tool.parameters[0].type_hint == "string"
        assert callable(tool.handler)

    def test_reasoning_capability_representation_is_structured(self):
        capability = Capability(
            name="conversation", priority=10, reason="Respond", metadata={"action": "respond"}
        )
        assert capability.name == "conversation"
        assert capability.priority == 10
        assert capability.reason
        assert capability.metadata["action"] == "respond"

    def test_self_knowledge_capability_entry_is_structured(self):
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
        entry = next(
            e for e in build_capability_model(registry).entries if e.name == "memory_search"
        )
        assert entry.kind is CapabilityKind.CAPABILITY
        assert entry.components == ("memory_service",)
        assert entry.dependency.value in {
            "deterministic",
            "external_model_dependent",
            "unknown",
        }
        assert entry.availability.value in {
            "available",
            "degraded",
            "unavailable",
            "unknown",
        }
        assert entry.sources  # provenance carried on the representation

    def test_execution_contract_is_structured(self):
        result = ExecutionResult(
            capability="conversation", success=True, output={"status": "handled"}
        )
        assert result.capability == "conversation"
        assert result.success is True
        assert result.output["status"] == "handled"
