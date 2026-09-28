"""Step 14 — architecture self-understanding.

The baseline (real Atlas/kernel) showed the existing ArchitectureModel gave
component/subsystem/module/dependency facts but no capability OWNERSHIP join, no
governance boundaries and no explicit known/unknown statement, and the
conversation mis-routed architecture questions:

  * "Where is the investigation capability implemented?" ran a real read-only
    investigation;
  * "Which component owns memory_search?" ran a knowledge retrieval;
  * "What is the responsibility of the kernel component?" resolved to a spurious
    repository symbol;
  * "What are your governance boundaries?" was unsupported;
  * "What architecture information do you not know?" ran a knowledge retrieval.

Step 14 joins the EXISTING architecture and capability models (Steps 12-13) into
one consistent architecture self-understanding and answers the bounded
questions from that join. Representation only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.self_knowledge.capability_model import build_capability_model
from atlas.self_knowledge.operational_capabilities import (
    project_operational_capabilities,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path="atlas.memory.service.memory_manager_service",
            description="Memory retrieval, search, ranking, and storage.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search", "memory_store"],
            dependencies=["knowledge_base"],
        )
    )
    return registry


def _capability_model(*, external_model_available: bool = False):
    return build_capability_model(
        _registry(),
        None,
        None,
        operational_capabilities=project_operational_capabilities(
            external_provider=external_model_available
        ),
        external_model_available=external_model_available,
    )


def _architecture_model(*, external_model_available: bool = False):
    return build_architecture_model(
        _registry(), capability_model=_capability_model(
            external_model_available=external_model_available
        )
    )


def _service(*, external_model_available: bool = False):
    model = _capability_model(external_model_available=external_model_available)
    architecture = build_architecture_model(_registry(), capability_model=model)
    return BuiltinResponseService(
        capability_model_provider=lambda: model,
        architecture_model_provider=lambda: architecture,
    )


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
# 1. Capability ↔ architecture join
# ---------------------------------------------------------------------------


class TestCapabilityJoin:
    def test_registered_capability_has_component_owner(self):
        model = _architecture_model()
        entry = next(c for c in model.capabilities if c.name == "memory_search")
        assert entry.components == ("memory_service",)
        assert entry.state == "available"
        assert "memory_service" in entry.owner_evidence

    def test_operational_capability_has_route_owner_evidence(self):
        model = _architecture_model()
        entry = next(c for c in model.capabilities if c.name == "investigate")
        assert entry.components == ()
        assert entry.owner_evidence == ("atlas.conversation.investigation",)

    def test_governance_boundaries_are_grounded(self):
        model = _architecture_model()
        names = {g.capability for g in model.governance}
        assert "approve" in names and "execute" in names
        approve = next(g for g in model.governance if g.capability == "approve")
        assert approve.governing == "owner_approval"
        assert "OWNER approval" in approve.reason

    def test_knowledge_boundary_is_bounded(self):
        model = _architecture_model()
        assert model.knowledge_boundary is not None
        known = " ".join(model.knowledge_boundary.known)
        unknown = " ".join(model.knowledge_boundary.unknown)
        assert "component" in known and "capability" in known
        assert "Interfaces/contracts are not represented" in unknown
        assert model.unknown_state_count >= 0

    def test_unknown_state_counted(self):
        model = _architecture_model()
        unknown = [c for c in model.capabilities if c.state == "unknown"]
        assert len(unknown) == model.unknown_state_count

    def test_deterministic_and_serializable(self):
        import json

        first = _architecture_model().to_dict()
        second = _architecture_model().to_dict()
        assert first == second
        json.dumps(first)

    def test_step12_step13_behaviour_preserved(self):
        # The component↔capability mapping and the model limitations are intact.
        model = _architecture_model()
        component = next(c for c in model.components if c.name == "memory_service")
        assert "memory_search" in component.capability_names
        joined = " ".join(model.limitations)
        assert "Interfaces/contracts are not represented" in joined
        assert "State/data-flow is not represented" in joined
        assert model.locate("memory_search").matched_kind == "capability"

    def test_markdown_contains_new_sections(self):
        markdown = _architecture_model().to_markdown()
        assert "## Governance boundaries" in markdown
        assert "## Capabilities (ownership + state)" in markdown
        assert "## Knowledge boundary" in markdown


# ---------------------------------------------------------------------------
# 2. Conversation architecture questions
# ---------------------------------------------------------------------------


class TestConversationArchitectureQuestions:
    def test_ownership_question(self):
        message = _service().match_architecture_question("Which component owns memory_search?")
        assert message is not None
        assert message.metadata["architecture"]["kind"] == "ownership"
        assert "memory_service" in message.content

    def test_where_is_capability_implemented(self):
        message = _service().match_architecture_question(
            "Where is the investigation capability implemented?"
        )
        assert message is not None
        assert "atlas.conversation.investigation" in message.content
        assert "OPERATIONAL" in message.content

    def test_who_provides(self):
        message = _service().match_architecture_question("Who provides memory_store?")
        assert message is not None
        assert "memory_service" in message.content

    def test_component_responsibility(self):
        message = _service().match_architecture_question(
            "What is the responsibility of the memory_service component?"
        )
        assert message is not None
        assert "Memory retrieval" in message.content
        assert "atlas.memory.service" in message.content

    def test_unknown_component_is_reported_honestly(self):
        message = _service().match_architecture_question(
            "What is the responsibility of the frobnicator component?"
        )
        assert message is not None
        assert message.metadata["architecture"]["found"] is False
        assert "no registered component" in message.content

    def test_governance_boundaries(self):
        message = _service().match_architecture_question("What are your governance boundaries?")
        assert message is not None
        assert message.metadata["architecture"]["kind"] == "governance"
        assert "approve" in message.content
        assert "owner_approval" in message.content

    def test_knowledge_boundary_not_form(self):
        message = _service().match_architecture_question(
            "What architecture information do you not know?"
        )
        assert message is not None
        assert "Unknown / not represented:" in message.content

    def test_non_architecture_questions_are_not_hijacked(self):
        service = _service()
        for text in (
            "which component owns the storage layer?",
            "where is the payroll system implemented?",
            "How does a request flow through Atlas?",
            "What contracts or interfaces do your components expose?",
            "What is your architecture?",
        ):
            assert service.match_architecture_question(text) is None, text

    def test_no_model_is_unchanged(self):
        service = BuiltinResponseService()
        assert service.match_architecture_question("Which component owns memory_search?") is None

    def test_ownership_agrees_with_capability_contract(self):
        model = _capability_model()
        architecture = build_architecture_model(_registry(), capability_model=model)
        service = BuiltinResponseService(
            capability_model_provider=lambda: model,
            architecture_model_provider=lambda: architecture,
        )
        message = service.match_architecture_question("Which component owns memory_search?")
        entry = model.find("memory_search")
        assert entry.components[0] in message.content
        assert entry.state in message.content


# ---------------------------------------------------------------------------
# 3. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_architecture_model_joins_capabilities_and_governance(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            model = atlas.architecture_model()
            by_name = {c.name: c for c in model.capabilities}
            assert by_name["memory_search"].components
            assert by_name["investigate"].owner_evidence == (
                "atlas.conversation.investigation",
            )
            governed = {g.capability for g in model.governance}
            assert {"approve", "execute", "knowledge_acquisition"} <= governed
            assert model.knowledge_boundary is not None
            assert model.knowledge_boundary.unknown
        finally:
            atlas.shutdown()

    def test_ownership_question_reaches_the_join(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            contract = atlas.capability_contract("memory_search")
            message = atlas.chat("Which component owns memory_search?")
            assert message.metadata.get("architecture", {}).get("kind") == "ownership"
            assert contract["components"][0] in message.content
            assert contract["state"] in message.content
        finally:
            atlas.shutdown()

    def test_investigation_question_is_architecture_not_execution(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("Where is the investigation capability implemented?")
            assert message.metadata.get("architecture", {}).get("kind") == "ownership"
            assert "## Investigation" not in message.content
            assert message.metadata.get("investigation") is None
        finally:
            atlas.shutdown()

    def test_component_responsibility_from_registry(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "What is the responsibility of the memory_service component?"
            )
            assert message.metadata.get("architecture", {}).get("kind") == "component"
            assert "memory" in message.content.lower()
        finally:
            atlas.shutdown()

    def test_governance_and_knowledge_boundaries(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            governance = atlas.chat("What are your governance boundaries?")
            assert governance.metadata.get("architecture", {}).get("kind") == "governance"
            assert "approve" in governance.content
            boundary = atlas.chat("What architecture information do you not know?")
            assert boundary.metadata.get("architecture", {}).get("kind") == "knowledge_boundary"
            assert "not represented" in boundary.content
        finally:
            atlas.shutdown()

    def test_unknown_component_is_honest(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("What is the responsibility of the frobnicator component?")
            assert message.metadata.get("architecture", {}).get("found") is False
            assert "no registered component" in message.content
        finally:
            atlas.shutdown()

    def test_send_stream_parity(self, monkeypatch, tmp_path):
        text = "Which component owns memory_search?"
        a = _started_atlas(monkeypatch, tmp_path)
        try:
            sent = a.chat(text).content
        finally:
            a.shutdown()
        b = _started_atlas(monkeypatch, tmp_path)
        try:
            streamed = "".join(b.stream(text))
        finally:
            b.shutdown()
        assert sent == streamed

    def test_no_authority_or_repository_mutation(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before = atlas.component_registry.component_count
            for q in (
                "Which component owns memory_search?",
                "What are your governance boundaries?",
                "What architecture information do you not know?",
            ):
                message = atlas.chat(q)
                for key in ("approval", "execution", "promotion", "authorization"):
                    assert key not in message.metadata, key
            assert atlas.component_registry.component_count == before
            assert atlas.pending_promotion_reviews() == []
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()

    def test_step12_and_step13_surfaces_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # Step 12: capability contract still resolves operational capabilities.
            assert atlas.capability_contract("investigate")["state"] == "available"
            # Step 13: the capability-state question surface still answers.
            assert atlas.chat("Is investigation available?").metadata.get(
                "builtin_intent"
            ) == "capability_state"
        finally:
            atlas.shutdown()
