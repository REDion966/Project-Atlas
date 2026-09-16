"""C5.1 — Canonical deterministic capability model tests.

Covers the pure projection, deterministic classification, source attribution,
limitation honesty, component health, stable ordering/serialization, aggregate
counts, empty/partial sources, read-only behavior, model independence, the
kernel accessor, and the read-only CLI surface.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import (
    CapabilityAvailability,
    CapabilityDependency,
    CapabilityKind,
    CapabilityModelBuilder,
    build_capability_model,
)
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _components() -> ComponentRegistry:
    reg = ComponentRegistry()
    reg.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path="atlas.memory.service.memory_manager_service",
            description="Memory retrieval.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search", "memory_store"],
        )
    )
    reg.register(
        ComponentMetadata(
            name="ai_service",
            package="atlas.ai",
            module_path="atlas.ai.ai_manager.AIManager.service",
            description="AI provider abstraction.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["ai_chat", "model_routing"],
        )
    )
    return reg


def _capability_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register("memory_search", lambda *_a, **_k: None)
    reg.register("research.coordinate", lambda *_a, **_k: None)
    return reg


def _tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool(name="echo", description="Echo", category="utility"))
    return reg


def _entry(model, name):
    return next(e for e in model.entries if e.name == name)


# ---------------------------------------------------------------------------
# Projection / creation
# ---------------------------------------------------------------------------


class TestModelCreation:
    def test_creates_canonical_model(self):
        model = build_capability_model(
            _components(), _capability_registry(), _tool_registry()
        )
        assert model.component_count == 2
        # memory_search (component+handler), memory_store, ai_chat,
        # model_routing, research.coordinate
        assert model.capability_count == 5
        assert model.tool_count == 1

    def test_projects_component_provided_capabilities(self):
        model = build_capability_model(_components())
        entry = _entry(model, "memory_search")
        assert entry.kind is CapabilityKind.CAPABILITY
        assert entry.components == ("memory_service",)
        assert any(s.kind == "component_registry" for s in entry.sources)

    def test_projects_handler_names(self):
        model = build_capability_model(_components(), _capability_registry())
        entry = _entry(model, "research.coordinate")
        assert any(s.kind == "capability_registry" for s in entry.sources)

    def test_projects_tools(self):
        model = build_capability_model(_components(), None, _tool_registry())
        entry = _entry(model, "echo")
        assert entry.kind is CapabilityKind.TOOL
        assert any(s.kind == "tool_registry" for s in entry.sources)

    def test_no_fabricated_capabilities(self):
        model = build_capability_model(_components())
        names = {e.name for e in model.entries}
        assert names == {"memory_search", "memory_store", "ai_chat", "model_routing"}

    def test_merges_overlapping_sources_without_duplication(self):
        model = build_capability_model(_components(), _capability_registry())
        entry = _entry(model, "memory_search")
        kinds = {s.kind for s in entry.sources}
        assert kinds == {"component_registry", "capability_registry"}
        assert sum(1 for e in model.entries if e.name == "memory_search") == 1


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestClassification:
    def test_deterministic_from_non_ai_component(self):
        model = build_capability_model(_components())
        assert (
            _entry(model, "memory_search").dependency
            is CapabilityDependency.DETERMINISTIC
        )

    def test_external_model_dependent_from_ai_package(self):
        model = build_capability_model(_components())
        assert (
            _entry(model, "ai_chat").dependency
            is CapabilityDependency.EXTERNAL_MODEL_DEPENDENT
        )

    def test_tool_is_deterministic(self):
        model = build_capability_model(_components(), None, _tool_registry())
        assert (
            _entry(model, "echo").dependency
            is CapabilityDependency.DETERMINISTIC
        )

    def test_handler_only_is_unknown_not_guessed(self):
        model = build_capability_model(_components(), _capability_registry())
        entry = _entry(model, "research.coordinate")
        assert entry.dependency is CapabilityDependency.UNKNOWN
        assert entry.components == ()
        assert entry.limitations  # honesty: uncertainty is represented


# ---------------------------------------------------------------------------
# Source attribution
# ---------------------------------------------------------------------------


class TestSourceAttribution:
    def test_every_entry_has_a_source(self):
        model = build_capability_model(
            _components(), _capability_registry(), _tool_registry()
        )
        for entry in model.entries:
            assert entry.sources, f"{entry.name} has no source"

    def test_source_counts_are_reported(self):
        model = build_capability_model(
            _components(), _capability_registry(), _tool_registry()
        )
        counts = dict(model.source_counts)
        assert counts["component_registry"] >= 4
        assert counts["capability_registry"] == 2
        assert counts["tool_registry"] == 1


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestComponentHealth:
    def test_healthy_component_is_available(self):
        model = build_capability_model(_components())
        assert (
            _entry(model, "memory_search").availability
            is CapabilityAvailability.AVAILABLE
        )

    def test_degraded_component_maps_to_degraded(self):
        reg = _components()
        reg.update_status("memory_service", ComponentStatus.DEGRADED)
        model = build_capability_model(reg)
        assert (
            _entry(model, "memory_search").availability
            is CapabilityAvailability.DEGRADED
        )

    def test_offline_component_maps_to_unavailable(self):
        reg = _components()
        reg.update_status("ai_service", ComponentStatus.OFFLINE)
        model = build_capability_model(reg)
        assert (
            _entry(model, "ai_chat").availability
            is CapabilityAvailability.UNAVAILABLE
        )

    def test_entry_without_component_health_is_unknown(self):
        model = build_capability_model(_components(), None, _tool_registry())
        assert _entry(model, "echo").availability is CapabilityAvailability.UNKNOWN

    def test_health_counts_reported(self):
        model = build_capability_model(_components())
        assert dict(model.health_counts).get("HEALTHY") == 2


# ---------------------------------------------------------------------------
# Limitations
# ---------------------------------------------------------------------------


class TestLimitations:
    def test_external_capability_has_limitation(self):
        model = build_capability_model(_components())
        assert _entry(model, "ai_chat").limitations

    def test_deterministic_capability_has_no_limitation(self):
        model = build_capability_model(_components())
        assert _entry(model, "memory_search").limitations == ()

    def test_model_level_limitations_only_when_evidenced(self):
        empty = build_capability_model(ComponentRegistry())
        assert empty.limitations == ()
        populated = build_capability_model(_components())
        assert any("external AI model" in x for x in populated.limitations)

    def test_absence_of_entry_is_not_a_limitation(self):
        # No entry for an unregistered name is simply absent; the model must
        # not invent "Atlas cannot X" statements.
        model = build_capability_model(_components())
        joined = " ".join(model.limitations) + " ".join(
            limitation for e in model.entries for limitation in e.limitations
        )
        assert "atlas cannot" not in joined.lower()


# ---------------------------------------------------------------------------
# Determinism / serialization / counts
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_stable_ordering(self):
        model = build_capability_model(
            _components(), _capability_registry(), _tool_registry()
        )
        names = [e.name for e in model.entries]
        assert names == sorted(names)
        for entry in model.entries:
            assert entry.components == tuple(sorted(entry.components))
            assert [s.kind for s in entry.sources] == sorted(
                s.kind for s in entry.sources
            )

    def test_repeated_build_is_identical(self):
        def build():
            return build_capability_model(
                _components(), _capability_registry(), _tool_registry()
            )

        assert build().to_dict() == build().to_dict()
        assert build().to_markdown() == build().to_markdown()

    def test_aggregate_counts(self):
        model = build_capability_model(
            _components(), _capability_registry(), _tool_registry()
        )
        assert model.component_count == 2
        assert model.capability_count == 5
        assert model.tool_count == 1
        deps = dict(model.dependency_counts)
        assert deps["deterministic"] == 3
        assert deps["external_model_dependent"] == 2
        assert deps["unknown"] == 1


# ---------------------------------------------------------------------------
# Partial / empty sources, read-only
# ---------------------------------------------------------------------------


class TestSourcesAndReadOnly:
    def test_empty_registry_yields_empty_model(self):
        model = build_capability_model(ComponentRegistry())
        assert model.entries == ()
        assert model.component_count == 0
        assert model.capability_count == 0
        assert model.tool_count == 0

    def test_partial_sources_allowed(self):
        model = build_capability_model(_components(), None, None)
        assert model.capability_count == 4
        assert model.tool_count == 0

    def test_no_provided_capabilities(self):
        reg = ComponentRegistry()
        reg.register(
            ComponentMetadata(name="x", package="atlas.x", module_path="atlas.x")
        )
        model = build_capability_model(reg)
        assert model.entries == ()
        assert model.component_count == 1

    def test_build_does_not_mutate_registries(self):
        components = _components()
        caps = _capability_registry()
        tools = _tool_registry()
        before = (
            [c.name for c in components.get_all()],
            list(caps.registered_names),
            [t.name for t in tools.list()],
        )
        build_capability_model(components, caps, tools)
        after = (
            [c.name for c in components.get_all()],
            list(caps.registered_names),
            [t.name for t in tools.list()],
        )
        assert before == after

    def test_builder_has_no_execute_or_apply(self):
        builder = CapabilityModelBuilder()
        assert not hasattr(builder, "execute")
        assert not hasattr(builder, "apply")
        assert not hasattr(builder, "persist")


class TestModelIndependence:
    def test_module_has_no_network_or_model_imports(self):
        source = (_REPO_ROOT / "atlas" / "self_knowledge" / "capability_model.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        banned = ("openai", "anthropic", "ollama", "requests", "httpx", "urllib")
        for module in imported:
            assert not module.startswith(banned)

    def test_build_requires_no_model(self):
        model = build_capability_model(_components())
        assert model.entries


# ---------------------------------------------------------------------------
# Kernel accessor + CLI
# ---------------------------------------------------------------------------


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


class TestKernelAccessor:
    def test_capability_model_from_kernel(self, _kernel):
        model = _kernel.capability_model()
        assert model.component_count > 0
        assert model.capability_count > 0
        assert model.tool_count > 0
        assert model.entries

    def test_kernel_model_is_deterministic(self, _kernel):
        assert (
            _kernel.capability_model().to_dict()
            == _kernel.capability_model().to_dict()
        )

    def test_kernel_model_is_read_only(self, _kernel):
        before = _kernel.component_registry.component_count
        model = _kernel.capability_model()
        assert _kernel.component_registry.component_count == before
        assert model.entries

    def test_kernel_model_classifies_ai_capability(self, _kernel):
        model = _kernel.capability_model()
        entry = next(e for e in model.entries if e.name == "ai_chat")
        assert entry.dependency.value == "external_model_dependent"


class TestCliSurface:
    def _stub_atlas(self):
        model = build_capability_model(
            _components(), _capability_registry(), _tool_registry()
        )
        return SimpleNamespace(capability_model=lambda: model)

    def test_markdown_render(self):
        from atlas.cli.capability_commands import cmd_capabilities

        out = cmd_capabilities(self._stub_atlas(), SimpleNamespace(json=False))
        assert "Atlas Canonical Capability Model" in out
        assert "memory_search" in out
        assert "Nothing was modified" in out

    def test_json_render(self):
        from atlas.cli.capability_commands import cmd_capabilities

        out = cmd_capabilities(self._stub_atlas(), SimpleNamespace(json=True))
        parsed = json.loads(out)
        assert parsed["component_count"] == 2
        assert any(e["name"] == "memory_search" for e in parsed["entries"])

    def test_cli_contains_no_discovery_logic(self):
        source = (_REPO_ROOT / "atlas" / "cli" / "capability_commands.py").read_text(
            encoding="utf-8"
        )
        assert "RepositoryMap" not in source
        assert "ComponentRegistry" not in source
        assert "ToolRegistry" not in source

    def test_cli_subprocess_smoke(self):
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, "-m", "atlas.cli.main", "capabilities", "--json"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr
        parsed = json.loads(proc.stdout)
        assert parsed["component_count"] > 0
        assert parsed["capability_count"] > 0
