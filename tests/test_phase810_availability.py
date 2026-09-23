"""Phase 8.10 — Capability availability after internalization: evidence contract.

Investigation result: availability already flows through the existing
registry/router/dispatcher/model chain. An acquired capability is unavailable
until governed activation, then discoverable, routable, and executable.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.capability_activation import CapabilityActivator
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.self_knowledge.capability_model import build_capability_model

_MODULE = "atlas/example/widget_handlers.py"
_CAPABILITY = "example.widget"


def _activate(tmp_path, registry):
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    supplied = ScaffoldChangeSupplier().supply_changes(
        SimpleNamespace(
            metadata={"scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}}
        )
    )
    body = supplied.code_changes[0][1]
    target = root / _MODULE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    artifact = capture_promotion_artifact(
        [{"path": _MODULE, "content": body}], proposal_id="P", repo_root=root
    )
    return CapabilityActivator(root, registry).activate(artifact)


class TestPhase810Availability:
    def test_capability_is_unavailable_before_internalization(self):
        registry = CapabilityRegistry()
        assert registry.has(_CAPABILITY) is False
        assert CapabilityRouter(registry).route([Capability(name=_CAPABILITY)]) == []

    def test_capability_becomes_available_and_routable_after_activation(self, tmp_path):
        registry = CapabilityRegistry()
        result = _activate(tmp_path, registry)
        assert result.activated is True

        # Registry → model → router all reflect the new capability.
        assert registry.has(_CAPABILITY)
        model = build_capability_model(ComponentRegistry(), capability_registry=registry)
        assert any(e.name == _CAPABILITY for e in model.entries)
        routes = CapabilityRouter(registry).route([Capability(name=_CAPABILITY)])
        assert [r.capability for r in routes] == [_CAPABILITY]

    def test_activated_capability_is_dispatchable(self, tmp_path):
        registry = CapabilityRegistry()
        _activate(tmp_path, registry)

        results = CapabilityDispatcher(registry).dispatch(
            [Capability(name=_CAPABILITY)]
        )
        assert results[0].capability == _CAPABILITY
        assert results[0].success is True

    def test_unknown_capability_still_fails_honestly(self):
        registry = CapabilityRegistry()
        results = CapabilityDispatcher(registry).dispatch(
            [Capability(name="never.registered")]
        )
        assert results[0].success is False
