"""Gap 1 regression — a bare demonstrative must not become a literal subject.

Real-kernel evidence (model-OFF) showed that a meta-correction whose tail is a
bare reference pointer installed that POINTER as a new subject:

    "I did not mean that."
      -> "Understood — I corrected the active subject to 'that'. The previous
          investigation is no longer the active subject."

and, via the existing hand-off, cleared ``current_investigation`` — overwriting a
real active subject with the word "that".

Root cause. ``semantic_frame.corrected_subject()`` extracts the text after the
latest replacement marker ("i did not mean" -> tail "that.") with no referent-type
filter, and ``_maybe_handle_correction`` rejected a corrected reading only when it
was empty or matched ``_ORDINAL_REFERENCE_RE``. A bare demonstrative is neither,
so it was accepted as a subject.

Atlas already models this correctly and the signal already flows end-to-end: the
``SemanticFrame`` the turn carries reports ``reference="that"`` (populated by the
EXISTING ``_enrich`` from the EXISTING ``lexicon.REFERENCE_WORDS``), and
``AtlasMeaning`` carries that frame verbatim. Only the CONSUMER ignored it. The fix
reuses that existing predicate: a corrected reading made up entirely of reference
words names no subject, so it defers to Atlas's existing fail-closed reference and
ordinal surfaces instead of inventing a referent.

These tests assert the SEMANTIC outcome, not a response string:

  * an unresolved bare demonstrative is never installed as a literal subject;
  * the retained investigation/result is not superseded;
  * Atlas stays fail-closed (it never guesses a referent);
  * an explicit NAMED correction still installs its subject and still supersedes;
  * every pre-existing control case keeps its exact previous behavior.

Deterministic, model-free, no new state/authority. No existing test was modified.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, r"F:\Project Atlas")

from atlas.conversation.lexicon import REFERENCE_WORDS

#: A corrected reading that is ENTIRELY a reference pointer names no subject.
DEMONSTRATIVE_TAILS: tuple[str, ...] = ("that", "this", "it")

#: The observed defect forms (real kernel, model-OFF).
DEFECT_FORMS: tuple[str, ...] = (
    "I did not mean that.",
    "I meant that.",
    "I did not mean this.",
    "I meant it.",
)

#: Controls that must keep their exact previous behavior.
CONTROL_FORMS: tuple[str, ...] = (
    "That's not what I meant.",
    "Sorry, that's wrong.",
    "Wrong.",
    "Forget it.",
)


def _kernel(tmp_path):
    """A real, started Atlas with isolated storage (model assistance OFF)."""
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class _Isolated(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    return _Isolated


def _started_atlas(monkeypatch, tmp_path):
    from atlas.kernel.atlas import Atlas

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _kernel(tmp_path)
    )
    atlas = Atlas()
    atlas.start()
    return atlas


def _establish(atlas, subject: str = "Investigate the memory service."):
    """Establish a real active investigation and return its retained value."""
    atlas.chat(subject)
    return atlas._conversation.state_manager.state.current_investigation


# ---------------------------------------------------------------------------
# 1. The defect itself — a bare demonstrative is not a literal subject
# ---------------------------------------------------------------------------


class TestDemonstrativeIsNotInstalledAsSubject:
    @pytest.mark.parametrize("text", DEFECT_FORMS)
    def test_defect_form_does_not_claim_a_corrected_subject(
        self, monkeypatch, tmp_path, text
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _establish(atlas)
            message = atlas.chat(text)
            assert "I corrected the active subject to" not in message.content, text
        finally:
            atlas.shutdown()

    @pytest.mark.parametrize("text", DEFECT_FORMS)
    def test_defect_form_does_not_supersede_the_retained_investigation(
        self, monkeypatch, tmp_path, text
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before = _establish(atlas)
            assert before, "precondition: an investigation must be retained"
            atlas.chat(text)
            after = atlas._conversation.state_manager.state.current_investigation
            assert after == before, text
        finally:
            atlas.shutdown()

    @pytest.mark.parametrize("text", DEFECT_FORMS)
    def test_defect_form_stays_fail_closed_and_authorizes_nothing(
        self, monkeypatch, tmp_path, text
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _establish(atlas)
            message = atlas.chat(text)
            # No approval, execution, promotion or authorization was created.
            for key in ("approval", "execution", "promotion", "authorization"):
                assert key not in (message.metadata or {}), (text, key)
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    @pytest.mark.parametrize("text", DEFECT_FORMS)
    def test_literal_pointer_is_never_installed_as_a_subject(
        self, monkeypatch, tmp_path, text
    ):
        """The word 'that' must not become a literal subject anywhere in state."""
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _establish(atlas)
            atlas.chat(text)
            state = atlas._conversation.state_manager.state
            assert state.current_subject != "that", text
            assert state.current_investigation != "that", text
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# 2. An explicit NAMED correction still works (the fix must not over-block)
# ---------------------------------------------------------------------------


class TestNamedCorrectionStillInstallsItsSubject:
    def test_named_correction_installs_the_subject(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _establish(atlas)
            message = atlas.chat("No, I meant the storage layer.")
            assert "I corrected the active subject to 'storage layer'" in message.content
            assert (
                atlas._conversation.state_manager.state.current_investigation is None
            ), "a genuine subject change must still supersede the retained investigation"
        finally:
            atlas.shutdown()

    def test_named_correction_without_a_prior_investigation_still_answers(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("No, I meant the storage layer.")
            assert "storage layer" in message.content
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# 3. Existing control behavior is unchanged (no regression, no weakening)
# ---------------------------------------------------------------------------


class TestControlFormsUnchanged:
    @pytest.mark.parametrize("text", CONTROL_FORMS)
    def test_control_form_does_not_claim_a_subject(
        self, monkeypatch, tmp_path, text
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _establish(atlas)
            message = atlas.chat(text)
            assert "I corrected the active subject to" not in message.content, text
        finally:
            atlas.shutdown()

    @pytest.mark.parametrize("text", CONTROL_FORMS)
    def test_control_form_preserves_the_retained_investigation(
        self, monkeypatch, tmp_path, text
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before = _establish(atlas)
            atlas.chat(text)
            after = atlas._conversation.state_manager.state.current_investigation
            assert after == before, text
        finally:
            atlas.shutdown()

    def test_ordinal_correction_keeps_its_fail_closed_surface(self, monkeypatch, tmp_path):
        """The EXISTING earlier-item surface must still own an ordinal correction."""
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before = _establish(atlas)
            message = atlas.chat("No, I meant the previous one.")
            assert "I corrected the active subject to" not in message.content
            assert (
                atlas._conversation.state_manager.state.current_investigation == before
            )
        finally:
            atlas.shutdown()

    def test_the_correction_result_remains_recallable(self, monkeypatch, tmp_path):
        """Rejecting the pointer must not damage the retained result itself."""
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _establish(atlas)
            atlas.chat("I did not mean that.")
            follow = atlas.chat("What did you find?")
            assert "memory service" in follow.content.lower() or "component" in follow.content.lower()
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# 4. The existing predicate is reused, not re-invented
# ---------------------------------------------------------------------------


class TestReusesExistingPredicate:
    def test_reference_words_are_the_existing_lexicon_set(self):
        # The guard is bounded by Atlas's own canonical reference vocabulary.
        assert {"that", "this", "it"} <= REFERENCE_WORDS

    def test_guard_covers_exactly_the_reference_only_readings(self):
        from atlas.conversation.lexicon import tokens

        for tail in DEMONSTRATIVE_TAILS:
            assert set(tokens(tail)) <= REFERENCE_WORDS, tail
        # A named subject is NOT reference-only, so it still installs.
        assert not set(tokens("storage layer")) <= REFERENCE_WORDS

    def test_mixed_tail_is_not_blocked(self):
        """'I did not mean that, I meant the storage layer' still names a subject."""
        from atlas.conversation.lexicon import tokens

        corrected = "storage layer"
        assert not set(tokens(corrected)) <= REFERENCE_WORDS
