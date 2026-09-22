"""B2 — Conversational task intake (deterministic-first) tests."""

import json
from datetime import datetime

from atlas.conversation.task_intake import (
    TaskIntake,
    TaskType,
)


class TestTaskTypeClassification:
    def test_question(self):
        spec = TaskIntake().intake("What does this module do?")
        assert spec.task_type is TaskType.QUESTION

    def test_information_request(self):
        spec = TaskIntake().intake("Find the latest research on memory consolidation")
        assert spec.task_type is TaskType.INFORMATION_REQUEST

    def test_action_request(self):
        spec = TaskIntake().intake("Create a report of the last week")
        assert spec.task_type is TaskType.ACTION_REQUEST

    def test_development_request(self):
        spec = TaskIntake().intake("Add a new capability to Atlas for scheduling")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST

    def test_conversation(self):
        spec = TaskIntake().intake("Hello Atlas, how are you today")
        assert spec.task_type is TaskType.CONVERSATION

    def test_unknown_for_degenerate_input(self):
        spec = TaskIntake().intake("...")
        assert spec.task_type is TaskType.UNKNOWN


class TestObjectiveExtraction:
    def test_objective_starts_at_first_action_verb(self):
        spec = TaskIntake().intake("Could you please create a summary of today")
        assert spec.intent.startswith("create a summary")

    def test_objective_bounded(self):
        spec = TaskIntake().intake("build " + ("x" * 10_000))
        assert len(spec.intent) <= 400

    def test_develop_objective_anchors_at_the_whole_word_verb(self):
        spec = TaskIntake().intake(
            "Develop an email notification capability for long-running tasks."
        )
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.intent.startswith("Develop an email notification capability")
        assert "email notification capability" in spec.intent
        assert spec.intent != "running tasks."

    def test_objective_anchors_at_the_earliest_action_cue(self):
        # "generate" and "deploy" are both action cues; the earliest position
        # wins, independent of collection iteration order.
        spec = TaskIntake().intake("Generate a report for the deployment.")
        assert spec.intent == "Generate a report for the deployment."

    def test_objective_anchors_at_the_earliest_development_cue(self):
        spec = TaskIntake().intake("improve and add a module")
        assert spec.intent == "improve and add a module"

    def test_objective_earliest_cue_across_development_and_action(self):
        # An action cue before a whole-word development verb anchors the
        # objective; a development verb at the earliest position still wins.
        action_first = TaskIntake().intake("create a capability and develop it")
        assert action_first.intent == "create a capability and develop it"

        verb_first = TaskIntake().intake(
            "Develop a scheduling capability and create a report."
        )
        assert verb_first.intent.startswith("Develop a scheduling capability")

    def test_objective_falls_back_to_the_whole_instruction(self):
        text = "the memory architecture is interesting"
        spec = TaskIntake().intake(text)
        assert spec.intent == text


class TestItemExtraction:
    def test_constraints(self):
        spec = TaskIntake().intake("build a report without internet using local data")
        assert spec.constraints
        assert any("without internet" in c for c in spec.constraints)

    def test_priorities(self):
        spec = TaskIntake().intake("first fix the bug, urgent")
        assert spec.priorities
        assert any("first" in p for p in spec.priorities)

    def test_success_criteria(self):
        spec = TaskIntake().intake("write the code and make sure tests pass")
        assert spec.success_criteria
        assert any("make sure tests pass" in s for s in spec.success_criteria)

    def test_appearance_order_and_dedup(self):
        spec = TaskIntake().intake("do not use cache; without network; do not use cache")
        assert len(spec.constraints) == len(set(spec.constraints))


class TestDeterminism:
    def test_identical_input_identical_spec(self):
        text = "add a capability to Atlas that verifies results"
        now = datetime(2026, 8, 28, 12, 0, 0)
        a = TaskIntake(now=now).intake(text)
        b = TaskIntake(now=now).intake(text)
        assert a.to_dict() == b.to_dict()

    def test_deterministic_ids(self):
        text = "analyze this input"
        a = TaskIntake().intake(text)
        b = TaskIntake().intake(text)
        assert a.task_id == b.task_id
        assert a.input_hash == b.input_hash
        assert len(a.task_id) == 16


class TestAmbiguity:
    def test_under_specified_action_has_clarification(self):
        spec = TaskIntake().intake("make it work")
        assert spec.needs_clarification
        assert spec.ambiguity.clarification_questions

    def test_well_specified_action_no_clarification(self):
        spec = TaskIntake().intake(
            "create a report so that I can review progress, using local data"
        )
        assert not spec.needs_clarification

    def test_reference_detection_is_word_boundary_aware(self):
        # "it" inside "priority" must not trigger reference ambiguity.
        spec = TaskIntake().intake("build a report with priority")
        assert "reference" not in spec.ambiguity.ambiguities


class TestRelativeComplementizerThat:
    """L6 — a bounded relative/complementizer "that" is not a reference.

    The reference reason is evaluated PER OCCURRENCE: a "that" in the closed
    function-word context ``<determiner|quantifier> <word> that`` is a
    complementizer (a different lexeme from a demonstrative/pronoun "that") and
    contributes nothing, while every other occurrence keeps its existing
    fail-closed behavior.
    """

    def test_relative_that_no_longer_raises_the_reference_reason(self):
        spec = TaskIntake().intake("Build a module that tracks long-running tasks.")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.ambiguity.ambiguities == ("success",)
        assert "reference" not in spec.ambiguity.ambiguities
        assert spec.ambiguity.ambiguity_score == 0.25
        assert spec.needs_clarification is False

    def test_second_relative_that_case(self):
        spec = TaskIntake().intake("Add a capability that remembers context.")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert "reference" not in spec.ambiguity.ambiguities
        assert spec.needs_clarification is False

    def test_other_relative_that_cases(self):
        for text in (
            "Build a module that tracks tasks.",
            "Add a capability that remembers context.",
        ):
            spec = TaskIntake().intake(text)
            assert "reference" not in spec.ambiguity.ambiguities, text
            assert spec.needs_clarification is False, text

    def test_mixed_occurrence_keeps_the_genuine_reference(self):
        # The "that" is a complementizer, but "this" IS a genuine (unresolved)
        # reference: only the relative "that" contribution is removed, so the
        # reason survives and the turn stays fail-closed.
        for text in (
            "Create a module that handles this.",
            "Improve the module that tracks this.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.ambiguity.ambiguities == ("reference", "success"), text
            assert spec.ambiguity.ambiguity_score == 0.55, text
            assert spec.needs_clarification is True, text

    def test_genuine_demonstrative_reference_is_unchanged(self):
        spec = TaskIntake().intake("Develop that capability.")
        assert spec.ambiguity.ambiguities == ("reference", "success")
        assert spec.ambiguity.ambiguity_score == 0.55
        assert spec.needs_clarification is True

    def test_bare_references_are_unchanged(self):
        for text in ("Build it.", "Run this.", "Summarize them.", "make it work"):
            spec = TaskIntake().intake(text)
            assert spec.ambiguity.ambiguities == ("reference", "success"), text
            assert spec.ambiguity.ambiguity_score == 0.55, text
            assert spec.needs_clarification is True, text

    def test_determiner_demonstrative_is_unchanged(self):
        spec = TaskIntake().intake("Deploy this service.")
        assert spec.ambiguity.ambiguities == ("reference", "success")
        assert spec.ambiguity.ambiguity_score == 0.55
        assert spec.needs_clarification is True

    def test_research_reference_evidence_is_unchanged(self):
        spec = TaskIntake().intake(
            "Find evidence about how this repository currently handles references."
        )
        assert spec.task_type is TaskType.INFORMATION_REQUEST
        assert spec.ambiguity.ambiguities == ("reference",)
        assert spec.ambiguity.ambiguity_score == 0.30
        assert spec.needs_clarification is False

    def test_deferred_expletive_it_is_unchanged(self):
        for text in (
            "It would be useful if Atlas could notify me when something takes too long.",
            "Would it be possible for Atlas to research this and tell me if finds?",
        ):
            spec = TaskIntake().intake(text)
            assert "reference" in spec.ambiguity.ambiguities, text
            assert spec.ambiguity.ambiguity_score == 0.30, text

    def test_relative_that_does_not_suppress_other_reasons(self):
        # Only the reference reason is affected; the success reason is untouched.
        spec = TaskIntake().intake("Build a module that tracks tasks.")
        assert spec.ambiguity.ambiguities == ("success",)
        assert spec.ambiguity.clarification_questions == (
            "What outcome would tell you this is done?",
        )


class TestRobustness:
    def test_empty_input(self):
        spec = TaskIntake().intake("")
        assert spec.task_type is TaskType.UNKNOWN
        assert spec.needs_clarification is False

    def test_whitespace_input(self):
        spec = TaskIntake().intake("   ")
        assert spec.task_type is TaskType.UNKNOWN

    def test_non_string_input(self):
        spec = TaskIntake().intake(12345)  # type: ignore[arg-type]
        assert spec.task_type is TaskType.UNKNOWN

    def test_overlong_input_bounded(self):
        spec = TaskIntake().intake("build " + ("y" * 100_000))
        assert len(spec.intent) <= 400
        assert len(spec.goal) <= 500
        assert len(spec.to_dict()["context"]["concepts"]) <= 24

    def test_control_characters_sanitized(self):
        spec = TaskIntake().intake("build\x00a report\x1fnow")
        assert "\x00" not in spec.intent
        assert "\x1f" not in spec.intent

    def test_json_safe_serialization(self):
        spec = TaskIntake().intake("build a report with priority, ensure done")
        json.dumps(spec.to_dict())


class TestProvenance:
    def test_deterministic_provenance(self):
        spec = TaskIntake().intake("summarize the file")
        assert spec.source == "deterministic"
        assert spec.verified is True

    def test_model_metadata_empty_for_deterministic(self):
        spec = TaskIntake().intake("summarize the file")
        assert spec.model_metadata == {}


class _FakeParser:
    """Duck-typed IntentParser returning a fixed parse dict."""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def parse(self, text, context):
        if self._exc is not None:
            raise self._exc
        return self._result


class TestModelAssistedParsing:
    def test_injected_parser_used(self):
        parser = _FakeParser(
            result={"intent": "model intent", "task_type": "action_request"}
        )
        spec = TaskIntake(parser=parser).intake("build a report")
        assert spec.intent == "model intent"
        assert spec.source == "model_assisted"
        assert spec.verified is False

    def test_model_assisted_provenance(self):
        parser = _FakeParser(result={"intent": "model intent"})
        spec = TaskIntake(parser=parser).intake("build a report")
        assert spec.source == "model_assisted"
        assert spec.verified is False
        assert spec.model_metadata.get("intent_provided") is True

    def test_parser_disabled_by_default(self):
        spec = TaskIntake().intake("build a report")
        assert spec.source == "deterministic"
        assert spec.verified is True

    def test_parser_exception_falls_back(self):
        parser = _FakeParser(exc=RuntimeError("boom"))
        spec = TaskIntake(parser=parser).intake("build a report")
        assert spec.source == "deterministic"
        assert spec.verified is True

    def test_malformed_parser_output_rejected(self):
        parser = _FakeParser(result="not a dict")
        spec = TaskIntake(parser=parser).intake("build a report")
        assert spec.source == "deterministic"
        assert spec.verified is True

    def test_parser_conflict_fields_bounded(self):
        parser = _FakeParser(
            result={
                "intent": "x" * 10_000,
                "constraints": ["a"] * 100,
            }
        )
        spec = TaskIntake(parser=parser).intake("build a report")
        assert len(spec.intent) <= 400
        assert len(spec.constraints) <= 8

    def test_model_confidence_capped(self):
        parser = _FakeParser(result={"intent": "model intent", "task_type": "question"})
        spec = TaskIntake(parser=parser).intake("build a report")
        assert spec.confidence <= 0.5


class TestInvestigationFirstCompoundClassification:
    """Pilot-derived (Defect 1): an investigation-first compound request that
    asks for a proposal to approve must not be hijacked into APPROVAL by its
    forward-looking proposal/approval wording."""

    def test_exact_pilot_request_is_investigation(self):
        spec = TaskIntake().intake(
            "Investigate why the repository test suite is slow and then "
            "prepare a proposal for me to approve."
        )
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_natural_prepare_proposal_compound_is_investigation(self):
        spec = TaskIntake().intake(
            "Investigate the memory architecture and prepare a proposal for "
            "my approval."
        )
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_existing_development_proposal_compound_stays_investigation(self):
        spec = TaskIntake().intake(
            "Investigate the repository and create a development proposal for "
            "the improvement you find."
        )
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_approval_only_wording_stays_approval(self):
        spec = TaskIntake().intake("approve this proposal")
        assert spec.task_type is TaskType.APPROVAL


class TestNaturalLanguageDevelopmentCues:
    """The natural verb "develop" is a bounded, WHOLE-WORD development cue.

    It must recognize the standalone verb without capturing the unrelated
    ``development``/``developer``/``developing`` substrings, and it must keep
    requiring a self-target ("capability"/"module"/... ) to qualify.
    """

    def test_develop_phrases_are_development_requests(self):
        for text in (
            "I want you to develop that capability",
            "develop that capability",
            "Atlas, develop that capability",
            "develop a capability for scheduling follow-ups",
            "develop Atlas further",
            "develop a module for scheduling",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.DEVELOPMENT_REQUEST, text

    def test_existing_development_contracts_preserved(self):
        for text in (
            "implement that capability",
            "add an email notification capability",
            "Add a new capability to Atlas for scheduling",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.DEVELOPMENT_REQUEST, text

    def test_build_email_notifier_keeps_existing_classification(self):
        # "build" is an existing action cue; no self-target/capability/module
        # target is named, so the existing ACTION_REQUEST contract is kept.
        spec = TaskIntake().intake("build an email notifier")
        assert spec.task_type is TaskType.ACTION_REQUEST

    def test_unrelated_develop_wording_is_not_development(self):
        for text in (
            "the development roadmap is long",
            "explain the development lifecycle",
            "who developed this code",
            "what development work is pending",
            "how do I develop a plugin",
            "develop a plan for tomorrow",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST, text

    def test_negated_develop_is_not_development(self):
        for text in (
            "don't develop that capability",
            "do not develop that capability",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST, text

    def test_develop_verb_cue_is_whole_word_only(self):
        # "development"/"developed" merely contain "develop": the objective cue
        # must not match inside them, and the turn must stay non-development.
        for text in (
            "explain the development lifecycle",
            "who developed this code",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST, text
            assert not spec.intent.lower().startswith("develop"), text

    def test_long_running_action_classification_is_unchanged(self):
        # Fixing objective extraction must not change ACTION/DEVELOPMENT
        # classification: the action cue inside "long-running" still decides.
        for text in (
            "I need an email notifier for long-running tasks.",
            "I want Atlas to have an email notification capability for "
            "long-running tasks.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.ACTION_REQUEST, text


class TestBoundedDevelopmentForms:
    """Development cues are explicit accepted WHOLE-WORD forms.

    Substring containment must never turn an unrelated word ("address",
    "prefix") or a nominal/inflected form ("implementation", "improvement",
    "fixing", "modifying", "refactoring", "building") into a development
    signal, while the accepted forms (including the explicit "rebuild") stay
    recognized. The same policy feeds objective extraction.
    """

    def test_accepted_development_forms_are_recognized(self):
        for text in (
            "Add a capability for scheduled follow-ups.",
            "Build a capability for scheduled follow-ups.",
            "Rebuild the capability.",
            "Create a capability for scheduled follow-ups.",
            "Create a module for scheduled follow-ups.",
            "Fix the capability.",
            "Implement the capability.",
            "Improve the capability.",
            "Modify the module.",
            "Refactor the module.",
            "Develop the capability.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.DEVELOPMENT_REQUEST, text

    def test_accidental_substrings_are_not_development(self):
        for text in (
            "Address the capability.",
            "Prefix the capability.",
            "The implementation of the capability is complete.",
            "The improvement is useful.",
            "Fixing the capability is important.",
            "Modifying the capability is unnecessary.",
            "Refactoring the module is complete.",
            "Building the capability is underway.",
            "The capability was developed yesterday.",
            "Development of the capability is complete.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST, text

    def test_objective_does_not_anchor_on_accidental_substrings(self):
        for text in (
            "Address the capability.",
            "Prefix the capability.",
            "The implementation of the capability is complete.",
            "The improvement is useful.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.intent == text, text

    def test_rebuild_anchors_at_the_accepted_form(self):
        spec = TaskIntake().intake("Rebuild the capability.")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.intent == "Rebuild the capability."

    def test_long_running_development_phrasings_are_preserved(self):
        for text in (
            "I want Atlas to add an email notification capability for "
            "long-running tasks.",
            "I want Atlas to develop an email notification capability for "
            "long-running tasks.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.DEVELOPMENT_REQUEST, text


class TestBoundedActionForms:
    """Action cues are explicit accepted WHOLE-WORD forms.

    Substring containment must never turn a word that merely contains a cue
    ("runtime", "writer", "compiler", "computer", "makefile", "unclean") or an
    inflected/passive form ("generated", "compiled", "deployed", "analyzed")
    into an action signal. The same bounded policy feeds objective extraction.
    The observed "long-running" compound is preserved by one narrow explicit
    form rather than by restoring substring matching.
    """

    def test_accepted_action_forms_are_recognized(self):
        for text in (
            "Run the verification.",
            "Write the report.",
            "Create a report.",
            "Generate a report.",
            "Produce a report.",
            "Summarize the report.",
            "Compile the project.",
            "Compute the result.",
            "Calculate the result.",
            "Clean the workspace.",
            "Deploy the service.",
            "Organize the files.",
            "Make a report.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.ACTION_REQUEST, text

    def test_words_containing_a_cue_are_not_action(self):
        for text in (
            "The runtime is available.",
            "Please rerun the verification.",
            "The project is running correctly.",
            "The runway is clear.",
            "Documentation for the writer.",
            "Use the compiler.",
            "Use the makefile.",
            "Please remake the report.",
            "The records are unclean.",
            "A rebuild is needed.",
            "The recreation area is closed.",
            "The project is long-running.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.ACTION_REQUEST, text

    def test_inflected_and_passive_forms_are_not_action(self):
        for text in (
            "The report was generated.",
            "The report was produced.",
            "The report was summarized.",
            "The project was compiled.",
            "The result was computed.",
            "The service was deployed.",
            "The workspace was cleaned.",
            "The data was analyzed.",
            "The total was calculated.",
            "The files were organized.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.ACTION_REQUEST, text

    def test_genuine_whole_word_cue_wins_over_a_collision(self):
        for text in (
            "Run this on the computer.",
            "Write documentation for the writer module.",
            "Compute the result on the computer.",
            "Clean up the unclean records.",
            "Generate a report for the deployment.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.ACTION_REQUEST, text

    def test_objective_does_not_anchor_on_accidental_substrings(self):
        for text in (
            "The runtime is available.",
            "Please rerun the verification.",
            "Documentation for the writer.",
            "Use the compiler.",
            "Use the makefile.",
            "The records are unclean.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.intent == text, text

    def test_objective_anchors_at_the_genuine_action_verb(self):
        for text, prefix in (
            ("Run this on the computer.", "Run this on the computer."),
            ("Write documentation for the writer module.", "Write documentation"),
            ("Compute the result on the computer.", "Compute the result"),
            ("Clean up the unclean records.", "Clean up the unclean records."),
            ("Generate a report for the deployment.", "Generate a report"),
        ):
            spec = TaskIntake().intake(text)
            assert spec.intent.startswith(prefix), text

    def test_long_running_compound_compatibility_is_preserved(self):
        for text in (
            "I need an email notifier for long-running tasks.",
            "I want Atlas to have an email notification capability for "
            "long-running tasks.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.ACTION_REQUEST, text
            assert spec.intent == "long-running tasks."

    def test_run_collisions_are_not_action(self):
        # "run" is whole-word: the compound compatibility form must not leak
        # into ordinary words or into a bare statement.
        for text in (
            "The project is long-running.",
            "The project is running.",
            "Check the runtime.",
            "Please rerun.",
            "The runway is clear.",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.ACTION_REQUEST, text

    def test_frozen_development_and_investigation_precedence_is_unchanged(self):
        # These words are intercepted BEFORE the action family by contracts that
        # are out of scope for this matcher change: "build"/"rebuild" name a
        # self-target ("module") for the development family, and "analyze" is an
        # investigation cue. They must not be re-classified as ACTION here.
        assert (
            TaskIntake().intake("Analyze the report.").task_type
            is TaskType.INVESTIGATION_REQUEST
        )
        assert (
            TaskIntake().intake("Build a module.").task_type
            is TaskType.DEVELOPMENT_REQUEST
        )
        assert (
            TaskIntake().intake("Rebuild the module.").task_type
            is TaskType.DEVELOPMENT_REQUEST
        )
        # Residual: the development objective source owns the whole-word
        # "rebuild" accepted form, so this CONVERSATION turn still anchors its
        # objective there. Changing that would alter the frozen development
        # objective source, so it is pinned here rather than silently drifted.
        rebuild_statement = TaskIntake().intake("A rebuild is needed.")
        assert rebuild_statement.task_type is TaskType.CONVERSATION
        assert rebuild_statement.intent == "rebuild is needed."
