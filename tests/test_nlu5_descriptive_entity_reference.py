"""NLU-5 — bounded descriptive entity reference resolution tests.

Deterministic and model-free: no provider, no kernel, no network.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import (
    ConversationState,
    ConversationStateManager,
)
from atlas.conversation.entity_capture import CapturedEntity
from atlas.conversation.reference_resolution import (
    ConversationReferenceResolver,
    ReferenceResolutionStatus,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.target_resolution import task_spec_to_execution_steps
from atlas.research.dimensions import extract_dimensions

_SAMSUNG = "Samsung Galaxy S26 Ultra"
_ZFOLD = "Samsung Galaxy Z Fold"
_IPHONE = "iPhone 17 Pro"


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


def _service() -> ConversationService:
    return ConversationService(
        _FakeAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
    )


# ---------------------------------------------------------------------------
# A-E: resolution shape
# ---------------------------------------------------------------------------


class TestDescriptiveResolution:
    def _resolve(self, text, *names):
        return ConversationReferenceResolver().resolve_contextual(
            text, None, _state(*names)
        )

    def test_A_unique_descriptive_match(self):
        result = self._resolve("Research the Samsung phone.", _SAMSUNG)
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "captured_entity"
        assert result.resolved_value == _SAMSUNG

    def test_B_possessive_descriptive_match(self):
        result = self._resolve("Research the Samsung phone's camera system.", _SAMSUNG)
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_value == _SAMSUNG

    def test_C_demonstrative_descriptive_match(self):
        result = self._resolve("Research this Samsung phone.", _SAMSUNG)
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_value == _SAMSUNG

    def test_D_case_normalization(self):
        assert (
            self._resolve("Research the SAMSUNG phone.", _SAMSUNG).status
            is ReferenceResolutionStatus.RESOLVED
        )
        assert (
            self._resolve("Research the samsung PHONE.", _SAMSUNG).resolved_value
            == _SAMSUNG
        )

    def test_E_generic_noun_alone_does_not_resolve(self):
        assert (
            self._resolve("Research the phone.", _SAMSUNG).status
            is not ReferenceResolutionStatus.RESOLVED
        )
        assert (
            self._resolve("Research the device.", _SAMSUNG).status
            is not ReferenceResolutionStatus.RESOLVED
        )

    def test_non_reference_turn_does_not_resolve(self):
        assert (
            self._resolve("Research smartphone cameras.", _SAMSUNG).status
            is not ReferenceResolutionStatus.RESOLVED
        )


# ---------------------------------------------------------------------------
# F-H: ambiguity / no antecedent
# ---------------------------------------------------------------------------


class TestAmbiguityAndNoAntecedent:
    def _resolve(self, text, *names):
        return ConversationReferenceResolver().resolve_contextual(
            text, None, _state(*names)
        )

    def test_F_ambiguous_descriptor(self):
        result = self._resolve("Research the Samsung phone.", _SAMSUNG, _ZFOLD)
        assert result.status is ReferenceResolutionStatus.AMBIGUOUS
        assert set(result.candidates) == {_SAMSUNG, _ZFOLD}

    def test_G_distinctive_descriptor_resolves(self):
        result = self._resolve("Research the Samsung phone.", _SAMSUNG, _IPHONE)
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_value == _SAMSUNG

    def test_H_no_captured_entity_does_not_resolve(self):
        assert (
            self._resolve("Research the Samsung phone.").status
            is not ReferenceResolutionStatus.RESOLVED
        )

    def test_explicitly_named_entities_are_not_a_descriptive_reference(self):
        # A statement that names both entities in full is not a reference and
        # must not be turned into an ambiguity clarification.
        result = self._resolve(
            f"I am comparing the {_SAMSUNG} and the {_ZFOLD}.", _SAMSUNG, _ZFOLD
        )
        assert result.status is not ReferenceResolutionStatus.RESOLVED
        message = _service().send(
            f"I am comparing the {_SAMSUNG} and the {_ZFOLD}."
        )
        assert "which of the products" not in message.content.lower()

    def test_ambiguous_descriptor_clarifies_through_the_service(self):
        service = _service()
        service.send(f"I am comparing the {_SAMSUNG} and the {_ZFOLD}.")
        message = service.send("Research the Samsung phone.")
        assert "which of the products" in message.content.lower()
        assert "could not complete" not in message.content.lower()

    def test_fresh_conversation_never_invents_an_entity(self):
        message = _service().send("Research the Samsung phone's camera system.")
        assert "samsung galaxy s26 ultra" not in message.content.lower()


# ---------------------------------------------------------------------------
# I-K: precedence + isolation
# ---------------------------------------------------------------------------


class TestPrecedenceAndIsolation:
    def test_I_explicit_current_turn_target_wins(self):
        service = _service()
        service.send(f"I am reviewing the {_SAMSUNG}.")
        spec = service._intake(f"Research the {_IPHONE} camera.", 2)
        spec, response = service._apply_reference_resolution(
            spec, f"Research the {_IPHONE} camera."
        )
        assert response is None
        resolved = spec.context.get("resolved_reference")
        assert resolved is None or resolved.get("value") == _IPHONE
        steps = task_spec_to_execution_steps(spec)
        assert _IPHONE in steps[0].inputs["question"]
        assert not steps[0].inputs["question"].startswith(f"{_SAMSUNG}:")

    def test_J_existing_nlu4_references_still_resolve(self):
        for text in (
            "Research its camera system.",
            "Research this phone.",
            "Research this phone's camera system.",
        ):
            result = ConversationReferenceResolver().resolve_contextual(
                text, None, _state(_SAMSUNG)
            )
            assert result.status is ReferenceResolutionStatus.RESOLVED, text
            assert result.resolved_value == _SAMSUNG, text

    def test_K_context_isolation(self):
        a = ConversationStateManager()
        a.record_captured_entities((CapturedEntity(name=_SAMSUNG),))
        b = ConversationStateManager()
        assert b.state.captured_entities == ()
        assert (
            ConversationReferenceResolver()
            .resolve_contextual("Research the Samsung phone.", None, b.state)
            .status
            is not ReferenceResolutionStatus.RESOLVED
        )


# ---------------------------------------------------------------------------
# L: research integration
# ---------------------------------------------------------------------------


class TestResearchIntegration:
    def test_L_resolved_descriptive_reference_and_dimensions(self):
        service = _service()
        service.send(f"I am reviewing the {_SAMSUNG}.")
        text = "Research the Samsung phone's camera system, battery, and display."
        spec = service._intake(text, 2)
        spec, response = service._apply_reference_resolution(spec, text)
        assert response is None
        assert spec.context.get("resolved_reference") == {
            "field": "captured_entity",
            "value": _SAMSUNG,
        }
        steps = task_spec_to_execution_steps(spec)
        question = steps[0].inputs["question"]
        assert question.startswith(f"{_SAMSUNG}: ")
        assert extract_dimensions(question) == ("camera system", "battery", "display")
