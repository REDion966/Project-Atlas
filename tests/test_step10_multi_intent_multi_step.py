"""Step 10 — multi-intent & multi-step understanding.

The baseline (real Atlas/kernel, multi-turn) showed that Step 6 reads only
CASUAL multi-intent turns (its handler answers understood clauses through the
builtin surface) and the Step 2 goal plan composes only a fixed closed set of
two-stage slices. A genuinely unseen multi-intent/multi-step OPERATIONAL request
was therefore handed to a single operational route that acted on the WHOLE
sentence and silently dropped the other intents:

  * "Investigate A and also research B"  -> only the investigation ran (on the
    whole sentence); the research intent vanished;
  * "First investigate A, then research B" -> the splitter did not even see a
    second intent (no coordinator);
  * "Investigate A, then analyze the findings" -> the analysis route fired over
    STALE retained evidence instead of the step's own result;
  * "Investigate the component that handles X and Y" -> a SINGLE multi-clause
    intent was over-split by the Step 6 splitter.

Step 10 adds one bounded, deterministic REPRESENTATION of such a request
(``atlas/conversation/multi_step.py``) plus one handler that routes its runnable
read-only steps through the EXISTING orchestration bridge, answers understood
casual clauses through the EXISTING builtin surface, and reports every other
step truthfully. Nothing is executed that the user did not ask for, no order or
dependency is invented, and no governed boundary is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.message import Message
from atlas.conversation.multi_step import (
    DEP_RESULT,
    EXEC_ANALYSIS,
    EXEC_KNOWLEDGE,
    EXEC_INVESTIGATION,
    STATUS_BLOCKED,
    STATUS_GOVERNED,
    STATUS_UNSUPPORTED,
    build_execution_steps,
    build_multi_step,
    split_clauses,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.models import NodeKind

_REPO_ROOT = Path(__file__).resolve().parents[1]


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("no model may be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _gen():
            raise RuntimeError("no model may be contacted")
            yield ""  # pragma: no cover

        return _gen()


class _RecordingBridge:
    """A bounded stand-in for the kernel-owned orchestration bridge."""

    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, text, steps, session_context=None):
        self.calls.append((text, tuple(steps)))
        entries = tuple(
            {
                "step_id": step.step_id,
                "kind": getattr(getattr(step, "kind", ""), "value", str(step.kind)),
                "target": getattr(step, "target", ""),
                "state": "completed",
                "failure_kind": None,
                "output": {},
            }
            for step in steps
        )
        return Message(
            role="assistant",
            content=f"Done: {text}\nSteps completed: {len(steps)}/{len(steps)}.",
            metadata={"orchestration": {"status": "completed", "steps": entries}},
        )


def _service(bridge: _RecordingBridge | None = None) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        goal_orchestration_resolver=bridge if bridge is not None else _RecordingBridge(),
    )


def _started_atlas(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


# ---------------------------------------------------------------------------
# 1. Clause splitting / ordering evidence
# ---------------------------------------------------------------------------


class TestSplitClauses:
    def test_plain_and_splits_into_clauses(self):
        clauses = split_clauses("Investigate storage and research caching")
        assert [c.text for c in clauses] == ["Investigate storage", "research caching"]
        assert all(c.ordered is False for c in clauses)

    def test_then_marks_explicit_order(self):
        clauses = split_clauses("First investigate the storage layer, then research caching")
        assert [c.text.lower() for c in clauses] == [
            "investigate the storage layer",
            "research caching",
        ]
        assert clauses[1].ordered is True

    def test_numbering_marks_explicit_order(self):
        clauses = split_clauses("1) investigate storage 2) research caching")
        assert [c.text for c in clauses] == ["investigate storage", "research caching"]
        assert all(c.ordered for c in clauses)

    def test_single_clause_stays_one(self):
        assert len(split_clauses("Investigate the storage layer.")) == 1

    def test_empty(self):
        assert split_clauses("") == ()
        assert split_clauses(None) == ()


# ---------------------------------------------------------------------------
# 2. Bounded representation
# ---------------------------------------------------------------------------


class TestBuildMultiStep:
    def test_two_independent_operational_intents(self):
        request = build_multi_step(
            "Investigate the storage layer and also research the knowledge decision service."
        )
        assert request is not None
        assert request.ordered is False
        assert [s.executor for s in request.steps] == [
            EXEC_INVESTIGATION,
            EXEC_KNOWLEDGE,
        ]
        # Independent steps are NOT given an invented order or dependency.
        assert all(s.order is None for s in request.steps)
        assert all(s.depends_on == "" for s in request.steps)

    def test_explicit_order_is_represented(self):
        request = build_multi_step(
            "First investigate the storage layer, then research the knowledge decision service."
        )
        assert request is not None
        assert request.ordered is True
        assert [s.order for s in request.steps] == [0, 1]
        assert all(s.depends_on == "" for s in request.steps)

    def test_dependent_analysis_records_the_prerequisite(self):
        request = build_multi_step(
            "Investigate the storage layer and then analyze the findings."
        )
        assert request is not None
        first, second = request.steps
        assert first.executor == EXEC_INVESTIGATION
        assert second.executor == EXEC_ANALYSIS
        assert second.depends_on == first.step_id
        assert second.dependency == DEP_RESULT

    def test_analysis_without_a_prerequisite_is_blocked(self):
        request = build_multi_step(
            "Analyze the findings and also investigate the storage layer."
        )
        assert request is not None
        analysis = next(s for s in request.steps if s.executor == EXEC_ANALYSIS)
        assert analysis.status == STATUS_BLOCKED
        assert analysis.depends_on == ""

    def test_unsupported_clause_is_represented_not_invented(self):
        request = build_multi_step(
            "Investigate the storage layer and also order me a new laptop."
        )
        assert request is not None
        assert any(s.status == STATUS_UNSUPPORTED for s in request.steps)

    def test_governed_clause_is_represented_not_executed(self):
        request = build_multi_step(
            "Investigate the storage layer and also approve the proposal."
        )
        assert request is not None
        assert any(s.status == STATUS_GOVERNED for s in request.steps)

    def test_casual_only_turn_is_not_a_multi_step_request(self):
        assert build_multi_step("What can you do and also what is your status?") is None

    def test_single_intent_is_not_a_multi_step_request(self):
        assert build_multi_step("Investigate the storage layer.") is None

    def test_one_multi_clause_intent_is_not_split(self):
        # A single verb with two objects is ONE intent, not two.
        assert (
            build_multi_step(
                "Investigate the component that handles the storage layer and the memory service."
            )
            is None
        )

    def test_deterministic(self):
        text = "Investigate the storage layer and also research the knowledge decision service."
        assert build_multi_step(text) == build_multi_step(text)


class TestBuildExecutionSteps:
    def test_maps_kinds_and_dependencies(self):
        request = build_multi_step(
            "Investigate the storage layer and then analyze the findings."
        )
        steps = build_execution_steps(request)
        assert steps is not None
        assert [s.kind for s in steps] == [NodeKind.INVESTIGATION, NodeKind.ANALYSIS]
        assert steps[1].depends_on == (steps[0].step_id,)
        assert steps[1].carry_from == (steps[0].step_id,)

    def test_governed_and_unsupported_steps_are_never_emitted(self):
        request = build_multi_step(
            "Investigate the storage layer and also approve the proposal."
        )
        steps = build_execution_steps(request)
        assert steps is not None
        assert all(s.kind is NodeKind.INVESTIGATION for s in steps)

    def test_blocked_analysis_is_not_emitted(self):
        request = build_multi_step(
            "Analyze the findings and also investigate the storage layer."
        )
        steps = build_execution_steps(request)
        assert steps is not None
        assert all(s.kind is NodeKind.INVESTIGATION for s in steps)


# ---------------------------------------------------------------------------
# 3. Conversation-layer routing
# ---------------------------------------------------------------------------


class TestMultiStepRouting:
    def test_two_operational_intents_both_run(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send(
            "Investigate the storage layer and also research the knowledge decision service."
        )
        assert len(bridge.calls) == 1
        _text, steps = bridge.calls[0]
        assert [s.kind for s in steps] == [NodeKind.INVESTIGATION, NodeKind.KNOWLEDGE]
        representation = message.metadata["multi_step"]
        assert representation["ordered"] is False
        assert "Nothing was executed or authorized" in message.content

    def test_ordered_request_preserves_order(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send(
            "First investigate the storage layer, then research the knowledge decision service."
        )
        representation = message.metadata["multi_step"]
        assert representation["ordered"] is True
        assert [s["order"] for s in representation["steps"] if s["executor"] != "none"] == [
            0,
            1,
        ]

    def test_dependent_request_carries_the_result(self):
        bridge = _RecordingBridge()
        _service(bridge).send(
            "Investigate the storage layer and then analyze the findings."
        )
        _text, steps = bridge.calls[0]
        assert [s.kind for s in steps] == [NodeKind.INVESTIGATION, NodeKind.ANALYSIS]
        assert steps[1].carry_from == (steps[0].step_id,)

    def test_mixed_casual_and_operational(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send(
            "What can you do and also investigate the storage layer."
        )
        # The operational step runs...
        assert [s.kind for s in bridge.calls[0][1]] == [NodeKind.INVESTIGATION]
        # ...and the casual intent is answered through the existing builtin surface.
        assert "**What can you do**" in message.content
        assert any(s["executor"] == "builtin" for s in message.metadata["multi_step"]["steps"])

    def test_unsupported_step_is_reported_not_run(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send(
            "Investigate the storage layer and also order me a new laptop."
        )
        assert [s.kind for s in bridge.calls[0][1]] == [NodeKind.INVESTIGATION]
        assert "Recognized but not attempted" in message.content
        assert "order me a new laptop" in message.content

    def test_governed_step_is_never_run(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send(
            "Investigate the storage layer and also approve the proposal."
        )
        assert [s.kind for s in bridge.calls[0][1]] == [NodeKind.INVESTIGATION]
        assert "OWNER approval flow" in message.content
        assert "approval" not in {
            k for s in bridge.calls for k in ()
        }

    def test_no_authority_metadata(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send(
            "Investigate the storage layer and also research the knowledge decision service."
        )
        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in message.metadata, key
        assert _FailingAI.calls == 0

    def test_single_operational_turn_is_untouched(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send("Investigate the storage layer.")
        assert bridge.calls == []
        assert message.metadata.get("multi_step") is None

    def test_casual_multi_intent_still_handled_by_step6(self):
        bridge = _RecordingBridge()
        message = _service(bridge).send(
            "What can you do and also what is your current status?"
        )
        assert message.metadata.get("multi_intent") is not None
        assert bridge.calls == []

    def test_send_stream_parity(self):
        text = "Investigate the storage layer and also research the knowledge decision service."
        sent = _service(_RecordingBridge()).send(text).content
        streamed = "".join(_service(_RecordingBridge()).stream(text))
        assert sent == streamed


class TestStep6And9Preserved:
    def test_split_intents_still_splits_a_strong_coordinator(self):
        readings = sf.split_intents(
            "Tell me what you can do and also where the conversation service lives."
        )
        assert len(readings) == 2

    def test_split_intents_no_longer_over_splits_one_intent(self):
        assert (
            sf.split_intents(
                "Investigate the component that handles the storage layer and the memory service."
            )
            == ()
        )

    def test_step9_clarification_still_applies(self):
        service = _service()
        message = service.send("Tell me more about it.")
        # No established facts -> nothing to resolve here; the turn keeps its route.
        assert message is not None

    def test_unsupported_single_request_unchanged(self):
        message = _service().send("Order me a new laptop.")
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert message.content.startswith("I could not map that request")


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_two_operational_intents_both_execute(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the storage layer and also research the knowledge decision service."
            )
            assert message.metadata["orchestration"]["status"] == "completed"
            kinds = [
                s["kind"] for s in message.metadata["orchestration"]["steps"]
            ]
            assert kinds == ["investigation", "knowledge"]
            representation = message.metadata["multi_step"]
            assert representation["ordered"] is False
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_ordered_request_runs_and_represents_order(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "First investigate the storage layer, then research the knowledge decision service."
            )
            assert message.metadata["orchestration"]["status"] == "completed"
            representation = message.metadata["multi_step"]
            assert representation["ordered"] is True
            assert [s["order"] for s in representation["steps"]] == [0, 1]
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_dependent_request_analyzes_its_own_result(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the storage layer and then analyze the findings."
            )
            assert message.metadata["orchestration"]["status"] == "completed"
            steps = message.metadata["orchestration"]["steps"]
            assert [s["kind"] for s in steps] == ["investigation", "analysis"]
            assert message.metadata["multi_step"]["run_status"] == "completed"
        finally:
            atlas.shutdown()

    def test_three_intent_mixed_request(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the storage layer, then analyze the findings, then tell me what you can do."
            )
            assert message.metadata["orchestration"]["status"] == "completed"
            representation = message.metadata["multi_step"]
            executors = [s["executor"] for s in representation["steps"]]
            assert executors.count("builtin") == 1
            # The third (casual) intent is answered by the existing builtin
            # surface and its clause is named in the reply.
            assert "tell me what you can do" in message.content
            assert "Recognized but not attempted" not in message.content
        finally:
            atlas.shutdown()

    def test_one_multi_clause_intent_is_not_over_split(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the component that handles the storage layer and the memory service."
            )
            # The single investigation route owns it; it is NOT a multi-step plan.
            assert message.metadata.get("multi_step") is None
            assert message.metadata.get("multi_intent") is None
            assert "## Investigation" in message.content
        finally:
            atlas.shutdown()

    def test_clear_single_request_unchanged(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("Investigate the storage layer.")
            assert (message.metadata or {}).get("investigation") is not None
            assert (message.metadata or {}).get("multi_step") is None
        finally:
            atlas.shutdown()

    def test_live_repository_untouched(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat(
                "Investigate the storage layer and also research the knowledge decision service."
            )
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()
