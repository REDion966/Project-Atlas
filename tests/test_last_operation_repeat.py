"""Last governed operation + bounded, safe repeat (Stage C).

Atlas retains exactly ONE facts-only record of the most recent governed
operation (kind + operand + optional proposal_id) and can answer a bounded
cue-less repeat ("Check that again.") by referring to that record:

  * the operation KIND comes from the retained record, never from the verb
    ("check"/"run"/"do"/"repeat");
  * read-only operations are re-entered through their EXISTING handler;
  * governed/mutating operations are never silently re-executed or approved;
  * with nothing retained, recognition fails closed: the G1 semantic frame reads
    the bare cue as an unresolved REFERENCE and the turn asks for its subject
    (it is never guessed, routed, or answered from the literal phrase).

No LLM, no embeddings, no new interpretation layer, no execution authority.
"""

from __future__ import annotations

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import (
    ConversationStateManager,
    GovernedOperation,
)
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.reference_resolution import is_repeat_request
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.evolution.approval_manager import ApprovalManager

INVESTIGATION = "Investigate the memory architecture."
IMPACT = "What is affected if I change atlas.conversation.conversation_state?"


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


def _service(investigation: bool = True, planning: bool = False) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService() if investigation else None,
        approval_manager=ApprovalManager() if planning else None,
    )


# ---------------------------------------------------------------------------
# 1. State representation
# ---------------------------------------------------------------------------


class TestGovernedOperationState:
    def test_record_and_read_back(self):
        manager = ConversationStateManager()
        manager.record_operation(
            "investigation_request",
            operand="Investigate the memory architecture",
            proposal_id="P1",
        )
        assert manager.state.last_operation == GovernedOperation(
            kind="investigation_request",
            operand="Investigate the memory architecture",
            proposal_id="P1",
        )

    def test_kind_is_the_existing_task_type_value(self):
        manager = ConversationStateManager()
        manager.record_operation(
            TaskType.INVESTIGATION_REQUEST.value, operand="x"
        )
        assert (
            manager.state.last_operation.kind
            == TaskType.INVESTIGATION_REQUEST.value
        )

    def test_operand_and_proposal_id_optional(self):
        manager = ConversationStateManager()
        manager.record_operation("execution_request")
        op = manager.state.last_operation
        assert op.kind == "execution_request"
        assert op.operand is None
        assert op.proposal_id is None

    def test_single_valued_only_most_recent_retained(self):
        manager = ConversationStateManager()
        manager.record_operation("investigation_request", operand="first")
        manager.record_operation("planning_request", proposal_id="P2")
        assert manager.state.last_operation.kind == "planning_request"
        assert manager.state.last_operation.operand is None
        assert manager.state.last_operation.proposal_id == "P2"

    def test_serialization_is_json_safe_and_round_trips(self):
        manager = ConversationStateManager()
        manager.record_operation("investigation_request", operand="x", proposal_id="P1")
        payload = manager.state.to_dict()["last_operation"]
        assert payload == {
            "kind": "investigation_request",
            "operand": "x",
            "proposal_id": "P1",
        }
        # An unrelated update must not lose or corrupt the typed record.
        manager.update(current_subject="y")
        assert isinstance(manager.state.last_operation, GovernedOperation)
        assert manager.state.last_operation.operand == "x"

    def test_blank_kind_is_ignored_fail_closed(self):
        manager = ConversationStateManager()
        assert manager.record_operation("").last_operation is None
        assert manager.record_operation("   ").last_operation is None

    def test_operand_is_bounded(self):
        manager = ConversationStateManager()
        manager.record_operation("investigation_request", operand="x" * 5000)
        assert len(manager.state.last_operation.operand) <= 500


# ---------------------------------------------------------------------------
# 2. Production lifecycle recording
# ---------------------------------------------------------------------------


class TestOperationLifecycleRecording:
    def test_completed_investigation_records_operation(self):
        service = _service()
        service.send(INVESTIGATION)
        op = service.state_manager.state.last_operation
        assert op is not None
        assert op.kind == TaskType.INVESTIGATION_REQUEST.value
        assert op.operand.startswith("Investigate the memory architecture")

    def test_completed_repository_impact_records_operation(self):
        service = _service()
        service.send(IMPACT)
        op = service.state_manager.state.last_operation
        assert op.kind == TaskType.REPOSITORY_IMPACT_REQUEST.value
        assert op.operand
        assert op.proposal_id is None

    def test_declined_operation_is_not_recorded(self):
        # "verify the result" classifies as a verification request but declines
        # (no development lifecycle); a declined request must not be recorded.
        service = _service()
        service.send("verify the result.")
        assert service.state_manager.state.last_operation is None

    def test_repeat_with_nothing_retained_is_not_recorded(self):
        service = _service()
        service.send("Check that again.")
        assert service.state_manager.state.last_operation is None

    def test_planned_governed_operation_records_planning(self):
        service = _service(planning=True)
        service.send("Investigate the memory architecture")
        service.send("Plan this improvement")
        op = service.state_manager.state.last_operation
        assert op.kind == TaskType.PLANNING_REQUEST.value
        assert op.proposal_id


# ---------------------------------------------------------------------------
# 3. Repeat recognition
# ---------------------------------------------------------------------------


class TestRepeatRecognition:
    @pytest.mark.parametrize(
        "text",
        [
            "Check that again.",
            "check this again",
            "Check it again",
            "do that again",
            "do it again",
            "run that again.",
            "Repeat that.",
            "repeat that again",
            "again",
            "Again!",
            "please check that again",
            "Investigate that again.",
            "investigate this again",
        ],
    )
    def test_bounded_forms_recognized(self, text):
        assert is_repeat_request(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "Investigate the memory architecture.",
            "Check the result.",
            "We voted against the rule.",
            "what did you find?",
            "again and again we tried",
            "Investigate again the memory architecture",
            "run the approved proposal",
            "can you check that again please",
            "that investigation",
        ],
    )
    def test_unrelated_and_unbounded_forms_not_recognized(self, text):
        assert is_repeat_request(text) is False


# ---------------------------------------------------------------------------
# 4. Operation selection uses the retained kind
# ---------------------------------------------------------------------------


class TestOperationSelectionUsesRetainedKind:
    def test_repeat_uses_retained_kind_not_the_verb(self):
        # Retain a repository-impact operation, then repeat with the "check"
        # verb: the retained KIND must decide (impact), not the word "check".
        service = _service()
        service.send(IMPACT)
        message = service.send("Check that again.")
        assert message.metadata.get("repository_impact") is not None
        assert message.metadata.get("investigation") is None

    def test_run_verb_repeats_retained_investigation(self):
        service = _service()
        service.send(INVESTIGATION)
        message = service.send("Run that again.")
        assert message.metadata.get("investigation") is not None

    def test_bare_again_repeats_retained_operation(self):
        service = _service()
        service.send(INVESTIGATION)
        message = service.send("again")
        assert message.metadata.get("investigation") is not None


# ---------------------------------------------------------------------------
# 5. Read-only repeat
# ---------------------------------------------------------------------------


class TestReadOnlyRepeat:
    def test_investigation_repeat_reuses_retained_operand(self):
        service = _service()
        service.send(INVESTIGATION)
        target = service.state_manager.state.last_operation.operand
        message = service.send("Check that again.")
        assert message.metadata["investigation"]["target"] == target
        assert "Check that again" not in message.metadata["investigation"]["target"]

    def test_repository_impact_repeat_reuses_retained_operand(self):
        service = _service()
        service.send(IMPACT)
        operand = service.state_manager.state.last_operation.operand
        message = service.send("Check that again.")
        assert message.metadata["repository_impact"] is not None
        assert operand
        assert "Check that again" not in (operand or "")

    def test_repeat_refreshes_latest_result_through_existing_path(self):
        service = _service()
        service.send(INVESTIGATION)
        service.send("Check that again.")
        assert service.state_manager.state.latest_result  # recorded via handler
        assert (
            service.state_manager.state.last_operation.kind
            == TaskType.INVESTIGATION_REQUEST.value
        )

    def test_repeat_contacts_no_provider(self):
        service = _service()
        service.send(INVESTIGATION)
        service.send("Check that again.")
        assert _FailingAI.calls == 0


# ---------------------------------------------------------------------------
# 6. Mutating repeat refused (no execution, no approval)
# ---------------------------------------------------------------------------


class TestMutatingRepeatRefused:
    @staticmethod
    def _planned_service() -> ConversationService:
        service = _service(planning=True)
        service.send("Investigate the memory architecture")
        service.send("Plan this improvement")
        return service

    def test_planning_is_retained(self):
        service = self._planned_service()
        assert (
            service.state_manager.state.last_operation.kind
            == TaskType.PLANNING_REQUEST.value
        )

    @pytest.mark.parametrize(
        "repeat_text", ["Do that again.", "Check that again.", "Run that again."]
    )
    def test_governed_repeat_is_refused_without_side_effects(self, repeat_text):
        service = self._planned_service()
        proposals = dict(service._active_proposals)
        approvals = dict(service._active_approval_requests)
        evolution = dict(service._active_evolution_proposals)

        message = service.send(repeat_text)

        assert message.metadata.get("repeat", {}).get("status") == "not_repeated"
        assert "execution" not in message.metadata
        assert "approval" not in message.metadata
        assert dict(service._active_proposals) == proposals
        assert dict(service._active_approval_requests) == approvals
        assert dict(service._active_evolution_proposals) == evolution
        assert _FailingAI.calls == 0

    def test_state_unchanged_by_governed_repeat(self):
        service = self._planned_service()
        before = service.state_manager.state.to_dict()
        service.send("Do that again.")
        after = service.state_manager.state.to_dict()
        assert after == before


# ---------------------------------------------------------------------------
# 7. Adjacent regression — "Investigate that again."
# ---------------------------------------------------------------------------


class TestInvestigateThatAgain:
    def test_uses_retained_operand_not_literal_phrase(self):
        service = _service()
        service.send(INVESTIGATION)
        target = service.state_manager.state.last_operation.operand

        message = service.send("Investigate that again.")

        assert message.metadata["investigation"]["target"] == target
        assert "Investigate that again" != message.metadata["investigation"]["target"]
        assert "Investigate that again" not in message.metadata["investigation"]["target"]

    def test_ordinary_investigation_is_unchanged(self):
        service = _service()
        message = service.send(INVESTIGATION)
        assert message.metadata["investigation"]["target"].startswith(
            "Investigate the memory architecture"
        )

    def test_investigate_that_again_without_prior_operation_clarifies(self):
        # No retained operation -> recognition fails closed. The G1 semantic
        # frame reads the bare cue as an unresolved REFERENCE, so the turn asks
        # for its subject instead of treating the literal phrase as the target
        # of an investigation (nothing is guessed or routed).
        service = _service()
        message = service.send("Investigate that again.")
        assert message.metadata.get("frame_clarification") == {
            "domain": "unsupported",
            "operation": "reference",
        }
        assert "investigation" not in message.metadata
        assert "Which subject should I use?" in message.content
        assert service.state_manager.state.last_operation is None
        assert _FailingAI.calls == 0


# ---------------------------------------------------------------------------
# 8. Existing behavior regression
# ---------------------------------------------------------------------------


class TestExistingBehaviorRegression:
    def test_stage_a_reference_consumption_intact(self):
        service = _service()
        service.send(INVESTIGATION)
        message = service.send("What about the result?")
        assert message.metadata.get("builtin_intent") == "reference"
        assert message.metadata.get("reference_field") == "latest_result"

    def test_result_qualifier_aliases_intact(self):
        service = _service()
        service.send(INVESTIGATION)
        for text in (
            "What about the previous result?",
            "What about the last result?",
            "What about the prior result?",
        ):
            message = service.send(text)
            assert message.metadata.get("builtin_intent") == "reference"
            assert message.metadata.get("reference_field") == "latest_result"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("hello", "greeting"),
            ("help", "help"),
            ("status", "status"),
            ("who are you", "identity"),
            ("what can you do", "help"),
        ],
    )
    def test_builtin_intents_intact(self, text, expected):
        service = _service()
        assert service.send(text).metadata.get("builtin_intent") == expected

    def test_check_that_again_without_operation_clarifies(self):
        # With nothing retained, the fail-closed contract is a clarification
        # request: the G1 frame marks the bare cue an unresolved REFERENCE and
        # asks for its subject. It is not answered and invents no operand.
        service = _service()
        message = service.send("Check that again.")
        assert message.metadata.get("frame_clarification") == {
            "domain": "unsupported",
            "operation": "reference",
        }
        assert message.metadata.get("builtin_intent") is None
        assert "Which subject should I use?" in message.content
        assert service.state_manager.state.last_operation is None
        assert _FailingAI.calls == 0

    def test_send_and_stream_parity_on_repeat(self):
        # The investigation report carries a timestamped proposal id, so compare
        # structure and retained operation rather than byte-identical content.
        sent_service = _service()
        sent_service.send(INVESTIGATION)
        sent = sent_service.send("Check that again.")

        streamed_service = _service()
        streamed_service.send(INVESTIGATION)
        streamed = "".join(streamed_service.stream("Check that again."))

        assert sent.content.startswith("## Investigation:")
        assert streamed.startswith("## Investigation:")
        assert sent.metadata["investigation"]["target"] == (
            streamed_service.conversation.messages[-1].metadata["investigation"][
                "target"
            ]
        )

    def test_correction_still_unsupported(self):
        service = _service()
        service.send(INVESTIGATION)
        message = service.send("No, I meant the cognition pipeline.")
        assert message.metadata.get("builtin_intent") == "unsupported"
