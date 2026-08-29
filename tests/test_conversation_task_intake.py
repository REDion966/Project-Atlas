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
