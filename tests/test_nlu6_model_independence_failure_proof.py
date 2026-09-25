"""NLU-6 — model-independence / failure-proof (public conversation path).

The repository defines this contract across several existing suites and reports
(``docs/INDEPENDENCE.md`` Phase 12, ``tests/test_conversational_independence.py``,
``tests/test_phase125_model_free_conversation.py``,
``tests/test_builtin_default_routing.py::TestNoProviderKernelStartup``,
``tests/test_phase123_model_seam_audit.py``):

* the conversational path is deterministic and Atlas-owned, with
  ``model_used = False`` and no provider HTTP ever attempted;
* external providers require explicit opt-in (``[ai].external_providers``) and
  remain optional, bounded, fail-soft seams;
* provider absence/failure never fabricates an answer and never becomes
  authoritative; unsupported/ambiguous/unauthorized requests stay honest and
  governed.

This module proves that contract for the full NLU surface (NLU-2 research
routing/relevance, NLU-3 dimension coverage, NLU-4 entity capture/context,
NLU-5 descriptive reference resolution, C5.1 self-knowledge, C6.1 validated
knowledge access) under three adverse provider conditions, through the real
public path — with NO production change.

Storage is isolated to a temporary database; the model-free nonce reuses the
repository's own Phase-12 environment primitive. Nothing here removes or
disables optional provider infrastructure.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.phase12_environment import BLOCKED_MODULES, model_free_environment

_TMP_DIR = Path(tempfile.mkdtemp(prefix="nlu6_"))
_TMP_DB = _TMP_DIR / "atlas_experience.db"
_FIXTURES = _TMP_DIR / "fixtures"
_FIXTURES.mkdir()
_FACT = _FIXTURES / "nlu6_device.md"
_FACT.write_text(
    "# Atlas Evidence Device (test fixture)\n\n"
    "The Atlas Evidence Device sensor count is 4.\n",
    encoding="utf-8",
)

_SAMSUNG = "Samsung Galaxy S26 Ultra"

#: The NLU surface exercised everywhere in this module (deterministic turns).
#: Intent expectations mirror the repository's existing suites
#: (``tests/test_conversational_independence.py``): "what can you do?" is the
#: bounded HELP surface; the inventory is reached by the capability wording.
DETERMINISTIC_TURNS: tuple[tuple[str, str], ...] = (
    ("hello", "greeting"),
    ("Who are you?", "identity"),
    ("what can you do?", "help"),
    ("What capabilities do you have?", "capabilities"),
    ("status", "status"),
    ("What are your current limitations?", "self_knowledge"),
    ("What do you know about your own architecture?", "architecture"),
    ("Explain what Atlas does.", "self_description"),
    ("what is the meaning of ??!", "unsupported"),
)

ALL_TURNS: tuple[str, ...] = tuple(text for text, _ in DETERMINISTIC_TURNS) + (
    "please invent a brand new physics engine and deploy it to production",
    "How many sensors does the Atlas Evidence Device have?",
    "what did you verify about?",
    f"What do you know about {_SAMSUNG}?",
    "Research the memory service, including memory storage and memory search "
    "of the atlas memory subsystem.",
    "Research the Samsung Galaxy S26 Ultra camera system.",
    "Use the information you researched earlier.",
)


class _RaisingProvider:
    """Existing seam (``tests/test_phase125_model_free_conversation.py``):
    a provider double that always raises."""

    def name(self) -> str:
        return "raising-provider"

    def chat(self, messages, model=None, timeout=None):  # noqa: ARG002
        raise RuntimeError("provider unavailable")

    def stream_chat(self, messages, model=None, timeout=None):  # noqa: ARG002
        raise RuntimeError("provider unavailable")

    def complete(self, prompt, model=None):  # noqa: ARG002
        raise RuntimeError("provider unavailable")

    def models(self):
        return []


@pytest.fixture(scope="module", autouse=True)
def _isolated_storage():
    """Point every SQLite store at a temporary database for this module."""
    import atlas.storage as storage_pkg

    saved: list[tuple[type, object]] = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = importlib.import_module(f"atlas.storage.{info.name}")
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                setattr(obj, "DEFAULT_DB_PATH", _TMP_DB)
    try:
        yield
    finally:
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


@pytest.fixture(scope="module")
def kernel():
    """One fully-wired kernel: no external provider configured (default)."""
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        atlas.shutdown()


@pytest.fixture(scope="module")
def raising_kernel():
    """A kernel whose active provider ALWAYS raises (provider failure state)."""
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    router = atlas._ai_manager._router
    router.registry.register(_RaisingProvider())
    router.use("raising-provider")
    try:
        yield atlas
    finally:
        atlas.shutdown()


@pytest.fixture
def provider_http():
    """Block AND record every provider HTTP route (unavailable-provider state)."""
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


def _conversation(atlas, text=None):
    service = atlas.container.get("conversation")
    return service


def _fresh(atlas):
    service = atlas.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service


def _send(atlas, text):
    return _fresh(atlas).send(text)


# ---------------------------------------------------------------------------
# A. NO PROVIDER CONFIGURED — deterministic operation (model-free environment)
# ---------------------------------------------------------------------------


class TestNoProviderConfigured:
    def test_deterministic_turns_answer_model_free(self, kernel):
        """Ordinary/self-knowledge/unsupported turns stay Atlas-owned."""
        with model_free_environment() as attempts:
            service = _fresh(kernel)
            for text, intent in DETERMINISTIC_TURNS:
                message = service.send(text)
                metadata = message.metadata or {}
                assert message.content, text
                assert metadata.get("builtin_intent") == intent, text
                assert metadata.get("model_used") is False, text
            assert attempts == [], "an outbound connection was attempted"

    def test_nlu2_research_routing_is_model_free(self, kernel):
        """NLU-2: research routing runs without a model or a provider.

        Reconciled (Evidence-Driven Improvement 3): the original assertion also
        pinned the research turn to the orchestration bridge. Improvement 3
        routes a single-clause research request through the existing local-first
        knowledge path instead. The invariant this test exists for is unchanged
        and still asserted: the turn is answered deterministically, with no
        model, no provider content, and no outbound connection attempt.
        """
        with model_free_environment() as attempts:
            message = _send(
                kernel,
                "Research the memory service, including memory storage of the "
                "atlas memory subsystem.",
            )
            metadata = message.metadata or {}
            assert metadata.get("model_used") is not True
            assert message.content.strip()
            assert "provider" not in message.content.lower()
            assert attempts == []

    def test_nlu3_dimension_request_is_model_free(self, kernel):
        """NLU-3: an enumerated-dimension request stays deterministic/honest.

        Reconciled (Evidence-Driven Improvement 3) — see the NLU-2 test above;
        the deterministic/model-free invariant is unchanged.
        """
        with model_free_environment() as attempts:
            message = _send(
                kernel,
                "Research the memory service, including memory storage, memory "
                "ranking, and memory search of the atlas memory subsystem.",
            )
            metadata = message.metadata or {}
            assert metadata.get("model_used") is not True
            assert message.content.strip()
            assert "provider" not in message.content.lower()
            assert attempts == []

    def test_nlu4_entity_capture_is_model_free(self, kernel):
        """NLU-4: conversational entity capture needs no model."""
        with model_free_environment() as attempts:
            service = _fresh(kernel)
            service.send(f"I am reviewing the {_SAMSUNG}.")
            names = [e.name for e in service._state_manager.state.captured_entities]
            assert names == [_SAMSUNG]
            assert attempts == []

    def test_nlu5_descriptive_resolution_is_model_free(self, kernel):
        """NLU-5: descriptive reference resolution is deterministic."""
        from atlas.conversation.conversation_state import ConversationState
        from atlas.conversation.entity_capture import CapturedEntity
        from atlas.conversation.reference_resolution import (
            ConversationReferenceResolver,
            ReferenceResolutionStatus,
        )

        with model_free_environment() as attempts:
            service = _fresh(kernel)
            service.send(f"I am reviewing the {_SAMSUNG}.")
            state = service._state_manager.state
            assert [e.name for e in state.captured_entities] == [_SAMSUNG]

            resolver = ConversationReferenceResolver()
            result = resolver.resolve_contextual(
                "Research the Samsung phone's camera system.", None, state
            )
            assert result.status is ReferenceResolutionStatus.RESOLVED
            assert result.resolved_value == _SAMSUNG
            assert result.resolved_field == "captured_entity"

            # ... and the public turn itself stays model-free.
            message = service.send("Research the Samsung phone's camera system.")
            assert (message.metadata or {}).get("model_used") is not True
            assert attempts == []

    def test_c5_1_self_knowledge_and_c6_1_knowledge_access_are_model_free(self, kernel):
        """C5.1 self-knowledge and C6.1 validated-knowledge access need no model."""
        acquired = kernel.acquisition_service.acquire(
            question="atlas evidence device sensor count", sources=[str(_FACT)]
        )
        assert acquired.status == "ok"

        with model_free_environment() as attempts:
            service = _fresh(kernel)
            knowledge = service.send(
                "What do you know about the Atlas Evidence Device sensor count?"
            )
            assert knowledge.metadata.get("builtin_intent") == "validated_knowledge"
            assert knowledge.metadata.get("validated_knowledge_status") == "ok"
            assert knowledge.metadata.get("model_used") is False

            limitations = service.send("What are your current limitations?")
            assert limitations.metadata.get("builtin_intent") == "self_knowledge"
            assert limitations.metadata.get("model_used") is False
            assert attempts == []

    def test_ambiguous_request_is_governed_not_guessed(self, kernel):
        """An ambiguous request is clarified, never invented (no model)."""
        with model_free_environment() as attempts:
            message = _send(
                kernel,
                "please invent a brand new physics engine and deploy it to production",
            )
            lowered = message.content.lower()
            assert "?" in message.content or "detail" in lowered
            assert "deployed" not in lowered
            assert (message.metadata or {}).get("model_used") is not True
            assert attempts == []

    def test_unsupported_requests_decline_honestly(self, kernel):
        with model_free_environment() as attempts:
            for text in (
                "what is the meaning of ??!",
                "How many sensors does the Atlas Evidence Device have?",
                "what did you verify about?",
            ):
                message = _send(kernel, text)
                lowered = message.content.lower()
                assert "without an external ai model" in lowered, text
                assert (message.metadata or {}).get("model_used") is False, text
            assert attempts == []

    def test_no_ai_sdk_is_imported_or_needed(self, kernel):
        """No external AI/model ecosystem is imported by the conversation path."""
        with model_free_environment() as attempts:
            _fresh(kernel).send("hello")
            for name in BLOCKED_MODULES:
                module = name.split(".")[0]
                assert module not in sys.modules, module
                with pytest.raises(ImportError):
                    importlib.import_module(module)
            assert attempts == []

    def test_stream_matches_send_without_a_model(self, kernel):
        service = _fresh(kernel)
        sent = service.send("who are you")
        chunks = list(service.stream("who are you"))
        assert chunks and "".join(chunks) == sent.content
        assert (sent.metadata or {}).get("model_used") is False


# ---------------------------------------------------------------------------
# B. PROVIDER UNAVAILABLE — HTTP blocked and recorded
# ---------------------------------------------------------------------------


class TestProviderUnavailable:
    def test_nlu_surface_answers_with_provider_http_blocked(self, kernel, provider_http):
        service = _fresh(kernel)
        for text, intent in DETERMINISTIC_TURNS:
            message = service.send(text)
            metadata = message.metadata or {}
            assert metadata.get("builtin_intent") == intent, text
            assert metadata.get("model_used") is False, text
        _assert_no_provider_http(provider_http)

    def test_research_and_knowledge_turns_survive_provider_http_blocked(
        self, kernel, provider_http
    ):
        service = _fresh(kernel)
        research = service.send(
            "Research the memory storage module of the atlas memory subsystem."
        )
        knowledge = service.send(
            "What do you know about the Atlas Evidence Device sensor count?"
        )
        assert research.content.strip()
        assert knowledge.metadata.get("builtin_intent") == "validated_knowledge"
        _assert_no_provider_http(provider_http)


# ---------------------------------------------------------------------------
# C. PROVIDER FAILURE — the active provider always raises
# ---------------------------------------------------------------------------


class TestProviderFailure:
    def test_raising_provider_never_becomes_the_answer(self, raising_kernel):
        service = _fresh(raising_kernel)
        for text, intent in DETERMINISTIC_TURNS:
            message = service.send(text)
            metadata = message.metadata or {}
            assert metadata.get("builtin_intent") == intent, text
            assert metadata.get("model_used") is False, text
            assert "provider unavailable" not in message.content, text
            assert "raising-provider" not in message.content, text

    def test_raising_provider_does_not_bypass_the_builtin_floor(self, raising_kernel):
        for text in ("what is the meaning of ??!", "blorptastic quux zizzle"):
            message = _fresh(raising_kernel).send(text)
            assert (message.metadata or {}).get("builtin_intent") == "unsupported", text
            assert (message.metadata or {}).get("model_used") is False, text

    def test_raising_provider_keeps_research_governed(self, raising_kernel):
        """A failing provider cannot manufacture a research result.

        Reconciled (Evidence-Driven Improvement 3): the original assertion also
        required the orchestration report shape. Improvement 3 answers a
        single-clause research request from the existing local-first knowledge
        path, which reports the retrieval's own honest outcome when nothing is
        validated. The invariant this test exists for is unchanged and still
        asserted: the answer is a deterministic, governed, provider-free
        outcome — never provider content, never a fabricated result.
        """
        message = _fresh(raising_kernel).send(
            "Research the Samsung Galaxy S26 Ultra camera system."
        )
        metadata = message.metadata or {}
        assert metadata.get("model_used") is not True
        lowered = message.content.lower()
        assert "provider" not in lowered
        assert message.content.strip()
        # Honest deterministic outcome (either the knowledge path's own
        # no-match/insufficiency report or the existing governed report).
        assert "no validated knowledge matched" in lowered or "could not complete" in lowered

    def test_no_exception_escapes_the_governed_path(self, raising_kernel):
        """Failure-proof: the whole NLU surface returns governed messages."""
        service = _fresh(raising_kernel)
        for text in ALL_TURNS:
            message = service.send(text)
            assert message.content.strip(), text
            assert message.role == "assistant", text
            assert (message.metadata or {}).get("model_used") is not True, text

    def test_raising_provider_keeps_nlu4_nlu5_deterministic(self, raising_kernel):
        service = _fresh(raising_kernel)
        service.send(f"I am reviewing the {_SAMSUNG}.")
        state = service._state_manager.state
        assert [e.name for e in state.captured_entities] == [_SAMSUNG]

        from atlas.conversation.reference_resolution import (
            ConversationReferenceResolver,
            ReferenceResolutionStatus,
        )

        result = ConversationReferenceResolver().resolve_contextual(
            "Research the Samsung phone's camera system.", None, state
        )
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_value == _SAMSUNG
        assert (service.send("what is its camera system?").metadata or {}).get(
            "model_used"
        ) is not True


# ---------------------------------------------------------------------------
# D. TRUTHFUL METADATA / PROVIDER STATE
# ---------------------------------------------------------------------------


class TestTruthfulMetadata:
    def test_model_used_is_explicitly_false_on_deterministic_turns(self, kernel):
        service = _fresh(kernel)
        for text, _intent in DETERMINISTIC_TURNS:
            metadata = service.send(text).metadata or {}
            assert metadata.get("model_used") is False, text
            assert metadata.get("builtin_response") is True, text

    def test_external_providers_defaults_off(self, kernel):
        """External providers are opt-in; the default active tier is Atlas-owned."""
        assert (
            kernel._config.get("ai", "external_providers", default=False) is False
        )
        router = kernel._ai_manager._router
        assert getattr(router, "external_providers", False) is False

    def test_orchestration_metadata_makes_no_model_claim(self, kernel):
        """A research answer is the deterministic step report, never model text."""
        message = _send(
            kernel,
            "Research the memory storage module of the atlas memory subsystem.",
        )
        metadata = message.metadata or {}
        assert metadata.get("model_used") is not True
        assert isinstance(metadata.get("orchestration"), dict)
        assert "model_used" not in metadata or metadata["model_used"] is False
        lowered = message.content.lower()
        assert lowered.startswith("done:") or "could not complete" in lowered
        assert "step-0000" in lowered or "steps:" in lowered


# ---------------------------------------------------------------------------
# E / F. EVIDENCE FAILURE + GOVERNANCE
# ---------------------------------------------------------------------------


class TestEvidenceFailureAndGovernance:
    def test_research_without_authorized_evidence_fails_honestly(self, kernel):
        message = _send(kernel, "Research the zeppelin maintenance schedule of Mars.")
        lowered = message.content.lower()
        assert "could not complete" in lowered or "no" in lowered
        assert "done:" not in lowered
        assert (message.metadata or {}).get("model_used") is not True

    def test_unauthorized_source_remains_denied_without_a_model(self, kernel):
        result = kernel.acquisition_service.acquire(
            question="atlas evidence device unauthorized probe",
            sources=["https://example.test/device"],
        )
        assert result.sources == ()
        assert result.claim_count == 0

    def test_no_credentials_are_exposed_by_deterministic_turns(self, kernel):
        service = _fresh(kernel)
        for text in ("hello", "status", "What are your current limitations?"):
            lowered = service.send(text).content.lower()
            for marker in ("api_key", "apikey", "password", "secret", "bearer "):
                assert marker not in lowered, text


# ---------------------------------------------------------------------------
# G. REPRODUCIBILITY / RESTART
# ---------------------------------------------------------------------------


class TestReproducibility:
    def test_behaviour_is_reproducible_after_restart_without_a_model(self, kernel):
        """A fresh kernel reproduces the same deterministic answers model-free."""
        from atlas.kernel.atlas import Atlas

        with model_free_environment() as attempts:
            atlas2 = Atlas()
            atlas2.start()
            try:
                service = atlas2.container.get("conversation")
                service._conversation = service._history.create()
                service._state_manager.clear()
                for text, intent in DETERMINISTIC_TURNS:
                    message = service.send(text)
                    assert (message.metadata or {}).get("builtin_intent") == intent, text
                    assert (message.metadata or {}).get("model_used") is False, text
                assert attempts == []
            finally:
                atlas2.shutdown()

    def test_boot_inside_a_model_free_environment_succeeds(self):
        """Atlas starts and answers with every AI ecosystem unimportable."""
        with model_free_environment() as attempts:
            from atlas.kernel.atlas import Atlas

            atlas = Atlas()
            atlas.start()
            try:
                message = atlas.chat("hello")
                assert message.content
                assert (message.metadata or {}).get("model_used") is False
                assert attempts == []
            finally:
                atlas.shutdown()
