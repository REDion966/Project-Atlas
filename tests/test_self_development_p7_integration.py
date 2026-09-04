"""P7.4 — Route confirmed development needs into the existing F9 path.

End-to-end tests for the P7.4 integration: detection → explanation →
explicit confirmation → existing development bridge → PENDING_APPROVAL stop.

These tests exercise the ConversationService with an injected
DevelopmentNeedCoordinator (and injected development bridge) to prove the
full conversational route without touching the kernel or evolution execution.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_need_coordinator import (
    DevelopmentNeedCoordinator,
    PendingConfirmation,
)
from atlas.conversation.development_need_detector import (
    DetectedDevelopmentNeed,
    DevelopmentNeedDetector,
    DevelopmentSignalKind,
)
from atlas.conversation.development_need_dialogue import (
    ConfirmationStatus,
    DevelopmentNeedDialogue,
)
from atlas.conversation.development_need_router import (
    explicit_intent_to_task_spec,
)
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

_ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Resp:
    def __init__(self, text):
        self.text = text


class _FakeAI:
    def chat(self, prompt, routing_context=None):
        return _Resp("Model generated response.")

    def stream_chat(self, prompt, routing_context=None):
        def gen():
            yield "Model streamed response."

        return gen()


def _session_context(*, owner=False, user_id="alice"):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if owner:
        session = manager.create_session("owner")
    else:
        authority.add_user(user_id, principal_id=user_id)
        session = manager.create_session(user_id)
    return SessionContext.from_session(session)


def _spec(text, session=None):
    intake = TaskIntake(now=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc))
    spec = intake.intake(text)
    if session is not None:
        spec = ConversationService._attach_session_to_spec(spec, session)
    return spec


def _service(*, dev_bridge=None, coordinator=None, session=None):
    return ConversationService(
        _FakeAI(),
        task_intake=TaskIntake(now=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)),
        development_bridge=dev_bridge,
        orchestration_resolver=lambda s, ctx: None,  # always unresolved -> gap signal
        session_context=session,
        development_need_coordinator=coordinator,
    )


@pytest.fixture
def coordinator():
    return DevelopmentNeedCoordinator()


# ---------------------------------------------------------------------------
# Detection sourcing
# ---------------------------------------------------------------------------


class TestDetectionSourcing:
    def test_unresolved_action_reaches_detector(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        explanation = coordinator.detect_unresolved_action(spec)
        assert explanation is not None
        assert explanation.role == "assistant"
        assert coordinator.has_pending

    def test_normal_conversation_no_detection(self, coordinator):
        spec = _spec("Hello Atlas, how are you today")
        assert coordinator.detect_unresolved_action(spec) is None
        assert not coordinator.has_pending

    def test_resolvable_action_no_detection(self, coordinator):
        # A resolvable action is represented by NOT calling detect_unresolved_action.
        spec = _spec("run the quantum stabilizer diagnostic")
        # Direct detector with resolution=True returns None.
        assert coordinator._detector.detect(spec, resolution=True) is None

    def test_explicit_development_not_routed_to_detector(self, coordinator):
        spec = _spec("add a new capability to Atlas for scheduling so that tasks run on time")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert coordinator._detector.detect(spec, resolution=False) is None


# ---------------------------------------------------------------------------
# Explanation + pending confirmation
# ---------------------------------------------------------------------------


class TestExplanationAndPending:
    def test_explanation_establishes_pending(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        msg = coordinator.detect_unresolved_action(spec)
        assert msg is not None
        assert "yes or no" in msg.content.lower()
        assert coordinator.has_pending

    def test_pending_carries_provenance(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        pending = coordinator._pending
        assert pending is not None
        assert pending.session_id == session.session_id
        assert pending.principal_id == "alice"
        assert pending.authority == "user"


# ---------------------------------------------------------------------------
# Confirmation flow
# ---------------------------------------------------------------------------


class TestConfirmationFlow:
    def test_explicit_yes_produces_development_task_spec(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        outcome = coordinator.handle_reply("yes", session)
        assert isinstance(outcome, TaskSpec)
        assert outcome.task_type is TaskType.DEVELOPMENT_REQUEST
        assert not outcome.needs_clarification
        assert not coordinator.has_pending  # cleared after confirm

    def test_denial_no_development_request(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        outcome = coordinator.handle_reply("no", session)
        assert isinstance(outcome, Message)
        assert not coordinator.has_pending

    def test_ambiguous_no_development_request(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        outcome = coordinator.handle_reply("maybe", session)
        assert isinstance(outcome, Message)
        assert coordinator.has_pending  # still pending

    def test_unrelated_response_no_confirm(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        outcome = coordinator.handle_reply("the weather is nice", session)
        assert isinstance(outcome, Message)
        assert coordinator.has_pending

    def test_missing_pending_fails_closed(self, coordinator):
        session = _session_context(user_id="alice")
        assert coordinator.handle_reply("yes", session) is None


class TestSessionMismatch:
    def test_mismatched_session_fails_closed(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        # A different session must not confirm the pending opportunity.
        other = _session_context(user_id="alice")
        assert other.session_id != session.session_id
        assert coordinator.handle_reply("yes", other) is None
        assert coordinator.has_pending  # unchanged

    def test_mismatched_principal_fails_closed(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        # Same session id but different principal cannot happen via SessionManager;
        # we exercise the guard by constructing a mismatched session directly.
        other_session = _session_context(user_id="bob")
        assert coordinator.handle_reply("yes", other_session) is None
        assert coordinator.has_pending

    def test_missing_session_fails_closed(self, coordinator):
        session = _session_context(user_id="alice")
        spec = _spec("run the quantum stabilizer diagnostic", session)
        coordinator.detect_unresolved_action(spec)
        assert coordinator.handle_reply("yes", None) is None
        assert coordinator.has_pending


# ---------------------------------------------------------------------------
# Router (confirmed intent -> existing intake representation)
# ---------------------------------------------------------------------------


class TestIntentToTaskSpec:
    def test_confirmed_intent_to_task_spec(self):
        need = DetectedDevelopmentNeed(
            signal_kind=DevelopmentSignalKind.CAPABILITY_GAP,
            reason="could not resolve",
            capability="quantum_stabilizer",
            evidence=("quantum_stabilizer",),
            principal_id="alice",
            authority="user",
            session_id="sess-1",
        )
        intent = DevelopmentNeedDialogue().build_intent(need)
        spec = explicit_intent_to_task_spec(intent)
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert not spec.needs_clarification
        assert spec.context["principal_id"] == "alice"
        assert spec.context["authority"] == "user"
        assert spec.context["session_id"] == "sess-1"
        assert "code_changes" not in spec.context

    def test_intent_spec_is_accepted_by_b3_intake(self):
        from atlas.conversation.development_intake import task_spec_to_development_need

        need = DetectedDevelopmentNeed(
            signal_kind=DevelopmentSignalKind.CAPABILITY_GAP,
            reason="could not resolve",
            capability="quantum_stabilizer",
        )
        intent = DevelopmentNeedDialogue().build_intent(need)
        spec = explicit_intent_to_task_spec(intent)
        dev_need = task_spec_to_development_need(spec)
        assert dev_need is not None
        assert "quantum_stabilizer" in dev_need.title


# ---------------------------------------------------------------------------
# ConversationService integration (end-to-end)
# ---------------------------------------------------------------------------


class TestConversationServiceIntegration:
    def test_confirmed_route_reaches_development_bridge(self):
        session = _session_context(user_id="alice")
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        service = _service(
            dev_bridge=bridge,
            coordinator=DevelopmentNeedCoordinator(),
            session=session,
        )
        # 1. unresolved action -> explanation (pending established)
        first = service.send("run the quantum stabilizer diagnostic", session_context=session)
        assert "yes or no" in first.content.lower()
        bridge.assert_not_called()

        # 2. explicit yes -> confirmed -> development bridge
        second = service.send("yes", session_context=session)
        bridge.assert_called_once()
        assert second.content == "PREPARED"

    def test_confirmed_route_does_not_approve_or_execute(self):
        session = _session_context(user_id="alice")
        calls = []

        def bridge(spec):
            calls.append("bridge")
            return Message(
                role="assistant",
                content="PENDING_APPROVAL; nothing approved or executed",
            )

        service = _service(dev_bridge=bridge, coordinator=DevelopmentNeedCoordinator(), session=session)
        service.send("run the quantum stabilizer diagnostic", session_context=session)
        service.send("yes", session_context=session)
        assert calls == ["bridge"]
        # No approval/execution/promotion methods are reachable through the service.
        assert not hasattr(service, "approval_manager")

    def test_denial_does_not_reach_bridge(self):
        session = _session_context(user_id="alice")
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        service = _service(dev_bridge=bridge, coordinator=DevelopmentNeedCoordinator(), session=session)
        service.send("run the quantum stabilizer diagnostic", session_context=session)
        resp = service.send("no", session_context=session)
        bridge.assert_not_called()
        assert "won't propose" in resp.content.lower()

    def test_repeated_confirmation_no_duplicate_requests(self):
        session = _session_context(user_id="alice")
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        service = _service(dev_bridge=bridge, coordinator=DevelopmentNeedCoordinator(), session=session)
        service.send("run the quantum stabilizer diagnostic", session_context=session)
        service.send("yes", session_context=session)
        # After confirm, no pending state remains; a second "yes" is ordinary.
        service.send("yes", session_context=session)
        assert bridge.call_count == 1


# ---------------------------------------------------------------------------
# Purity + dependency direction + tick + B4
# ---------------------------------------------------------------------------


class TestArchitecture:
    def test_coordinator_imports_no_forbidden_machinery(self):
        for name in ("development_need_coordinator", "development_need_router"):
            source = (_ROOT / "atlas" / "conversation" / f"{name}.py").read_text(
                encoding="utf-8"
            )
            tree = ast.parse(source, filename=name)
            forbidden = (
                "atlas.evolution",
                "atlas.orchestration",
                "atlas.advisory",
                "atlas.kernel",
                "atlas.runtime",
                "atlas.storage",
            )
            for node in ast.walk(tree):
                module = getattr(node, "module", None)
                if module and any(
                    module == p or module.startswith(p + ".") for p in forbidden
                ):
                    raise AssertionError(f"{name} imports forbidden module: {module}")

    def test_conversation_service_no_evolution_execution_import(self):
        source = (
            _ROOT / "atlas" / "conversation" / "conversation_service.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="conversation_service.py")
        forbidden = (
            "atlas.evolution.approval_manager",
            "atlas.evolution.development_planner",
            "atlas.evolution.self_development_loop",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.promotion_gate",
            "atlas.evolution.model_assisted_supplier",
            "atlas.evolution.autonomy",
        )
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and any(
                module == p or module.startswith(p + ".") for p in forbidden
            ):
                raise AssertionError(f"conversation_service imports {module}")

    def test_tick_remains_development_execution_free(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        for marker in (
            "run_development_cycle",
            "run_development_execution",
            "confirm_development_approval",
            "submit_development_for_promotion_review",
        ):
            assert marker not in tick_src

    def test_dialogue_and_detector_remain_pure(self):
        # Detector and dialogue must expose no development execution surface.
        detector = DevelopmentNeedDetector()
        dialogue = DevelopmentNeedDialogue()
        for obj in (detector, dialogue):
            for attr in (
                "approval_manager",
                "development_controller",
                "planner",
                "self_development_loop",
                "execution_gateway",
                "promotion_gate",
                "code_sandbox",
                "scheduler",
                "tick",
            ):
                assert not hasattr(obj, attr), f"{type(obj).__name__} has {attr}"

    def test_no_b4_execution_references(self):
        source = (
            _ROOT / "atlas" / "conversation" / "conversation_service.py"
        ).read_text(encoding="utf-8")
        assert "ModelAssistedChangeSupplier" not in source
        assert "model_assisted_authoring" not in source
