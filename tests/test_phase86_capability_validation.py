"""Phase 8.6 — Capability validation: evidence contract.

Investigation result: ``DevelopmentVerification`` validates sandbox results, and
the capability registry answers whether a capability actually exists. The
smallest read-only validation helper was added (Phase 8.6) at
``atlas/evolution/capability_acquisition.py`` to confirm an internalized
capability is present, routable, and reflected in the capability model — reusing
those existing surfaces (no second verifier).
"""

from __future__ import annotations

from atlas.evolution.capability_acquisition import validate_internalized_capability
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import build_capability_model


class TestPhase86CapabilityValidation:
    def test_unregistered_capability_fails_validation(self):
        validation = validate_internalized_capability(
            "example.widget", capability_registry=CapabilityRegistry()
        )
        assert validation.ok is False
        assert validation.registered is False
        assert validation.failures

    def test_registered_capability_validates_and_is_in_the_model(self):
        registry = CapabilityRegistry()
        registry.register("example.widget", lambda params: None)
        model = build_capability_model(ComponentRegistry(), capability_registry=registry)

        validation = validate_internalized_capability(
            "example.widget",
            capability_registry=registry,
            capability_model=model,
        )
        assert validation.ok is True
        assert validation.registered is True
        assert validation.routable is True
        assert validation.in_model is True

    def test_missing_registry_fails_closed(self):
        validation = validate_internalized_capability(
            "example.widget", capability_registry=None
        )
        assert validation.ok is False
        assert validation.registered is False

    def test_blank_capability_name_fails_closed(self):
        registry = CapabilityRegistry()
        validation = validate_internalized_capability(
            "", capability_registry=registry
        )
        assert validation.ok is False
        assert "no capability name supplied" in validation.failures

    def test_validation_is_json_safe(self):
        import json

        registry = CapabilityRegistry()
        json.dumps(
            validate_internalized_capability(
                "x", capability_registry=registry
            ).to_dict(),
            sort_keys=True,
        )
