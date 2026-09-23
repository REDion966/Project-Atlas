"""Phase 12.4 — Model-free boot & core runtime validation: evidence contract.

Validation result: with every external AI/model/provider SDK made unimportable,
all AI-related environment variables absent, and every outbound socket
connection refused, Atlas still boots and initializes its core runtime:
self-knowledge, capability registry/model/router/dispatcher, governance,
research, and the development engine.
"""

from __future__ import annotations

import sys

import pytest

from tests.phase12_environment import (
    BLOCKED_MODULES,
    model_free_environment,
)


@pytest.fixture(scope="module")
def model_free_kernel():
    with model_free_environment() as attempts:
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            yield atlas, attempts
        finally:
            atlas.shutdown()


class TestPhase124ModelFreeBoot:
    def test_blocker_actually_refuses_an_ai_sdk(self):
        with model_free_environment():
            with pytest.raises(ImportError):
                __import__("openai")
            with pytest.raises(ImportError):
                __import__("anthropic")

    def test_network_guard_actually_refuses_connections(self):
        import socket

        with model_free_environment():
            with pytest.raises(OSError):
                socket.socket().connect(("example.invalid", 80))

    def test_kernel_boots_without_any_external_ai(self, model_free_kernel):
        atlas, _attempts = model_free_kernel
        assert atlas._started is True
        assert atlas.provider.name() == "Mock Provider"
        assert atlas.models() == ["atlas-mock-v1"]

    def test_core_services_are_initialized(self, model_free_kernel):
        atlas, _attempts = model_free_kernel
        assert atlas.architecture_model() is not None
        assert atlas.capability_model() is not None
        assert atlas.repository_map is not None
        assert atlas.component_registry.get_all()
        assert atlas.capability_registry is not None
        assert atlas.capability_dispatcher is not None
        assert atlas.research_coordinator is not None
        assert atlas.rule_engine is not None
        assert atlas.self_development_loop is not None
        assert atlas.container.names()

    def test_governance_and_development_accessors_exist_without_a_model(
        self, model_free_kernel
    ):
        atlas, _attempts = model_free_kernel
        for name in (
            "run_development_cycle",
            "authorize_development_execution",
            "approve_promotion_review",
            "promote_validated_change",
        ):
            assert callable(getattr(atlas, name))

    def test_no_outbound_connection_is_attempted_during_boot(self, model_free_kernel):
        _atlas, attempts = model_free_kernel
        assert attempts == []

    def test_no_ai_sdk_entered_sys_modules_during_boot(self, model_free_kernel):
        leaked = [
            name
            for name in sys.modules
            if any(name == p or name.startswith(p + ".") for p in BLOCKED_MODULES)
        ]
        assert leaked == []

    def test_ai_absence_is_not_silently_a_success_claim(self, model_free_kernel):
        atlas, _attempts = model_free_kernel
        # The local tier is explicitly a non-model tier, and the kernel's
        # availability tracker reports UNKNOWN until an outcome is recorded.
        snapshot = atlas.ai_availability.snapshot()
        assert snapshot["status"] == "UNKNOWN"
        assert snapshot["recorded_total"] == 0
