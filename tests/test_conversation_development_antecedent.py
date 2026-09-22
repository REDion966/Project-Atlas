"""A/B — development antecedent retention + resolved-reference reconciliation.

Evidence-backed correction from the read-only antecedent investigation:

  A — a development request the existing handler actually ACCEPTS records the
      same bounded goal/intent text it already records as the governed
      operation operand into the existing ``ConversationState.development_intent``
      slot, so a following turn can refer back to it ("develop that
      capability"). Single value, no history. ``current_subject`` keeps its
      catalog-entity contract and is never used as a generic request slot.
  B — once the existing deterministic reference pipeline returns RESOLVED and
      attaches a valid ``resolved_reference``, only the resolved ``reference``
      component of the ambiguity report is reconciled. The weight table and the
      global ``>= 0.5`` threshold are untouched and every other reason is
      retained, so unrelated ambiguity still blocks.

Fail-closed behavior is preserved: an unresolved or ambiguous reference, an
absent antecedent, a clarification-pending request, a hypothetical, or an
ordinary capability question all still clarify and never reach the bridge.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.entity_identification import EntityCatalog
from atlas.conversation.message import Message
from atlas.conversation.task_intake import (
    _AMBIGUITY_WEIGHTS,
    _CLARIFICATION_THRESHOLD,
    AmbiguityReport,
    TaskIntake,
    TaskType,
    reconcile_resolved_reference_ambiguity,
)
from tests.test_conversation_development_bridge import (
    _ConcreteSupplier,
    _started_atlas,
    _stub_research,
)

CATALOG = EntityCatalog.from_names({"capability": ["code_inspector"]})

DEV_REQUEST = "Develop an email notification capability for long-running tasks."
REFER_BACK = "Develop that capability."
MOTIVATING = (
    "I want Atlas to have an email notification capability for long-running tasks."
)
HYPOTHETICAL = "I was wondering whether Atlas could send emails someday."
QUESTION = "What is an email notification capability?"
DISCUSSION = "Tell me about email notifications."
ACTION_WORDED = "I need an email notifier for long-running tasks."
CLARIFICATION_PENDING = "Can you develop an email notification capability for it?"


class _FailingAI:
    """No provider: the deterministic path must stand alone."""

    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


class _RecordingBridge:
    """Records every bridge call and returns a bounded acceptance message."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, spec):
        self.calls.append(spec)
        return Message(role="assistant", content="BRIDGED")


class _DecliningBridge:
    """Bridge that returns no accepted result (fail-closed path)."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, spec):
        self.calls.append(spec)
        return None


def _service(*, bridge=None, seed=None):
    service = ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        entity_catalog=CATALOG,
        development_bridge=bridge,
    )
    if seed:
        service.state_manager.update(**seed)
    return service


def _spec(service: ConversationService, text: str):
    return service._intake(text, len(service.conversation.messages))


# ---------------------------------------------------------------------------
# A — the antecedent is written only under the approved predicate
# ---------------------------------------------------------------------------


class TestDevelopmentIntentPredicate:
    def test_accepted_development_request_retains_the_bounded_operand(self):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge)

        service.send(DEV_REQUEST)

        state = service.state_manager.state
        assert len(bridge.calls) == 1
        assert state.development_intent
        # The antecedent is exactly the text the governed operation recorded.
        assert state.last_operation is not None
        assert state.development_intent == state.last_operation.operand
        # Bounded like the existing state text: never beyond the goal bound.
        assert len(state.development_intent) <= 500

    def test_antecedent_is_available_on_the_following_turn(self):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge)
        service.send(DEV_REQUEST)

        resolution = service._reference_resolver.resolve_contextual(
            REFER_BACK,
            service._build_conversation_context(),
            service.state_manager.state,
        )

        assert resolution.resolved_field == "development_intent"
        assert resolution.resolved_value == service.state_manager.state.development_intent

    def test_newest_accepted_request_replaces_the_previous_intent(self):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge, seed={"development_intent": "an old intent"})

        service.send(DEV_REQUEST)
        first = service.state_manager.state.development_intent
        # Single value: the accepted request replaces, never accumulates.
        assert first != "an old intent"
        assert first == service.state_manager.state.last_operation.operand

        service.send("Develop a capability for scheduling follow-ups.")

        state = service.state_manager.state
        assert len(bridge.calls) == 2
        assert state.development_intent == state.last_operation.operand
        assert state.development_intent != "an old intent"

    def test_current_subject_contract_is_unchanged(self):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge, seed={"current_subject": "code_inspector"})

        service.send(DEV_REQUEST)

        state = service.state_manager.state
        assert state.current_subject == "code_inspector"
        assert state.development_intent

    @pytest.mark.parametrize(
        "text",
        [HYPOTHETICAL, QUESTION, DISCUSSION],
    )
    def test_hypothetical_and_capability_discussion_never_write(self, text):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge)

        service.send(text)

        assert bridge.calls == []
        assert service.state_manager.state.development_intent is None

    def test_action_request_never_writes_the_development_antecedent(self):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge)

        service.send(ACTION_WORDED)

        assert _spec(service, ACTION_WORDED).task_type is TaskType.ACTION_REQUEST
        assert bridge.calls == []
        assert service.state_manager.state.development_intent is None

    def test_clarification_pending_request_never_writes(self):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge)

        message = service.send(CLARIFICATION_PENDING)

        assert _spec(
            service, CLARIFICATION_PENDING
        ).needs_clarification is True
        assert "more detail" in message.content
        assert bridge.calls == []
        assert service.state_manager.state.development_intent is None

    def test_bridge_absence_or_failure_never_writes(self):
        # No bridge wired at all: the handler declines, so nothing is recorded.
        unwired = _service(bridge=None)
        unwired.send(DEV_REQUEST)
        assert unwired.state_manager.state.development_intent is None

        # Bridge present but returning no accepted result (fail-closed path).
        declining = _DecliningBridge()
        failing = _service(bridge=declining)
        message = failing.send(DEV_REQUEST)
        assert len(declining.calls) == 1
        assert "could not be prepared" in message.content
        assert failing.state_manager.state.development_intent is None

    def test_blank_operand_records_the_operation_but_leaves_intent_unchanged(self):
        bridge = _RecordingBridge()
        service = _service(bridge=bridge, seed={"development_intent": "keep me"})

        service._accept_development_request(None)
        service._accept_development_request("   ")

        state = service.state_manager.state
        assert state.development_intent == "keep me"
        assert state.last_operation is not None


# ---------------------------------------------------------------------------
# B — only the resolved reference component is reconciled
# ---------------------------------------------------------------------------


class TestResolvedReferenceReconciliation:
    def test_reference_reason_is_cleared_and_request_proceeds(self):
        service = _service()
        spec = _spec(service, REFER_BACK)
        assert spec.ambiguity.ambiguities == ("reference", "success")
        assert spec.ambiguity.ambiguity_score == 0.55
        assert spec.needs_clarification is True

        out = reconcile_resolved_reference_ambiguity(spec)

        # Only the reference component is gone; the unrelated reason remains.
        assert out.ambiguity.ambiguities == ("success",)
        assert out.ambiguity.ambiguity_score == 0.25
        assert out.needs_clarification is False
        assert out.ambiguity.clarification_questions == (
            "What outcome would tell you this is done?",
        )

    def test_another_blocking_reason_still_clarifies(self):
        service = _service()
        spec = _spec(service, REFER_BACK)
        blocking = replace(
            spec,
            ambiguity=AmbiguityReport(
                ambiguity_score=0.8,
                ambiguities=("objective", "reference", "success"),
                clarification_questions=("q1", "q2"),
            ),
            needs_clarification=True,
        )

        out = reconcile_resolved_reference_ambiguity(blocking)

        assert out.ambiguity.ambiguities == ("objective", "success")
        assert out.ambiguity.ambiguity_score == 0.5
        # Still at/above the unchanged threshold: unrelated ambiguity blocks.
        assert out.needs_clarification is True

    def test_spec_without_a_reference_reason_is_returned_unchanged(self):
        service = _service()
        spec = _spec(service, DEV_REQUEST)
        assert "reference" not in spec.ambiguity.ambiguities

        assert reconcile_resolved_reference_ambiguity(spec) is spec

    def test_threshold_and_weights_are_unchanged(self):
        assert _CLARIFICATION_THRESHOLD == 0.5
        assert _AMBIGUITY_WEIGHTS == {
            "objective": 0.25,
            "success": 0.25,
            "reference": 0.3,
            "task_type": 0.35,
        }


# ---------------------------------------------------------------------------
# The resolver: one established fact resolves, two stay ambiguous
# ---------------------------------------------------------------------------


class TestAntecedentResolution:
    def test_single_established_development_intent_resolves(self):
        service = _service(seed={"development_intent": "add email notifications"})

        resolution = service._reference_resolver.resolve_contextual(
            REFER_BACK,
            service._build_conversation_context(),
            service.state_manager.state,
        )

        assert resolution.resolved_field == "development_intent"
        assert resolution.resolved_value == "add email notifications"

    def test_single_established_subject_still_resolves_to_the_subject(self):
        service = _service(seed={"current_subject": "code_inspector"})

        resolution = service._reference_resolver.resolve_contextual(
            "tell me about that", service._build_conversation_context(),
            service.state_manager.state,
        )

        assert resolution.resolved_field == "current_subject"
        assert resolution.resolved_value == "code_inspector"

    def test_two_established_facts_stay_ambiguous(self):
        service = _service(
            seed={"current_subject": "code_inspector", "development_intent": "intent"}
        )

        resolution = service._reference_resolver.resolve_contextual(
            REFER_BACK,
            service._build_conversation_context(),
            service.state_manager.state,
        )

        assert resolution.status.value == "ambiguous"
        assert len(resolution.candidates) == 2

    def test_no_antecedent_stays_unresolved(self):
        service = _service()

        resolution = service._reference_resolver.resolve_contextual(
            REFER_BACK,
            service._build_conversation_context(),
            service.state_manager.state,
        )

        assert resolution.status.value == "unresolved"
        assert resolution.candidates == ()

    def test_investigation_candidates_keep_precedence(self):
        service = _service(
            seed={"current_investigation": "inv-1", "development_intent": "intent"}
        )

        resolution = service._reference_resolver.resolve_contextual(
            REFER_BACK,
            service._build_conversation_context(),
            service.state_manager.state,
        )

        assert resolution.resolved_field == "current_investigation"
        assert resolution.resolved_value == "inv-1"

    def test_antecedent_matching_the_turn_itself_is_skipped(self):
        service = _service(seed={"development_intent": REFER_BACK})

        resolution = service._reference_resolver.resolve_contextual(
            REFER_BACK,
            service._build_conversation_context(),
            service.state_manager.state,
        )

        assert resolution.status.value == "unresolved"


# ---------------------------------------------------------------------------
# End to end: the governed lifecycle is reached and stops at approval
# ---------------------------------------------------------------------------


class TestGovernedLifecycleEndToEnd:
    def _atlas(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        _stub_research(atlas)
        atlas.development_controller._change_supplier = _ConcreteSupplier()  # noqa: SLF001
        return atlas

    def test_reference_back_reaches_pending_approval(self, monkeypatch, tmp_path):
        atlas = self._atlas(monkeypatch, tmp_path)
        try:
            approval_manager = atlas._approval_manager  # noqa: SLF001
            original_approve = approval_manager.approve
            calls = []
            approval_manager.approve = lambda *a, **k: (
                calls.append(a) or original_approve(*a, **k)
            )

            first = atlas.chat(DEV_REQUEST)
            assert "PENDING_APPROVAL" in first.content
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            retained = state.development_intent
            assert retained == state.last_operation.operand

            second = atlas.chat(REFER_BACK)
        finally:
            atlas.shutdown()

        # The resolved reference was reconciled and the bridge was reached
        # again: no clarification, a fresh governed proposal, stopped for the
        # OWNER at the existing approval boundary.
        assert "more detail" not in second.content
        assert "PENDING_APPROVAL" in second.content
        assert "Proposal ID:" in second.content
        assert "Nothing is approved, executed, or promoted" in second.content
        # Nothing was approved, executed, promoted, or activated.
        assert calls == []
        assert tuple(atlas.pending_promotion_reviews()) == ()
        assert "Run status:" not in second.content

    def test_confirmed_detected_need_establishes_the_antecedent(
        self, monkeypatch, tmp_path
    ):
        """The kernel's natural path for an unresolved-action request: the
        confirmation turn is the accepted development request, and the turn
        after it can refer back to it."""
        atlas = self._atlas(monkeypatch, tmp_path)
        try:
            first = atlas.chat(MOTIVATING)
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert "governed development request" in first.content
            assert state.development_intent is None

            confirmed = atlas.chat("yes")
            established = atlas._conversation.state_manager.state  # noqa: SLF001
            assert established.development_intent

            third = atlas.chat(REFER_BACK)
        finally:
            atlas.shutdown()

        assert "PENDING_APPROVAL" in confirmed.content
        assert "PENDING_APPROVAL" in third.content
        assert "more detail" not in third.content
        assert tuple(atlas.pending_promotion_reviews()) == ()

    def test_motivating_pair_boundary_is_still_fail_closed(
        self, monkeypatch, tmp_path
    ):
        """Documented boundary: the motivating turn is classified
        ACTION_REQUEST by the existing deterministic intake, so it routes to
        the existing development-need confirmation dialogue rather than to the
        development handler. No antecedent is established, and the follow-up
        therefore still clarifies — it never guesses."""
        atlas = self._atlas(monkeypatch, tmp_path)
        try:
            first = atlas.chat(MOTIVATING)
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert state.development_intent is None

            second = atlas.chat(REFER_BACK)
        finally:
            atlas.shutdown()

        assert "governed development request" in first.content
        assert "more detail" in second.content
        assert "Proposal ID:" not in second.content
        assert tuple(atlas.pending_promotion_reviews()) == ()
