"""Phase 12.5 — Model-Free Conversation → Reasoning → Planning.

Validation result: the Atlas-owned conversational path is deterministic and
model-free. With every external AI SDK unimportable and the network refused,
ordinary conversation answers from the built-in deterministic engine
(``model_used: False``), self-knowledge questions are answered from Atlas's own
architecture model, ambiguity triggers a clarification request, and unsupported
requests are declined honestly — never fabricated.
"""

from __future__ import annotations

import pytest

from tests.phase12_environment import model_free_environment


@pytest.fixture(scope="module")
def model_free_kernel():
    with model_free_environment() as attempts:
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            yield atlas, attempts
        finally:
            atlas.shutdown()


def _reply(atlas, text):
    message = atlas.chat(text)
    content = str(getattr(message, "content", message))
    metadata = dict(getattr(message, "metadata", {}) or {})
    return content, metadata


class TestPhase125ModelFreeConversation:
    def test_ordinary_conversation_is_served_deterministically(self, model_free_kernel):
        atlas, _ = model_free_kernel
        content, metadata = _reply(atlas, "hello")
        assert content.strip()
        assert metadata.get("model_used") is False
        assert metadata.get("builtin_response") is True

    def test_self_knowledge_question_answered_from_the_architecture_model(
        self, model_free_kernel
    ):
        atlas, _ = model_free_kernel
        content, metadata = _reply(
            atlas, "what do you know about your own architecture?"
        )
        assert "architecture" in content.lower()
        assert metadata.get("model_used") is False
        assert metadata.get("builtin_intent") == "architecture"

    def test_ambiguous_request_asks_for_clarification_instead_of_guessing(
        self, model_free_kernel
    ):
        atlas, _ = model_free_kernel
        content, _metadata = _reply(
            atlas, "please invent a brand new physics engine and deploy it to production"
        )
        lowered = content.lower()
        assert "detail" in lowered or "?" in content
        assert "deployed" not in lowered  # never claims an action happened

    def test_unsupported_request_is_declined_honestly(self, model_free_kernel):
        atlas, _ = model_free_kernel
        content, metadata = _reply(atlas, "what is the meaning of ??!")
        lowered = content.lower()
        assert "cannot" in lowered or "unsupported" in lowered or "do not" in lowered
        assert metadata.get("model_used") is False

    def test_conversation_makes_no_outbound_connection(self, model_free_kernel):
        atlas, attempts = model_free_kernel
        _reply(atlas, "hello")
        _reply(atlas, "who are you?")
        assert attempts == []

    def test_reasoning_eligibility_is_computed_deterministically(self, model_free_kernel):
        atlas, _ = model_free_kernel
        # The unsupported path still reports its deterministic reasoning
        # eligibility analysis, proving reasoning ran without a model.
        _content, metadata = _reply(atlas, "how does your memory system work?")
        eligibility = metadata.get("reasoning_eligibility")
        assert isinstance(eligibility, dict)
        assert eligibility.get("eligible") is True

    def test_provider_failure_yields_an_honest_deterministic_answer(self):
        # A provider double that ALWAYS raises: the conversation must still
        # answer deterministically and must never leak or fabricate a
        # provider-looking answer.
        with model_free_environment() as attempts:
            from atlas.kernel.atlas import Atlas

            atlas = Atlas()
            atlas.start()
            try:
                class _Raising:
                    def name(self):
                        return "raising-provider"

                    def chat(self, messages, model=None, timeout=None):  # noqa: ARG002
                        raise RuntimeError("provider unavailable")

                    def stream_chat(self, messages, model=None, timeout=None):  # noqa: ARG002
                        raise RuntimeError("provider unavailable")

                    def complete(self, prompt, model=None):  # noqa: ARG002
                        raise RuntimeError("provider unavailable")

                    def models(self):
                        return []

                router = atlas._ai_manager._router
                router.registry.register(_Raising())
                router.use("raising-provider")

                content, metadata = _reply(atlas, "hello")
                assert content.strip()
                assert metadata.get("model_used") is False
                assert "provider unavailable" not in content
                assert attempts == []
            finally:
                atlas.shutdown()
