"""Phase 10.1 — Capability landscape awareness: evidence contract.

Investigation result: Atlas already has ``CapabilityModel`` + the Phase-9
``SelfDevelopmentInventory``; the discovery layer adds a deterministic read-only
``inspect_landscape`` projection over them — no second capability registry.
"""

from __future__ import annotations

import json

from atlas.evolution.capability_discovery import inspect_landscape
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.self_knowledge.capability_model import build_capability_model


def _model():
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="ok_provider",
            package="atlas.a",
            module_path="atlas.a.x",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["cap.ok"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="down_provider",
            package="atlas.b",
            module_path="atlas.b.x",
            status=ComponentStatus.OFFLINE,
            provided_capabilities=["cap.down"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="slow_provider",
            package="atlas.c",
            module_path="atlas.c.x",
            status=ComponentStatus.DEGRADED,
            provided_capabilities=["cap.slow"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="ai_service",
            package="atlas.ai",
            module_path="atlas.ai.x",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["ai_chat"],
        )
    )
    return build_capability_model(registry)


class TestPhase101CapabilityLandscape:
    def test_landscape_classifies_availability_and_dependency(self):
        landscape = inspect_landscape(_model())
        assert set(landscape.known_capabilities) >= {
            "cap.ok",
            "cap.down",
            "cap.slow",
            "ai_chat",
        }
        assert landscape.unavailable == ("cap.down",)
        assert landscape.degraded == ("cap.slow",)
        assert landscape.external_dependent == ("ai_chat",)

    def test_unknown_information_remains_unknown(self):
        # No model -> nothing is claimed.
        landscape = inspect_landscape(None)
        assert landscape.known_capabilities == ()
        assert landscape.unavailable == ()

    def test_landscape_is_deterministic_and_json_safe(self):
        first = inspect_landscape(_model()).to_dict()
        second = inspect_landscape(_model()).to_dict()
        assert first == second
        json.dumps(first, sort_keys=True)
