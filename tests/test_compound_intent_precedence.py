"""Compound-intent precedence — capability-level tests.

The architecture rule (documented since the compound-intake fix) is:

    the LEADING requested operation outranks a later development cue.

A development cue appearing LATER is usually describing the SUBJECT of the
leading operation rather than issuing a directive — "Research how Atlas could
improve scheduling" is research, not development. Atlas owns exactly two
read-only evidence-gathering operations, ``RESEARCH`` and ``INVESTIGATE``; the
rule previously covered only ``RESEARCH``, so a turn whose LEADING operation was
investigation was wrongly claimed by the development branch whenever a
development cue appeared later.

These tests pin the RULE, not individual sentences:

* a read-only LEADING operation wins over a later development cue;
* a development LEADING operation still wins over a later investigation clause
  (the compound-intake fix, which must not regress);
* single-clause development and investigation requests are unchanged.

Deterministic and model-free throughout.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, r"F:\Project Atlas")

from atlas.conversation.task_intake import TaskIntake

# The original observed failure: a hypothetical capability question whose
# leading operation is investigate but which also carries development cues.
ORIGINAL = (
    "Suppose I asked you to gain a capability that you don't currently have. "
    "Could you investigate what's missing, research possible ways to implement "
    "it, and develop it under your normal safety rules?"
)

# Structurally similar: the SAME shape (read-only leading operation, later
# development cue, capability-flavoured subject) with different wording.
SIMILAR_READ_ONLY_LEAD = (
    "Suppose I wanted a feature you don't have. Could you investigate the gap "
    "and develop a capability to close it?",
    "Could you investigate what capability is missing and then develop it "
    "under your normal safety rules?",
    "Investigate what capability is missing and develop a plan to add it.",
    "Look into what capability is missing, research the options, and develop "
    "the best one.",
)

# Leading read-only operation + a later development cue, in ordinary phrasing.
INVESTIGATE_LEAD_DEV_CUE = (
    "Investigate the conversation service and then improve it.",
    "Investigate the memory service, then fix the bug.",
    "Investigate the storage layer and then refactor it.",
)

# Leading DEVELOPMENT operation + a later investigation clause: the
# compound-intake fix must keep these on the development path.
DEVELOP_LEAD_INV_CLAUSE = (
    "Add a test. Investigate the implementation.",
    "I want you to add a regression test. First investigate the implementation "
    "and existing tests.",
    "Improve the conversation service capability and investigate the result.",
)

RESEARCH_LEAD_DEV_CUE = (
    "Research how Atlas could improve scheduling.",
    "Research how Atlas could improve scheduling and then implement it.",
    "Find out how you would add a new capability.",
)


def _bare(text: str):
    """Deterministic intake with no resolver injected (precedence only)."""
    return TaskIntake().intake(text)


@pytest.fixture(scope="module")
def kernel():
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        _ = atlas.repository_map
        yield atlas
    finally:
        atlas.shutdown()


# ---------------------------------------------------------------------------
# 1. The original defect
# ---------------------------------------------------------------------------


class TestOriginalDefect:
    def test_read_only_leading_question_is_investigation(self):
        assert _bare(ORIGINAL).task_type.value == "investigation_request"

    def test_same_through_the_live_conversation_intake(self, kernel):
        spec = kernel._conversation._intake(ORIGINAL)
        assert spec.task_type.value == "investigation_request"

    def test_the_leading_operation_really_is_read_only(self):
        from atlas.conversation.task_intake import build_utterance_meaning

        meaning = build_utterance_meaning(ORIGINAL)
        assert meaning.operation.value == "investigate"


# ---------------------------------------------------------------------------
# 2. The RULE, not the sentence: read-only lead beats a later develop cue
# ---------------------------------------------------------------------------


class TestReadOnlyLeadOutranksLaterDevelopmentCue:
    @pytest.mark.parametrize("text", SIMILAR_READ_ONLY_LEAD)
    def test_similar_read_only_led_compounds_are_investigation(self, text):
        assert _bare(text).task_type.value == "investigation_request", text

    @pytest.mark.parametrize("text", INVESTIGATE_LEAD_DEV_CUE)
    def test_investigate_led_compounds_are_investigation(self, text):
        assert _bare(text).task_type.value == "investigation_request", text

    @pytest.mark.parametrize("text", RESEARCH_LEAD_DEV_CUE)
    def test_research_led_compounds_are_information(self, text):
        assert _bare(text).task_type.value == "information_request", text

    def test_rule_is_about_the_LEADING_operation_not_the_cue_set(self):
        """Same cues, different order → different route."""
        investigate_first = "Investigate the memory service and then fix the bug."
        develop_first = "Fix the bug and then investigate the memory service."
        assert _bare(investigate_first).task_type.value == "investigation_request"
        assert _bare(develop_first).task_type.value == "development_request"


# ---------------------------------------------------------------------------
# 3. The compound-intake fix must not regress
# ---------------------------------------------------------------------------


class TestDevelopmentLeadStillWins:
    @pytest.mark.parametrize("text", DEVELOP_LEAD_INV_CLAUSE)
    def test_development_led_compounds_stay_development(self, text):
        assert _bare(text).task_type.value == "development_request", text

    def test_development_lead_with_a_later_investigation_is_still_development(
        self, kernel
    ):
        for text in DEVELOP_LEAD_INV_CLAUSE:
            assert kernel._conversation._intake(text).task_type.value == (
                "development_request"
            ), text


# ---------------------------------------------------------------------------
# 4. Compounds with targets
# ---------------------------------------------------------------------------


class TestCompoundTargets:
    def test_compound_with_an_architectural_target_follows_the_leading_operation(
        self, kernel
    ):
        text = (
            "Investigate the conversation service and then improve the "
            "conversation service."
        )
        assert kernel._conversation._intake(text).task_type.value == (
            "investigation_request"
        )

    def test_compound_with_an_ambiguous_target_does_not_guess(self):
        """'research' is both a component and a capability; nothing is chosen."""
        text = "Improve research and investigate what is missing."
        assert _bare(text).task_type.value == "investigation_request"

    def test_compound_with_an_unresolved_target_does_not_fabricate(self):
        text = "Improve the zzz widget and investigate the flooble."
        assert _bare(text).task_type.value == "investigation_request"

    def test_a_literal_capability_word_still_qualifies_a_development_lead(self):
        text = "Improve capability and investigate the gaps."
        assert _bare(text).task_type.value == "development_request"


# ---------------------------------------------------------------------------
# 5. Single-clause requests are unchanged
# ---------------------------------------------------------------------------


class TestSingleClauseUnchanged:
    @pytest.mark.parametrize(
        "text",
        (
            "Add a deterministic regression test.",
            "Fix this documented bug.",
            "Improve the conversation capability.",
            "Refactor the conversation module.",
        ),
    )
    def test_single_clause_development_is_development(self, text):
        assert _bare(text).task_type.value == "development_request", text

    @pytest.mark.parametrize(
        "text",
        (
            "Investigate the storage layer.",
            "Investigate the memory service but do not modify anything.",
            "Examine the conversation service.",
        ),
    )
    def test_single_clause_investigation_is_investigation(self, text):
        assert _bare(text).task_type.value == "investigation_request", text

    def test_plain_questions_are_unchanged(self):
        for text in ("What is the conversation service?", "How does it work?"):
            assert _bare(text).task_type.value != "development_request", text


# ---------------------------------------------------------------------------
# 6. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    @pytest.mark.parametrize("text", (ORIGINAL,) + SIMILAR_READ_ONLY_LEAD)
    def test_repeated_classification_is_identical(self, text):
        first = _bare(text).task_type.value
        for _ in range(3):
            assert _bare(text).task_type.value == first
