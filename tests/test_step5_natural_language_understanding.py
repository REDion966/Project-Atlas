"""Step 5 — natural-language understanding: interpreting unseen phrasing.

The G1/G2 layer (`atlas.conversation.semantic_frame`) already turns ordinary
utterances into a bounded, inspectable semantic frame over word CLASSES rather
than literal phrases. The baseline probe found the remaining capability gap in
what happened NEXT: a turn the shared frame could not map to any bounded
operation was answered with the *model-unavailable* floor text, which
misreported an out-of-scope request as a missing-model problem and discarded the
interpretation entirely.

Step 5 surfaces that interpretation as truthful meaning: an unhandled turn whose
frame names no bounded operation now answers with what was read, states that the
request is out of scope rather than a missing model, restates the bounded
capability surface, records the bounded interpretation for audit, and states that
nothing was executed. Every other unsupported shape keeps its existing notice
verbatim, and interpretation never routes, approves, executes or promotes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_UNSUPPORTED,
    BuiltinResponseService,
    uninterpreted_interpretation,
)
from atlas.conversation.task_intake import TaskIntake

_OUT_OF_SCOPE = [
    "Book me a table for two at the nearest restaurant.",
    "Order me a new laptop.",
    "Enumerate your provider options.",
    "Bro, what's the crack with your knowledge store?",
    "The conversation part keeps falling over for me.",
]

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _respond(text: str):
    return BuiltinResponseService().respond(
        text, spec=TaskIntake().intake(text), message_count=0, context=None
    )


# ---------------------------------------------------------------------------
# 1. Unknown / out-of-scope wording is represented truthfully
# ---------------------------------------------------------------------------


class TestUninterpretedRequests:
    @pytest.mark.parametrize("text", _OUT_OF_SCOPE)
    def test_unseen_out_of_scope_request_is_reported_as_unmapped(self, text):
        message = _respond(text)
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_UNSUPPORTED
        assert message.metadata["model_used"] is False
        assert message.content.startswith("I could not map that request")
        # The reading is stated, and the out-of-scope cause is made explicit...
        assert "out-of-scope request rather than a missing-model problem" in message.content
        assert "no external AI model was contacted" in message.content
        assert "no approval, no authorization, and no change was made" in message.content
        # ...while the existing bounded surface + fail-closed wording survive.
        assert "without an external AI model" in message.content
        assert "investigate" in message.content

    @pytest.mark.parametrize("text", _OUT_OF_SCOPE)
    def test_bounded_interpretation_is_recorded_for_audit(self, text):
        frame = sf.interpret(text)
        metadata = _respond(text).metadata["frame_interpretation"]
        assert metadata["domain"] == "unsupported"
        assert metadata["operation"] == ""
        assert metadata["subject"] == frame.subject[:120]
        assert metadata["role"] == frame.role.value
        assert metadata["confidence"] == float(frame.confidence)
        assert metadata["needs_clarification"] is False
        # The identified subject is restated, not invented.
        if frame.subject:
            assert f"'{frame.subject[:120]}'" in _respond(text).content

    def test_interpretation_is_a_pure_function_of_the_text(self):
        text = _OUT_OF_SCOPE[0]
        first = uninterpreted_interpretation(text)
        second = uninterpreted_interpretation(text)
        assert first == second
        # The conversation path and the bare builtin path render identically.
        assert _respond(text).content.startswith(first[0])
        assert _respond(text).content.endswith("approval steps.")

    def test_interpretation_is_bounded(self):
        block, metadata = uninterpreted_interpretation(
            "Book me a table " + "x " * 300 + "now"
        )
        assert len(block) < 1_000
        assert len(metadata["frame_interpretation"]["subject"]) <= 120

    def test_supported_phrasing_is_not_claimed_by_the_notice(self):
        # The notice applies ONLY when the frame names no bounded operation.
        for text in (
            "What can you do?",
            "Investigate why the conversation layer stalls.",
            "Handle it.",
            "Research how Atlas handles references.",
        ):
            assert sf.interpret(text).domain is not sf.SemanticDomain.UNSUPPORTED, text
            assert uninterpreted_interpretation(text) is None, text

    def test_the_existing_unsupported_contract_is_preserved(self):
        # A turn the L7 floor answers keeps its intent + metadata contract,
        # whichever notice text applies.
        message = _respond("What should I work on next?")
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_UNSUPPORTED
        assert message.metadata["builtin_response"] is True
        assert message.metadata["model_used"] is False

    def test_empty_text_is_not_claimed(self):
        assert uninterpreted_interpretation("") is None
        assert uninterpreted_interpretation("   ") is None


def _interpreted_intent(text: str) -> str | None:
    message = _respond(text)
    return (message.metadata or {}).get("builtin_intent") if message else None


# ---------------------------------------------------------------------------
# 2. Structured meaning for unseen phrasing (the understanding side)
# ---------------------------------------------------------------------------


class TestStructuredMeaningForUnseenPhrasing:
    @pytest.mark.parametrize(
        "text,domain,operation",
        [
            ("Spill the beans on what you're capable of.", "capabilities", "capabilities"),
            ("What are you able to handle for me?", "capabilities", "capabilities"),
            ("Which modules make up your conversation side?", "self_knowledge", "self_knowledge"),
            ("What governs the way you lot decide about outside knowledge?", "self_knowledge", "self_knowledge"),
            ("Investigate the conversation layer and then explain what it means.", "investigation", "investigate"),
        ],
    )
    def test_unseen_paraphrase_yields_bounded_meaning(self, text, domain, operation):
        frame = sf.interpret(text)
        assert frame.domain.value == domain
        assert frame.operation == operation
        assert frame.confidence > 0.0            # evidence-backed, not a guess
        assert frame.evidence                    # the frame names its evidence
        assert not frame.governance_sensitive    # interpretation grants nothing

    @pytest.mark.parametrize(
        "text,role",
        [
            ("Spill the beans on what you're capable of.", "new_objective"),
            ("Investigate the conversation layer and then explain what it means.", "new_objective"),
        ],
    )
    def test_unseen_paraphrase_keeps_the_expected_turn_role(self, text, role):
        assert sf.interpret(text).role.value == role


# ---------------------------------------------------------------------------
# 3. Ambiguity, clarification and references
# ---------------------------------------------------------------------------


class TestAmbiguityAndReferences:
    def test_short_unresolvable_request_asks_for_clarification(self):
        # No prior objective: a bare "do it" style turn is ambiguous.
        frame = sf.interpret("Handle it.")
        assert frame.needs_clarification is True
        # The existing clarification seam owns it (no uninterpreted notice).
        assert uninterpreted_interpretation("Handle it.") is None

    def test_bare_reference_with_context_is_not_treated_as_ambiguous(self):
        frame = sf.interpret("How does it fit together?", has_prior_objective=True)
        assert frame.needs_clarification is False

    def test_empty_frame_is_not_a_guess(self):
        frame = sf.interpret("Book me a table for two.")
        assert frame.domain is sf.SemanticDomain.UNSUPPORTED
        assert frame.operation == ""
        assert frame.confidence == 0.0


# ---------------------------------------------------------------------------
# 4. Safety / authority
# ---------------------------------------------------------------------------


class TestInterpretationCarriesNoAuthority:
    def test_notice_metadata_contains_no_governance_keys(self):
        metadata = _respond(_OUT_OF_SCOPE[0]).metadata
        for key in ("approval", "execution", "promotion", "authorization", "orchestration"):
            assert key not in metadata, key
        assert set(metadata) <= {
            "builtin_response",
            "builtin_intent",
            "model_used",
            "frame_interpretation",
        }

    def test_builtin_service_has_no_authority_surface(self):
        service = BuiltinResponseService()
        for name in ("approve", "promote", "authorize", "execute", "grant"):
            assert not hasattr(service, name)

    def test_interpretation_does_not_claim_or_execute(self):
        content = _respond(_OUT_OF_SCOPE[1]).content
        assert "no approval, no authorization, and no change was made" in content
        # The interpretation never asserts that any action was taken.
        assert "i have" not in content.lower()
        assert "i will" not in content.lower()


# ---------------------------------------------------------------------------
# 5. Real kernel
# ---------------------------------------------------------------------------


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


class TestRealKernel:
    def test_unseen_out_of_scope_requests_are_represented_truthfully(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            for text in _OUT_OF_SCOPE[:3]:
                message = atlas.chat(text)
                metadata = message.metadata or {}
                assert metadata["builtin_intent"] == BUILTIN_INTENT_UNSUPPORTED, text
                assert message.content.startswith("I could not map that request"), text
                assert metadata["frame_interpretation"]["domain"] == "unsupported", text
                assert "orchestration" not in metadata, text
                assert metadata["model_used"] is False, text
            # Nothing was created by an uninterpreted turn.
            assert atlas.pending_promotion_reviews() == []
            assert atlas._conversation.state_manager.state.pending_approval_id is None  # noqa: SLF001
        finally:
            atlas.shutdown()

    def test_unseen_supported_phrasing_still_routes(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            capabilities = atlas.chat("Spill the beans on what you're capable of.")
            assert (capabilities.metadata or {}).get("builtin_intent") == "capabilities"

            architecture = atlas.chat("Which modules make up your conversation side?")
            assert (architecture.metadata or {}).get("builtin_intent") == "architecture"

            orchestrated = atlas.chat(
                "Investigate the conversation state handling and then explain what we should do next."
            )
            assert (orchestrated.metadata or {}).get("orchestration", {}).get(
                "status"
            ) == "completed"
        finally:
            atlas.shutdown()

    def test_ambiguous_turn_asks_for_clarification(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("Handle it.")
            assert (message.metadata or {}).get("frame_clarification") is not None
            assert "more detail" in message.content
        finally:
            atlas.shutdown()

    def test_live_repository_untouched(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat(_OUT_OF_SCOPE[0])
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()
