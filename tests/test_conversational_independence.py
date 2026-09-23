"""Master Roadmap 1.12 — conversational independence (public path).

Proves the PRODUCTION conversational path — ``Atlas.start()`` → ``Atlas.chat()``
/ ``Atlas.stream()`` — needs no external AI model: every provider HTTP route is
blocked AND asserted never to be touched, while the Atlas-owned deterministic
surfaces answer. No model is required, contacted, or authoritative.

This is the kernel-level companion to the service-level suites
(``tests/test_builtin_default_routing.py``, ``tests/test_model_independence_p6.py``).
Those prove the contract on a ``ConversationService``; this suite proves it on
the real composed kernel through the public entry point.

Boundary: no network, no provider, no repository mutation. The kernel is booted
once per module against an isolated evolution database.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.test_durable_guided_improvement import _storage_class


@pytest.fixture(scope="module")
def atlas(tmp_path_factory):
    """One real, fully-started Atlas with isolated evolution storage."""
    import atlas.kernel.atlas as kernel_mod

    mp = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("conversational_independence")
    mp.setattr(kernel_mod, "SQLiteEvolutionStorage", _storage_class(tmp_path))
    kernel = kernel_mod.Atlas()
    kernel.start()
    try:
        yield kernel
    finally:
        kernel.shutdown()
        mp.undo()


@pytest.fixture
def provider_http():
    """Block and RECORD every provider HTTP route.

    A MagicMock (not a raising side-effect) is used so an attempted provider
    call is observable via ``call_count`` even if the service swallows the
    error. ``Session()`` never being constructed means no session-based
    provider path can run either.
    """
    posts = patch("requests.post", side_effect=ConnectionError("no network"))
    gets = patch("requests.get", side_effect=ConnectionError("no network"))
    sessions = patch("requests.Session")
    post, get, session = posts.start(), gets.start(), sessions.start()
    try:
        yield post, get, session
    finally:
        posts.stop()
        gets.stop()
        sessions.stop()


def _assert_no_provider_http(provider_http) -> None:
    post, get, session = provider_http
    assert post.call_count == 0, "provider HTTP (requests.post) was attempted"
    assert get.call_count == 0, "provider HTTP (requests.get) was attempted"
    assert session.call_count == 0, "a provider HTTP session was constructed"


class TestKernelConversationalIndependence:
    """Casual conversation is Atlas-owned and provider-free."""

    CASUAL = (
        ("hello", "greeting"),
        ("who are you", "identity"),
        ("what can you do?", "help"),
        ("status", "status"),
    )

    def test_casual_turns_answered_without_any_provider(self, atlas, provider_http):
        for text, intent in self.CASUAL:
            message = atlas.chat(text)
            metadata = message.metadata or {}
            assert message.content, text
            assert metadata.get("builtin_intent") == intent, text
            assert metadata.get("model_used") is False, text
        _assert_no_provider_http(provider_http)

    def test_self_knowledge_turn_answered_without_any_provider(
        self, atlas, provider_http
    ):
        message = atlas.chat(
            "Which parts of your architecture are responsible for memory, "
            "reasoning, research, and evolution?"
        )
        metadata = message.metadata or {}
        assert metadata.get("builtin_intent") == "architecture"
        assert metadata.get("model_used") is False
        assert "architecture self-knowledge" in message.content
        _assert_no_provider_http(provider_http)

    def test_declined_turn_needs_no_model_either(self, atlas, provider_http):
        """Even the bounded no-answer notice is produced without a provider."""
        message = atlas.chat("blorptastic quux zizzle frobnicate")
        metadata = message.metadata or {}
        assert message.content
        assert metadata.get("model_used") is False
        assert metadata.get("builtin_intent") == "unsupported"
        _assert_no_provider_http(provider_http)

    def test_self_description_turn_answered_without_any_provider(
        self, atlas, provider_http
    ):
        """Phase 2.9 — "what does Atlas do" is Atlas-owned self-knowledge."""
        message = atlas.chat("Explain what Atlas does.")
        metadata = message.metadata or {}
        assert metadata.get("builtin_intent") == "self_description"
        assert metadata.get("model_used") is False
        assert "I am Atlas" in message.content
        _assert_no_provider_http(provider_http)

    def test_stream_is_provider_free_and_matches_send(self, atlas, provider_http):
        text = "who are you"
        sent = atlas.chat(text)
        chunks = list(atlas.stream(text))
        assert chunks
        assert "".join(chunks) == sent.content
        _assert_no_provider_http(provider_http)
