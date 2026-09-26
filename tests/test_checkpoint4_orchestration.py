"""Checkpoint 4 — orchestration & capability/consumer selection.

Checkpoint 3 established that the state layer is sound and that the remaining
multi-turn problems are consumer/route problems. Checkpoint 4 traced which
existing consumer claims each turn and found ONE demonstrated gap with a safe
smallest correction: an already-BOUND reference was not delivered to any answer
consumer, so a findings follow-up ("What did you find?" after an investigation)
asked for a target instead of reporting the retained result — even though the
deterministic resolver had bound it and the reference answer surface already
existed (it answers question-typed turns such as "What about the result?").

This pins the corrected selection:

* informational, pure reference/follow-up turns are ANSWERED from the bound
  referent by the existing reference renderer (no new capability, no planner);
* a governed request carrying a bound reference keeps its governed route
  (investigation/development), so nothing is captured;
* a turn with a genuinely multiple referent still fails closed;
* nothing falls through to a provider.
"""

from __future__ import annotations

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model


class _FailingAI:
    """Any provider contact is a failure: these routes are deterministic."""

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


class _RecordingInvestigation:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append({"target": target, "objective": objective})
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis="Identified 3 relevant component(s) in atlas",
            components=("atlas.memory",),
            modification_status="NONE",
        )


def _svc() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _service(investigation=None) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
        investigation_service=investigation,
    )


def _investigated(recording: _RecordingInvestigation) -> ConversationService:
    """A conversation that has completed one investigation."""
    service = _service(recording)
    service.send("Investigate the memory architecture.")
    return service


# ---------------------------------------------------------------------------
# 1. The corrected selection: a bound reference reaches the answer consumer
# ---------------------------------------------------------------------------


class TestFindingsReferenceIsAnswered:
    def test_findings_follow_up_reports_the_retained_result(self):
        recording = _RecordingInvestigation()
        service = _investigated(recording)
        investigations_before = len(recording.calls)

        message = service.send("What did you find?")

        assert message.metadata.get("builtin_intent") == "reference"
        assert message.metadata.get("reference_field") == "latest_result"
        assert "The most recent result" in message.content
        assert "Identified 3 relevant component(s)" in message.content
        # No new operation was started, and nothing asked for a target.
        assert len(recording.calls) == investigations_before
        assert "more detail" not in message.content
        assert _FailingAI.calls == 0

    def test_result_reference_still_answered(self):
        recording = _RecordingInvestigation()
        service = _investigated(recording)

        message = service.send("What about the result?")

        assert message.metadata.get("builtin_intent") == "reference"
        assert message.metadata.get("reference_field") == "latest_result"

    def test_answer_is_deterministic(self):
        recording = _RecordingInvestigation()
        service = _investigated(recording)
        first = service.send("What did you find?").content
        assert service.send("What did you find?").content == first


# ---------------------------------------------------------------------------
# 2. Nothing else is captured: governed routes and new objectives keep theirs
# ---------------------------------------------------------------------------


class TestOtherRoutesKeepTheirConsumer:
    def test_governed_investigation_follow_up_still_investigates(self):
        recording = _RecordingInvestigation()
        service = _investigated(recording)
        before = len(recording.calls)

        service.send("Investigate this further.")

        assert len(recording.calls) == before + 1
        assert recording.calls[-1]["objective"].startswith(
            "Investigate the memory architecture"
        )

    def test_new_objective_is_not_answered_as_a_reference(self):
        recording = _RecordingInvestigation()
        service = _investigated(recording)

        message = service.send("Compare that with the conversation state system.")

        assert message.metadata.get("builtin_intent") != "reference"

    def test_new_explicit_research_task_is_unchanged(self):
        recording = _RecordingInvestigation()
        service = _investigated(recording)

        message = service.send("Now research the capability registry.")

        assert message.metadata.get("builtin_intent") != "reference"

    def test_no_reference_bound_means_unchanged_behaviour(self):
        # With nothing bound there is no referent to report: the corrected route
        # declines and the turn keeps its pre-existing path (nothing is
        # invented, and no provider answer is surfaced).
        service = _service(_RecordingInvestigation())

        message = service.send("What did you find?")

        assert message.metadata.get("builtin_intent") != "reference"
        assert "The most recent result" not in message.content
        assert "first AI provider" not in message.content

    def test_genuine_multi_referent_turn_still_fails_closed(self):
        # Two referents that provably do NOT come from one retained operation.
        service = _service(_RecordingInvestigation())
        service.state_manager.update(
            current_investigation="inv-1", latest_result="res-1"
        )

        message = service.send("What did you find?")

        assert message.metadata.get("builtin_intent") != "reference"
        assert "Multiple plausible findings referents" in message.content


# ---------------------------------------------------------------------------
# 3. Governance and model independence on the corrected route
# ---------------------------------------------------------------------------


class TestCorrectedRouteStaysSafe:
    def test_reference_answer_creates_no_authority_and_reuses_nothing(self):
        recording = _RecordingInvestigation()
        service = _investigated(recording)
        state_before = service.state_manager.state

        message = service.send("What did you find?")

        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in message.metadata, key
        after = service.state_manager.state
        assert after.pending_approval_id is None
        assert after.last_operation == state_before.last_operation
        assert after.current_investigation == state_before.current_investigation
        assert after.latest_result == state_before.latest_result

    @pytest.mark.parametrize(
        "text", ["What did you find?", "What about the result?", "status"]
    )
    def test_no_provider_is_consulted(self, text):
        recording = _RecordingInvestigation()
        service = _investigated(recording)
        message = service.send(text)
        assert message.content.strip()
        assert _FailingAI.calls == 0
        assert message.metadata.get("model_used") is not True
