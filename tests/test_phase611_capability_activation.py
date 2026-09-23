"""Phase 6.11 — Capability activation/integration: evidence contract.

Investigation result: a verified development result can already be turned into a
governed capability activation, so no new activation framework was introduced.

* ``atlas/evolution/capability_activation.py::CapabilityActivator`` — bounded,
  path-confined, byte-match-validated, AST-contract-validated activation that
  registers the promoted capability on the EXISTING ``CapabilityRegistry``.
  Malformed/unsupported/duplicate contracts are refused fail-closed.
* The ``CapabilityModel`` stays consistent after activation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlas.evolution.capability_activation import (
    CapabilityActivationError,
    CapabilityActivator,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import build_capability_model

_MODULE = "atlas/example/widget_handlers.py"
_CAPABILITY = "example.widget"


def _artifact(tmp_path, content=None):
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    body = content
    if body is None:
        supplied = ScaffoldChangeSupplier().supply_changes(
            SimpleNamespace(
                metadata={
                    "scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}
                }
            )
        )
        body = supplied.code_changes[0][1]
    target = root / _MODULE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    artifact = capture_promotion_artifact(
        [{"path": _MODULE, "content": body}], proposal_id="P", repo_root=root
    )
    return root, artifact


class TestPhase611CapabilityActivation:
    def test_valid_capability_activates_and_registers(self, tmp_path):
        root, artifact = _artifact(tmp_path)
        registry = CapabilityRegistry()
        result = CapabilityActivator(root, registry).activate(artifact)

        assert result.activated is True
        assert result.capabilities == (_CAPABILITY,)
        assert registry.has(_CAPABILITY)

    def test_non_capability_artifact_is_not_applicable(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir(parents=True)
        (root / "plain.py").write_text("VALUE = 1\n", encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": "plain.py", "content": "VALUE = 1\n"}],
            proposal_id="P",
            repo_root=root,
        )
        registry = CapabilityRegistry()
        result = CapabilityActivator(root, registry).activate(artifact)
        assert result.activated is False
        assert registry.registered_names == []

    def test_malformed_contract_is_refused_fail_closed(self, tmp_path):
        root, artifact = _artifact(tmp_path, content='CAPABILITY_NAME = "x.y"\n')
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)

    def test_existing_capability_is_not_overwritten(self, tmp_path):
        root, artifact = _artifact(tmp_path)
        registry = CapabilityRegistry()
        registry.register(_CAPABILITY, lambda params: None)
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, registry).activate(artifact)

    def test_capability_model_stays_consistent_after_activation(self, tmp_path):
        root, artifact = _artifact(tmp_path)
        registry = CapabilityRegistry()
        CapabilityActivator(root, registry).activate(artifact)

        model = build_capability_model(ComponentRegistry(), capability_registry=registry)
        assert any(e.name == _CAPABILITY for e in model.entries)
