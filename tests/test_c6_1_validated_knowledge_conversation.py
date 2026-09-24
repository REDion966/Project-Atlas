"""C6.1 — Conversational access to EXISTING validated knowledge.

C6.1 is an integration/access step, not a new knowledge system. These tests prove
that the already-existing, evidence-validated, provenance-carrying, persistent
knowledge capability is reachable through the real public path
(``ConversationService.send``), that the access is strictly READ-ONLY, and that
every pre-existing conversational intent keeps its behaviour.

The fixture knowledge is produced by the EXISTING acquisition service from a
test-only deterministic fixture file in a temporary directory ("Atlas Evidence
Device"), and every SQLite store is pointed at a fresh temporary database, so
neither production data nor production knowledge is touched.
"""

from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_VALIDATED_KNOWLEDGE,
    BuiltinResponseService,
)
from atlas.kernel.atlas import Atlas
from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever

_TMP_DIR = Path(tempfile.mkdtemp(prefix="c6_1_"))
_TMP_DB = _TMP_DIR / "atlas_experience.db"

#: Test-only deterministic fixture (same synthetic subject as the C6 evidence
#: fixture: facts that cannot be confused with real-world knowledge).
_FACT = _TMP_DIR / "evidence_device_a.md"
_FACT.write_text(
    "# Atlas Evidence Device (test fixture)\n\n"
    "The Atlas Evidence Device sensor count is 4.\n"
    "The Atlas Evidence Device operating mode is bounded test mode.\n",
    encoding="utf-8",
)

_ACQUIRE_QUESTION = "atlas evidence device sensor count operating mode"
_TOPIC = "the Atlas Evidence Device"
_TOPIC_QUERY = "atlas evidence device"


def _patch_default_db_paths(new_path: Path) -> list[tuple[type, object]]:
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
                setattr(obj, "DEFAULT_DB_PATH", new_path)
    return saved


@pytest.fixture(scope="module")
def kernel():
    saved = _patch_default_db_paths(_TMP_DB)
    atlas = Atlas()
    atlas.start()
    try:
        result = atlas.acquisition_service.acquire(
            question=_ACQUIRE_QUESTION, sources=[str(_FACT)]
        )
        assert result.status == "ok"
        assert result.claim_count > 0
        yield atlas
    finally:
        try:
            atlas.shutdown()
        except Exception:  # noqa: BLE001
            pass
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


def _conversation(kernel):
    service = kernel.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service


def _send(kernel, text):
    return _conversation(kernel).send(text)


def _counts(kernel) -> tuple[int, int, int]:
    storage = kernel._research_storage
    return (
        len(storage.load_claims()),
        len(storage.load_verifications()),
        len(storage.load_citations()),
    )


# ---------------------------------------------------------------------------
# A. BASIC RETRIEVAL (public path)
# ---------------------------------------------------------------------------


class TestBasicRetrieval:
    def test_validated_claim_is_returned_through_the_public_path(self, kernel):
        """An already-validated claim is reachable from a conversational turn."""
        message = _send(kernel, f"What do you know about {_TOPIC}?")
        assert message.metadata.get("builtin_intent") == BUILTIN_INTENT_VALIDATED_KNOWLEDGE
        assert "bounded test mode" in message.content
        assert message.metadata.get("validated_knowledge_status") == "ok"
        assert message.metadata.get("validated_query") == _TOPIC_QUERY

    def test_returned_claim_reports_its_validation_status(self, kernel):
        """The answer states that the knowledge is validated (SUPPORTED)."""
        message = _send(kernel, f"What do you know about {_TOPIC}?")
        assert "Validated claim (SUPPORTED)" in message.content
        assert "validated knowledge store" in message.content

    def test_returned_citation_is_preserved(self, kernel):
        """Source attribution from the existing citation records is preserved."""
        message = _send(kernel, f"What do you know about {_TOPIC}?")
        assert _FACT.name in message.content

    def test_answer_is_labelled_as_read_only_and_model_free(self, kernel):
        message = _send(kernel, f"What do you know about {_TOPIC}?")
        assert "read-only retrieval" in message.content
        assert message.metadata.get("model_used") is False


# ---------------------------------------------------------------------------
# B. NATURAL-LANGUAGE VARIANTS (bounded cue family)
# ---------------------------------------------------------------------------


class TestNaturalLanguageVariants:
    @pytest.mark.parametrize(
        "template",
        [
            "What do you know about {topic}?",
            "What do you remember about {topic}?",
            "What did you find about {topic}?",
            "What did you learn about {topic}?",
            "What verified information do you have about {topic}?",
            "What information did you verify about {topic}?",
            "Do you remember {topic}?",
        ],
    )
    def test_bounded_cue_variants_reach_validated_knowledge(self, kernel, template):
        message = _send(kernel, template.format(topic=_TOPIC))
        assert (
            message.metadata.get("builtin_intent")
            == BUILTIN_INTENT_VALIDATED_KNOWLEDGE
        ), template
        assert "bounded test mode" in message.content, template
        assert message.metadata.get("model_used") is False


# ---------------------------------------------------------------------------
# C. EMPTY / NO TOPIC (fail honestly / fail closed)
# ---------------------------------------------------------------------------


class TestEmptyAndNoTopic:
    def test_unknown_topic_reports_no_validated_knowledge(self, kernel):
        """An unknown topic is reported honestly as an empty result."""
        message = _send(
            kernel,
            "What verified information do you have about zeppelin maintenance schedules?",
        )
        assert message.metadata.get("builtin_intent") == BUILTIN_INTENT_VALIDATED_KNOWLEDGE
        assert message.metadata.get("validated_knowledge_status") == "empty"
        assert "No validated knowledge matched" in message.content
        assert "status: empty" in message.content
        assert "bounded test mode" not in message.content

    def test_empty_result_does_not_research_or_guess(self, kernel):
        """Nothing is acquired, inferred, or invented for an empty result."""
        message = _send(kernel, "What did you find about quantum flux capacitors?")
        assert "No validated knowledge matched" in message.content
        assert "nothing is acquired, inferred, or invented" in message.content
        assert not (message.metadata or {}).get("orchestration")

    def test_no_topic_fails_closed(self, kernel):
        """A cue without a usable topic declines instead of querying broadly."""
        message = _send(kernel, "What did you verify about?")
        assert message.metadata.get("builtin_intent") != BUILTIN_INTENT_VALIDATED_KNOWLEDGE
        assert message.metadata.get("validated_query") is None

    def test_bare_shared_cue_keeps_existing_recall_behaviour(self, kernel):
        """A shared cue with nothing validated still uses the existing recall."""
        message = _send(kernel, "do you remember zzzqqqx_no_such_topic")
        assert message.metadata.get("builtin_intent") == "recall"
        assert "No memory or knowledge entry matched" in message.content


# ---------------------------------------------------------------------------
# D. STORE UNAVAILABLE (fail closed, no fallback)
# ---------------------------------------------------------------------------


class TestStoreUnavailable:
    @staticmethod
    def _unavailable_service():
        # The real retriever over an absent store is the authoritative
        # ``store_unavailable`` path (fail closed).
        retriever = ValidatedKnowledgeRetriever(None)
        return BuiltinResponseService(
            validated_knowledge_provider=retriever.retrieve,
        )

    def test_store_unavailable_is_reported_honestly(self):
        service = self._unavailable_service()
        message = service.respond("What verified information do you have about memory storage?")
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_VALIDATED_KNOWLEDGE
        assert message.metadata["validated_knowledge_status"] == "store_unavailable"
        assert "unavailable" in message.content.lower()
        assert message.metadata["model_used"] is False

    def test_store_unavailable_does_not_fall_back_to_other_stores(self):
        """It must not answer from memory, state, or a model instead."""

        class _Memory:
            def search(self, keyword=None, limit=3):  # pragma: no cover - guard
                raise AssertionError("memory store must not be consulted")

        class _Knowledge:
            def query(self, text):  # pragma: no cover - guard
                raise AssertionError("knowledge store must not be consulted")

        service = BuiltinResponseService(
            memory_service=_Memory(),
            knowledge_manager=_Knowledge(),
            validated_knowledge_provider=ValidatedKnowledgeRetriever(None).retrieve,
        )
        message = service.respond("What did you find about memory storage?")
        assert message is not None
        assert message.metadata["validated_knowledge_status"] == "store_unavailable"
        assert "No memory or knowledge entry matched" not in message.content

    def test_provider_failure_declines(self):
        """A raising provider fails closed (never an invented answer)."""

        def _boom(_query):
            raise RuntimeError("store failure")

        service = BuiltinResponseService(validated_knowledge_provider=_boom)
        message = service.respond("What did you find about memory storage?")
        assert message is not None
        assert message.metadata["builtin_intent"] != BUILTIN_INTENT_VALIDATED_KNOWLEDGE


# ---------------------------------------------------------------------------
# E. READ-ONLY GUARANTEE
# ---------------------------------------------------------------------------


class TestReadOnly:
    def test_successful_retrieval_does_not_mutate_validated_knowledge(self, kernel):
        before = _counts(kernel)
        message = _send(kernel, f"What do you know about {_TOPIC}?")
        assert message.metadata.get("builtin_intent") == BUILTIN_INTENT_VALIDATED_KNOWLEDGE
        assert _counts(kernel) == before

    def test_successful_retrieval_creates_no_knowledge_or_memory_record(self, kernel):
        knowledge_before = len(kernel._knowledge_manager.query("atlas evidence device"))
        memory_before = len(kernel._memory_service.list_memories())
        _send(kernel, f"What did you find about {_TOPIC}?")
        assert len(kernel._knowledge_manager.query("atlas evidence device")) == knowledge_before
        assert len(kernel._memory_service.list_memories()) == memory_before

    def test_empty_retrieval_does_not_mutate_validated_knowledge(self, kernel):
        before = _counts(kernel)
        _send(kernel, "What verified information do you have about zeppelin maintenance?")
        assert _counts(kernel) == before


# ---------------------------------------------------------------------------
# F. USER ASSERTIONS ARE NOT KNOWLEDGE
# ---------------------------------------------------------------------------


class TestUserAssertions:
    def test_unsupported_user_fact_is_not_returned_as_validated_knowledge(self, kernel):
        service = _conversation(kernel)
        service.send("The Atlas Evidence Device has 99 sensors.")
        message = service.send(f"What do you know about {_TOPIC}?")
        assert "99" not in message.content
        assert "bounded test mode" in message.content

    def test_asserted_value_never_enters_the_validated_store(self, kernel):
        service = _conversation(kernel)
        service.send("The Atlas Evidence Device has 99 sensors.")
        result = kernel.validated_knowledge(_TOPIC_QUERY)
        assert not any("99" in item.statement for item in result.items)


# ---------------------------------------------------------------------------
# G. EXISTING BEHAVIOUR PROTECTION
# ---------------------------------------------------------------------------


class TestExistingBehaviourProtection:
    @pytest.mark.parametrize(
        ("text", "intent"),
        [
            ("What do you know about yourself?", "identity"),
            ("What are your current limitations?", "self_knowledge"),
            ("What can you currently do?", "capabilities"),
            ("What capabilities do you have?", "capabilities"),
            ("Who are you?", "identity"),
        ],
    )
    def test_self_and_inventory_intents_keep_precedence(self, kernel, text, intent):
        message = _send(kernel, text)
        assert message.metadata.get("builtin_intent") == intent, text

    def test_architecture_self_knowledge_is_not_stolen(self, kernel):
        message = _send(kernel, "What do you know about your own architecture?")
        assert message.metadata.get("builtin_intent") in ("architecture", "self_knowledge")

    def test_domain_capability_question_is_not_atlas_self_knowledge(self, kernel):
        # Mirrors the C3 domain-capability case: with an established external
        # subject, a domain capability question is not the Atlas inventory.
        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        message = service.send("What about the video recording capabilities?")
        assert message.metadata.get("builtin_intent") not in (
            BUILTIN_INTENT_VALIDATED_KNOWLEDGE,
            "capabilities",
            "self_knowledge",
            "architecture",
        )
        assert "confirmed registered capabilities" not in message.content.lower()

    def test_ordinary_research_still_researches(self, kernel):
        message = _send(
            kernel,
            "Research the memory service, including memory storage of the "
            "atlas memory subsystem.",
        )
        assert message.metadata.get("builtin_intent") is None
        assert isinstance(message.metadata.get("orchestration"), dict)

    def test_store_recall_intent_is_unchanged_without_a_validated_match(self, kernel):
        for text in (
            "do you remember zzzqqqx_no_such_topic",
            "What did we discover about the investigation system?",
        ):
            message = _send(kernel, text)
            assert message.metadata.get("builtin_intent") == "recall", text

    def test_reference_resolution_behaviour_is_intact(self, kernel):
        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        message = service.send("What is its camera system?")
        assert message.metadata.get("builtin_intent") != BUILTIN_INTENT_VALIDATED_KNOWLEDGE


# ---------------------------------------------------------------------------
# H. MODEL INDEPENDENCE
# ---------------------------------------------------------------------------


class TestModelIndependence:
    def test_cue_turns_never_use_a_model(self, kernel):
        service = _conversation(kernel)
        for text in (
            f"What do you know about {_TOPIC}?",
            "What did you find about zeppelin maintenance?",
            "what did you verify about?",
        ):
            message = service.send(text)
            assert message.metadata.get("model_used") is False, text

    def test_no_provider_or_embedding_surface_is_engaged(self, kernel):
        message = _send(kernel, f"What do you know about {_TOPIC}?")
        metadata = message.metadata or {}
        assert metadata.get("model_used") is False
        assert not any("embedding" in str(key).lower() for key in metadata)
        assert not any("vector" in str(key).lower() for key in metadata)
        assert (
            kernel._config.get("ai", "external_providers", default=False) is not True
        )


# ---------------------------------------------------------------------------
# I. PERSISTENCE
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_validated_knowledge_is_reachable_after_a_kernel_restart(self, kernel):
        atlas2 = Atlas()
        atlas2.start()
        try:
            service = atlas2.container.get("conversation")
            service._conversation = service._history.create()
            service._state_manager.clear()
            message = service.send(f"What do you know about {_TOPIC}?")
            assert (
                message.metadata.get("builtin_intent")
                == BUILTIN_INTENT_VALIDATED_KNOWLEDGE
            )
            assert "bounded test mode" in message.content
        finally:
            atlas2.shutdown()
