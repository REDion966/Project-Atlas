"""Phase 3.3 — Self-knowledge storage/retrieval: evidence contract.

Investigation result (evidence, not aspiration): Atlas already has an
Atlas-owned ``authoritative source → derived model → retrieval surface`` chain
for self-knowledge, so no self-knowledge database/snapshot store was introduced.

Authority map
-------------
* architecture / components / services — authoritative in the
  :class:`~atlas.lifecycle.component_registry.ComponentRegistry`, populated from
  the executable declarations in
  ``atlas/lifecycle/component_definitions.CORE_COMPONENTS`` (plus track wiring).
* capability handlers — authoritative in
  ``atlas/reasoning/execution/registry.CapabilityRegistry`` (executable
  declarations).
* tools — authoritative in ``atlas/tools/registry.ToolRegistry``.
* modules / dependencies — derived from the repository by
  ``atlas/research/repository_map.RepositoryMapBuilder`` (AST scan), cached in the
  kernel and rebuildable via ``Atlas.refresh_repository_map()``.
* capability facts — derived model ``CapabilityModel`` over the three registries.
* architecture facts — derived model ``ArchitectureModel`` over the
  ComponentRegistry + CapabilityModel + the cached RepositoryMap.
* validated research knowledge — persisted (SQLite) with provenance, retrieved
  by ``ValidatedKnowledgeRetriever``.

Retrieval surfaces (all Atlas-owned, read-only, deterministic, model-free):
``Atlas.capability_model()``, ``Atlas.architecture_model()``,
``Atlas.repository_map`` / ``refresh_repository_map()``,
``Atlas.validated_knowledge(query)``, the ``atlas capabilities`` /
``atlas architecture`` CLIs, and the conversational self-knowledge floor
(``BuiltinResponseService`` grounded in the injected ArchitectureModel).

These tests pin: executable-declaration authority, structured retrieval of
representative architecture/capability facts, honest unknown lookups, model
independence, and fresh-kernel reconstruction with grounded self-description.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atlas.lifecycle.component_definitions import CORE_COMPONENTS
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.self_knowledge.capability_model import build_capability_model

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path=(
                "atlas.memory.service.memory_manager_service.MemoryManagerService"
            ),
            description="Memory retrieval, search, ranking, and storage.",
            status=ComponentStatus.HEALTHY,
            dependencies=["memory_repository", "ranking_engine"],
            provided_capabilities=["memory_search", "memory_store"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="memory_repository",
            package="atlas.memory",
            module_path="atlas.memory.repository.memory_repository",
            description="Memory persistence.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search"],
        )
    )
    return registry


def _model():
    registry = _registry()
    capabilities = CapabilityRegistry()
    capabilities.register("memory_search", lambda *_a, **_k: None)
    return build_architecture_model(
        registry,
        capability_model=build_capability_model(registry, capabilities, None),
    )


class TestPhase33SelfKnowledgeEvidence:
    def test_authoritative_sources_are_executable_declarations(self):
        declared = {c.name: c for c in CORE_COMPONENTS}
        assert "memory_service" in declared
        # The authority is a declaration carrying real structural facts.
        assert "memory_repository" in declared["memory_service"].dependencies
        assert declared["memory_service"].module_path

        handlers = CapabilityRegistry()
        handlers.register("memory_search", lambda *_a, **_k: None)
        assert "memory_search" in handlers.registered_names

    def test_retrieves_architecture_and_capability_facts(self):
        model = _model()

        # What components exist?
        assert "memory_service" in {c.name for c in model.components}

        # What modules belong to this subsystem (projected by package)?
        subsystem = next(
            s for s in model.subsystems if s.package == "atlas.memory.service"
        )
        assert "memory_service" in subsystem.components

        # What capabilities does Atlas provide, and what provides them?
        index = dict(model.capability_index)
        assert index["memory_search"] == ("memory_repository", "memory_service")

        # What does a component depend on?
        entry = next(c for c in model.components if c.name == "memory_service")
        assert entry.declared_dependencies == (
            "memory_repository",
            "ranking_engine",
        )

        # What are Atlas's known limitations? (honest scope boundary)
        assert any(
            "Interfaces/contracts are not represented" in item
            for item in model.limitations
        )

    def test_unknown_self_knowledge_lookup_fails_honestly(self):
        result = _model().locate("does_not_exist_at_all")
        assert result.found is False
        assert result.matched_kind == "none"
        assert result.components == ()
        assert result.packages == ()

    def test_self_knowledge_path_has_no_model_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx", "urllib")
        for relative in (
            "atlas/self_knowledge/architecture_model.py",
            "atlas/self_knowledge/capability_model.py",
            "atlas/research/repository_map.py",
            "atlas/research/validated_retrieval.py",
        ):
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"


@pytest.fixture
def _kernel(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class _Tmp(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(kernel_mod, "SQLiteEvolutionStorage", _Tmp)
    atlas = kernel_mod.Atlas()
    atlas.start()
    yield atlas
    atlas.shutdown()


class TestPhase33FreshKernel:
    def test_fresh_kernel_reconstructs_grounds_and_uses_no_model(
        self, _kernel, monkeypatch
    ):
        atlas = _kernel

        # Any provider contact on the self-knowledge path fails loudly.
        def _boom(*_a, **_k):
            raise AssertionError("self-knowledge path contacted a provider")

        monkeypatch.setattr(
            atlas._ai_manager.service, "chat", _boom, raising=False
        )

        # Fresh initialization reconstructs architecture + capability knowledge.
        model = atlas.architecture_model()
        assert model.component_count > 0
        assert model.subsystem_count > 0

        capabilities = atlas.capability_model()
        assert capabilities.component_count > 0
        assert any(e.name == "memory_search" for e in capabilities.entries)

        # Authority consistency: retrieved facts match the executable declaration.
        declared = {c.name: c for c in CORE_COMPONENTS}
        entry = next(c for c in model.components if c.name == "memory_service")
        assert set(entry.declared_dependencies) == set(
            declared["memory_service"].dependencies
        )

        # Grounded self-description is projected from the authoritative model.
        message = atlas.builtin_response.respond("What does Atlas do?")
        assert message is not None
        assert (message.metadata or {}).get("builtin_intent") == "self_description"
        assert f"- Components (registered): {model.component_count}" in message.content
