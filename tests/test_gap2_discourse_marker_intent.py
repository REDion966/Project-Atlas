"""Gap 2 regression — a discourse marker must not create a second intent.

Real-kernel, model-OFF evidence showed that

    "Okay, investigate the remaining problem."

was represented as TWO intents:

    That request carries more than one intent. I answered 2 of 2:
    **Okay**            Noted, and no action taken.
    **investigate the remaining problem**   ## Investigation: ...

Root cause. ``_operation_comma_index`` treats a bare comma as a compound-intent
boundary when BOTH sides name a bounded operation. That guard exists to protect
an enumerative subject ("investigate the memory service, the cache layer"), and
it works. But ``interpret("Okay")`` returns the operation ``acknowledge``
(evidence ``acknowledgement-class``) and ``interpret("Hello")`` returns ``greet``
(evidence ``greeting-class``), so a pure discourse marker satisfied the
BOTH-sides test and one natural request was described as two intents.

Fix. The comma rule now skips a HEAD that Atlas's EXISTING whole-turn
classification already reads as a conversational marker (acknowledgement or
greeting). No new vocabulary, parser, state, or dialogue-act system: the marker
set is exactly the architecture's own acknowledgement/greeting evidence.

Contract these tests protect:

  A. an acknowledgement/greeting-led request is NOT split;
  B. genuine compound requests STILL split (strong coordinator, ordered, and the
     plain comma join);
  C. the enumerative-subject anti-over-split guard is INTACT;
  D. a standalone acknowledgement is still an acknowledgement (never silenced);
  E. everything else is unchanged, including that the actionable request itself
     is still understood and still executes.

Deterministic, model-free. No existing test was modified.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, r"F:\Project Atlas")

from atlas.conversation import semantic_frame as sf

REQUEST = "investigate the remaining problem"

#: A discourse marker leading one genuinely actionable request.
DISCOURSE_LED: tuple[str, ...] = (
    "Okay, investigate the remaining problem.",
    "Alright, investigate the remaining problem.",
    "Sure, investigate the remaining problem.",
    "Yes, investigate the remaining problem.",
    # greeting-led (a distinct existing whole-turn class)
    "Hello, investigate the remaining problem.",
)

#: Additional markers Atlas already classifies, proving no per-word special-casing.
OTHER_MARKERS: tuple[str, ...] = (
    "Ok, investigate the remaining problem.",
    "Thanks, investigate the remaining problem.",
    "Got it, investigate the remaining problem.",
)

#: Genuine compound requests that MUST still split into two intents.
COMPOUNDS: tuple[str, ...] = (
    "Investigate the memory service and also research the cache layer.",
    "First investigate the memory service, then research the cache layer.",
    "Investigate the memory service, research the cache layer",
    "Investigate the memory service and research the cache layer.",
)

#: Enumerative subjects the anti-over-split guard must keep unsplit.
ENUMERATIVE: tuple[str, ...] = (
    "Investigate the memory service, the cache layer",
    "Investigate the component that handles references and memory.",
    "Investigate the android thenar handler",
)

#: Standalone markers that must still be understood as such.
STANDALONE_ACKNOWLEDGEMENTS: tuple[str, ...] = (
    "Okay.",
    "Thanks.",
    "Got it.",
    "Okay, understood.",
)


def _ops(readings) -> tuple[str, ...]:
    return tuple(getattr(r.operation, "value", r.operation) for r in readings)


# ---------------------------------------------------------------------------
# A. A discourse marker leading one request is NOT a second intent
# ---------------------------------------------------------------------------


class TestDiscourseLedRequestIsNotSplit:
    @pytest.mark.parametrize("text", DISCOURSE_LED)
    def test_no_multi_intent_reading(self, text):
        assert sf.split_intents(text) == (), text

    @pytest.mark.parametrize("text", OTHER_MARKERS)
    def test_other_markers_are_not_special_cased(self, text):
        assert sf.split_intents(text) == (), text

    @pytest.mark.parametrize("text", DISCOURSE_LED)
    def test_the_actionable_request_is_still_understood(self, text):
        """Not splitting must not lose the request: it stays ONE investigation."""
        frame = sf.interpret(text, has_prior_objective=True)
        assert getattr(frame.domain, "value", frame.domain) == "investigation"
        assert frame.operation == "investigate"

    def test_decompose_is_unaffected(self):
        assert sf.decompose("Okay, investigate the remaining problem.") == ()


# ---------------------------------------------------------------------------
# B. Genuine compound requests STILL split
# ---------------------------------------------------------------------------


class TestGenuineCompoundsStillSplit:
    @pytest.mark.parametrize("text", COMPOUNDS)
    def test_compound_still_yields_two_intents(self, text):
        readings = sf.split_intents(text)
        assert len(readings) == 2, text
        assert _ops(readings) == ("investigate", "research"), text

    def test_strong_coordinator_still_splits(self):
        readings = sf.split_intents(
            "Investigate the memory service and also research the cache layer."
        )
        assert _ops(readings) == ("investigate", "research")

    def test_ordered_compound_still_splits(self):
        readings = sf.split_intents(
            "First investigate the memory service, then research the cache layer."
        )
        assert _ops(readings) == ("investigate", "research")


# ---------------------------------------------------------------------------
# C. The enumerative-subject guard is INTACT
# ---------------------------------------------------------------------------


class TestEnumerativeSubjectGuardIntact:
    @pytest.mark.parametrize("text", ENUMERATIVE)
    def test_enumerative_subject_is_not_split(self, text):
        assert sf.split_intents(text) == (), text


# ---------------------------------------------------------------------------
# D. A standalone acknowledgement is still an acknowledgement
# ---------------------------------------------------------------------------


class TestStandaloneAcknowledgementUnaffected:
    @pytest.mark.parametrize("text", STANDALONE_ACKNOWLEDGEMENTS)
    def test_standalone_acknowledgement_is_still_acknowledgement(self, text):
        frame = sf.interpret(text, has_prior_objective=True)
        assert frame.role is sf.SemanticRole.ACKNOWLEDGEMENT, text
        assert frame.operation == "acknowledge", text

    def test_standalone_greeting_is_still_a_greeting(self):
        frame = sf.interpret("Hello.", has_prior_objective=True)
        assert frame.operation == "greet", "a standalone greeting is not silenced"


# ---------------------------------------------------------------------------
# E. The marker helper reuses EXISTING classification evidence
# ---------------------------------------------------------------------------


class TestReusesExistingClassification:
    def test_marker_helper_reads_architecture_evidence_only(self):
        ack = sf.interpret("Okay.", has_prior_objective=True)
        greeting = sf.interpret("Hello.", has_prior_objective=True)
        action = sf.interpret("Investigate the memory service.")
        assert sf._is_discourse_marker(ack) is True
        assert sf._is_discourse_marker(greeting) is True
        assert sf._is_discourse_marker(action) is False

    def test_helper_is_fail_closed_on_unexpected_input(self):
        assert sf._is_discourse_marker(None) is False
        assert sf._is_discourse_marker("not a frame") is False


# ---------------------------------------------------------------------------
# F. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    @pytest.mark.parametrize("text", DISCOURSE_LED + COMPOUNDS)
    def test_repeated_reading_is_identical(self, text):
        first = sf.split_intents(text)
        second = sf.split_intents(text)
        assert _ops(first) == _ops(second)