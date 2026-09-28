"""Step 12 — Unified capability model.

The baseline (real Atlas/kernel) showed Atlas already had a canonical
``CapabilityModel`` projected from the registries — but it modelled only the
*registered implementation* surface (reasoning handlers, component-provided
capabilities, tools). The OPERATIONAL (conversational) abilities Atlas actually
supports had no identity at all: they lived in a hard-coded help string and the
implicit routes, so a capability question about them could not be answered from
the model (``capability_contract("investigation")`` -> not found), and the
conversational capability inventory and the canonical model disagreed about what
exists.

Step 12 adds the missing identity — a bounded, evidence-grounded operational
capability catalogue — and merges it into the EXISTING canonical
``CapabilityModel`` (no parallel universe), so capability lookup and the
conversation capability answers speak one consistent, grounded view. It is
representation only: nothing is registered, executed, authorized or mutated.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.capability_model import (
    CapabilityAvailability,
    CapabilityKind,
    build_capability_model,
    describe_capability,
)
from atlas.self_knowledge.operational_capabilities import (
    DEP_EXTERNAL_MODEL,
    MAX_OPERATIONAL_CAPABILITIES,
    all_operational_capabilities,
    find_operational_capability,
    project_operational_capabilities,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _started_atlas(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


# ---------------------------------------------------------------------------
# 1. Operational capability catalogue (the missing identity)
# ---------------------------------------------------------------------------


class TestOperationalCatalogue:
    def test_bounded_and_unique(self):
        caps = all_operational_capabilities()
        assert 0 < len(caps) <= MAX_OPERATIONAL_CAPABILITIES
        ids = [c.id for c in caps]
        assert len(ids) == len(set(ids))

    def test_every_capability_is_grounded_in_evidence(self):
        for capability in all_operational_capabilities():
            assert capability.evidence, capability.id
            assert capability.category
            assert capability.description
            assert capability.operations

    def test_availability_is_grounded_in_wiring(self):
        off = project_operational_capabilities(external_provider=False)
        on = project_operational_capabilities(external_provider=True)
        open_off = next(c for c in off if c.id == "open_conversation")
        open_on = next(c for c in on if c.id == "open_conversation")
        assert open_off.available is False
        assert open_on.available is True
        assert open_off.dependency == DEP_EXTERNAL_MODEL
        # A deterministic conversational capability is always available.
        assert next(c for c in off if c.id == "investigate").available is True

    def test_governed_capability_unavailable_when_boundary_unwired(self):
        unwired = project_operational_capabilities(governed_wired=False)
        approve = next(c for c in unwired if c.id == "approve")
        assert approve.available is False and approve.governed is True
        wired = project_operational_capabilities(governed_wired=True)
        assert next(c for c in wired if c.id == "approve").available is True

    def test_lookup_by_id_alias_and_unknown(self):
        assert find_operational_capability("investigate").id == "investigate"
        assert find_operational_capability("Investigation").id == "investigate"
        assert find_operational_capability("knowledge").id == "research"
        assert find_operational_capability("definitely_not_a_capability") is None
        assert find_operational_capability("") is None


# ---------------------------------------------------------------------------
# 2. Unified model
# ---------------------------------------------------------------------------


class TestUnifiedModel:
    def _model(self):
        caps = project_operational_capabilities(external_provider=False)
        return build_capability_model(
            ComponentRegistry(), None, None, operational_capabilities=caps
        )

    def test_operational_entries_are_merged(self):
        model = self._model()
        assert model.operational_count == len(all_operational_capabilities())
        operational = [e for e in model.entries if e.kind is CapabilityKind.OPERATIONAL]
        assert len(operational) == model.operational_count
        assert all(e.sources for e in operational)

    def test_operational_entries_carry_category_and_operations(self):
        model = self._model()
        entry = model.find("investigate")
        assert entry is not None
        assert entry.category == "investigation"
        assert entry.operations == ("investigate",)
        assert entry.availability is CapabilityAvailability.AVAILABLE
        assert any(s.kind == "operational_capability" for s in entry.sources)
        assert entry.limitations  # read-only limitation is stated

    def test_unavailable_operational_entry_is_truthful(self):
        model = self._model()
        entry = model.find("open_conversation")
        assert entry is not None
        assert entry.availability is CapabilityAvailability.UNAVAILABLE

    def test_model_without_operational_capabilities_is_unchanged(self):
        model = build_capability_model(ComponentRegistry())
        assert model.operational_count == 0
        assert model.entries == ()

    def test_describe_capability_resolves_operational(self):
        caps = project_operational_capabilities(external_provider=False)
        payload = describe_capability(
            "investigate", ComponentRegistry(), operational_capabilities=caps
        )
        assert payload["found"] is True
        assert payload["kind"] == "operational"
        assert payload["category"] == "investigation"
        assert payload["operations"] == ["investigate"]
        assert payload["availability"] == "available"

    def test_describe_capability_resolves_alias(self):
        caps = project_operational_capabilities(external_provider=False)
        payload = describe_capability(
            "investigation", ComponentRegistry(), operational_capabilities=caps
        )
        assert payload["found"] is True
        assert payload["name"] == "investigate"

    def test_describe_capability_fails_closed(self):
        caps = project_operational_capabilities(external_provider=False)
        payload = describe_capability(
            "totally_unknown", ComponentRegistry(), operational_capabilities=caps
        )
        assert payload == {"found": False, "name": "totally_unknown"}

    def test_deterministic(self):
        caps = project_operational_capabilities(external_provider=False)
        a = build_capability_model(ComponentRegistry(), None, None, operational_capabilities=caps)
        b = build_capability_model(ComponentRegistry(), None, None, operational_capabilities=caps)
        assert a.to_dict() == b.to_dict()
        assert a.to_markdown() == b.to_markdown()


# ---------------------------------------------------------------------------
# 3. Conversation integration
# ---------------------------------------------------------------------------


class TestConversationIntegration:
    def _service(self):
        caps = project_operational_capabilities(external_provider=False)
        model = build_capability_model(
            ComponentRegistry(), None, None, operational_capabilities=caps
        )
        return BuiltinResponseService(capability_model_provider=lambda: model)

    def test_inventory_lists_operational_capabilities(self):
        content = self._service()._render_capabilities()
        assert "Operational capabilities" in content
        assert "**investigate**" in content
        # The pinned registered-inventory phrase is preserved.
        assert "Confirmed registered capabilities" in content

    def test_explain_operational_capability_is_consistent(self):
        message = self._service().respond("explain investigate")
        assert message.metadata["builtin_intent"] == "capability_detail"
        assert "operational capability" in message.content
        assert "investigation" in message.content
        assert "investigate" in message.content
        assert "Availability: available" in message.content
        assert "atlas.conversation.investigation" in message.content

    def test_explain_unknown_still_fails_closed(self):
        message = self._service().respond("explain totally_unknown")
        assert message.metadata.get("builtin_intent") != "capability_detail"

    def test_no_model_wired_is_unchanged(self):
        # Without the provider, the inventory has no operational section and
        # every existing answer is unchanged.
        content = BuiltinResponseService()._render_capabilities()
        assert "Operational capabilities" not in content


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_kernel_model_is_unified(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            model = atlas.capability_model()
            assert model.operational_count > 0
            assert model.find("investigate") is not None
            assert model.find("plan") is not None
            # The structural projection remains available and operational-free.
            structural = atlas.capability_model(include_operational=False)
            assert structural.operational_count == 0
        finally:
            atlas.shutdown()

    def test_capability_contract_is_consistent(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            payload = atlas.capability_contract("investigation")
            assert payload["found"] is True
            assert payload["name"] == "investigate"
            assert payload["kind"] == "operational"
            assert payload["category"] == "investigation"
            assert payload["operations"] == ["investigate"]
            assert payload["availability"] == "available"
            assert any(
                s["kind"] == "operational_capability" for s in payload["sources"]
            )
        finally:
            atlas.shutdown()

    def test_unavailable_and_unknown_are_truthful(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # The optional model-backed capability is truthfully unavailable
            # (no external provider is configured by default).
            open_conv = atlas.capability_contract("open_conversation")
            assert open_conv["found"] is True
            assert open_conv["availability"] == "unavailable"
            # An unknown name is never invented.
            assert atlas.capability_contract("definitely_not_a_capability")["found"] is False
        finally:
            atlas.shutdown()

    def test_conversation_and_kernel_agree(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            contract = atlas.capability_contract("investigation")
            message = atlas.chat("explain investigation")
            assert message.metadata.get("builtin_intent") == "capability_detail"
            # The conversation detail reflects the SAME grounded facts.
            assert contract["name"] in message.content
            assert contract["category"] in message.content
            assert contract["availability"] in message.content
            assert "atlas.conversation.investigation" in message.content
        finally:
            atlas.shutdown()

    def test_inventory_reflects_the_unified_model(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("What capabilities do you have?")
            assert "Confirmed registered capabilities" in message.content
            assert "Operational capabilities" in message.content
            assert "investigate" in message.content
        finally:
            atlas.shutdown()

    def test_send_stream_parity(self, monkeypatch, tmp_path):
        a = _started_atlas(monkeypatch, tmp_path)
        try:
            sent = a.chat("explain investigation").content
        finally:
            a.shutdown()
        b = _started_atlas(monkeypatch, tmp_path)
        try:
            streamed = "".join(b.stream("explain investigation"))
        finally:
            b.shutdown()
        assert sent == streamed

    def test_no_authority_or_repository_mutation(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before = atlas.component_registry.component_count
            atlas.chat("What capabilities do you have?")
            atlas.chat("explain investigation")
            message = atlas.chat("explain approve")
            assert atlas.component_registry.component_count == before
            for key in ("approval", "execution", "promotion", "authorization"):
                assert key not in message.metadata, key
            assert atlas.pending_promotion_reviews() == []
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()
