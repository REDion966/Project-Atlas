"""Command 4 — structured change-request meaning (L1/L3/L6) + classification
convergence.

Covers the Atlas-owned meaning layer, the fail-closed contracts, and the
integration points in the deterministic intake — including the existing
classification contracts that must NOT change.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.conversation.development_intent import (  # noqa: E402
    MAX_TARGETS,
    MAX_TEXT_CHARS,
    ChangeAction,
    MeaningStatus,
    RequestModality,
    TargetKind,
    action_forms,
    interpret_development_intent,
)
from atlas.conversation.task_intake import TaskIntake, TaskType  # noqa: E402


def _types(text: str) -> TaskType:
    return TaskIntake().intake(text).task_type


class TestMeaningLayer:
    def test_imperative_change_request(self):
        intent = interpret_development_intent("Add a small helper for X.")
        assert intent.modality is RequestModality.IMPERATIVE
        assert intent.action is ChangeAction.CREATE
        assert intent.is_change_request is True

    def test_gerund_subject_is_not_an_imperative(self):
        intent = interpret_development_intent("Fixing the capability is important.")
        assert intent.modality is RequestModality.STATEMENT
        assert intent.is_change_request is False

    def test_past_form_is_not_an_imperative(self):
        intent = interpret_development_intent("Built the capability.")
        assert intent.is_change_request is False

    def test_action_classes_are_recognised(self):
        cases = {
            "Add a helper.": ChangeAction.CREATE,
            "Refactor the helper.": ChangeAction.MODIFY,
            "Remove the import.": ChangeAction.REMOVE,
            "Fix the bug.": ChangeAction.REPAIR,
            "Document the module.": ChangeAction.DOCUMENT,
        }
        for text, expected in cases.items():
            assert interpret_development_intent(text).action is expected, text

    def test_modality_is_independent_of_action(self):
        assert interpret_development_intent("Implement X.").modality is RequestModality.IMPERATIVE
        assert interpret_development_intent("Can you implement X?").modality is RequestModality.REQUEST
        assert interpret_development_intent("Please add X.").modality is RequestModality.REQUEST
        assert interpret_development_intent("I need X implemented.").modality is RequestModality.NEED
        assert interpret_development_intent("How do I add X?").modality is RequestModality.QUESTION

    def test_negation_is_detected_and_refuses(self):
        intent = interpret_development_intent("Do not add anything to atlas/kernel/atlas.py.")
        assert intent.negated is True
        assert intent.is_change_request is False

    def test_a_bare_report_is_not_a_change_request(self):
        for text in (
            "There is a bug in the parser.",
            "The implementation is complete.",
            "Hello there.",
        ):
            assert interpret_development_intent(text).is_change_request is False, text

    def test_a_question_about_method_is_not_a_change_request(self):
        assert interpret_development_intent("How do I add a helper?").is_change_request is False

    def test_a_light_verb_with_a_demonstrative_object_is_not_a_change(self):
        # A follow-up about the previous RESPONSE, not a request to change code.
        for text in (
            "Can you make that simpler?",
            "Make it better.",
            "Could you make this clearer?",
        ):
            assert interpret_development_intent(text).is_change_request is False, text

    def test_a_light_verb_with_a_named_object_is_still_a_change(self):
        assert interpret_development_intent("Could you make X work?").is_change_request is True
        assert interpret_development_intent("Make a helper for X.").is_change_request is True


class TestTargets:
    def test_paths_modules_and_symbols_are_extracted(self):
        intent = interpret_development_intent(
            "Refactor `helper` in atlas/evolution/change_guard.py and "
            "atlas.research.repository_map."
        )
        kinds = {target.kind for target in intent.targets}
        assert TargetKind.PATH in kinds
        assert TargetKind.MODULE in kinds
        assert TargetKind.SYMBOL in kinds
        values = {target.value for target in intent.targets}
        assert "atlas/evolution/change_guard.py" in values

    def test_code_unit_nouns_are_inferred_not_concrete(self):
        intent = interpret_development_intent("Add a small helper for X.")
        assert intent.concrete_targets == ()
        assert any(t.kind is TargetKind.CODE_UNIT for t in intent.targets)

    def test_targets_are_bounded(self):
        text = "Add " + " ".join(f"atlas/f{index}.py" for index in range(50))
        intent = interpret_development_intent(text)
        assert len(intent.targets) <= MAX_TARGETS


class TestMeaningStatus:
    def test_known_when_a_concrete_target_is_named(self):
        intent = interpret_development_intent("Add a function to atlas/research/relevance.py.")
        assert intent.status is MeaningStatus.KNOWN

    def test_inferred_when_only_a_code_unit_is_named(self):
        assert interpret_development_intent("Add a helper.").status is MeaningStatus.INFERRED

    def test_ambiguous_when_only_a_pronoun_refers(self):
        intent = interpret_development_intent("There's something missing; can you add it?")
        assert intent.status is MeaningStatus.AMBIGUOUS

    def test_unknown_when_not_a_change_request(self):
        assert interpret_development_intent("Hello there.").status is MeaningStatus.UNKNOWN

    def test_unsupported_when_no_action_is_recognised(self):
        # A request directed at Atlas whose action is outside the closed classes.
        intent = interpret_development_intent("Can you frobnicate the thing?")
        assert intent.is_change_request is False
        assert intent.status is MeaningStatus.UNKNOWN

    def test_the_status_vocabulary_is_exactly_the_l6_set(self):
        assert {status.value for status in MeaningStatus} == {
            "known",
            "inferred",
            "ambiguous",
            "unknown",
            "unsupported",
        }


class TestContractAndFailingClosed:
    def test_malformed_input_never_raises(self):
        for bad in (None, 5, [], {}, "", "   "):
            intent = interpret_development_intent(bad)
            assert intent.is_change_request is False

    def test_input_is_bounded(self):
        intent = interpret_development_intent("Add a helper. " + "x" * (MAX_TEXT_CHARS * 2))
        assert len(intent.text) <= MAX_TEXT_CHARS

    def test_to_dict_is_json_safe_and_carries_no_authority(self):
        intent = interpret_development_intent("Add a helper to atlas/x.py.")
        payload = intent.to_dict()
        for forbidden in ("authorized", "approved", "execute", "promote", "apply"):
            assert forbidden not in payload
        assert payload["is_change_request"] is True
        assert isinstance(payload["targets"], list)

    def test_the_intent_is_immutable(self):
        intent = interpret_development_intent("Add a helper.")
        with pytest.raises(Exception):
            intent.text = "changed"  # type: ignore[misc]

    def test_interpretation_is_deterministic(self):
        text = "Can you add a helper to atlas/x.py?"
        assert interpret_development_intent(text).to_dict() == (
            interpret_development_intent(text).to_dict()
        )

    def test_the_action_vocabulary_is_closed_and_auditable(self):
        forms = action_forms()
        assert set(forms) == {action.value for action in ChangeAction if action is not ChangeAction.UNKNOWN}
        assert all(isinstance(v, tuple) for v in forms.values())


class TestIntakeConvergence:
    """§17 — semantically equivalent requests converge on ONE representation."""

    EQUIVALENTS = (
        "Implement X.",
        "Can you implement X?",
        "I need X implemented.",
        "Please add X.",
        "Could you make X work?",
        "I want Atlas to support X.",
        "Add a small helper for X.",
        "I need you to implement X.",
        "Implement a development change in atlas/research/relevance.py: add a helper.",
        "Add a module-level docstring line to atlas/research/relevance.py.",
        "Add a bounded function `describe_ranking_constants` to atlas/research/relevance.py.",
    )

    def test_every_equivalent_phrasing_classifies_as_development(self):
        for text in self.EQUIVALENTS:
            assert _types(text) is TaskType.DEVELOPMENT_REQUEST, text

    def test_a_long_specified_request_reaches_the_need_bridge(self):
        from atlas.conversation.development_intake import (
            task_spec_to_development_need,
        )

        text = (
            "Add a small bounded helper function to the repository relevance module "
            "that returns the module's deterministic ranking constants as a "
            "read-only list of (name, value) pairs. Target "
            "atlas/research/relevance.py. Preserve all existing behaviour."
        )
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        # The relative "that" must not be read as an unresolved reference.
        assert "reference" not in spec.ambiguity.ambiguities
        assert task_spec_to_development_need(spec) is not None

    def test_negated_requests_are_not_promoted(self):
        assert _types("Do not add anything to atlas/kernel/atlas.py.") is not (
            TaskType.DEVELOPMENT_REQUEST
        )


class TestPreservedContracts:
    """Existing classification contracts that Command 4 must NOT change."""

    def test_bare_artifact_actions_stay_action_requests(self):
        for text in (
            "Create a report of the last week",
            "Write the report.",
            "Create a report.",
            "Generate a report.",
            "Make a report.",
            "Build an email notifier.",
            "Write documentation for the writer module.",
        ):
            assert _types(text) is TaskType.ACTION_REQUEST, text

    def test_greeting_is_still_conversation(self):
        assert _types("Hello Atlas, how are you today") is TaskType.CONVERSATION

    def test_research_is_still_information(self):
        assert (
            _types("Find the latest research on memory consolidation")
            is TaskType.INFORMATION_REQUEST
        )

    def test_questions_are_still_questions(self):
        assert _types("What does this module do?") is TaskType.QUESTION

    def test_gerund_reports_are_not_development(self):
        for text in (
            "Fixing the capability is important.",
            "Modifying the capability is unnecessary.",
            "Refactoring the module is complete.",
            "Building the capability is underway.",
            "The capability was developed yesterday.",
        ):
            assert _types(text) is not TaskType.DEVELOPMENT_REQUEST, text

    def test_explicit_development_cues_are_unchanged(self):
        for text in (
            "Add a new capability to Atlas for scheduling",
            "Rebuild the capability.",
            "I want Atlas to add an email notification capability for "
            "long-running tasks.",
        ):
            assert _types(text) is TaskType.DEVELOPMENT_REQUEST, text
