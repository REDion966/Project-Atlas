"""P7.7 — Advisory-input integration tests.

Connects the EXISTING P5 advisory output/signals to the EXISTING P7
conversational self-development path::

    P5 Advisory Opportunity
        ↓  (kernel projects AdvisoryItem → AdvisorySignal)
    P7.2 DevelopmentNeedDetector
        ↓
    P7.3 Explanation + Explicit Confirmation
        ↓
    confirmed DEVELOPMENT_REQUEST
        ↓
    existing P7.4 development bridge
        ↓
    existing F9 development cycle
        ↓
    PENDING_APPROVAL

Critical invariant under test::

    ADVISORY != DEVELOPMENT. An advisory opportunity must NEVER directly
    create, approve, execute, or promote a development proposal. Only explicit
    human confirmation may turn an advisory opportunity into a DEVELOPMENT_REQUEST.

The projection (AdvisoryItem → AdvisorySignal) lives at the kernel composition
boundary; the conversation layer never imports atlas.advisory.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from atlas.advisory.models import (
    AdvisoryItem,
    AdvisoryReport,
    AdvisorySeverity,
    AdvisorySource,
)
from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_need_coordinator import (
    DevelopmentNeedCoordinator,
)
from atlas.conversation.development_need_detector import (
    AdvisorySignal,
    DevelopmentSignalKind,
)
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.kernel.atlas import Atlas
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


# ---------------------------------------------------------------------------
# Shared test doubles (local — keep this file self-contained)
# ---------------------------------------------------------------------------


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


def _service(*, dev_bridge=None, coordinator=None, session=None):
    return ConversationService(
        _FakeAI(),
        task_intake=TaskIntake(now=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)),
        development_bridge=dev_bridge,
        orchestration_resolver=lambda s, ctx: None,
        session_context=session,
        development_need_coordinator=coordinator if coordinator is not None else DevelopmentNeedCoordinator(),
    )


def _improvement_item(*, summary="Stale authorizations detected.", principal_id="owner"):
    return AdvisoryItem(
        item_id="ADV-ITEM-000001",
        severity=AdvisorySeverity.WARNING,
        source=AdvisorySource.SELF_MANAGEMENT,
        kind="maintenance_need",
        summary=summary,
        evidence_ids=("E1", "E2"),
        suggested_action="atlas.run_self_management_review",
        requires_owner=False,
        principal_id=principal_id,
        recorded_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# 1. Projection: AdvisoryItem → AdvisorySignal (kernel composition boundary)
# ---------------------------------------------------------------------------


class TestProjection:
    def test_improvement_item_projects(self):
        item = _improvement_item()
        signal = Atlas.project_advisory(item)
        assert isinstance(signal, AdvisorySignal)
        assert signal.suggested_action == "atlas.run_self_management_review"
        assert signal.summary == "Stale authorizations detected."
        assert signal.principal_id == "owner"
        assert signal.evidence_ids == ("E1", "E2")

    def test_projection_preserves_requires_owner_without_elevating_authority(self):
        """requires_owner must NOT cause the projection to invent OWNER authority."""
        item = _improvement_item()
        # run_self_management_review is not owner-only; build an owner-only one.
        owner_only = AdvisoryItem(
            item_id="ADV-ITEM-000002",
            severity=AdvisorySeverity.WARNING,
            source=AdvisorySource.SELF_MANAGEMENT,
            kind="maintenance_need",
            summary="Lifecycle component OFFLINE: scheduler",
            evidence_ids=("scheduler",),
            suggested_action="atlas.run_development_cycle",
            requires_owner=True,
            principal_id="owner",
            recorded_at=datetime.now(timezone.utc),
        )
        signal = Atlas.project_advisory(owner_only)
        assert isinstance(signal, AdvisorySignal)
        # Authority is never projected from advisory content — the session context
        # is authoritative. A USER must never be elevated by advisory content.
        assert signal.authority == ""

    def test_non_improvement_item_with_no_summary_projects_empty(self):
        item = AdvisoryItem(
            item_id="ADV-ITEM-000003",
            severity=AdvisorySeverity.INFO,
            source=AdvisorySource.ENVIRONMENT,
            kind="environment_change",
            summary="",
            suggested_action="",
            recorded_at=datetime.now(timezone.utc),
        )
        assert Atlas.project_advisory(item) is None

    def test_none_item_projects_none(self):
        assert Atlas.project_advisory(None) is None


# ---------------------------------------------------------------------------
# 2/3. Advisory reaches P7: detection + bounded explanation + confirmation prompt
# ---------------------------------------------------------------------------


class TestAdvisoryReachesP7:
    def test_advisory_reaches_detector_through_coordinator(self):
        coordinator = DevelopmentNeedCoordinator()
        session = _session_context(owner=True)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
            evidence_ids=("E1",),
            principal_id="owner",
        )
        msg = coordinator.advisory_input(signal, session)
        assert msg is not None
        assert msg.role == "assistant"
        assert coordinator.has_pending

    def test_explanation_asks_yes_no(self):
        coordinator = DevelopmentNeedCoordinator()
        session = _session_context(owner=True)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
        )
        msg = coordinator.advisory_input(signal, session)
        assert "yes or no" in msg.content.lower()

    def test_advisory_alone_never_invokes_development_bridge(self):
        """The core P7.7 safety property: advisory input produces only an
        explanation; the development bridge is never called."""
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        coordinator = DevelopmentNeedCoordinator()
        session = _session_context(owner=True)
        service = _service(dev_bridge=bridge, coordinator=coordinator, session=session)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
        )
        msg = service.handle_advisory(signal, session)
        assert msg is not None
        bridge.assert_not_called()

    def test_non_improvement_advisory_produces_no_message(self):
        coordinator = DevelopmentNeedCoordinator()
        session = _session_context(owner=True)
        signal = AdvisorySignal(
            kind="environment_change",
            summary="Provider X changed.",
            suggested_action="atlas.run_operation_cycle",  # not an improvement hint
        )
        assert coordinator.advisory_input(signal, session) is None
        assert not coordinator.has_pending

    def test_pending_bound_to_authoritative_session_context(self):
        """The pending confirmation is bound to the session context, not the
        advisory's claimed principal_id."""
        coordinator = DevelopmentNeedCoordinator()
        owner_session = _session_context(owner=True)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
            principal_id="owner",
        )
        coordinator.advisory_input(signal, owner_session)
        assert coordinator._pending.session_id == owner_session.session_id
        assert coordinator._pending.principal_id == "owner"


# ---------------------------------------------------------------------------
# 4/5/6. Negative / ambiguous / unrelated confirmation never invokes bridge
# ---------------------------------------------------------------------------


class TestConfirmationGates:
    def _setup(self, *, owner=True, user_id="alice"):
        coordinator = DevelopmentNeedCoordinator()
        session = _session_context(owner=owner, user_id=user_id)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
        )
        coordinator.advisory_input(signal, session)
        return coordinator, session

    def test_negative_confirmation_no_bridge(self):
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        coordinator, session = self._setup()
        service = _service(dev_bridge=bridge, coordinator=coordinator, session=session)
        coordinator.advisory_input(
            AdvisorySignal(
                kind="maintenance_need",
                summary="Stale authorizations detected.",
                suggested_action="atlas.run_self_management_review",
            ),
            session,
        )
        resp = service.send("no", session_context=session)
        bridge.assert_not_called()
        assert "won't propose" in resp.content.lower()

    def test_ambiguous_confirmation_no_bridge(self):
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        coordinator, session = self._setup()
        service = _service(dev_bridge=bridge, coordinator=coordinator, session=session)
        resp = service.send("maybe", session_context=session)
        bridge.assert_not_called()
        assert coordinator.has_pending  # still pending

    def test_unrelated_reply_no_bridge(self):
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        coordinator, session = self._setup()
        service = _service(dev_bridge=bridge, coordinator=coordinator, session=session)
        resp = service.send("the weather is nice", session_context=session)
        bridge.assert_not_called()
        assert coordinator.has_pending


# ---------------------------------------------------------------------------
# 7/8. Explicit confirmation invokes the existing development bridge exactly once
#   and the confirmed advisory becomes a DEVELOPMENT_REQUEST TaskSpec.
# ---------------------------------------------------------------------------


class TestConfirmedAdvisory:
    def test_explicit_confirmation_invokes_bridge_once(self):
        session = _session_context(owner=True)
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        service = _service(dev_bridge=bridge, session=session)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
        )
        # Advisory → explanation (pending established).
        first = service.handle_advisory(signal, session)
        assert "yes or no" in first.content.lower()
        bridge.assert_not_called()

        # Explicit yes → confirmed → existing development bridge, exactly once.
        second = service.send("yes", session_context=session)
        bridge.assert_called_once()
        assert second.content == "PREPARED"

    def test_confirmed_advisory_becomes_development_request(self):
        session = _session_context(owner=True)
        coordinator = DevelopmentNeedCoordinator()
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
        )
        coordinator.advisory_input(signal, session)
        outcome = coordinator.handle_reply("yes", session)
        assert isinstance(outcome, TaskSpec)
        assert outcome.task_type is TaskType.DEVELOPMENT_REQUEST
        assert not outcome.needs_clarification

    def test_provenance_preserved_on_confirmed_request(self):
        session = _session_context(user_id="alice")
        coordinator = DevelopmentNeedCoordinator()
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
            evidence_ids=("E1", "E2"),
            principal_id="alice",
        )
        coordinator.advisory_input(signal, session)
        outcome = coordinator.handle_reply("yes", session)
        assert outcome.context["principal_id"] == "alice"
        assert outcome.context["session_id"] == session.session_id
        assert outcome.context["signal_kind"] == DevelopmentSignalKind.ADVISORY_OPPORTUNITY.value


# ---------------------------------------------------------------------------
# 9. Existing B3 development intake remains authoritative.
# ---------------------------------------------------------------------------


class TestB3IntakeAuthoritative:
    def test_explicit_dev_request_not_rerouted_through_advisory(self):
        """An explicit DEVELOPMENT_REQUEST TaskSpec still flows through the
        existing B3 intake (task_spec_to_development_need), not the advisory
        path."""
        from atlas.conversation.development_intake import task_spec_to_development_need

        coordinator = DevelopmentNeedCoordinator()
        session = _session_context(user_id="alice")
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
        )
        coordinator.advisory_input(signal, session)
        spec = coordinator.handle_reply("yes", session)
        need = task_spec_to_development_need(spec)
        assert need is not None
        # B3 intake is authoritative: the title reflects the confirmed intent,
        # not an advisory merge.
        assert "capability" in need.title.lower() or "improve" in need.title.lower()


# ---------------------------------------------------------------------------
# 11. USER cannot be elevated through advisory content.
# ---------------------------------------------------------------------------


class TestNoUserElevation:
    def test_user_session_stays_user_after_confirming_advisory(self):
        """A USER who confirms an advisory opportunity produces a development
        request scoped to the USER session — never elevated to OWNER."""
        session = _session_context(user_id="alice")
        coordinator = DevelopmentNeedCoordinator()
        # An OWNER-only suggested action, confirmed by a USER session.
        # (AdvisorySignal carries no authority — the session context is.)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Lifecycle component OFFLINE: scheduler",
            suggested_action="atlas.run_development_cycle",
            principal_id="owner",
        )
        coordinator.advisory_input(signal, session)
        outcome = coordinator.handle_reply("yes", session)
        assert isinstance(outcome, TaskSpec)
        # The request is bound to the USER session context, not elevated.
        assert outcome.context["principal_id"] == "alice"
        assert outcome.context["authority"] == "user"

    def test_advisory_for_owner_cannot_be_confirmed_by_different_session(self):
        """The pending confirmation is bound to the authoritative session; a
        different session cannot confirm it."""
        coordinator = DevelopmentNeedCoordinator()
        owner_session = _session_context(owner=True)
        signal = AdvisorySignal(
            kind="maintenance_need",
            summary="Stale authorizations detected.",
            suggested_action="atlas.run_self_management_review",
            principal_id="owner",
        )
        coordinator.advisory_input(signal, owner_session)
        other_session = _session_context(user_id="bob")
        assert coordinator.handle_reply("yes", other_session) is None
        assert coordinator.has_pending  # unchanged


# ---------------------------------------------------------------------------
# 12. Multiple advisory opportunities handled safely and deterministically.
# ---------------------------------------------------------------------------


class TestMultipleAdvisories:
    def test_multiple_opportunities_bounded_by_single_pending_slot(self):
        """Multiple signals are fed deterministically; the single pending-
        confirmation slot bounds state and the bridge is called at most once."""
        session = _session_context(owner=True)
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        service = _service(dev_bridge=bridge, session=session)
        signals = [
            AdvisorySignal(
                kind="maintenance_need",
                summary=f"Opportunity {i}.",
                suggested_action="atlas.run_self_management_review",
            )
            for i in range(3)
        ]
        explanations = []
        for sig in signals:
            msg = service.handle_advisory(sig, session)
            if msg is not None:
                explanations.append(msg)
        # Each improvement signal produces an explanation.
        assert len(explanations) == 3
        # But the single pending slot holds only the last detected need.
        assert coordinator_has_single_pending(service)
        # Confirm once → bridge called exactly once, not three times.
        service.send("yes", session_context=session)
        assert bridge.call_count == 1

    def test_feed_advisory_projects_and_feeds_in_report_order(self):
        session = _session_context(owner=True)
        service = _service(session=session)
        report = AdvisoryReport(
            advisory_id="ADV-000001",
            generated_at=datetime.now(timezone.utc),
            principal_id="owner",
            items=(
                _improvement_item(summary="First opportunity."),
                AdvisoryItem(
                    item_id="ADV-ITEM-NOOP",
                    severity=AdvisorySeverity.INFO,
                    source=AdvisorySource.ENVIRONMENT,
                    kind="environment_change",
                    summary="",
                    suggested_action="",
                    recorded_at=datetime.now(timezone.utc),
                ),
                _improvement_item(summary="Second opportunity."),
            ),
        )
        # feed_advisory is a kernel-level integration; exercise via a minimal
        # kernel projection + service feed to avoid a full boot.
        messages = []
        for item in report.items:
            sig = Atlas.project_advisory(item)
            if sig is None:
                continue
            msg = service.handle_advisory(sig, session)
            if msg is not None:
                messages.append(msg)
        # Two improvement items project; the empty non-improvement item does not.
        assert len(messages) == 2
        assert "First opportunity." in messages[0].content


def coordinator_has_single_pending(service) -> bool:
    coordinator = service._development_need_coordinator
    return coordinator is not None and coordinator.has_pending


# ---------------------------------------------------------------------------
# 17-20. Safety invariants: no retry, no bypass, tick-free, B4 off.
# ---------------------------------------------------------------------------


class TestSafetyInvariants:
    def test_no_automatic_retry_in_advisory_path(self):
        coordinator = DevelopmentNeedCoordinator()
        assert not hasattr(coordinator, "retry")
        assert not hasattr(coordinator, "max_retries")
        service = ConversationService(_FakeAI())
        assert not hasattr(service, "retry_advisory")

    def test_no_approval_execute_promote_bypass(self):
        """The advisory path exposes no direct approval/execute/promote surface."""
        coordinator = DevelopmentNeedCoordinator()
        for attr in (
            "approval_manager",
            "approve",
            "run_development_execution",
            "confirm_development_approval",
            "submit_development_for_promotion_review",
            "promote",
            "execution_gateway",
            "planner",
        ):
            assert not hasattr(coordinator, attr), f"coordinator must not expose {attr}"

    def test_tick_remains_development_execution_free(self):
        tick_src = inspect.getsource(Atlas.tick)
        for marker in (
            "handle_advisory",
            "feed_advisory",
            "run_development_cycle",
            "run_development_execution",
            "confirm_development_approval",
            "submit_development_for_promotion_review",
        ):
            assert marker not in tick_src

    def test_b4_remains_disabled(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        cfg = (root / "config.toml").read_text(encoding="utf-8")
        assert "model_assisted_authoring = false" in cfg


# ---------------------------------------------------------------------------
# 21/22. Dependency direction: conversation must not import advisory/evolution/
# kernel/runtime/storage; advisory must not gain P7 execution machinery.
# ---------------------------------------------------------------------------


class TestDependencyDirection:
    _ROOT = pathlib.Path(__file__).resolve().parents[1]

    def test_conversation_imports_no_advisory_or_evolution_machinery(self):
        conv_dir = self._ROOT / "atlas" / "conversation"
        # The conversation layer must not import advisory runtime machinery or
        # evolution execution machinery directly. (Its OWN storage module,
        # atlas.storage.conversation_storage, is legitimate and allowed.)
        forbidden = (
            "atlas.advisory",
            "atlas.evolution.autonomy",
            "atlas.evolution.approval_manager",
            "atlas.evolution.development_planner",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.governance",
            "atlas.evolution.model_assisted_supplier",
            "atlas.evolution.promotion_gate",
            "atlas.evolution.self_development_loop",
            "atlas.kernel",
            "atlas.runtime",
        )
        violations = []
        for path in sorted(conv_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = getattr(node, "module", None)
                if module and any(module == p or module.startswith(p + ".") for p in forbidden):
                    violations.append(f"{path.relative_to(self._ROOT)}: {module}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p + ".") for p in forbidden):
                            violations.append(f"{path.relative_to(self._ROOT)}: {alias.name}")
        assert violations == [], f"conversation imports forbidden: {violations}"

    def test_advisory_imports_no_p7_execution_machinery(self):
        advisory_dir = self._ROOT / "atlas" / "advisory"
        forbidden = (
            "atlas.conversation.development_need_coordinator",
            "atlas.conversation.development_need_router",
            "atlas.evolution.autonomy",
            "atlas.evolution.approval_manager",
            "atlas.evolution.development_planner",
            "atlas.evolution.self_development_loop",
            "atlas.evolution.promotion_gate",
            "atlas.evolution.execution_gateway",
        )
        violations = []
        for path in sorted(advisory_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = getattr(node, "module", None)
                if module and any(module == p or module.startswith(p + ".") for p in forbidden):
                    violations.append(f"{path.relative_to(self._ROOT)}: {module}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p + ".") for p in forbidden):
                            violations.append(f"{path.relative_to(self._ROOT)}: {alias.name}")
        assert violations == [], f"advisory imports forbidden: {violations}"
