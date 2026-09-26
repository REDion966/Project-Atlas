"""Step — capability contracts & discovery (MCP-adapted).

Atlas-native capability discovery layered onto the EXISTING canonical
``CapabilityModel`` (no second registry): a capability can now be described with
its declared description, provider component, implementation module, availability,
dependency class, provenance, and declared tool input contract.

Mechanism source: MCP's explicit capability declarations + discovery +
tools/resources separation + input contracts. Adapted to Atlas: metadata is
descriptive only and grants NO authority; the CapabilityRegistry and
ComponentRegistry remain the sole authorities.
"""

from __future__ import annotations

import json

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import (
    CapabilityAvailability,
    CapabilityDependency,
    CapabilityKind,
    build_capability_model,
    describe_capability,
)
from atlas.tools.models import Tool, ToolParameter
from atlas.tools.registry import ToolRegistry

_DESCRIPTION = "Memory retrieval, search, ranking, and storage."
_MODULE = "atlas.memory.service.memory_manager_service.MemoryManagerService"


def _components() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path=_MODULE,
            description=_DESCRIPTION,
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search", "memory_store"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="ai_service",
            package="atlas.ai",
            module_path="atlas.ai.ai_service.AIService",
            description="Optional external model chat.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["ai_chat"],
        )
    )
    return registry


def _tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="Echo the input text.",
            category="utility",
            parameters=[ToolParameter(name="text", type_hint="string", required=True)],
        )
    )
    return registry


# ---------------------------------------------------------------------------
# Contract creation + metadata correctness
# ---------------------------------------------------------------------------


class TestCapabilityContract:
    def test_description_and_implementation_from_evidence(self):
        contract = describe_capability("memory_search", _components())
        assert contract["found"] is True
        assert contract["description"] == _DESCRIPTION
        assert contract["implementation"] == _MODULE

    def test_provider_availability_and_dependency(self):
        contract = describe_capability("memory_search", _components())
        assert contract["components"] == ["memory_service"]
        assert contract["availability"] == CapabilityAvailability.AVAILABLE.value
        assert contract["dependency"] == CapabilityDependency.DETERMINISTIC.value
        assert contract["kind"] == CapabilityKind.CAPABILITY.value

    def test_model_dependent_classification(self):
        contract = describe_capability("ai_chat", _components())
        assert contract["dependency"] == (
            CapabilityDependency.EXTERNAL_MODEL_DEPENDENT.value
        )
        assert contract["limitations"]

    def test_tool_input_contract_exposed(self):
        contract = describe_capability(
            "echo", _components(), tool_registry=_tools()
        )
        assert contract["kind"] == CapabilityKind.TOOL.value
        assert contract["description"] == "Echo the input text."
        assert contract["inputs"] == [["text", "string", True]]

    def test_unknown_capability_is_not_invented(self):
        contract = describe_capability("no_such_capability", _components())
        assert contract == {"found": False, "name": "no_such_capability"}

    def test_provenance_is_preserved(self):
        contract = describe_capability("memory_search", _components())
        kinds = {source["kind"] for source in contract["sources"]}
        assert "component_registry" in kinds

    def test_contract_is_json_safe_and_deterministic(self):
        first = describe_capability("memory_search", _components())
        second = describe_capability("memory_search", _components())
        assert first == second
        json.dumps(first)


# ---------------------------------------------------------------------------
# Registry-backed discovery (no second registry)
# ---------------------------------------------------------------------------


class TestRegistryBackedDiscovery:
    def test_registry_only_capability_is_discovered_honestly(self):
        registry = CapabilityRegistry()
        registry.register("conversation", lambda params: None)
        model = build_capability_model(ComponentRegistry(), registry)
        entry = model.find("conversation")
        assert entry is not None
        assert entry.dependency is CapabilityDependency.UNKNOWN
        assert entry.components == ()

    def test_find_is_deterministic_and_empty_on_miss(self):
        model = build_capability_model(_components())
        assert model.find("memory_search") is not None
        assert model.find("") is None
        assert model.find("nope") is None


# ---------------------------------------------------------------------------
# Authority / governance
# ---------------------------------------------------------------------------


class TestNoAuthorityEscalation:
    def test_contract_carries_no_authority_fields(self):
        contract = describe_capability("memory_search", _components())
        for banned in (
            "authority",
            "permissions",
            "approved",
            "promote",
            "activate",
            "execute",
        ):
            assert banned not in contract

    def test_discovery_does_not_mutate_registries(self):
        components = _components()
        before = components.get_all()
        describe_capability("memory_search", components)
        assert components.get_all() == before

    def test_model_counts_unchanged_by_contract_layer(self):
        components = _components()
        model = build_capability_model(components)
        assert model.capability_count == 3
        assert {e.name for e in model.entries} == {
            "memory_search",
            "memory_store",
            "ai_chat",
        }


# ---------------------------------------------------------------------------
# Integration — kernel discovery accessor
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage
    from tests.test_durable_guided_improvement import _storage_class

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )

    class _TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", _TmpResearch)
    atlas = kernel_mod.Atlas()
    atlas.start()
    return atlas


class TestKernelDiscovery:
    def test_kernel_capability_contract(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert atlas.capability_contract("conversation")["found"] is True
            assert atlas.capability_contract("no_such_capability") == {
                "found": False,
                "name": "no_such_capability",
            }
        finally:
            atlas.shutdown()

    def test_capability_model_render_includes_contract_fields(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            markdown = atlas.capability_model().to_markdown()
            assert "## Entries" in markdown
        finally:
            atlas.shutdown()
