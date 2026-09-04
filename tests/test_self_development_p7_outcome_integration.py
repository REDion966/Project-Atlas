"""P7.5 integration — bridge result is surfaced through DevelopmentOutcomeReporter.

Proves the ConversationService routes an authoritative F9 result object (not a
pre-rendered Message) through the reporter, producing truthful reports without
any approval/execute/promote bypass.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.development_outcome_reporter import (
    DevelopmentOutcomeReporter,
)
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

_ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Resp:
    def __init__(self, text):
        self.text = text


class _FakeAI:
    def chat(self, prompt, routing_context=None):
        return _Resp("Model generated response.")


def _session(*, owner=False, user_id="alice"):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if owner:
        session = manager.create_session("owner")
    else:
        authority.add_user(user_id, principal_id=user_id)
        session = manager.create_session(user_id)
    return SessionContext.from_session(session)


def _service(*, dev_bridge, reporter=None, session=None):
    return ConversationService(
        _FakeAI(),
        task_intake=TaskIntake(),
        development_bridge=dev_bridge,
        session_context=session,
        development_need_coordinator=DevelopmentNeedCoordinator(),
        outcome_reporter=reporter or DevelopmentOutcomeReporter(),
    )


# ---------------------------------------------------------------------------
# Fake F9 result objects (duck-typed to the real shapes)
# ---------------------------------------------------------------------------


class _CycleResult:
    ok = True
    proposal_id = "DEV-1"
    approval_request_id = "APPR-1"
    failures = ()


class _CycleResultFailure:
    ok = False
    proposal_id = ""
    approval_request_id = ""
    failures = (("supplier", "no changes"),)


class _Decision:
    def __init__(self, name):
        self.name = name


class _ApprovalRequest:
    def __init__(self, decision):
        self.decision = _Decision(decision)
        self.proposal_id = "DEV-1"
        self.request_id = "APPR-1"


class _RunResult:
    def __init__(self, status_name, rollback=False, verification=False, message=""):
        self.status = _Decision(status_name)
        self.plan = type("_Plan", (), {"proposal_id": "DEV-1"})()
        self.message = message
        self.outcomes = [
            type(
                "_Outcome",
                (),
                {
                    "rollback_occurred": rollback,
                    "verification_passed": verification,
                    "test_outcome": "passed",
                },
            )()
        ]


# ---------------------------------------------------------------------------
# Integration: confirmed request -> bridge -> reporter
# ---------------------------------------------------------------------------


class TestBridgeResultReporting:
    def test_cycle_result_reported_as_awaiting_approval(self):
        session = _session(user_id="alice")
        service = _service(dev_bridge=lambda spec: _CycleResult(), session=session)
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert resp.role == "assistant"
        assert "awaiting human approval" in resp.content.lower()
        assert resp.metadata["development_outcome"]["state"] == "awaiting_approval"

    def test_cycle_result_not_reported_as_success(self):
        session = _session(user_id="alice")
        service = _service(dev_bridge=lambda spec: _CycleResult(), session=session)
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert "success" not in resp.content.lower()
        assert "executed" not in resp.content.lower()

    def test_preparation_failure_reported(self):
        session = _session(user_id="alice")
        service = _service(dev_bridge=lambda spec: _CycleResultFailure(), session=session)
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert "failed" in resp.content.lower()
        assert resp.metadata["development_outcome"]["state"] == "preparation_failed"

    def test_approval_rejection_reported(self):
        session = _session(user_id="alice")
        service = _service(
            dev_bridge=lambda spec: _ApprovalRequest("REJECTED"), session=session
        )
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert "denied" in resp.content.lower()
        assert resp.metadata["development_outcome"]["state"] == "approval_rejected"

    def test_execution_success_reported(self):
        session = _session(user_id="alice")
        service = _service(
            dev_bridge=lambda spec: _RunResult("SUCCESS", verification=True),
            session=session,
        )
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert "completed successfully" in resp.content.lower()
        assert resp.metadata["development_outcome"]["state"] == "execution_succeeded"

    def test_execution_failure_reported(self):
        session = _session(user_id="alice")
        service = _service(
            dev_bridge=lambda spec: _RunResult("FAILED"), session=session
        )
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert "failed" in resp.content.lower()
        assert resp.metadata["development_outcome"]["state"] == "execution_failed"

    def test_rollback_reported(self):
        session = _session(user_id="alice")
        service = _service(
            dev_bridge=lambda spec: _RunResult("FAILED", rollback=True),
            session=session,
        )
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert "rolled back" in resp.content.lower()
        assert resp.metadata["development_outcome"]["state"] == "rolled_back"

    def test_unknown_result_fails_closed(self):
        session = _session(user_id="alice")
        service = _service(dev_bridge=lambda spec: object(), session=session)
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert "could not be determined" in resp.content.lower()

    def test_message_result_bypasses_reporter(self):
        session = _session(user_id="alice")
        service = _service(
            dev_bridge=lambda spec: Message(role="assistant", content="custom report"),
            session=session,
        )
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert resp.content == "custom report"

    def test_provenance_preserved_and_not_elevated(self):
        session = _session(user_id="alice")
        service = _service(dev_bridge=lambda spec: _CycleResult(), session=session)
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time",
            session_context=session,
        )
        assert resp.metadata["principal_id"] == "alice"
        assert resp.metadata["authority"] == "user"
        assert resp.metadata["session_id"] == session.session_id


# ---------------------------------------------------------------------------
# No approval/execute/promote bypass + idempotency
# ---------------------------------------------------------------------------


class TestNoBypass:
    def test_bridge_result_does_not_approve_or_execute(self):
        # The bridge is a plain callable; returning a result object must not
        # reach into any approval/execution surface on the service.
        service = _service(dev_bridge=lambda spec: _CycleResult())
        for attr in ("approval_manager", "planner", "self_development_loop", "execution_gateway", "promotion_gate"):
            assert not hasattr(service, attr)

    def test_repeated_result_handling_is_idempotent(self):
        session = _session(user_id="alice")
        calls = []

        def bridge(spec):
            calls.append(1)
            return _CycleResult()

        service = _service(dev_bridge=bridge, session=session)
        text = "add a new capability to Atlas for scheduling so that tasks run on time"
        first = service.send(text, session_context=session)
        second = service.send(text, session_context=session)
        # Two separate explicit requests each invoke the bridge once; the
        # reporter itself is stateless and never retries/creates requests.
        assert len(calls) == 2
        assert first.content == second.content
        assert first.metadata == second.metadata


# ---------------------------------------------------------------------------
# Dependency direction + tick + B4
# ---------------------------------------------------------------------------


class TestArchitecture:
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

    def test_reporter_no_evolution_import(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_outcome_reporter.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="development_outcome_reporter.py")
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and module.startswith("atlas.evolution"):
                raise AssertionError(f"reporter imports {module}")

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

    def test_no_b4_references_in_conversation(self):
        source = (
            _ROOT / "atlas" / "conversation" / "conversation_service.py"
        ).read_text(encoding="utf-8")
        assert "ModelAssistedChangeSupplier" not in source
        assert "model_assisted_authoring" not in source
