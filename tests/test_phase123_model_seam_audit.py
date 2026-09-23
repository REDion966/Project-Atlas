"""Phase 12.3 — External model seam audit: evidence contract.

Validation result: every model/provider seam is optional, bounded, OFF by
default, never authoritative, and absent from the core dependency path. The
ACTIVE provider is the local no-network tier unless external providers are
explicitly opted in, and a configured external provider name alone never
activates network I/O.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.ai.ai_manager import AIManager
from atlas.evolution.development_cycle import (
    DeterministicChangeSupplier,
    DevelopmentNeed,
    SuppliedChanges,
)
from atlas.evolution.development_scaffold_supplier import CompositeChangeSupplier
from atlas.evolution.model_assisted_supplier import (
    ORIGIN_MODEL_ASSISTED_DRAFT,
    ModelAssistedChangeSupplier,
)

_ROOT = Path(__file__).resolve().parents[1]


class _Boom:
    """A model double that must never be trusted."""

    def __call__(self, prompt):  # noqa: ARG002
        raise RuntimeError("external model unavailable")


class TestPhase123ExternalModelSeamAudit:
    def test_model_assisted_supplier_is_off_by_default(self):
        supplier = ModelAssistedChangeSupplier()
        assert supplier.supply_changes(DevelopmentNeed(title="x")) is None

    def test_model_failure_fails_soft_never_fabricates(self):
        supplier = ModelAssistedChangeSupplier(authoring_model=_Boom())
        assert supplier.supply_changes(DevelopmentNeed(title="x")) is None

    def test_model_output_is_marked_as_unverified_draft(self):
        supplier = ModelAssistedChangeSupplier(
            authoring_model=lambda prompt: (
                '{"code_changes": [{"path": "atlas/example/x.py", '
                '"content": "VALUE = 1\\n"}], "confidence": 0.5}'
            )
        )
        supplied = supplier.supply_changes(DevelopmentNeed(title="x"))
        assert isinstance(supplied, SuppliedChanges)
        assert supplied.origin == ORIGIN_MODEL_ASSISTED_DRAFT
        assert supplied.confidence == 0.5

    def test_model_supplier_rejects_unsafe_or_unsupported_output(self):
        unsafe = ModelAssistedChangeSupplier(
            authoring_model=lambda prompt: (
                '{"code_changes": [{"path": "../evil.py", "content": "x"}]}'
            )
        )
        assert unsafe.supply_changes(DevelopmentNeed(title="x")) is None
        sensitive = ModelAssistedChangeSupplier(
            authoring_model=lambda prompt: (
                '{"code_changes": [{"path": "atlas/kernel/evil.py", '
                '"content": "VALUE = 1\\n"}]}'
            )
        )
        assert sensitive.supply_changes(DevelopmentNeed(title="x")) is None
        unsupported = ModelAssistedChangeSupplier(
            authoring_model=lambda prompt: (
                '{"code_changes": [], "execute": "rm -rf /"}'
            )
        )
        assert unsupported.supply_changes(DevelopmentNeed(title="x")) is None

    def test_model_supplier_module_never_imports_the_ai_package(self):
        tree = ast.parse(
            (_ROOT / "atlas/evolution/model_assisted_supplier.py").read_text(
                encoding="utf-8"
            )
        )
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.lower() for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.lower())
        assert not any(n.startswith("atlas.ai") for n in names)

    def test_composite_supplier_tolerates_an_absent_model_supplier(self):
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), ModelAssistedChangeSupplier(None)]
        )
        assert (
            composite.supply_changes(
                DevelopmentNeed(
                    title="x",
                    metadata={"code_changes": [{"path": "a.py", "content": "V=1\n"}]},
                )
            )
            is not None
        )
        # With nothing supplied anywhere, the composite returns None (no
        # fabrication, no partial result).
        assert composite.supply_changes(DevelopmentNeed(title="y")) is None

    def test_configured_external_provider_is_inert_without_opt_in(self):
        manager = AIManager()
        manager.initialize("Ollama", "qwen3:8b", 5)
        # The configured name is recorded, but the ACTIVE provider is the local
        # no-network tier.
        assert manager.configured_provider == "Ollama"
        assert manager.external_providers is False
        assert manager.provider.name() == AIManager.LOCAL_PROVIDER_NAME

    def test_external_providers_require_explicit_opt_in(self):
        manager = AIManager()
        manager.initialize("Ollama", "qwen3:8b", 5, external_providers=True)
        assert manager.external_providers is True
        assert manager.provider.name() == "Ollama"

    def test_ai_service_works_with_no_api_keys_configured(self):
        manager = AIManager()
        manager.initialize("OpenAI", "gpt-x", 5)
        reply = manager.service.chat([{"role": "user", "content": "hi"}])
        assert reply.text  # served by the local deterministic tier
        assert reply.provider == AIManager.LOCAL_PROVIDER_NAME

    def test_seam_defaults_are_safe_in_config(self):
        config = (_ROOT / "config.toml").read_text(encoding="utf-8")
        assert "external_providers = false" in config
        assert "allow_fallback = false" in config
        assert "model_assisted_authoring = false" in config
        assert "web_allowed_hosts = []" in config

    def test_kernel_gates_the_model_supplier_on_the_config_flag(self):
        source = (_ROOT / "atlas/kernel/atlas.py").read_text(encoding="utf-8")
        assert "model_supplier = None" in source
        # The construction sits inside the guarded region between the default
        # None and the deterministic-first composite supplier.
        guarded = source.split("model_supplier = None", 1)[1].split(
            "CompositeChangeSupplier", 1
        )[0]
        assert "if bool(" in guarded
        assert "model_assisted_authoring" in guarded
        assert "ModelAssistedChangeSupplier(" in guarded
