"""P7.1 — Conversational Self-Development contract tests (TESTS ONLY).

These tests pin the behavioral contracts that P7.2-P7.7 must satisfy. They are
written against CURRENT public/observable behavior and existing seams; no
production code is modified. Where a future mechanism does not yet exist
(e.g. the P7.3 confirmation gate), the test asserts the currently-observable
safety invariant that the mechanism must PRESERVE, and the test name /
docstring states the forward requirement.

Contracts covered:
  1. Five-way development-related classification (normal / action / explicit
     dev / capability-gap / advisory).
  2. No false positives.
  3. Explicit development request intake (B3) fail-closed mapping.
  4. Confirmation-gate invariant (P7.3 forward requirement documented).
  5. F9 stop-at-approval conversational boundary.
  6. Session / provenance retention at the conversation seam.
  7. Advisory-only isolation (advisory never drives dev execution).
  8. Tick safety (development execution must not enter Atlas.tick()).
  9. Dependency direction (conversation routes through the injected kernel
     seam; never imports evolution execution machinery directly).
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from atlas.advisory.advisor import ProactiveAdvisor
from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_intake import (
    clarification_questions,
    is_development_request,
    needs_clarification as _needs_clarification,
    task_spec_to_development_need,
)
from atlas.conversation.message import Message
from atlas.conversation.task_intake import (
    AmbiguityReport,
    TaskIntake,
    TaskSpec,
    TaskType,
)
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
    SuppliedChanges,
)
from atlas.evolution.models import ProposalStatus
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


# ---------------------------------------------------------------------------
# Shared test doubles
# ---------------------------------------------------------------------------


class _FakeAI:
    """Minimal AIService stand-in: chat()/stream_chat() return canned text."""

    def chat(self, prompt, routing_context=None):
        return _Resp("Model generated response.")

    def stream_chat(self, prompt, routing_context=None):
        def gen():
            yield "Model streamed response."

        return gen()


class _Resp:
    def __init__(self, text):
        self.text = text


class _FakeAcquisition:
    """Duck-typed F8 acquisition result (no network)."""

    status = "ok"

    def to_dict(self):
        return {
            "acquisition_id": "ACQ-P7-001",
            "status": "ok",
            "report_id": "report:p7",
            "sources": (),
            "confidence": 0.8,
            "claim_count": 1,
        }


class _ConcreteSupplier:
    """Injected change supplier producing one concrete sandbox change."""

    def supply_changes(self, need):
        return SuppliedChanges(
            code_changes=(("docs/p7_bridge_note.md", "# p7\n"),),
            origin="deterministic",
        )


class _SpyApprovalManager(ApprovalManager):
    """ApprovalManager that records which lifecycle methods are invoked."""

    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    def create_approval_request(self, proposal):
        self.calls.append("create_approval_request")
        return super().create_approval_request(proposal)

    def approve(self, request, comment=""):
        self.calls.append("approve")
        return super().approve(request, comment)

    def reject(self, request, reason=""):
        self.calls.append("reject")
        return super().reject(request, reason)


def _frozen_now():
    return datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)


def _spec(text):
    return TaskIntake(now=_frozen_now()).intake(text)


def _session_context(*, owner=False, user_id="alice"):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if owner:
        session = manager.create_session("owner")
    else:
        authority.add_user(user_id, principal_id=user_id)
        session = manager.create_session(user_id)
    return SessionContext.from_session(session)


def _service(*, dev_bridge=None, orchestration_resolver=None, session=None):
    return ConversationService(
        _FakeAI(),
        task_intake=TaskIntake(now=_frozen_now()),
        development_bridge=dev_bridge,
        orchestration_resolver=orchestration_resolver,
        session_context=session,
    )


# ---------------------------------------------------------------------------
# Contract 1 — Five-way development-related classification
# ---------------------------------------------------------------------------


class TestFiveWayClassification:
    """Pin the distinction between normal / action / explicit-dev /
    capability-gap / advisory signals at the deterministic intake layer."""

    def test_normal_conversation_is_not_development(self):
        spec = _spec("Hello Atlas, how are you today")
        assert spec.task_type is TaskType.CONVERSATION
        assert not is_development_request(spec)
        assert task_spec_to_development_need(spec) is None

    def test_question_is_not_development(self):
        spec = _spec("What does this module do?")
        assert spec.task_type is TaskType.QUESTION
        assert task_spec_to_development_need(spec) is None

    def test_information_request_is_not_development(self):
        spec = _spec("Find the latest research on memory consolidation")
        assert spec.task_type is TaskType.INFORMATION_REQUEST
        assert task_spec_to_development_need(spec) is None

    def test_action_request_stays_action_not_development(self):
        spec = _spec("Create a report of the last week")
        assert spec.task_type is TaskType.ACTION_REQUEST
        assert not is_development_request(spec)
        assert task_spec_to_development_need(spec) is None

    def test_action_request_does_not_become_dev_through_service(self):
        """An action request must never reach the development bridge, even
        when its target cannot be resolved (a capability-gap signal)."""
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        # Unresolvable target -> orchestration resolver returns None.
        service = _service(dev_bridge=bridge, orchestration_resolver=lambda s, ctx: None)
        resp = service.send("Create a report of the last week")
        bridge.assert_not_called()
        assert "more detail" in resp.content.lower()

    def test_explicit_dev_request_add_capability(self):
        spec = _spec("add a new capability to Atlas for scheduling")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert is_development_request(spec)
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert need.title

    def test_explicit_dev_request_implement(self):
        # Dev cue ("implement") + "capability" + success criteria to pass the
        # clarification gate (else the fail-closed adapter returns None).
        spec = _spec(
            "implement a capability that retries outbound calls so that failures are retried"
        )
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert task_spec_to_development_need(spec) is not None

    def test_explicit_dev_request_modify_yourself(self):
        spec = _spec("modify yourself to support scheduled reminders")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert task_spec_to_development_need(spec) is not None

    def test_explicit_dev_request_develop_feature(self):
        # Dev cue ("build") + "module" + success criteria; "develop" is not a
        # dev cue, and the adapter is fail-closed without success criteria.
        spec = _spec(
            "build a module that summarizes weekly activity so that reports are ready"
        )
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert task_spec_to_development_need(spec) is not None

    def test_capability_gap_unresolvable_action_does_not_propose(self):
        """A capability-gap signal (action target that cannot be resolved) is
        NOT an explicit development request and must never produce a governed
        development proposal. P7 must not silently convert gaps into F9 work."""
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        service = _service(dev_bridge=bridge, orchestration_resolver=lambda s, ctx: None)
        resp = service.send("run the quantum stabilizer diagnostic")
        bridge.assert_not_called()
        assert "PENDING_APPROVAL" not in resp.content
        assert "Proposal ID" not in resp.content

    def test_capability_gap_vague_dev_does_not_propose(self):
        """An under-specified development request is gated by clarification
        and must not reach the development bridge / F9."""
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        service = _service(dev_bridge=bridge)
        resp = service.send("improve this module")
        bridge.assert_not_called()
        assert "more detail" in resp.content.lower()
        assert "PENDING_APPROVAL" not in resp.content

    def test_advisory_suggestion_is_not_execution_or_dev_request(self):
        """A proactive advisory signal is inert: it never invokes dev
        machinery and is not itself an explicit development request."""
        advisor = ProactiveAdvisor()
        for attr in (
            "execution_gateway",
            "application_engine",
            "approval_manager",
            "rule_engine",
            "dispatcher",
            "tool_executor",
            "development_controller",
            "planner",
            "tick",
        ):
            assert not hasattr(advisor, attr), f"advisor unexpectedly has {attr}"
        report = advisor.run_advisory(principal_id="alice")
        # No sources -> empty, advisory-only report; never a proposal.
        assert report.count == 0


# ---------------------------------------------------------------------------
# Contract 2 — No false positives
# ---------------------------------------------------------------------------


class TestNoFalsePositives:
    """Ordinary traffic must never produce a development record / proposal."""

    @pytest.mark.parametrize(
        "text",
        [
            "Hello Atlas, how are you today",
            "What does this module do?",
            "Find the latest research on memory consolidation",
            "Create a report of the last week",
            "Tell me a joke",
        ],
    )
    def test_ordinary_input_never_reaches_dev_bridge(self, text):
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        service = _service(dev_bridge=bridge)
        service.send(text)
        bridge.assert_not_called()

    def test_vague_dev_request_clarified_not_proposed(self):
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        service = _service(dev_bridge=bridge)
        resp = service.send("improve this module")
        bridge.assert_not_called()
        assert "more detail" in resp.content.lower()

    def test_advisory_text_does_not_propose(self):
        """Advisory-framed text that lacks a dev cue + self-target/capability/
        module must not be treated as an explicit development request."""
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        service = _service(dev_bridge=bridge)
        resp = service.send(
            "the advisory suggests reviewing provider reliability"
        )
        bridge.assert_not_called()
        assert "PENDING_APPROVAL" not in resp.content


# ---------------------------------------------------------------------------
# Contract 3 — Explicit development request intake (B3) fail-closed
# ---------------------------------------------------------------------------


class TestExplicitDevelopmentIntakeContract:
    """Pin the B3 adapter contract as P7's conversational dev entry point."""

    def test_clear_dev_request_maps_to_need(self):
        need = task_spec_to_development_need(
            _spec("add a new capability to Atlas for scheduling so that tasks run on time")
        )
        assert need is not None
        assert need.title
        assert need.summary
        assert need.candidate_id  # == task_id

    def test_non_dev_types_refused(self):
        for text in (
            "hello Atlas how are you",
            "what does this module do?",
            "find the latest research on memory consolidation",
            "create a report of the last week",
        ):
            assert task_spec_to_development_need(_spec(text)) is None, text

    def test_none_and_unknown_refused(self):
        assert task_spec_to_development_need(None) is None
        assert task_spec_to_development_need(_spec("...")) is None

    def test_under_specified_dev_request_gated(self):
        spec = _spec("improve this module")
        assert is_development_request(spec)
        assert _needs_clarification(spec)
        assert task_spec_to_development_need(spec) is None
        questions = clarification_questions(spec)
        assert questions
        assert all(isinstance(q, str) for q in questions)

    def test_no_fabricated_code_changes(self):
        """The adapter must never fabricate code_changes / test_files; the
        deterministic supplier therefore fails closed without external input."""
        need = task_spec_to_development_need(
            _spec("add a new capability to Atlas for scheduling")
        )
        assert need is not None
        assert "code_changes" not in need.metadata
        assert "test_files" not in need.metadata


# ---------------------------------------------------------------------------
# Contract 4 — Confirmation-gate invariant (P7.3 forward requirement)
# ---------------------------------------------------------------------------


class TestConfirmationGateContract:
    """P7.3 MUST add an explicit confirmation step before an unrequested
    capability-gap or advisory suggestion can become a development proposal.
    Today no such path exists; these tests pin the safety invariant the gate
    must preserve (no proposal without an explicit, clarified dev request)."""

    def test_P7_3_capability_gap_requires_confirmation_before_proposal(self):
        """Forward requirement: a detected capability gap must not produce a
        governed proposal without explicit user confirmation. Today the
        invariant holds because no path reaches F9 from a gap signal."""
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        service = _service(dev_bridge=bridge, orchestration_resolver=lambda s, ctx: None)
        resp = service.send("run the quantum stabilizer diagnostic")
        bridge.assert_not_called()
        assert "PENDING_APPROVAL" not in resp.content
        assert "Proposal ID" not in resp.content

    def test_P7_3_advisory_suggestion_requires_confirmation_before_proposal(self):
        """Forward requirement: an advisory suggestion must not auto-propose
        governed development. Today advisory text is ordinary conversation."""
        bridge = MagicMock(return_value=Message(role="assistant", content="DEV"))
        service = _service(dev_bridge=bridge)
        resp = service.send(
            "the advisory suggests reviewing provider reliability via inspection"
        )
        bridge.assert_not_called()
        assert "PENDING_APPROVAL" not in resp.content

    def test_P7_3_explicit_dev_request_still_reaches_bridge(self):
        """The confirmation gate must not block an explicit, fully-specified
        development request from reaching the governed preparation path."""
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        service = _service(dev_bridge=bridge)
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time"
        )
        bridge.assert_called_once()
        assert resp.content == "PREPARED"


# ---------------------------------------------------------------------------
# Contract 5 — F9 stop-at-approval conversational boundary
# ---------------------------------------------------------------------------


class TestF9StopAtApprovalContract:
    """A conversational development request reaches F9 and STOPS at
    PENDING_APPROVAL: it must not auto-approve, execute, or promote."""

    def test_conversational_dev_need_stops_at_pending_approval(self):
        need = task_spec_to_development_need(
            _spec(
                "add a new capability to Atlas for scheduling so that tasks run on time"
            )
        )
        assert need is not None
        spy = _SpyApprovalManager()
        controller = DevelopmentCycleController(
            approval_manager=spy,
            change_supplier=_ConcreteSupplier(),
            researcher=lambda **kwargs: _FakeAcquisition(),
        )
        result = controller.run_development_cycle(need)

        assert result.ok
        assert result.decision == "prepared"
        assert result.proposal_status == "PENDING_APPROVAL"
        assert result.proposal_id.startswith("DEV-")
        assert result.approval_request_id.startswith("APPR-")
        # The ONLY lifecycle call is submission; never approve/reject.
        assert spy.calls == ["create_approval_request"]

    def test_f9_never_approves_executes_or_promotes(self):
        need = task_spec_to_development_need(
            _spec("implement a bounded retry policy for outbound calls")
        )
        spy = _SpyApprovalManager()
        controller = DevelopmentCycleController(
            approval_manager=spy,
            change_supplier=_ConcreteSupplier(),
            researcher=lambda **kwargs: _FakeAcquisition(),
        )
        controller.run_development_cycle(need)
        assert "approve" not in spy.calls
        assert "reject" not in spy.calls

    def test_explicit_dev_reaches_bridge_through_service(self):
        """End-to-end conversation seam: an explicit dev request is routed to
        the injected development bridge (the F9 gateway)."""
        bridge = MagicMock(return_value=Message(role="assistant", content="PREPARED"))
        service = _service(dev_bridge=bridge)
        resp = service.send(
            "add a new capability to Atlas for scheduling so that tasks run on time"
        )
        assert bridge.call_count == 1
        spec = bridge.call_args[0][0]
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert resp.content == "PREPARED"


# ---------------------------------------------------------------------------
# Contract 6 — Session / provenance retention at the conversation seam
# ---------------------------------------------------------------------------


class TestSessionProvenanceContract:
    """A conversational development request must retain the SessionContext /
    provenance available at the conversation seam."""

    def test_dev_bridge_receives_user_session_attribution(self):
        ctx = _session_context(owner=False, user_id="alice")
        captured: dict = {}

        def bridge(spec):
            captured["spec"] = spec
            return Message(role="assistant", content="ok")

        service = _service(dev_bridge=bridge, session=ctx)
        service.send("add a new capability to Atlas for scheduling")

        spec = captured["spec"]
        assert spec.context["principal_id"] == "alice"
        assert spec.context["authority"] == "user"
        assert spec.context["session_id"] == ctx.session_id

    def test_dev_bridge_receives_owner_session_attribution(self):
        ctx = _session_context(owner=True)
        captured: dict = {}

        def bridge(spec):
            captured["spec"] = spec
            return Message(role="assistant", content="ok")

        service = _service(dev_bridge=bridge, session=ctx)
        service.send("add a new capability to Atlas for scheduling")

        spec = captured["spec"]
        assert spec.context["principal_id"] == "owner"
        assert spec.context["authority"] == "owner"
        assert spec.context["session_id"] == ctx.session_id

    def test_user_authority_not_elevated_to_owner(self):
        ctx = _session_context(owner=False, user_id="alice")
        captured: dict = {}

        def bridge(spec):
            captured["spec"] = spec
            return Message(role="assistant", content="ok")

        service = _service(dev_bridge=bridge, session=ctx)
        service.send("add a new capability to Atlas for scheduling")

        assert captured["spec"].context["authority"] == "user"


# ---------------------------------------------------------------------------
# Contract 7 — Advisory-only isolation
# ---------------------------------------------------------------------------


class TestAdvisoryOnlyContract:
    """Advisory signals are suggestions only; they must never drive governed
    development execution, approval, sandboxing, or promotion."""

    def test_advisor_has_no_dev_execution_surface(self):
        advisor = ProactiveAdvisor()
        for attr in (
            "execution_gateway",
            "application_engine",
            "approval_manager",
            "rule_engine",
            "dispatcher",
            "tool_executor",
            "development_controller",
            "planner",
            "promotion_gate",
            "tick",
        ):
            assert not hasattr(advisor, attr), f"advisor unexpectedly has {attr}"

    def test_advisory_run_never_touches_dev_machinery(self):
        advisor = ProactiveAdvisor()
        report = advisor.run_advisory(principal_id="alice")
        # No sources configured -> empty report; crucially, no proposal created.
        assert report.count == 0
        assert report.items == ()

    def test_advisory_module_imports_no_dev_machinery(self):
        """Structural guarantee: the advisory package cannot reach governed
        development execution directly."""
        root = pathlib.Path(__file__).resolve().parents[1]
        advisory_dir = root / "atlas" / "advisory"
        forbidden = (
            "atlas.evolution.development_cycle",
            "atlas.evolution.approval_manager",
            "atlas.evolution.development_planner",
            "atlas.evolution.self_development_loop",
            "atlas.evolution.promotion_gate",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.autonomy",
            "atlas.kernel",
        )
        for path in sorted(advisory_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = getattr(node, "module", None)
                if module and module.startswith(forbidden):
                    raise AssertionError(
                        f"{path} imports dev machinery: {module}"
                    )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden):
                            raise AssertionError(
                                f"{path} imports dev machinery: {alias.name}"
                            )


# ---------------------------------------------------------------------------
# Contract 8 — Tick safety
# ---------------------------------------------------------------------------


class TestTickSafetyContract:
    """Development execution MUST NOT be added to Atlas.tick()."""

    def test_tick_contains_no_development_execution(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        forbidden = (
            "run_development_cycle",
            "_development_bridge",
            "run_development_execution",
            "confirm_development_approval",
            "submit_development_for_promotion_review",
            "DevelopmentPlanner",
            "SelfDevelopmentLoop",
            "PromotionGate",
        )
        for marker in forbidden:
            assert marker not in tick_src, f"tick() must not reference {marker}"


# ---------------------------------------------------------------------------
# Contract 9 — Dependency direction
# ---------------------------------------------------------------------------


class TestDependencyDirectionContract:
    """The conversation layer must route through the injected kernel seam and
    must NOT import evolution execution machinery directly."""

    def test_conversation_imports_no_evolution_execution_machinery(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        conv_dir = root / "atlas" / "conversation"
        # Execution machinery the conversation layer must NOT import directly.
        forbidden = (
            "atlas.evolution.autonomy",
            "atlas.evolution.approval_manager",
            "atlas.evolution.development_planner",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.governance",
            "atlas.evolution.model_assisted_supplier",
            "atlas.evolution.promotion_gate",
            "atlas.evolution.self_development_loop",
        )
        # Allowed data-type seams the conversation layer may import.
        allowed = (
            "atlas.evolution.development_cycle",
            "atlas.evolution.models",
        )

        def _violates(module: str) -> bool:
            if module in allowed or any(module == a or module.startswith(a + ".") for a in allowed):
                return False
            return any(module == f or module.startswith(f + ".") for f in forbidden)

        violations: list[str] = []
        for path in sorted(conv_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = getattr(node, "module", None)
                if module and _violates(module):
                    violations.append(f"{path.relative_to(root)}: {module}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if _violates(alias.name):
                            violations.append(
                                f"{path.relative_to(root)}: {alias.name}"
                            )
        assert violations == [], f"conversation imports exec machinery: {violations}"
