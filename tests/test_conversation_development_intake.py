"""B3 — Conversational development intake (TaskSpec -> DevelopmentNeed) tests.

Covers the pure adapter and clarification gate:
  * DEVELOPMENT_REQUEST mapping
  * non-development TaskTypes are refused
  * needs_clarification gates development
  * bounded fields
  * deterministic output
  * no fabricated code_changes
  * context/constraints propagation
  * malformed/minimal TaskSpec handling
"""

from __future__ import annotations

import json
from datetime import datetime

from atlas.conversation.development_intake import (
    clarification_questions,
    is_development_request,
    needs_clarification,
    task_spec_to_development_need,
)
from atlas.conversation.task_intake import AmbiguityReport, TaskIntake, TaskSpec, TaskType


def _spec(text: str) -> TaskSpec:
    return TaskIntake(now=datetime(2026, 8, 29, 12, 0, 0)).intake(text)


class TestClassificationGate:
    def test_development_request_is_recognized(self):
        spec = _spec("add a new capability to Atlas for scheduling")
        assert is_development_request(spec) is True
        assert needs_clarification(spec) is False

    def test_non_development_types_refused(self):
        for text in (
            "hello Atlas how are you",
            "what does this module do?",
            "find the latest research on memory consolidation",
            "create a report of the last week",
        ):
            spec = _spec(text)
            assert is_development_request(spec) is False, text
            assert task_spec_to_development_need(spec) is None, text

    def test_unknown_refused(self):
        assert task_spec_to_development_need(_spec("...")) is None

    def test_none_refused(self):
        assert is_development_request(None) is False
        assert needs_clarification(None) is False
        assert task_spec_to_development_need(None) is None
        assert clarification_questions(None) == ()


class TestClarificationGate:
    def test_under_specified_development_request_gated(self):
        # "improve this module" is a development cue + self-target ("module")
        # but has no success criteria and an ambiguous reference ("this")
        # -> needs_clarification.
        spec = TaskIntake(now=datetime(2026, 8, 29, 12, 0, 0)).intake(
            "improve this module"
        )
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.needs_clarification is True
        assert needs_clarification(spec) is True
        assert task_spec_to_development_need(spec) is None

    def test_clarification_questions_returned(self):
        spec = _spec("improve this module")
        questions = clarification_questions(spec)
        assert questions
        assert all(isinstance(q, str) for q in questions)


class TestMapping:
    def test_fields_mapped(self):
        spec = _spec(
            "add a new capability to Atlas for scheduling so that tasks run on time, using local data"
        )
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert need.title
        assert need.summary
        assert need.candidate_id == spec.task_id

    def test_constraints_propagate_to_rationale(self):
        spec = _spec(
            "add a capability to Atlas for scheduling without internet using local data"
        )
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert "without internet" in need.rationale
        assert "without internet" in " ".join(need.metadata.get("constraints", []))

    def test_success_criteria_propagate_to_benefit(self):
        spec = _spec(
            "add a capability to Atlas for scheduling so that tasks run on time"
        )
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert need.expected_benefit

    def test_context_propagates_bounded(self):
        spec = _spec("add a capability to Atlas for scheduling")
        need = task_spec_to_development_need(spec)
        assert need is not None
        context = need.metadata.get("context", {})
        assert "concepts" in context
        assert isinstance(context["concepts"], list)
        assert len(context["concepts"]) <= 24

    def test_no_fabricated_code_changes(self):
        spec = _spec("add a new capability to Atlas for scheduling")
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert "code_changes" not in need.metadata
        assert "test_files" not in need.metadata


class TestBounds:
    def test_title_bounded(self):
        spec = TaskIntake(now=datetime(2026, 8, 29, 12, 0, 0)).intake(
            "add " + ("x" * 10_000) + " to Atlas"
        )
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert len(need.title) <= 200

    def test_summary_bounded(self):
        spec = TaskIntake(now=datetime(2026, 8, 29, 12, 0, 0)).intake(
            "add " + ("y" * 10_000) + " to Atlas"
        )
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert len(need.summary) <= 2000

    def test_metadata_is_json_safe(self):
        need = task_spec_to_development_need(
            _spec("add a capability to Atlas for scheduling using local data")
        )
        assert need is not None
        json.dumps(need.metadata)


class TestDeterminism:
    def test_identical_input_identical_need(self):
        text = "add a capability to Atlas for scheduling so that tasks run on time"
        a = task_spec_to_development_need(_spec(text))
        b = task_spec_to_development_need(_spec(text))
        assert a is not None and b is not None
        assert a == b
        assert a.metadata == b.metadata

    def test_minimal_task_spec_handled(self):
        # A minimally valid, fully-specified DEVELOPMENT_REQUEST TaskSpec
        # constructed directly (no success criteria is acceptable for mapping;
        # only needs_clarification gates).
        spec = TaskSpec(
            task_id="abc123",
            task_type=TaskType.DEVELOPMENT_REQUEST,
            intent="improve the capability registry",
            goal="improve the capability registry",
            constraints=(),
            priorities=(),
            success_criteria=("registry stays bounded",),
            context={},
            ambiguity=AmbiguityReport(ambiguity_score=0.0),
            confidence=0.6,
            needs_clarification=False,
            source="deterministic",
            verified=True,
            model_metadata={},
            created_at=datetime(2026, 8, 29, 12, 0, 0),
            input_hash="abc123",
        )
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert need.title == "improve the capability registry"


# ---------------------------------------------------------------------------
# F9 authoring boundary (Command 6)
# ---------------------------------------------------------------------------


class TestAuthoringBoundary:
    """A conversational DevelopmentNeed carries no authoring input, so the
    kernel's deterministic composite change supplier cannot author and the
    governed cycle must fail closed. This documents the existing F9 contract:
    change content is SUPPLIED (operator spec / pre-authored metadata /
    scaffold spec / opt-in model), never derived from a natural-language goal.
    """

    _GOAL = (
        "Add a capability to Atlas that exports the conversation history to a "
        "Markdown file so that I can keep notes. Success criteria: the export "
        "writes a valid Markdown file."
    )

    def _need(self):
        need = task_spec_to_development_need(_spec(self._GOAL))
        assert need is not None
        return need

    def test_conversational_need_carries_no_authoring_input(self):
        need = self._need()
        assert "code_changes" not in need.metadata
        assert "test_files" not in need.metadata
        assert "scaffold" not in need.metadata
        assert need.has_direct_evidence is False

    def test_deterministic_composite_cannot_author_it(self):
        from atlas.evolution.development_cycle import (
            DeterministicChangeSupplier,
        )
        from atlas.evolution.development_scaffold_supplier import (
            CompositeChangeSupplier,
            ScaffoldChangeSupplier,
        )

        need = self._need()
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), ScaffoldChangeSupplier()]
        )
        assert DeterministicChangeSupplier().supply_changes(need) is None
        assert ScaffoldChangeSupplier().supply_changes(need) is None
        assert composite.supply_changes(need) is None

    def test_scaffold_authoring_requires_a_supplied_spec(self):
        from atlas.evolution.development_cycle import DevelopmentNeed
        from atlas.evolution.development_scaffold_supplier import (
            ScaffoldChangeSupplier,
        )

        need = DevelopmentNeed(
            title="add example capability",
            summary="add example capability",
            metadata={
                "scaffold": {
                    "module": "atlas/example/demo_handlers.py",
                    "capability_name": "example.run",
                }
            },
        )
        supplied = ScaffoldChangeSupplier().supply_changes(need)
        assert supplied is not None
        assert supplied.origin == "deterministic-scaffold"
        assert supplied.code_changes[0][0] == "atlas/example/demo_handlers.py"
