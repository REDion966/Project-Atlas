"""Step 13 — capability state & self-knowledge.

The baseline (real Atlas/kernel) showed the Step 12 unified capability model
represented capability DEFINITIONS and a coarse ``availability`` but did not
expose a grounded, explicit capability STATE:

  * a structural external-model-dependent capability (``ai_chat`` /
    ``model_routing``) reported ``available`` because its component was HEALTHY
    — even though no external model was configured and the limitation itself
    said it was unavailable — while the operational ``open_conversation`` (the
    same dependency class) correctly reported ``unavailable``;
  * there was no ``state``/``reason``/``blocked_by``/``governing`` at all, so a
    consumer had to parse limitation prose;
  * capability-STATE questions ("Is investigation available?", "What is the
    status of investigation?", "Which capabilities are unavailable?") were
    misrouted (a real investigation / knowledge retrieval) or unsupported.

Step 13 derives a bounded, grounded STATE from the SAME evidence the model
already projects and exposes it consistently through the kernel contract and the
conversation. It is representation only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.self_knowledge.capability_model import (
    CapabilityState,
    build_capability_model,
)
from atlas.self_knowledge.operational_capabilities import (
    OperationalCapability,
    all_operational_capabilities,
    project_operational_capabilities,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _registry() -> ComponentRegistry:
    registry = ComponentRegistry()
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
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path="atlas.memory.service.memory_manager_service",
            description="Memory retrieval.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="degraded_service",
            package="atlas.example",
            module_path="atlas.example.service",
            description="A degraded component.",
            status=ComponentStatus.DEGRADED,
            provided_capabilities=["degraded_cap"],
        )
    )
    return registry


def _model(*, external_model_available: bool, governed_wired: bool = True):
    caps = project_operational_capabilities(
        external_provider=external_model_available, governed_wired=governed_wired
    )
    return build_capability_model(
        _registry(),
        None,
        None,
        operational_capabilities=caps,
        external_model_available=external_model_available,
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
# 1. Grounded state derivation
# ---------------------------------------------------------------------------


class TestStateDerivation:
    def test_available_capability(self):
        entry = _model(external_model_available=True).find("memory_search")
        assert entry.state == CapabilityState.AVAILABLE.value
        assert "healthy" in entry.reason

    def test_unavailable_external_model_capability(self):
        entry = _model(external_model_available=False).find("ai_chat")
        assert entry.state == CapabilityState.UNAVAILABLE.value
        assert "external AI model" in entry.reason

    def test_external_model_capability_available_when_configured(self):
        entry = _model(external_model_available=True).find("ai_chat")
        assert entry.state == CapabilityState.AVAILABLE.value

    def test_partially_supported_from_degraded_component(self):
        entry = _model(external_model_available=True).find("degraded_cap")
        assert entry.state == CapabilityState.PARTIALLY_SUPPORTED.value
        assert "DEGRADED" in entry.reason

    def test_governed_capability(self):
        entry = _model(external_model_available=True).find("approve")
        assert entry.state == CapabilityState.GOVERNED.value
        assert entry.governing == "owner_approval"
        assert "OWNER approval" in entry.reason

    def test_unknown_capability_fails_closed(self):
        from atlas.reasoning.execution.registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("handler_only", lambda params: "x")
        model = build_capability_model(ComponentRegistry(), registry)
        entry = model.find("handler_only")
        assert entry.state == CapabilityState.UNKNOWN.value
        assert "insufficient evidence" in entry.reason

    def test_blocked_capability_reports_its_blocker(self):
        caps = (
            OperationalCapability(
                id="base",
                name="Base",
                description="A capability that is not available.",
                category="test",
                operations=("base",),
                evidence=("atlas.test",),
                available=False,
            ),
            OperationalCapability(
                id="depends_on_base",
                name="Depends on base",
                description="A capability that requires base.",
                category="test",
                operations=("depends",),
                evidence=("atlas.test",),
                available=True,
                requires=("base",),
            ),
        )
        model = build_capability_model(
            ComponentRegistry(), None, None, operational_capabilities=caps
        )
        entry = model.find("depends_on_base")
        assert entry.state == CapabilityState.BLOCKED.value
        assert entry.blocked_by == ("base",)
        assert "blocked" in entry.reason

    def test_state_counts_and_determinism(self):
        model = _model(external_model_available=False)
        first = model.to_dict()
        second = _model(external_model_available=False).to_dict()
        assert first == second
        assert dict(model.state_counts).get(CapabilityState.UNAVAILABLE.value, 0) >= 1
        assert dict(model.state_counts).get(CapabilityState.PARTIALLY_SUPPORTED.value) == 1

    def test_step12_fields_are_preserved(self):
        entry = _model(external_model_available=True).find("investigate")
        assert entry.category == "investigation"
        assert entry.operations == ("investigate",)
        assert any(s.kind == "operational_capability" for s in entry.sources)
        assert entry.dependency.value == "deterministic"


# ---------------------------------------------------------------------------
# 2. Conversation capability-state questions
# ---------------------------------------------------------------------------


class TestConversationStateQuestions:
    def _service(self, *, external_model_available: bool = False):
        model = _model(external_model_available=external_model_available)
        return BuiltinResponseService(capability_model_provider=lambda: model)

    def test_is_available(self):
        message = self._service().match_capability_state_question("Is investigation available?")
        assert message is not None
        assert message.metadata["builtin_intent"] == "capability_state"
        assert "available" in message.content
        assert message.metadata["capability_state"]["state"] == "available"

    def test_is_unavailable_with_reason(self):
        message = self._service().match_capability_state_question("Is open conversation enabled?")
        assert message is not None
        assert message.metadata["capability_state"]["state"] == "unavailable"
        assert "external AI model" in message.content

    def test_can_you_operation(self):
        message = self._service().match_capability_state_question("Can you investigate?")
        assert message is not None
        assert message.metadata["capability_state"]["name"] == "investigate"

    def test_why_question(self):
        message = self._service().match_capability_state_question("Why can't you research?")
        assert message is not None
        assert message.metadata["capability_state"]["name"] == "research"

    def test_inventory_of_unavailable(self):
        message = self._service().match_capability_state_question(
            "Which capabilities are unavailable?"
        )
        assert message is not None
        assert "open_conversation" in message.content
        assert message.metadata["capability_state"]["query"] == "unavailable"

    def test_governed_reported(self):
        message = self._service().match_capability_state_question(
            "What is the status of approve?"
        )
        assert message is not None
        assert message.metadata["capability_state"]["state"] == "governed"
        assert message.metadata["capability_state"]["governing"] == "owner_approval"

    def test_real_request_is_not_hijacked(self):
        service = self._service()
        # A request that names a concrete object keeps its existing route.
        assert service.match_capability_state_question(
            "Can you investigate the storage layer?"
        ) is None
        # An unknown name is not a capability-state question (fail closed).
        assert service.match_capability_state_question(
            "Is the storage layer available?"
        ) is None
        assert service.match_capability_state_question("Can you order me a laptop?") is None
        assert service.match_capability_state_question("Can you help me?") is None

    def test_no_model_is_unchanged(self):
        # Without the unified model wired, no state question is claimed.
        service = BuiltinResponseService()
        assert service.match_capability_state_question("Is investigation available?") is None

    def test_contract_and_conversation_agree(self):
        model = _model(external_model_available=False)
        service = BuiltinResponseService(capability_model_provider=lambda: model)
        message = service.match_capability_state_question("Is open conversation enabled?")
        entry = model.find("open_conversation")
        assert message.metadata["capability_state"]["state"] == entry.state
        assert message.metadata["capability_state"]["reason"] == entry.reason
        assert message.metadata["capability_state"]["availability"] == entry.availability.value


# ---------------------------------------------------------------------------
# 3. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_capability_contract_exposes_grounded_state(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            available = atlas.capability_contract("investigate")
            assert available["state"] == "available"
            assert available["reason"]

            unavailable = atlas.capability_contract("open_conversation")
            assert unavailable["state"] == "unavailable"
            assert "external AI model" in unavailable["reason"]

            # The structural external-model capability is unavailable too (the
            # Step 12 inconsistency: it used to report available).
            structural = atlas.capability_contract("ai_chat")
            assert structural["dependency"] == "external_model_dependent"
            assert structural["availability"] == "unavailable"
            assert structural["state"] == "unavailable"

            governed = atlas.capability_contract("approve")
            assert governed["state"] == "governed"
            assert governed["governing"] == "owner_approval"
        finally:
            atlas.shutdown()

    def test_unknown_is_truthful(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # A tool with no providing component has no state evidence.
            echo = atlas.capability_contract("echo")
            assert echo["found"] is True
            assert echo["state"] == "unknown"
        finally:
            atlas.shutdown()

    def test_conversation_state_agrees_with_kernel(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            contract = atlas.capability_contract("investigation")
            message = atlas.chat("Is investigation available?")
            assert message.metadata.get("builtin_intent") == "capability_state"
            assert contract["state"] in message.content
            assert contract["reason"] in message.content
            assert message.metadata["capability_state"]["name"] == contract["name"]
        finally:
            atlas.shutdown()

    def test_unavailable_question_is_answered_from_the_model(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("Which capabilities are unavailable?")
            assert message.metadata.get("builtin_intent") == "capability_state"
            assert "open_conversation" in message.content
        finally:
            atlas.shutdown()

    def test_state_reflects_configuration_change(self, monkeypatch, tmp_path):
        # Grounded: the SAME model derivation flips the external-model-dependent
        # capability when the provider configuration changes. No approval,
        # promotion, sandbox or governance control is bypassed.
        off = _model(external_model_available=False).find("ai_chat")
        on = _model(external_model_available=True).find("ai_chat")
        assert off.state == "unavailable"
        assert on.state == "available"

    def test_send_stream_parity(self, monkeypatch, tmp_path):
        text = "Is investigation available?"
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
            for q in ("Is investigation available?", "Which capabilities are unavailable?", "Can you approve?"):
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

    def test_step12_catalogue_is_intact(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            from atlas.self_knowledge.development_capabilities import (
                all_development_capabilities,
            )

            model = atlas.capability_model()
            # The kernel's operational surface is the Step 12 catalogue PLUS the
            # Command 6 DEVELOPMENT capability catalogue: it equals exactly the
            # DECLARED catalogues, so nothing is invented at runtime.
            assert model.operational_count == (
                len(all_operational_capabilities())
                + len(all_development_capabilities())
            )
            assert model.find("investigate") is not None
            assert model.find("plan").governing == "owner_approval"
        finally:
            atlas.shutdown()
