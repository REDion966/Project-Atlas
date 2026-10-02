"""Stage 10 — named-topic follow-up capability focused tests.

Evidence-driven Stage 10: a named-topic follow-up to a NON-ACTIVE prior referent
("What about the memory router?", "And the memory router?", "Regarding the
memory router.") was unrouted and fell to the unsupported floor. It is now
resolved deterministically through the EXISTING Stage 6 assessment (a soft
explicit named target). No model is involved.

No network or external model is used.
"""

from __future__ import annotations

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.response import SHAPE_CLARIFICATION, SHAPE_RESULT_SUMMARY
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

A = "the memory router"
B = "the cache layer"
C = "the memory cache"


class _FailingAI:
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
        self.calls: list[str] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        return InvestigationReport(
            target=target, objective=objective,
            diagnosis=f"Investigation result for {objective or target}",
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
        investigation_service=investigation or _RecordingInvestigation(),
    )


def _classify(message) -> str:
    content = (message.content or "").lower()
    if "which one do you mean" in content:
        return "clarified"
    if "could not map that request" in content:
        return "unsupported"
    if "no recorded result" in content:
        return "fail_closed"
    if "memory router" in content:
        return "A"
    if "cache layer" in content:
        return "B"
    return "other"


def _two_ops():
    service = _service()
    service.send(f"Investigate {A}.")
    service.send(f"Investigate {B}.")
    return service


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestNamedTopicFollowUp:
    def test_resolves_a_non_active_prior_referent(self):
        service = _two_ops()
        message = service.send("What about the memory router?")
        assert "memory router" in message.content
        assert "cache layer" not in message.content  # NOT latest/active
        assert (message.metadata or {})["response_plan"]["shape"] == SHAPE_RESULT_SUMMARY

    @pytest.mark.parametrize(
        "text",
        [
            "What about the memory router?",
            "And the memory router?",
            "Regarding the memory router.",
            "How about the memory router?",
        ],
    )
    def test_realistic_paraphrases(self, text):
        service = _two_ops()
        assert "memory router" in service.send(text).content

    def test_single_operation_named_target(self):
        service = _service()
        service.send(f"Investigate {A}.")
        assert "memory router" in service.send("What about the memory router?").content

    def test_explicit_target_unchanged(self):
        service = _two_ops()
        before = service.send(f"Explain the result of the {A[4:]} investigation.").content
        after = service.send(f"What about {A}?").content
        assert "memory router" in before and "memory router" in after


# ---------------------------------------------------------------------------
# Negatives / ambiguity / fail-closed
# ---------------------------------------------------------------------------


class TestNegatives:
    def test_fresh_conversation_not_fabricated(self):
        service = _service()
        message = service.send("What about the memory router?")
        assert _classify(message) == "unsupported"  # falls through, honest
        assert service.state_manager.state.discourse_state is None

    def test_named_target_matching_nothing_falls_through(self):
        service = _two_ops()
        message = service.send("What about the quorvex scheduler?")
        assert _classify(message) == "unsupported"  # soft no-match -> existing floor

    def test_ambiguous_named_target_clarifies(self):
        service = _service()
        service.send(f"Investigate {A}.")
        service.send(f"Investigate {C}.")
        message = service.send("What about the memory?")
        assert _classify(message) == "clarified"
        assert (message.metadata or {})["response_plan"]["shape"] == SHAPE_CLARIFICATION
        assert service.state_manager.state.pending_clarification is not None

    def test_no_new_operation_is_started(self):
        recording = _RecordingInvestigation()
        service = _service(recording)
        service.send(f"Investigate {A}.")
        service.send(f"Investigate {B}.")
        before = len(recording.calls)
        service.send("What about the memory router?")
        assert len(recording.calls) == before  # never a new operation


# ---------------------------------------------------------------------------
# State / reference / thread integrity
# ---------------------------------------------------------------------------


class TestIntegrity:
    def test_state_not_mutated_by_the_follow_up(self):
        service = _two_ops()
        before_latest = service.state_manager.state.latest_result
        before_refs = len(service.state_manager.state.discourse_state.referents)
        service.send("What about the memory router?")
        after = service.state_manager.state
        # No fabricated result and no new referents.
        assert after.latest_result == before_latest
        assert len(after.discourse_state.referents) == before_refs
        # The active thread deterministically follows the named target (A).
        assert after.thread_state.active().objective.endswith("memory router.")

    def test_reference_targets_the_named_not_latest(self):
        service = _two_ops()
        message = service.send("And the memory router?")
        assert "memory router" in message.content and "cache layer" not in message.content

    def test_soft_no_match_leaves_no_pending_clarification(self):
        service = _two_ops()
        service.send("What about the quorvex scheduler?")
        assert service.state_manager.state.pending_clarification is None


# ---------------------------------------------------------------------------
# Parity / isolation / persistence / governance
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_send_stream_parity(self):
        def run(use_stream):
            service = _two_ops()
            text = "What about the memory router?"
            if use_stream:
                return "".join(service.stream(text)), service._last_response_plan
            message = service.send(text)
            return message.content, service._last_response_plan

        send_out, send_plan = run(False)
        stream_out, stream_plan = run(True)
        assert send_out == stream_out
        assert send_plan == stream_plan

    def test_isolation(self):
        a = _two_ops()
        a.send("What about the memory router?")
        b = _service()
        assert b.state_manager.state.discourse_state is None
        assert _classify(b.send("What about the memory router?")) == "unsupported"

    def test_persistence_boundary(self, tmp_path, monkeypatch):
        from atlas.storage.conversation_storage import ConversationStorage

        monkeypatch.setattr(ConversationStorage, "STORAGE_DIR", tmp_path / "conv")
        service = _two_ops()
        service.send("What about the memory router?")
        assert "response_plan" not in service.save().read_text(encoding="utf-8")
        assert ConversationStateManager().state.thread_state is None

    def test_governance_unchanged(self):
        service = _service()
        service.send(f"Investigate {A}.")
        before = (dict(service._active_proposals),
                  dict(service._active_evolution_proposals),
                  dict(service._active_approval_requests))
        message = service.send("What about the proposal?")  # no such referent
        after = (dict(service._active_proposals),
                 dict(service._active_evolution_proposals),
                 dict(service._active_approval_requests))
        assert after == before
        assert service.state_manager.state.pending_approval_id is None

    def test_builtins_not_stolen(self):
        service = _service()
        assert "response_plan" not in (service.send("Who are you?").metadata or {})
