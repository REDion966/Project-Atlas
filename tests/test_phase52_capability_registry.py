"""Phase 5.2 — Capability registry/model: evidence contract.

Investigation result: Atlas already has an authoritative capability registry and
a derived capability model, so no new registry was introduced.

* ``atlas/reasoning/execution/registry.py::CapabilityRegistry`` — authoritative
  for registered capability *handlers* (execution). Duplicate registration is
  rejected (``ValueError``); retrieval is by name.
* ``atlas/self_knowledge/capability_model.py::CapabilityModel`` — authoritative
  read-only projection over the registry + ``ComponentRegistry`` declarations +
  ``ToolRegistry``.
* Reasoning/planning (``CapabilityAnalyzer``/``CapabilityRouter``) resolve
  capability names against the SAME ``CapabilityRegistry`` used for execution.
"""

from __future__ import annotations

import pytest

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import build_capability_model


class TestPhase52CapabilityRegistry:
    def test_registration_retrieval_and_indexing(self):
        registry = CapabilityRegistry()
        handler = lambda params: None  # noqa: E731
        registry.register("conversation", handler)

        assert registry.has("conversation") is True
        assert registry.get("conversation") is handler
        assert registry.registered_names == ["conversation"]
        assert registry.count == 1

    def test_duplicate_registration_is_rejected(self):
        registry = CapabilityRegistry()
        registry.register("conversation", lambda params: None)
        with pytest.raises(ValueError):
            registry.register("conversation", lambda params: None)

    def test_unknown_capability_is_reported_honestly(self):
        registry = CapabilityRegistry()
        assert registry.get("does_not_exist") is None
        assert registry.has("does_not_exist") is False

    def test_model_and_registry_are_consistent(self):
        registry = CapabilityRegistry()
        registry.register("memory_search", lambda params: None)

        model = build_capability_model(ComponentRegistry(), capability_registry=registry)
        entry = next(e for e in model.entries if e.name == "memory_search")
        # The registry is the authority for handler existence; the model reflects it.
        assert entry is not None
        assert any(s.kind == "capability_registry" for s in entry.sources)

    def test_declared_and_registered_capabilities_are_both_visible(self):
        # Declared capabilities (ComponentRegistry) and handler capabilities
        # (CapabilityRegistry) are joined into one authoritative model.
        components = ComponentRegistry()
        components.register(
            ComponentMetadata(
                name="memory_service",
                package="atlas.memory.service",
                module_path="atlas.memory.service.memory_manager_service",
                status=ComponentStatus.HEALTHY,
                provided_capabilities=["memory_search"],
            )
        )
        registry = CapabilityRegistry()
        registry.register("research.query", lambda params: None)

        names = {e.name for e in build_capability_model(
            components, capability_registry=registry
        ).entries}
        assert {"memory_search", "research.query"} <= names
