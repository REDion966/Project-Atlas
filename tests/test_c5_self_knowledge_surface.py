"""C5.1 — bounded, evidence-grounded self-knowledge surface tests.

Exercises the REAL public conversation path (``ConversationService.send`` on a
fully wired ``Atlas`` kernel, default config: ``external_providers=false``).

Every assertion checks SUBSTANTIVE, grounded content — the verified anchor
modules, the class names the architecture actually defines, and the enumerated
status/failure vocabularies — not merely that some text was returned.

Environment note: all SQLite stores default to one shared file
(``atlas_data/atlas_experience.db``); this module points them at a fresh
temporary database for the module's duration (restored afterwards) so the
evidence reflects a clean install and the module stays runnable. Test-harness
only; production behaviour is unchanged.
"""

from __future__ import annotations

import hashlib
import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.kernel.atlas import Atlas

_REPO_ROOT = Path(__file__).resolve().parents[1]


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
    saved = _patch_default_db_paths(
        Path(tempfile.mkdtemp(prefix="c5_self_knowledge_")) / "atlas_experience.db"
    )
    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        try:
            atlas.shutdown()
        except Exception:  # noqa: BLE001
            pass
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


def _conversation(kernel):
    """A fresh public conversation on the kernel-wired service."""
    service = kernel.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service


def _send(kernel, text):
    return _conversation(kernel).send(text)


# ---------------------------------------------------------------------------
# A. ARCHITECTURE / COMPONENTS
# ---------------------------------------------------------------------------


class TestArchitectureFamily:
    def test_parts_of_your_system_is_answered_from_verified_architecture(self, kernel):
        message = _send(kernel, "What parts of your system handle conversation?")
        assert message.metadata.get("builtin_intent") == "architecture"
        text = message.content
        # Grounded: the answer comes from the architecture model, not research.
        assert "architecture self-knowledge" in text.lower()
        assert "match kind" in text.lower()
        assert message.metadata.get("model_used") is False

    def test_which_components_is_answered_from_verified_architecture(self, kernel):
        message = _send(kernel, "Which components handle conversation?")
        assert message.metadata.get("builtin_intent") == "architecture"
        assert "architecture self-knowledge" in message.content.lower()


# ---------------------------------------------------------------------------
# B. REFERENCE RESOLUTION
# ---------------------------------------------------------------------------


class TestReferenceResolutionFamily:
    def test_reference_resolution_answer_is_grounded(self, kernel):
        message = _send(kernel, "How do you resolve references?")
        assert message.metadata.get("builtin_intent") == "self_knowledge"
        text = message.content
        # Verified anchors.
        assert "atlas/conversation/reference_resolution.py" in text
        assert "atlas/conversation/entity_capture.py" in text
        # The class the architecture actually defines.
        assert "ConversationReferenceResolver" in text
        # The real enumerated status vocabulary.
        assert "resolved" in text and "ambiguous" in text
        # Fail-closed statement, no model.
        assert "never guessed" in text.lower()
        assert message.metadata.get("model_used") is False


# ---------------------------------------------------------------------------
# C. EVIDENCE / FAILURE BEHAVIOUR
# ---------------------------------------------------------------------------


class TestEvidenceFamily:
    def test_no_evidence_answer_is_grounded(self, kernel):
        message = _send(kernel, "What happens when you don't have enough evidence?")
        assert message.metadata.get("builtin_intent") == "self_knowledge"
        text = message.content
        assert "atlas/orchestration/executor.py" in text
        assert "atlas/research/relevance.py" in text
        assert "atlas/research/acquisition.py" in text
        # The real failure-kind / status vocabulary.
        assert "no_evidence" in text
        assert "no_relevant_evidence" in text
        assert "rejected" in text
        assert message.metadata.get("model_used") is False


# ---------------------------------------------------------------------------
# D. CURRENT LIMITATIONS
# ---------------------------------------------------------------------------


class TestLimitationsFamily:
    def test_limitations_answer_is_bounded_and_grounded(self, kernel):
        message = _send(kernel, "What are your current limitations?")
        assert message.metadata.get("builtin_intent") == "self_knowledge"
        text = message.content
        assert "atlas/self_knowledge/architecture_model.py" in text
        assert "Registered capabilities:" in text
        # The architecture model's own recorded limitation is surfaced.
        assert "architecture model" in text.lower()
        # It does not invent a generic list.
        assert "not asserted" in text.lower()
        assert message.metadata.get("model_used") is False


# ---------------------------------------------------------------------------
# E. RESEARCH PROCESS
# ---------------------------------------------------------------------------


class TestResearchFamily:
    @pytest.mark.parametrize(
        "question",
        [
            "Can you explain how your research process works?",
            "How does Atlas perform research?",
        ],
    )
    def test_research_answer_is_grounded(self, kernel, question):
        message = _send(kernel, question)
        assert message.metadata.get("builtin_intent") == "self_knowledge"
        text = message.content
        assert "atlas/research/acquisition.py" in text
        assert "atlas/research/coordinator.py" in text
        assert "ConcreteResearchCoordinator" in text
        assert "InformationAcquisitionService" in text
        assert "deny-by-default" in text.lower()
        assert message.metadata.get("model_used") is False


# ---------------------------------------------------------------------------
# F. CAPABILITY INVENTORY REGRESSION
# ---------------------------------------------------------------------------


class TestCapabilityInventoryRegression:
    def test_capability_inventory_still_works(self, kernel):
        message = _send(kernel, "What can you currently do?")
        assert message.metadata.get("builtin_intent") == "capabilities"
        assert "confirmed registered capabilities" in message.content.lower()
        assert message.metadata.get("model_used") is False

    def test_capability_inventory_alias_still_works(self, kernel):
        message = _send(kernel, "What are your capabilities?")
        assert message.metadata.get("builtin_intent") == "capabilities"

    def test_bare_capability_word_in_a_fresh_conversation_is_atlas(self, kernel):
        # No established external subject -> the Atlas inventory is correct.
        message = _send(kernel, "list the capabilities")
        assert message.metadata.get("builtin_intent") == "capabilities"


# ---------------------------------------------------------------------------
# G/H. DOMAIN CAPABILITY REGRESSIONS (the C3 misroute must not occur)
# ---------------------------------------------------------------------------


class TestDomainCapabilityRegression:
    def test_domain_capabilities_after_a_subject_is_not_atlas_inventory(self, kernel):
        service = _conversation(kernel)
        service.send("I'm reviewing the Samsung Galaxy S26 Ultra.")
        message = service.send("What about the video recording capabilities?")
        assert message.metadata.get("builtin_intent") != "capabilities"
        assert "confirmed registered capabilities" not in message.content.lower()
        assert "noop" not in message.content  # not the Atlas capability list

    def test_domain_capable_question_is_not_atlas_self_capability(self, kernel):
        service = _conversation(kernel)
        service.send("I'm reviewing the Samsung Galaxy S26 Ultra.")
        message = service.send("Can you look into what its cameras are capable of?")
        assert message.metadata.get("builtin_intent") != "capabilities"
        assert "confirmed registered capabilities" not in message.content.lower()

    def test_this_phone_capabilities_is_not_atlas_inventory(self, kernel):
        message = _send(kernel, "What capabilities does this phone have?")
        assert message.metadata.get("builtin_intent") != "capabilities"


# ---------------------------------------------------------------------------
# I. UNKNOWN SELF-KNOWLEDGE
# ---------------------------------------------------------------------------


class TestUnknownSelfKnowledge:
    def test_out_of_contract_self_knowledge_question_does_not_guess(self, kernel):
        message = _send(
            kernel, "What exact internal decision caused the last request to fail?"
        )
        text = message.content.lower()
        # Honest bounded unsupported response — no invented architecture claims.
        assert "verified architectural anchors" not in text
        assert "atlas/" not in text
        assert message.metadata.get("builtin_intent") != "self_knowledge"


# ---------------------------------------------------------------------------
# J. READ-ONLY
# ---------------------------------------------------------------------------


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestReadOnly:
    def test_self_knowledge_query_does_not_modify_sources_or_state(self, kernel):
        watched = [
            _REPO_ROOT / "atlas" / "conversation" / "builtin_response.py",
            _REPO_ROOT / "atlas" / "self_knowledge" / "architecture_model.py",
            _REPO_ROOT / "atlas" / "self_knowledge" / "capability_model.py",
        ]
        before = {path: _digest(path) for path in watched}

        service = _conversation(kernel)
        builtin = service.builtin_response
        capabilities_before = sorted(builtin._capability_names())
        captured_before = list(service._state_manager.state.captured_entities)

        for question in (
            "What parts of your system handle conversation?",
            "How do you resolve references?",
            "What happens when you don't have enough evidence?",
            "What are your current limitations?",
            "Can you explain how your research process works?",
        ):
            service.send(question)

        after = {path: _digest(path) for path in watched}
        assert after == before, "self-knowledge must not modify source files"
        # The registered capability inventory is unchanged, and no self-knowledge
        # answer manufactured conversation state or entity captures.
        assert sorted(builtin._capability_names()) == capabilities_before
        assert list(service._state_manager.state.captured_entities) == captured_before


# ---------------------------------------------------------------------------
# K. MODEL INDEPENDENCE
# ---------------------------------------------------------------------------


class TestModelIndependence:
    def test_no_external_model_is_used_for_self_knowledge(self, kernel):
        for question in (
            "What parts of your system handle conversation?",
            "How do you resolve references?",
            "What happens when you don't have enough evidence?",
            "What are your current limitations?",
            "Can you explain how your research process works?",
        ):
            message = _send(kernel, question)
            assert message.metadata.get("model_used") is False, question
            assert message.metadata.get("fallback_after_provider_failure") is None
