"""NLU-4 — bounded conversational entity capture & reference resolution tests.

Deterministic and model-free: no provider, no kernel, no network.
"""

from __future__ import annotations

from dataclasses import replace

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import (
    MAX_CAPTURED_ENTITIES,
    ConversationState,
    ConversationStateManager,
)
from atlas.conversation.entity_capture import (
    CapturedEntity,
    capture_named_entities,
)
from atlas.conversation.reference_resolution import (
    ConversationReferenceResolver,
    ReferenceResolutionStatus,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.target_resolution import task_spec_to_execution_steps
from atlas.research.dimensions import extract_dimensions


class _FakeAI:
    def chat(self, *args, **kwargs):
        raise RuntimeError("no provider")

    def stream_chat(self, *args, **kwargs):
        def _gen():
            raise RuntimeError("no provider")
            yield ""  # pragma: no cover

        return _gen()


def _state(*names: str) -> ConversationState:
    return ConversationState(
        captured_entities=tuple(
            CapturedEntity(name=n, normalized=n.lower()) for n in names
        )
    )


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


class TestEntityCapture:
    def test_multi_word_product_is_captured(self):
        assert capture_named_entities(
            "I am reviewing the Samsung Galaxy S26 Ultra."
        ) == ("Samsung Galaxy S26 Ultra",)

    def test_brand_with_internal_capital_is_captured(self):
        assert capture_named_entities("I am reviewing the iPhone 17 Pro.") == (
            "iPhone 17 Pro",
        )
        assert capture_named_entities("I am reviewing a Dell XPS laptop.") == (
            "Dell XPS",
        )

    def test_two_entities_in_one_turn(self):
        assert capture_named_entities(
            "I am comparing the Samsung Galaxy S26 Ultra and iPhone 17 Pro."
        ) == ("Samsung Galaxy S26 Ultra", "iPhone 17 Pro")

    def test_pronouns_and_prose_are_not_captured(self):
        for text in (
            "Research its camera system.",
            "Research this phone's camera system.",
            "Research the Samsung phone's camera system.",
            "What is its camera sensor size?",
            "Hello, how are you today?",
            "Research the memory architecture.",
            "Please fix the bug in the login flow.",
        ):
            assert capture_named_entities(text) == (), text

    def test_single_capitalised_word_is_not_enough(self):
        # An ordinary capitalised word must not become an entity.
        assert capture_named_entities("Research Python today.") == ()

    def test_non_product_entity_is_captured(self):
        assert capture_named_entities("I met Alice Johnson at the office.") == (
            "Alice Johnson",
        )


# ---------------------------------------------------------------------------
# Conversation-scoped state
# ---------------------------------------------------------------------------


class TestCapturedEntityState:
    def test_record_and_deduplicate(self):
        manager = ConversationStateManager()
        manager.record_captured_entities((CapturedEntity(name="A1 B2"),))
        manager.record_captured_entities((CapturedEntity(name="a1 b2"),))
        assert len(manager.state.captured_entities) == 1
        assert manager.state.captured_entities[0].normalized == "a1 b2"

    def test_most_recent_mention_moves_to_the_end(self):
        manager = ConversationStateManager()
        manager.record_captured_entities((CapturedEntity(name="A1 B2"),))
        manager.record_captured_entities((CapturedEntity(name="C3 D4"),))
        manager.record_captured_entities((CapturedEntity(name="A1 B2"),))
        assert [e.name for e in manager.state.captured_entities] == ["C3 D4", "A1 B2"]

    def test_bounded(self):
        manager = ConversationStateManager()
        for index in range(MAX_CAPTURED_ENTITIES + 4):
            manager.record_captured_entities(
                (CapturedEntity(name=f"Brand{index} X1"),)
            )
        assert len(manager.state.captured_entities) == MAX_CAPTURED_ENTITIES

    def test_to_dict_is_json_safe_and_round_trips_through_update(self):
        manager = ConversationStateManager()
        manager.record_captured_entities((CapturedEntity(name="A1 B2"),))
        assert manager.state.to_dict()["captured_entities"][0]["name"] == "A1 B2"
        updated = manager.update(current_subject="topic")
        assert isinstance(updated.captured_entities[0], CapturedEntity)

    def test_state_is_conversation_scoped(self):
        a = ConversationStateManager()
        b = ConversationStateManager()
        a.record_captured_entities((CapturedEntity(name="A1 B2"),))
        assert b.state.captured_entities == ()

    def test_malformed_entities_are_ignored(self):
        manager = ConversationStateManager()
        manager.record_captured_entities((object(),))
        assert manager.state.captured_entities == ()


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------


class TestCapturedEntityResolution:
    def _resolve(self, text, *names):
        return ConversationReferenceResolver().resolve_contextual(
            text, None, _state(*names)
        )

    def test_its_resolves_to_the_single_captured_entity(self):
        result = self._resolve(
            "Research its camera system.", "Samsung Galaxy S26 Ultra"
        )
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "captured_entity"
        assert result.resolved_value == "Samsung Galaxy S26 Ultra"

    def test_demonstrative_resolves(self):
        for text in ("Research this phone's camera system.", "Research this phone."):
            result = self._resolve(text, "Samsung Galaxy S26 Ultra")
            assert result.status is ReferenceResolutionStatus.RESOLVED, text

    def test_two_entities_are_ambiguous(self):
        result = self._resolve(
            "Research its camera system.", "Samsung Galaxy S26 Ultra", "iPhone 17 Pro"
        )
        assert result.status is ReferenceResolutionStatus.AMBIGUOUS

    def test_no_entity_is_unresolved(self):
        assert (
            self._resolve("Research its camera system.").status
            is ReferenceResolutionStatus.UNRESOLVED
        )

    def test_non_reference_turn_is_unresolved(self):
        assert (
            self._resolve(
                "Research smartphone cameras.", "Samsung Galaxy S26 Ultra"
            ).status
            is ReferenceResolutionStatus.UNRESOLVED
        )

    def test_investigation_candidate_still_wins(self):
        # Existing behavior must not be overridden by captured entities.
        from atlas.conversation.conversation_context import build_conversation_context
        from atlas.conversation.message import Message

        context = build_conversation_context(
            [Message(role="user", content="Investigate the reference resolution flow.")]
        )
        result = ConversationReferenceResolver().resolve_contextual(
            "Research its camera system.",
            context,
            _state("Samsung Galaxy S26 Ultra"),
        )
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field != "captured_entity"


# ---------------------------------------------------------------------------
# Conversation-path capture + resolution
# ---------------------------------------------------------------------------


class TestConversationPath:
    def _service(self) -> ConversationService:
        return ConversationService(
            _FakeAI(),
            task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
        )

    def test_turn_one_captures_and_turn_two_resolves(self):
        service = self._service()
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        captured = service.state_manager.state.captured_entities
        assert [e.name for e in captured] == ["Samsung Galaxy S26 Ultra"]
        assert captured[0].turn_id  # bounded provenance

        spec = service._intake("Research its camera system.", 2)
        spec, response = service._apply_reference_resolution(
            spec, "Research its camera system."
        )
        assert response is None
        assert spec.context.get("resolved_reference") == {
            "field": "captured_entity",
            "value": "Samsung Galaxy S26 Ultra",
        }

    def test_no_antecedent_does_not_resolve(self):
        service = self._service()
        spec = service._intake("Research its camera system.", 0)
        spec, _ = service._apply_reference_resolution(spec, "Research its camera system.")
        assert "resolved_reference" not in spec.context

    def test_two_entities_do_not_resolve(self):
        service = self._service()
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        service.send("I am also comparing it with the iPhone 17 Pro.")
        spec = service._intake("Research its camera system.", 3)
        spec, _ = service._apply_reference_resolution(spec, "Research its camera system.")
        assert "resolved_reference" not in spec.context


# ---------------------------------------------------------------------------
# Research propagation
# ---------------------------------------------------------------------------


class TestResearchPropagation:
    def test_resolved_entity_is_carried_into_the_research_question(self):
        spec = TaskIntake().intake("Research its camera system.")
        spec = replace(
            spec,
            context={
                **spec.context,
                "resolved_reference": {
                    "field": "captured_entity",
                    "value": "Samsung Galaxy S26 Ultra",
                },
            },
        )
        steps = task_spec_to_execution_steps(spec)
        assert steps is not None
        assert steps[0].inputs["question"] == (
            "Samsung Galaxy S26 Ultra: Research its camera system."
        )

    def test_without_resolved_reference_question_is_unchanged(self):
        spec = TaskIntake().intake("Research the memory architecture.")
        steps = task_spec_to_execution_steps(spec)
        assert steps is not None
        assert steps[0].inputs["question"] == spec.intent

    def test_dimensions_survive_the_resolved_subject_prefix(self):
        assert extract_dimensions(
            "Samsung Galaxy S26 Ultra: Research its camera specifications, "
            "stabilization, and autofocus."
        ) == ("camera specifications", "stabilization", "autofocus")
