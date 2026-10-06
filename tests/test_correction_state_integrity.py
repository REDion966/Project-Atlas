"""Correction-state integrity — a correction is installed and consumed ONCE.

Verified defect (reproduced on the current tree, model OFF):

    T1 "investigate the memory subsystem"   -> investigation established
    T2 "I meant the cache layer."           -> corrected subject installed
    T3 "Sorry, that's wrong."               -> REPLAYED the T2 correction, forever
    T4 "That's not what I meant."           -> installed the WHOLE utterance as the
                                               corrected subject and overwrote the
                                               active objective with a meta-utterance

Two coordinated defects, one structural rule:

  * the CORRECTION CONSUMER read ``state.corrections[-1]`` — the accumulated
    history — instead of the correction THIS turn produced, so any later turn
    that merely read as a correction replayed a stale, already-superseded subject;
  * the ENGINE fell back to ``spec.intent or text`` when no bounded replacement
    subject could be extracted, so a bare disagreement was recorded as installing
    the whole utterance as a new subject.

The rule now enforced at both points is the same:

    A correction installs (and is consumed as) a subject only when the turn
    itself names a bounded replacement subject.

These tests pin the CAPABILITY (a class of utterances), not one sentence: any
bare meta-correction after any prior correction. Deterministic and model-free.
"""

from __future__ import annotations

import unittest

from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.engine import ConversationEngine
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.turn_role import TurnRole, corrected_subject

OBJECTIVE = "investigate the memory subsystem"
CORRECTED = "I meant the cache layer."
CORRECTED_SUBJECT = "cache layer"

#: A class of bare meta-corrections: disagreement that names NO replacement
#: subject. None may ever install a subject or replay a prior correction.
BARE_META_CORRECTIONS = (
    "Sorry, that's wrong.",
    "That's not what I meant.",
    "No, that's wrong.",
    "I didn't mean that.",
    "That's incorrect.",
)


class _FailingAI:
    """Deterministic fallback is forced; no provider is contacted."""

    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No active AI provider selected.")

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            raise ConnectionError("No active AI provider selected.")
            yield ""  # pragma: no cover
        return _generator()


def _service() -> ConversationService:
    return ConversationService(
        ai_service=_FailingAI(),
        task_intake=TaskIntake(),
        investigation_service=InvestigationService(),
    )


def _state(service: ConversationService) -> ConversationState:
    return service._state_manager.state  # noqa: SLF001


def _objective(service: ConversationService) -> str:
    return str(getattr(_state(service), "current_objective", "") or "")


# ---------------------------------------------------------------------------
# 1. The engine: only a NAMED replacement subject is ever recorded
# ---------------------------------------------------------------------------


class TestEngineRecordsOnlyNamedSubjects(unittest.TestCase):
    def _engine(self) -> ConversationEngine:
        return ConversationEngine(task_intake=TaskIntake())

    def _interpret(self, text: str):
        state = ConversationState(current_objective=OBJECTIVE)
        engine = self._engine()
        return engine.interpret(text, state=state)

    def test_bare_disagreement_records_no_correction(self):
        for text in BARE_META_CORRECTIONS:
            with self.subTest(text=text):
                interp = self._interpret(text)
                self.assertEqual(
                    interp.corrections,
                    (),
                    "a bare meta-correction must never be recorded as a subject",
                )

    def test_bare_disagreement_never_installs_the_utterance_as_objective(self):
        engine = self._engine()
        for text in BARE_META_CORRECTIONS:
            with self.subTest(text=text):
                state = ConversationState(current_objective=OBJECTIVE)
                interp = engine.interpret(text, state=state)
                updates = engine.state_updates(interp, state)
                self.assertEqual(
                    updates.get("current_objective", OBJECTIVE),
                    OBJECTIVE,
                    "a meta-utterance must never become the active objective",
                )

    def test_named_replacement_is_still_recorded_exactly_once(self):
        interp = self._interpret(CORRECTED)
        self.assertIs(interp.turn_role, TurnRole.CORRECTION)
        self.assertEqual(len(interp.corrections), 1)
        self.assertEqual(interp.corrections[-1].corrected, CORRECTED_SUBJECT)
        self.assertEqual(interp.corrections[-1].previous, OBJECTIVE)

    def test_a_trailing_marker_with_no_subject_is_not_a_subject(self):
        """The exact shape that used to install the whole utterance."""
        for text in ("That's not what I meant.", "I meant.", "Sorry, I meant."):
            with self.subTest(text=text):
                self.assertEqual(corrected_subject(text), "")
                self.assertEqual(self._interpret(text).corrections, ())


# ---------------------------------------------------------------------------
# 2. The consumer: a correction is consumed once, on the turn that produced it
# ---------------------------------------------------------------------------


class TestCorrectionIsConsumedOnce(unittest.TestCase):
    def test_the_original_defect_does_not_replay(self):
        service = _service()
        service.send(OBJECTIVE)
        first = service.send(CORRECTED)
        self.assertIn(CORRECTED_SUBJECT, first.content)

        for text in BARE_META_CORRECTIONS:
            with self.subTest(text=text):
                replay = service.send(text)
                # The stale acknowledgement must never be re-emitted.
                self.assertNotIn(
                    "I corrected the active subject",
                    replay.content,
                    "a bare meta-correction must not replay a superseded correction",
                )

    def test_the_correction_record_is_not_duplicated(self):
        service = _service()
        service.send(OBJECTIVE)
        service.send(CORRECTED)
        before = len(_state(service).corrections)
        for text in BARE_META_CORRECTIONS:
            service.send(text)
        self.assertEqual(
            len(_state(service).corrections),
            before,
            "repeated disagreement must not append corrections",
        )

    def test_the_active_objective_survives_repeated_disagreement(self):
        service = _service()
        service.send(OBJECTIVE)
        service.send(CORRECTED)
        settled = _objective(service)
        self.assertEqual(settled, CORRECTED_SUBJECT)
        for text in BARE_META_CORRECTIONS:
            service.send(text)
        self.assertEqual(
            _objective(service),
            settled,
            "disagreement must not corrupt the active objective",
        )

    def test_a_genuinely_new_correction_still_applies(self):
        """Nearby valid behaviour: the rule blocks stale replay, not correction."""
        service = _service()
        service.send(OBJECTIVE)
        service.send(CORRECTED)
        second = service.send("Actually, I meant the storage layer.")
        self.assertIn("storage layer", second.content)
        self.assertEqual(_objective(service), "storage layer")

    def test_no_correction_yet_means_nothing_to_consume(self):
        service = _service()
        service.send(OBJECTIVE)
        for text in BARE_META_CORRECTIONS:
            with self.subTest(text=text):
                reply = service.send(text)
                self.assertNotIn("I corrected the active subject", reply.content)
        self.assertEqual(_state(service).corrections, ())


# ---------------------------------------------------------------------------
# 3. Fail-closed / determinism / no authority
# ---------------------------------------------------------------------------


class TestFailClosedAndDeterministic(unittest.TestCase):
    def test_repeated_runs_are_identical(self):
        def run():
            service = _service()
            transcript = []
            for text in (OBJECTIVE, CORRECTED, *BARE_META_CORRECTIONS, CORRECTED):
                transcript.append(service.send(text).content)
            return transcript

        self.assertEqual(run(), run())

    def test_the_correction_path_grants_no_authority(self):
        service = _service()
        service.send(OBJECTIVE)
        reply = service.send(CORRECTED)
        meta = reply.metadata or {}
        self.assertTrue(meta.get("builtin_response"))
        self.assertFalse(meta.get("model_used"))
        self.assertNotIn("approval", meta)
        self.assertNotIn("proposal", meta)

    def test_empty_and_whitespace_turns_never_record_a_correction(self):
        engine = ConversationEngine(task_intake=TaskIntake())
        for text in ("", "   ", "\n"):
            with self.subTest(text=repr(text)):
                state = ConversationState(current_objective=OBJECTIVE)
                self.assertEqual(engine.interpret(text, state=state).corrections, ())


# ---------------------------------------------------------------------------
# 4. The rule is structural, not a lexical exception list
# ---------------------------------------------------------------------------


class TestRuleIsStructural(unittest.TestCase):
    def test_the_guard_does_not_introduce_a_disagreement_word_list(self):
        """The rule keys on whether a bounded SUBJECT was extracted — not on
        matching a new list of disagreement phrases.

        Checked on the guard EXPRESSION, not on prose: the comments explaining the
        rule legitimately quote the utterances.
        """
        import inspect

        from atlas.conversation.engine import ConversationEngine

        body = inspect.getsource(ConversationEngine._detect_correction)  # noqa: SLF001
        code = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("#")
        )
        # The gate is the EXISTING extraction + the EXISTING reference predicate.
        self.assertIn("corrected_subject(", code)
        self.assertIn("REFERENCE_WORDS", code)
        # No new lexical list of disagreement phrases was introduced.
        self.assertNotIn("_DISAGREEMENT", code)
        self.assertNotIn("_META_CORRECTION", code)
        self.assertNotIn("_BARE_", code)

    def test_only_a_named_subject_unlocks_the_correction_surface(self):
        """Exactly the turns that name a bounded subject may correct.

        The raw extractor may still return a pointer token ("that"); what matters
        is that the ENGINE records no correction for any of these turns.
        """
        engine = ConversationEngine(task_intake=TaskIntake())
        named = (
            "I meant the cache layer.",
            "Actually, I meant the storage layer.",
            "No, I meant the memory service.",
        )
        for text in named:
            with self.subTest(text=text):
                self.assertTrue(corrected_subject(text))
                state = ConversationState(current_objective=OBJECTIVE)
                self.assertEqual(len(engine.interpret(text, state=state).corrections), 1)
        for text in BARE_META_CORRECTIONS:
            with self.subTest(text=text):
                state = ConversationState(current_objective=OBJECTIVE)
                self.assertEqual(engine.interpret(text, state=state).corrections, ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
