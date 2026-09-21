"""Phase 5.3 (G1) — governed capability activation: focused + E2E tests.

Closes the final lifecycle gap: a capability Atlas successfully develops and
promotes becomes an actual usable Atlas capability (registered, discoverable,
and invocable through the normal runtime path).

No production code is modified by these tests. Provider/network are blocked
where model independence is asserted.
"""

from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.evolution.capability_activation import (
    CapabilityActivationError,
    CapabilityActivator,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.promotion_artifact import (
    PromotionArtifact,
    PromotionFileEntry,
    capture_promotion_artifact,
    hash_content,
)
from atlas.evolution.promotion_executor import PromotionExecutor, PromotionOutcome
from atlas.reasoning.execution.registry import CapabilityRegistry
from tests.test_phase52_direct_evolution import _enable_envelope, _make_atlas

_MODULE = "atlas/example/widget_handlers.py"
_CAPABILITY = "example.widget"


def _scaffold_content(module_path=_MODULE, capability=_CAPABILITY) -> str:
    """Author the authentic capability module via the supported scaffolder."""
    supplied = ScaffoldChangeSupplier().supply_changes(
        SimpleNamespace(metadata={"scaffold": {"module": module_path, "capability_name": capability}})
    )
    assert supplied is not None
    return supplied.code_changes[0][1]


def _artifact_for(tmp_path: Path, *, module_path=_MODULE, capability=_CAPABILITY, content=None):
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    target = root / module_path
    target.parent.mkdir(parents=True, exist_ok=True)
    body = content if content is not None else _scaffold_content(module_path, capability)
    target.write_text(body, encoding="utf-8")
    artifact = capture_promotion_artifact(
        [{"path": module_path, "content": body}], proposal_id="P", repo_root=root
    )
    return root, artifact


# ---------------------------------------------------------------------------
# Unit: CapabilityActivator
# ---------------------------------------------------------------------------


class TestCapabilityActivator:
    def test_valid_capability_activates_and_registers(self, tmp_path):
        root, artifact = _artifact_for(tmp_path)
        registry = CapabilityRegistry()
        result = CapabilityActivator(root, registry).activate(artifact)
        assert result.activated is True
        assert result.capabilities == (_CAPABILITY,)
        assert _CAPABILITY in registry.registered_names
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

    def test_declared_but_invalid_contract_refused(self, tmp_path):
        content = f'CAPABILITY_NAME = "{_CAPABILITY}"\n'  # declaration, no factory class
        root, artifact = _artifact_for(tmp_path, content=content)
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)

    def test_handlers_not_a_mapping_refused(self, tmp_path):
        content = (
            f'CAPABILITY_NAME = "{_CAPABILITY}"\n\n'
            "class F:\n"
            "    def handlers(self):\n"
            "        return ['not-a-mapping']\n"
            "    def register(self, registry):\n"
            "        pass\n"
        )
        root, artifact = _artifact_for(tmp_path, content=content)
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)

    def test_non_callable_handler_refused(self, tmp_path):
        content = (
            f'CAPABILITY_NAME = "{_CAPABILITY}"\n\n'
            "class F:\n"
            "    def handlers(self):\n"
            f'        return {{"{_CAPABILITY}": "not-callable"}}\n'
            "    def register(self, registry):\n"
            "        pass\n"
        )
        root, artifact = _artifact_for(tmp_path, content=content)
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)

    def test_path_escape_refused(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir(parents=True)
        body = _scaffold_content()
        entry = PromotionFileEntry(
            path="../evil.py",
            pre_state=None,
            pre_hash=hash_content(""),
            post_content=body,
            post_hash=hash_content(body),
        )
        artifact = PromotionArtifact(artifact_id="a", proposal_id="P", files=(entry,))
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)

    def test_architecture_sensitive_module_refused(self, tmp_path):
        root, artifact = _artifact_for(
            tmp_path,
            module_path="atlas/kernel/evil_handlers.py",
            capability="kernel.evil",
            content=_scaffold_content(),
        )
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)

    def test_drifted_on_disk_content_refused(self, tmp_path):
        root, artifact = _artifact_for(tmp_path)
        # Drift the file after capture (validation/content mismatch).
        (root / _MODULE).write_text("VALUE = 999\n", encoding="utf-8")
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)

    def test_duplicate_registration_refused(self, tmp_path):
        root, artifact = _artifact_for(tmp_path)
        registry = CapabilityRegistry()
        CapabilityActivator(root, registry).activate(artifact)
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, registry).activate(artifact)


# ---------------------------------------------------------------------------
# Unit: PromotionExecutor × activation (ordering + fail-closed)
# ---------------------------------------------------------------------------


class TestPromotionActivationOrdering:
    def test_successful_promotion_activates_capability(self, tmp_path):
        root, artifact = _artifact_for(tmp_path)
        registry = CapabilityRegistry()
        executor = PromotionExecutor(root, activator=CapabilityActivator(root, registry))
        result = executor.promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.PROMOTED
        assert result.activated_capabilities == (_CAPABILITY,)
        assert _CAPABILITY in registry.registered_names

    def test_activation_failure_rolls_back_and_never_promotes(self, tmp_path):
        root, artifact = _artifact_for(tmp_path)
        registry = CapabilityRegistry()

        def failing(art):
            raise CapabilityActivationError("activation exploded")

        result = PromotionExecutor(root, activator=failing).promote(
            artifact, authorized=True
        )
        assert result.outcome is PromotionOutcome.FAILED_ROLLED_BACK
        assert result.rollback_verified is True
        # The file was restored to its captured pre-state content.
        assert (root / _MODULE).read_text(encoding="utf-8") == _scaffold_content()
        assert registry.registered_names == []

    def test_non_owner_cannot_promote_or_activate(self, tmp_path):
        root, artifact = _artifact_for(tmp_path)
        registry = CapabilityRegistry()
        executor = PromotionExecutor(root, activator=CapabilityActivator(root, registry))
        result = executor.promote(artifact, authorized=False)
        assert result.outcome is PromotionOutcome.REFUSED_UNAUTHORIZED
        assert registry.registered_names == []

    def test_existing_registrations_remain_intact(self, tmp_path):
        root, artifact = _artifact_for(tmp_path)
        registry = CapabilityRegistry()
        registry.register("existing.capability", lambda params: None)
        PromotionExecutor(root, activator=CapabilityActivator(root, registry)).promote(
            artifact, authorized=True
        )
        assert registry.has("existing.capability")
        assert _CAPABILITY in registry.registered_names


# ---------------------------------------------------------------------------
# Kernel E2E: full lifecycle → capability usable
# ---------------------------------------------------------------------------


class TestFullLifecycleCapabilityUsable:
    def test_drive_promote_activate_discover_invoke(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            before = set(atlas.capability_registry.registered_names)

            metadata = {
                "scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}
            }
            result = atlas.run_development_driver(
                "add a capability to handle widgets so that widgets work",
                metadata=metadata,
            )
            assert result.terminal.value == "validated", result.to_dict()

            # Envelope-authorized sandbox execution must NOT activate a live
            # capability before OWNER promotion.
            assert _CAPABILITY not in atlas.capability_registry.registered_names

            rid = result.promotion_request_id
            atlas.approve_promotion_review(atlas.session_context, rid)
            promotion = atlas.promote_validated_change(atlas.session_context, rid)

            assert promotion.outcome is PromotionOutcome.PROMOTED
            assert promotion.version_id  # CODE version (G-A)
            assert promotion.audit_id    # promotion audit
            assert promotion.activation_id  # activation audit
            assert promotion.activated_capabilities == (_CAPABILITY,)

            # Discovery through the existing registry + capability model.
            assert _CAPABILITY in atlas.capability_registry.registered_names
            model = atlas.capability_model()
            names = {getattr(entry, "name", "") for entry in getattr(model, "entries", ())}
            assert _CAPABILITY in names

            # Normal runtime invocation path (CapabilityDispatcher).
            from atlas.reasoning.capabilities.models import Capability

            outcomes = atlas.capability_dispatcher.dispatch(
                [Capability(name=_CAPABILITY, metadata={})]
            )
            assert len(outcomes) == 1
            assert outcomes[0].success is True
            assert outcomes[0].capability == _CAPABILITY

            # Audit trail: promotion + activation records exist; existing
            # registrations intact.
            events = {
                record.event_type
                for record in atlas._evolution_memory.get_records_by_type(
                    "capability_activation"
                )
            }
            assert "capability_activation" in events
            assert before <= set(atlas.capability_registry.registered_names)
            assert (repo / _MODULE).exists()
        finally:
            atlas.shutdown()

    def test_model_and_network_independence(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        atlas = _make_atlas(tmp_path, monkeypatch)
        calls = {"n": 0}

        def _boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("provider contacted")

        import atlas.ai.ai_service as ai_service

        monkeypatch.setattr(ai_service.AIService, "chat", _boom)
        monkeypatch.setattr(ai_service.AIService, "complete", _boom)
        try:
            import atlas.ai.router.ai_router as ai_router

            monkeypatch.setattr(ai_router.AIRouter, "chat", _boom)
            monkeypatch.setattr(ai_router.AIRouter, "complete", _boom)
        except Exception:
            pass
        monkeypatch.setattr(
            socket.socket, "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network attempted")),
        )
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            result = atlas.run_development_driver(
                "add a capability to handle widgets so that widgets work",
                metadata={"scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}},
            )
            rid = result.promotion_request_id
            atlas.approve_promotion_review(atlas.session_context, rid)
            promotion = atlas.promote_validated_change(atlas.session_context, rid)
            assert promotion.outcome is PromotionOutcome.PROMOTED
            assert _CAPABILITY in atlas.capability_registry.registered_names
            assert calls["n"] == 0
        finally:
            atlas.shutdown()

    def test_non_owner_cannot_activate_via_kernel(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            result = atlas.run_development_driver(
                "add a capability to handle widgets so that widgets work",
                metadata={"scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}},
            )
            rid = result.promotion_request_id
            atlas.approve_promotion_review(atlas.session_context, rid)

            atlas._authority_service.add_user("Alice", principal_id="alice")
            user_ctx = atlas.start_user_session("alice")
            with pytest.raises(RuntimeError):
                atlas.promote_validated_change(user_ctx, rid)
            assert _CAPABILITY not in atlas.capability_registry.registered_names
        finally:
            atlas.shutdown()
