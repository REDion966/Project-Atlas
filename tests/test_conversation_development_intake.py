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


class TestRealWorldDevelopmentTargets:
    """Development requests naming a code/test/repository work target.

    The real-world development-interface pilot showed that a developer talking
    to Atlas asks for changes to "a test" / "the bug" / "the code" without naming
    Atlas or a capability. Those are genuine development requests, but the
    original self-target gate dropped them onto the unsupported floor instead of
    the EXISTING governed development path. A code/test/repository target now
    qualifies the request exactly as a self-target does; the development cue is
    still required and negation still wins.
    """

    CODE_TARGET_REQUESTS = (
        "Add a small deterministic test for this behavior.",
        "Fix this specific documented bug.",
        "Fix the bug in Atlas.",
    )

    def test_code_target_request_enters_the_governed_development_path(self):
        for text in self.CODE_TARGET_REQUESTS:
            assert is_development_request(_spec(text)) is True, text

    def test_code_target_request_is_clarified_when_underspecified(self):
        # An under-specified request must fail closed into clarification and must
        # NOT become an executable need.
        for text in self.CODE_TARGET_REQUESTS:
            spec = _spec(text)
            if not needs_clarification(spec):
                continue
            assert task_spec_to_development_need(spec) is None, text

    def test_explicit_self_target_behaviour_is_unchanged(self):
        spec = _spec("add a new capability to Atlas for scheduling")
        assert is_development_request(spec) is True
        assert needs_clarification(spec) is False

    def test_negated_development_cue_still_wins(self):
        assert is_development_request(_spec("Don't fix anything yet.")) is False

    def test_a_bare_noun_is_not_a_development_request(self):
        for text in (
            "Thanks, that helps.",
            "Explain the code to me.",
            "I fixed the tests myself.",
            "What handles development requests?",
        ):
            assert is_development_request(_spec(text)) is False, text


class TestCompoundDevelopmentRequestWithTrailingConstraint:
    """Live REPL trial — a real development request that also carries an
    investigation clause and a "do not modify yet" constraint.

    Observed failure: the request below was classified INVESTIGATION_REQUEST and
    turned into a malformed investigation subject
    ("want add small deterministic regression test capability explanation
    behavior just") plus a development proposal, instead of the governed
    development path. Two bounded causes: the investigation branch was evaluated
    before the development evidence, and negation was applied per-utterance, so
    the negated "modify" in the trailing constraint cancelled the un-negated
    "add". Both are corrected in the existing deterministic intake; the
    contextual phrase "we just discussed" is NOT the cause (the single-sentence
    form already routed correctly) and no reference machinery was added.
    """

    ORIGINAL = (
        "I want you to add a small deterministic regression test for the "
        "capability-explanation behavior we just discussed. First investigate "
        "the relevant implementation and existing tests, then explain what you "
        "would change and why. Do not modify anything yet."
    )

    def test_original_request_is_a_development_request(self):
        assert is_development_request(_spec(self.ORIGINAL)) is True

    def test_trailing_no_modification_constraint_does_not_erase_the_request(self):
        # The constraint is a separate, already-supported stance: it must not
        # cancel the development request it is attached to.
        spec = _spec(
            "Add a deterministic test. Do not modify anything yet."
        )
        assert is_development_request(spec) is True

    def test_development_survives_an_investigation_clause(self):
        for text in (
            "Add a test. Investigate the implementation.",
            "I want you to add a regression test. First investigate the "
            "implementation and existing tests.",
        ):
            assert is_development_request(_spec(text)) is True, text

    def test_negation_still_wins_when_every_cue_is_negated(self):
        for text in (
            "Do not modify anything yet.",
            "Don't fix anything yet.",
        ):
            assert is_development_request(_spec(text)) is False, text

    def test_plain_investigation_requests_are_unchanged(self):
        for text in (
            "First investigate the relevant implementation and existing tests.",
            "Investigate the storage layer.",
            "Investigate the memory service but do not modify anything.",
            "Investigate the conversation system, create a development proposal, "
            "and present it for my approval.",
        ):
            assert _spec(text).task_type is TaskType.INVESTIGATION_REQUEST, text

    def test_research_lead_is_still_research(self):
        assert (
            _spec("Research how Atlas could improve scheduling.").task_type
            is TaskType.INFORMATION_REQUEST
        )
