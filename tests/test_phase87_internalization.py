"""Phase 8.7 — Capability internalization: evidence contract.

Investigation result: internalization already exists — ``CapabilityActivator``
registers a promoted capability on the EXISTING ``CapabilityRegistry`` (path-
confined, byte-match, AST-contract validated), and ``CapabilityModel`` derives
from that registry. No new internalization mechanism was introduced and the
governed activation path is not bypassed.
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


class TestPhase87Internalization:
    def test_validated_capability_is_internalized_and_consistent(self, tmp_path):
        root, artifact = _artifact(tmp_path)
        registry = CapabilityRegistry()
        result = CapabilityActivator(root, registry).activate(artifact)

        assert result.activated is True
        assert registry.has(_CAPABILITY)

        model = build_capability_model(ComponentRegistry(), capability_registry=registry)
        assert any(e.name == _CAPABILITY for e in model.entries)

    def test_invalid_contract_is_refused_without_registration(self, tmp_path):
        root, artifact = _artifact(tmp_path, content='CAPABILITY_NAME = "x.y"\n')
        registry = CapabilityRegistry()
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, registry).activate(artifact)
        assert registry.registered_names == []

    def test_existing_capability_is_not_overwritten(self, tmp_path):
        root, artifact = _artifact(tmp_path)
        registry = CapabilityRegistry()
        registry.register(_CAPABILITY, lambda params: None)
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, registry).activate(artifact)
        assert registry.registered_names == [_CAPABILITY]

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
