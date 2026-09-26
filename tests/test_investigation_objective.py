"""Investigation objective — the operation's bounded OBJECT reaches the investigation.

Checkpoint 1 finding: the shared semantic frame already records WHICH operation
owns a turn (``domain``/``operation``), but the investigation boundary received
only the raw sentence and re-derived a whole-sentence token bag, so function
words ("you", "don't", "know", "possible") became repository search terms.

This pins the smallest correcting integration:

* ``SemanticFrame.operation_object`` — the bounded OBJECT of the owning
  operation, with SURFACE words preserved (the read-only investigation matches
  repository text, not lemmas);
* ``InvestigationService.investigate(..., objective=...)`` — the objective
  selects the evidence concepts, falls back ONCE to the pre-existing
  whole-target concepts when it yields no scope, and reports the retained
  target unchanged;
* ``ConversationService`` — passes the objective derived from the frame.

Assertions target routing/representation (objective, retained target, scope,
governance metadata), never prose.
"""

from __future__ import annotations

from atlas.conversation import semantic_frame as sf
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.task_intake import TaskType


class _FailingAI:
    """Any provider contact is a failure: this path is deterministic/model-free."""

    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


def _tiny_repo(tmp_path):
    """A minimal repository so an investigation is fast and deterministic."""
    package = tmp_path / "atlas"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "technology_analysis.py").write_text(
        "class TechnologyAnalysis:\n"
        "    \"\"\"Assess a technology: technology fit, technology evidence.\"\"\"\n"
        "\n"
        "    def assess(self, technology):\n"
        "        return technology\n",
        encoding="utf-8",
    )
    (package / "scheduled_task.py").write_text(
        "class ScheduledTask:\n"
        "    \"\"\"A scheduled task.\"\"\"\n"
        "\n"
        "    def run(self):\n"
        "        return \"scheduled task\"\n",
        encoding="utf-8",
    )
    (package / "unrelated_thing.py").write_text(
        "class UnrelatedThing:\n"
        "    \"\"\"Nothing to do with the requests under test.\"\"\"\n"
        "\n"
        "    def play(self):\n"
        "        return 42\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# 1. The frame exposes the operation's bounded object
# ---------------------------------------------------------------------------


class TestOperationObject:
    def test_evidenced_turns_yield_their_object(self):
        assert (
            sf.operation_object(
                "If you don't know how to solve a problem, can you investigate "
                "possible solutions?"
            )
            == "possible solutions"
        )
        assert (
            sf.operation_object(
                "Could you investigate a new technology and see whether it would help you?"
            )
            == "new technology"
        )
        assert (
            sf.operation_object(
                "Suppose I asked you to gain a capability that you don't currently have. "
                "Could you investigate what's missing, research possible ways to "
                "implement it, and develop it under your normal safety rules?"
            )
            == "missing"
        )

    def test_well_formed_targets_keep_their_surface_words(self):
        # Surface forms are preserved, so the investigation's substring matching
        # behaves exactly as before for already-well-formed targets.
        assert (
            sf.operation_object("Investigate the memory architecture.")
            == "memory architecture"
        )
        assert (
            sf.operation_object("Investigate the F17 datetime failures")
            == "f17 datetime failures"
        )
        assert (
            sf.operation_object("Investigate why the scheduled task failed.")
            == "scheduled task failed"
        )

    def test_no_owning_operation_yields_nothing(self):
        for text in ("", "   ", "hello there", "thanks, that helps", "status"):
            assert sf.operation_object(text) == "", text
        assert sf.operation_object(None) == ""

    def test_bounded_and_deterministic(self):
        long_turn = "Investigate " + " ".join(f"topic{index}" for index in range(40))
        first = sf.operation_object(long_turn)
        assert first == sf.operation_object(long_turn)
        assert len(first) <= sf._MAX_SUBJECT_CHARS
        assert len(first.split()) <= sf.MAX_SUBJECT_TOKENS

    def test_other_operations_are_supported_by_the_same_helper(self):
        assert sf.operation_object("Explain how the memory system works.") == "memory system"
        assert sf.operation_object("Compare Atlas with Aider.") == "atlas aider"

    def test_constraint_markers_end_the_object_span(self):
        # Checkpoint 2: a boundary CONDITION ("without modifying anything") is not
        # the objective, so it must not be reported as one. The pre-existing
        # target-based concepts then apply unchanged.
        assert sf.operation_object("Investigate this without modifying anything.") == ""
        assert sf.operation_object("Investigate the deployment without downtime.") == (
            "deployment"
        )
        assert sf.operation_object("Investigate why the task did not run.") == "task"

    def test_constraint_only_objective_keeps_the_target_behaviour(self, tmp_path):
        service = InvestigationService(str(_tiny_repo(tmp_path)))
        turn = "Investigate this without modifying anything."
        report = service.investigate(turn, objective=sf.operation_object(turn))
        assert report.objective == ""
        assert "**Objective:**" not in report.to_markdown()
        # The pre-existing target cleaning already strips the constraint clause;
        # only the misleading objective is removed by this checkpoint.
        assert report.target == "Investigate this"
        assert report.modification_status == "NONE"


# ---------------------------------------------------------------------------
# 2. The investigation uses the objective, and cannot degenerate
# ---------------------------------------------------------------------------


class TestInvestigationObjective:
    def test_objective_selects_the_evidence_and_is_reported(self, tmp_path):
        service = InvestigationService(str(_tiny_repo(tmp_path)))
        turn = "Could you investigate a new technology and see whether it would help you?"
        report = service.investigate(turn, objective="new technology")
        assert report.target == turn  # retained identity unchanged
        assert report.objective == "new technology"
        assert any("technology_analysis" in f for f in report.affected_files), (
            report.affected_files
        )
        assert not any("unrelated_thing" in f for f in report.affected_files)
        assert "**Objective:** new technology" in report.to_markdown()

    def test_absent_objective_is_byte_identical_to_previous_behaviour(self, tmp_path):
        service = InvestigationService(str(_tiny_repo(tmp_path)))
        turn = "Investigate the memory architecture."
        baseline = service.investigate(turn)
        assert baseline.objective == ""
        assert "**Objective:**" not in baseline.to_markdown()
        assert baseline.findings == service.investigate(turn).findings  # deterministic

    def test_objective_matching_nothing_falls_back_to_the_target(self, tmp_path):
        service = InvestigationService(str(_tiny_repo(tmp_path)))
        turn = "Investigate why the scheduled task failed."
        baseline = service.investigate(turn)
        # A faithful objective can name no module at all; the report must not
        # degenerate into "no evidence" when the target itself yields some.
        fallback = service.investigate(turn, objective="zzz_nowhere_concept")
        assert fallback.objective == "zzz_nowhere_concept"  # what was asked is recorded
        assert fallback.components == baseline.components
        assert fallback.components, "the target's own concepts must still be used"

    def test_objective_changes_nothing_but_evidence_selection(self, tmp_path):
        service = InvestigationService(str(_tiny_repo(tmp_path)))
        turn = "Investigate the F17 datetime failures"
        report = service.investigate(turn, objective="f17 datetime failures")
        assert report.target == turn
        assert report.modification_status == "NONE"


# ---------------------------------------------------------------------------
# 3. Conversation integration: the frame's objective reaches the investigation
# ---------------------------------------------------------------------------


class _RecordingInvestigation:
    """Captures the exact call the conversation layer makes."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def investigate(self, target: str, *, objective: str = ""):
        from atlas.conversation.investigation import InvestigationReport

        self.calls.append({"target": target, "objective": objective})
        return InvestigationReport(
            target=target, objective=objective, modification_status="NONE"
        )


def _service(investigation=None) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        investigation_service=investigation,
    )


class TestConversationIntegration:
    def test_conversation_passes_the_bounded_objective(self):
        recording = _RecordingInvestigation()
        turn = "Could you investigate a new technology and see whether it would help you?"
        message = _service(recording).send(turn)

        assert recording.calls == [{"target": turn, "objective": "new technology"}]
        assert message.metadata["investigation"]["target"] == turn
        assert message.metadata["investigation"]["objective"] == "new technology"

    def test_well_formed_investigation_is_unchanged(self):
        recording = _RecordingInvestigation()
        turn = "Investigate the memory architecture."
        message = _service(recording).send(turn)

        assert recording.calls == [{"target": turn, "objective": "memory architecture"}]
        assert message.metadata["investigation"]["target"] == turn

    def test_real_end_to_end_objective_shapes_evidence(self, tmp_path):
        turn = "Could you investigate a new technology and see whether it would help you?"
        service = _service(InvestigationService(str(_tiny_repo(tmp_path))))
        message = service.send(turn)

        meta = message.metadata["investigation"]
        assert meta["objective"] == "new technology"
        assert meta["target"] == turn
        assert meta["modification_status"] == "NONE"
        assert any("technology_analysis" in f for f in meta["affected_files"])
        assert "**Objective:** new technology" in message.content
        assert "**Modification performed:** NONE" in message.content

    def test_read_only_and_governance_neutral(self):
        recording = _RecordingInvestigation()
        turn = "Could you investigate a new technology and see whether it would help you?"
        service = _service(recording)
        message = service.send(turn)

        for key in ("execution", "approval", "promotion"):
            assert key not in message.metadata, key
        state = service.state_manager.state
        assert state.pending_approval_id is None
        assert state.evolution_proposal_id is None
        # The retained operation is still the read-only investigation.
        assert state.last_operation.kind == TaskType.INVESTIGATION_REQUEST.value
        assert state.last_operation.operand == turn

    def test_task_typing_is_unchanged(self):
        intake = TaskIntake()
        assert (
            intake.intake(
                "Could you investigate a new technology and see whether it would help you?"
            ).task_type
            is TaskType.INVESTIGATION_REQUEST
        )
        assert (
            intake.intake(
                "Summarize the tradeoffs of caching."
            ).task_type
            is not TaskType.INVESTIGATION_REQUEST
        )
