"""Phase 5.4 — Capability status/availability: evidence contract.

Investigation result: Atlas already distinguishes capability availability and
operational routability, so no new status model was introduced.

* ``CapabilityModel`` derives availability from providing-component health:
  HEALTHY→available, DEGRADED→degraded, OFFLINE→unavailable, else unknown.
* ``CapabilityDependency`` distinguishes deterministic / external-model /
  unknown.
* ``CapabilityRouter`` routes only capabilities with a registered handler;
  ``CapabilityDispatcher`` reports a missing handler honestly.
"""

from __future__ import annotations

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.self_knowledge.capability_model import build_capability_model


def _entry_for(status):
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="provider",
            package="atlas.example",
            module_path="atlas.example.provider",
            status=status,
            provided_capabilities=["thing.do"],
        )
    )
    return next(
        e for e in build_capability_model(registry).entries if e.name == "thing.do"
    )


class TestPhase54CapabilityAvailability:
    def test_availability_reflects_providing_component_health(self):
        assert _entry_for(ComponentStatus.HEALTHY).availability.value == "available"
        assert _entry_for(ComponentStatus.DEGRADED).availability.value == "degraded"
        assert _entry_for(ComponentStatus.OFFLINE).availability.value == "unavailable"

    def test_available_capability_is_routed(self):
        registry = CapabilityRegistry()
        registry.register(
            "conversation",
            lambda params: ExecutionResult(capability="conversation", success=True),
        )
        routes = CapabilityRouter(registry).route([Capability(name="conversation")])
        assert [r.capability for r in routes] == ["conversation"]

    def test_unavailable_capability_is_not_falsely_executable(self):
        capabilities = [Capability(name="missing")]
        # Not routable...
        assert CapabilityRouter(CapabilityRegistry()).route(capabilities) == []
        # ...and honest failure if dispatched directly.
        results = CapabilityDispatcher(CapabilityRegistry()).dispatch(capabilities)
        assert results[0].success is False
        assert "No handler" in results[0].error

    def test_orphan_handler_capability_reports_unknown_availability(self):
        registry = CapabilityRegistry()
        registry.register("orphan", lambda params: None)
        entry = next(
            e
            for e in build_capability_model(
                ComponentRegistry(), capability_registry=registry
            ).entries
            if e.name == "orphan"
        )
        assert entry.availability.value == "unknown"
        assert entry.dependency.value == "unknown"
