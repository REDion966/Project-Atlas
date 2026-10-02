"""Correction routing — focused full-path regression tests.

Evidence: the deterministic engine already produces `role=correction`,
`operation=correct`, records a `Correction(previous, corrected)` in
`ConversationState.corrections` and installs the corrected objective — but no
conversation-boundary consumer existed, so the turn fell into the earlier-item
reference surface and was answered with a clarification denying the result it
was pointing at.

The consumer reuses the EXISTING routing/salience machinery to establish the
target and presents the RECORDED result with an explicit correction
acknowledgement. It never fabricates a target.

Deterministic, model-free, no network, no new state or reference system.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

CORRECTION = "Actually, I meant the previous result."
NEW_SUBJECT_CORRECTION = "Actually, I meant the memory service."
X = "the conversation architecture"
Y = "the memory service"


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


class _RecordingInvestigation:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis=f"Investigation result for {objective or target}",
            modification_status="NONE",
        )


def _service() -> tuple[ConversationService, _RecordingInvestigation]:
    investigation = _RecordingInvestigation()
    model = build_architecture_model(ComponentRegistry())
    service = ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(architecture_model_provider=lambda: model),
        investigation_service=investigation,
    )
    return service, investigation


def _meaning(service: ConversationService):
    return service._last_meaning


# ---------------------------------------------------------------------------
# A. Correction after a successful investigation
# ---------------------------------------------------------------------------


class TestCorrectionAfterResult:
    def test_full_path_grounds_the_correction_in_the_recorded_result(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")
        recorded_result = service.state_manager.state.latest_result
        calls_after_investigation = list(investigation.calls)

        message = service.send(CORRECTION)

        # meaning/function: the correction survives as a correction (never a
        # generic result query)
        meaning = _meaning(service)
        assert meaning.turn_role == "correction"
        assert meaning.domain == "knowledge"
        assert meaning.operation == "correct"
        # state: the existing engine record is present and used
        corrections = service.state_manager.state.corrections
        assert len(corrections) == 1
        assert corrections[0].corrected == "previous result"
        assert corrections[0].previous == f"Investigate {X}."
        # reference/response: grounded in the RECORDED result, explicitly a
        # correction acknowledgement
        assert recorded_result in message.content
        assert "I recorded that correction" in message.content
        metadata = message.metadata or {}
        assert metadata["correction"]["corrected"] == "previous result"
        assert metadata["correction"]["target_kind"] == "result"
        # no unrelated operation ran and the prior result is untouched
        assert investigation.calls == calls_after_investigation
        state = service.state_manager.state
        assert state.latest_result == recorded_result
        assert state.last_operation.kind == "investigation_request"

    def test_correction_is_not_a_generic_result_query(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        corrected = service.send(CORRECTION).content

        other, _ = _service()
        other.send(f"Investigate {X}.")
        plain = other.send("What did you find?").content

        assert corrected != plain
        assert "I recorded that correction" in corrected
        # the plain follow-up keeps its own existing rendering
        assert plain.startswith("The most recent result:")

    def test_new_subject_correction_keeps_its_existing_path(self):
        """A correction that installs a NEW subject is not answered as a result."""
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send(NEW_SUBJECT_CORRECTION)
        assert "I recorded that correction" not in message.content
        assert service.state_manager.state.latest_result  # prior result intact


# ---------------------------------------------------------------------------
# B. Correction with no established target
# ---------------------------------------------------------------------------


class TestCorrectionWithoutTarget:
    def test_fails_closed_without_inventing_anything(self):
        service, investigation = _service()
        message = service.send(CORRECTION)
        # no fabricated referent, no invented result, no operation executed
        assert investigation.calls == []
        assert "I recorded that correction" not in message.content
        assert "Investigation result" not in message.content
        assert service.state_manager.state.latest_result is None
        assert service.state_manager.state.corrections == ()
        # the existing honest surface owns the turn
        assert "cannot tell which earlier item" in message.content


# ---------------------------------------------------------------------------
# C. Ambiguity / determinism of the corrected reading
# ---------------------------------------------------------------------------


class TestCorrectionTargetSelection:
    def test_two_prior_results_resolve_deterministically_or_fail_closed(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        message = service.send(CORRECTION)
        # Either the existing salience machinery resolves exactly one recorded
        # result, or the turn fails closed — a target is never invented.
        if "I recorded that correction" in message.content:
            discourse = service.state_manager.state.discourse_state
            labels = [r.label for r in discourse.referents if r.kind == "result"]
            assert any(label in message.content for label in labels)
        else:
            assert "Investigation result" not in message.content


# ---------------------------------------------------------------------------
# F. send()/stream() parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    def _run(self, use_stream: bool) -> str:
        service, _ = _service()
        service.send(f"Investigate {X}.")
        if use_stream:
            return "".join(service.stream(CORRECTION))
        return service.send(CORRECTION).content

    def test_correction_is_identical_on_both_paths(self):
        assert self._run(False) == self._run(True)
