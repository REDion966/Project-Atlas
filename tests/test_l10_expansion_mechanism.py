"""L10 — evidence-driven expansion: validation of the EXISTING mechanism.

L10 asked whether Atlas already has enough infrastructure to close the loop

    observe language evidence -> identify a gap -> investigate -> determine the
    owner -> propose a bounded improvement -> verify -> govern/approve ->
    activate -> retain evidence -> use the improved capability

without inventing new architecture. The investigation found that the loop
already exists and is live: the P7.4 development-need path turns a *language*
observation (a well-specified ACTION request whose target cannot be resolved,
or a repeated clarification loop) into a bounded, provenance-carrying
detection record, requires an explicit human confirmation, and only then hands
a ``DEVELOPMENT_REQUEST`` to the EXISTING governed development route that owns
proposal -> approval -> sandbox verification -> promotion/rollback.

This suite validates that mechanism rather than adding to it. It does NOT
duplicate the Phase 16 governance suites (``tests/test_evolution_autonomy_*``),
which already cover validation/authorization/appliers/rollback, nor the
vocabulary-expansion suite (``tests/test_l10_evidence_driven_expansion.py``),
which covers the three committed recognition expansions. It pins the *linkage*
between language evidence and the governed route, the fail-closed boundaries
that make the loop safe, and the one thing that does not exist today (a
declarative language-rule surface).

L10 adds no production code.
"""

from __future__ import annotations

import ast
import inspect
import json
from types import SimpleNamespace

import pytest

from atlas.authority.models import AuthorityLevel, Principal
from atlas.conversation import development_need_detector as detector_module
from atlas.conversation import development_need_dialogue as dialogue_module
from atlas.conversation import development_need_router as router_module
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.development_need_detector import (
    AdvisorySignal,
    DevelopmentNeedDetector,
    DevelopmentSignalKind,
)
from atlas.conversation.development_need_dialogue import (
    ConfirmationStatus,
    DevelopmentNeedDialogue,
)
from atlas.conversation.development_need_router import explicit_intent_to_task_spec
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.evolution.autonomy.validator import EvolutionValidator
from atlas.evolution.governance.models import ScopeType
from atlas.session.context import SessionContext
from atlas.session.models import Session

#: Language observation whose target cannot be resolved to a capability.
UNRESOLVED_ACTION = "Create a task for backing up the database."

#: Language observations that must never produce a development signal.
NON_ACTION_OBSERVATIONS = (
    "Investigate why Atlas cannot answer this question.",
    "Research how Atlas handles references.",
    "What does Atlas do?",
    "Hello Atlas.",
    "Build a capability for scheduled follow-ups.",
    "Run this.",
)

ALLOWED_SIGNALS = frozenset({"unresolved_action", "capability_gap",
                             "repeated_clarification", "advisory_opportunity"})

RECORD_KEYS = frozenset({"signal_kind", "reason", "evidence", "capability",
                         "principal_id", "authority", "session_id"})


def _context(session_id: str = "sess-l10", principal_id: str = "operator",
             authority: AuthorityLevel = AuthorityLevel.OWNER) -> SessionContext:
    session = Session(
        session_id=session_id,
        principal=Principal(principal_id=principal_id, name="Operator",
                            authority=authority),
    )
    return SessionContext(session=session)


def _spec(text: str, context: SessionContext | None = None) -> TaskSpec:
    """Intake a real utterance, attached to a session exactly as production does."""
    spec = TaskIntake().intake(text)
    if context is not None:
        spec = ConversationService._attach_session_to_spec(spec, context)
    return spec


class _Cognition:
    """Fails if cognition is entered (these paths must never reach it)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def process(self, *args, **kwargs):
        self.calls.append("process")
        raise AssertionError("cognition must not be entered on a governed turn")


def _service(context, *, coordinator=None):
    """A service wired like the kernel; records any development-bridge hand-off."""
    bridge: list[TaskSpec] = []

    def _dev_bridge(spec):
        bridge.append(spec)
        return Message(role="assistant", content="DEVELOPMENT", metadata={})

    cognition = _Cognition()
    service = ConversationService(
        None,
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        cognition_api=cognition,
        orchestration_resolver=lambda spec, session_context: None,
        development_bridge=_dev_bridge,
        development_need_coordinator=coordinator,
        session_context=context,
    )
    return service, bridge, cognition


class TestEvidenceCapture:
    """Step 1 of the loop: observed language evidence becomes a bounded record."""

    def test_unresolved_action_is_detected_with_provenance(self):
        context = _context()
        spec = _spec(UNRESOLVED_ACTION, context)
        need = DevelopmentNeedDetector().detect(spec, resolution=False)

        assert need is not None
        assert need.signal_kind == DevelopmentSignalKind.UNRESOLVED_ACTION.value
        assert need.signal_kind in ALLOWED_SIGNALS
        # The evidence is the LANGUAGE-derived intent, not a synthesized string.
        assert need.evidence == (spec.intent,)
        assert need.capability == spec.intent
        assert need.session_id == context.session_id
        assert need.principal_id == context.principal_id
        assert need.authority == context.authority.value
        json.dumps(need.to_dict())
        # The detection record carries no lifecycle/approval/execution state.
        assert frozenset(need.to_dict()) == RECORD_KEYS

    def test_named_missing_capability_is_classified_as_a_capability_gap(self):
        spec = _spec(UNRESOLVED_ACTION, _context())
        need = DevelopmentNeedDetector().detect(
            spec, resolution=False, missing_capability="email_notifications"
        )
        assert need is not None
        assert need.signal_kind == DevelopmentSignalKind.CAPABILITY_GAP.value
        assert need.capability == "email_notifications"
        assert need.evidence == ("email_notifications",)

    def test_repeated_clarification_requires_the_threshold(self):
        spec = _spec("Run this.")
        assert spec.task_type is TaskType.ACTION_REQUEST
        assert spec.needs_clarification is True
        detector = DevelopmentNeedDetector()
        assert detector.detect(spec, clarification_count=1) is None
        repeated = detector.detect(spec, clarification_count=2)
        assert repeated is not None
        assert repeated.signal_kind == DevelopmentSignalKind.REPEATED_CLARIFICATION.value

    def test_missing_resolution_signal_fails_closed(self):
        spec = _spec(UNRESOLVED_ACTION, _context())
        assert DevelopmentNeedDetector().detect(spec, resolution=None) is None
        assert DevelopmentNeedDetector().detect(spec, resolution=True) is None

    @pytest.mark.parametrize("text", NON_ACTION_OBSERVATIONS)
    def test_non_action_language_never_produces_a_development_signal(self, text):
        spec = _spec(text, _context())
        assert DevelopmentNeedDetector().detect(spec, resolution=False) is None

    def test_explicit_development_requests_are_never_duplicated(self):
        # Explicit development already has its own governed route (B3 intake).
        spec = _spec("Build a capability for scheduled follow-ups.", _context())
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert DevelopmentNeedDetector().detect(spec, resolution=False) is None

    def test_detector_is_side_effect_free_and_repeatable(self):
        detector = DevelopmentNeedDetector()
        spec = _spec(UNRESOLVED_ACTION, _context())
        first = detector.detect(spec, resolution=False)
        second = detector.detect(spec, resolution=False)
        assert first == second
        assert first.to_dict() == second.to_dict()


class TestConfirmationBoundary:
    """Step 2: nothing is proposed without an explicit, bound human confirmation."""

    def test_ambiguous_and_empty_replies_never_confirm(self):
        dialogue = DevelopmentNeedDialogue()
        need = DevelopmentNeedDetector().detect(
            _spec(UNRESOLVED_ACTION, _context()), resolution=False
        )
        for reply in ("", "   ", "can you tell me more?", "yes, but not really",
                      "why do you ask?"):
            assert dialogue.interpret_confirmation(reply, need) is (
                ConfirmationStatus.AMBIGUOUS
            ), reply

    def test_explicit_affirmative_and_negative_are_distinguished(self):
        dialogue = DevelopmentNeedDialogue()
        need = DevelopmentNeedDetector().detect(
            _spec(UNRESOLVED_ACTION, _context()), resolution=False
        )
        assert dialogue.interpret_confirmation("yes please", need) is (
            ConfirmationStatus.CONFIRMED
        )
        assert dialogue.interpret_confirmation("no thanks", need) is (
            ConfirmationStatus.DENIED
        )
        assert dialogue.interpret_confirmation("yes", None) is (
            ConfirmationStatus.NO_PENDING_CONTEXT
        )

    def test_denial_leaves_no_pending_state_and_no_hand_off(self):
        coordinator = DevelopmentNeedCoordinator()
        context = _context()
        coordinator.detect_unresolved_action(_spec(UNRESOLVED_ACTION, context))
        assert coordinator.has_pending is True
        outcome = coordinator.handle_reply("no", context)
        assert isinstance(outcome, Message)
        assert outcome.metadata["development_need_dialogue"]["status"] == "denied"
        assert coordinator.has_pending is False
        assert coordinator.handle_reply("yes", context) is None

    def test_confirmation_requires_the_matching_session(self):
        coordinator = DevelopmentNeedCoordinator()
        owner = _context(session_id="sess-a", principal_id="operator")
        other = _context(session_id="sess-b", principal_id="operator")
        coordinator.detect_unresolved_action(_spec(UNRESOLVED_ACTION, owner))
        # A different session cannot confirm: fail-closed, pending is retained.
        assert coordinator.handle_reply("yes", other) is None
        assert coordinator.has_pending is True
        # The bound session still can.
        outcome = coordinator.handle_reply("yes", owner)
        assert isinstance(outcome, TaskSpec)
        assert coordinator.has_pending is False

    def test_advisory_cannot_elevate_identity(self):
        coordinator = DevelopmentNeedCoordinator()
        user = _context(session_id="sess-u", principal_id="user-1",
                        authority=AuthorityLevel.USER)
        advisory = AdvisorySignal(
            kind="improvement",
            summary="Add a capability.",
            suggested_action="atlas.run_development_cycle",
            evidence_ids=("E-1",),
            principal_id="forged-owner",
            authority=AuthorityLevel.OWNER.value,
        )
        message = coordinator.advisory_input(advisory, user)
        assert message is not None
        pending = coordinator._pending  # noqa: SLF001 - governance assertion
        assert pending.principal_id == "user-1"
        assert pending.authority == AuthorityLevel.USER.value
        assert coordinator.handle_reply("yes", user) is not None

    def test_unsupported_advisory_action_fails_closed(self):
        coordinator = DevelopmentNeedCoordinator()
        advisory = AdvisorySignal(suggested_action="atlas.delete_everything")
        assert coordinator.advisory_input(advisory, _context()) is None
        assert coordinator.has_pending is False


class TestBoundedProposal:
    """Step 3: a confirmed detection becomes a bounded request, not a change."""

    def test_confirmed_intent_becomes_a_development_request(self):
        need = DevelopmentNeedDetector().detect(
            _spec(UNRESOLVED_ACTION, _context()), resolution=False
        )
        intent = DevelopmentNeedDialogue().build_intent(need)
        spec = explicit_intent_to_task_spec(intent)

        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.needs_clarification is False
        assert spec.source == "development_need_dialogue"
        assert spec.context["source"] == "development_need_dialogue"
        assert spec.context["signal_kind"] == "unresolved_action"
        assert spec.context["session_id"] == "sess-l10"
        assert spec.context["principal_id"] == "operator"
        assert spec.context["authority"] == AuthorityLevel.OWNER.value
        assert spec.success_criteria

    def test_handoff_fabricates_no_code_changes_or_approval_state(self):
        need = DevelopmentNeedDetector().detect(
            _spec(UNRESOLVED_ACTION, _context()), resolution=False
        )
        spec = explicit_intent_to_task_spec(DevelopmentNeedDialogue().build_intent(need))
        assert "code_changes" not in spec.context
        assert "test_files" not in spec.context
        for forbidden in ("approval", "proposal_id", "sandbox", "promotion",
                          "execution", "status"):
            assert forbidden not in spec.context, forbidden


class TestProductionPathLoop:
    """The loop as actually reached through ConversationService.send()."""

    def test_unresolved_language_request_asks_then_proposes_governed_development(self):
        context = _context()
        service, bridge, cognition = _service(
            context, coordinator=DevelopmentNeedCoordinator()
        )

        asked = service.send(UNRESOLVED_ACTION)
        pending = asked.metadata["development_need_dialogue"]
        assert pending["status"] == "awaiting_confirmation"
        assert pending["signal_kind"] == "unresolved_action"
        assert "yes or no" in asked.content
        assert bridge == []
        assert cognition.calls == []

        confirmed = service.send("yes")
        assert len(bridge) == 1
        handed = bridge[0]
        assert handed.task_type is TaskType.DEVELOPMENT_REQUEST
        assert handed.context["source"] == "development_need_dialogue"
        assert handed.context["signal_kind"] == "unresolved_action"
        assert confirmed.content
        assert cognition.calls == []

    def test_language_evidence_is_the_real_intake_intent(self):
        context = _context()
        service, bridge, _cognition = _service(
            context, coordinator=DevelopmentNeedCoordinator()
        )
        service.send(UNRESOLVED_ACTION)
        service.send("yes")
        expected = TaskIntake().intake(UNRESOLVED_ACTION)
        assert expected.intent == UNRESOLVED_ACTION
        assert bridge[0].intent.startswith("Add or improve capability:")

    def test_denial_and_ambiguity_never_reach_the_development_bridge(self):
        context = _context()
        service, bridge, _cognition = _service(
            context, coordinator=DevelopmentNeedCoordinator()
        )
        service.send(UNRESOLVED_ACTION)
        ambiguous = service.send("what would that involve?")
        assert ambiguous.metadata["development_need_dialogue"]["status"] == "re_asking"
        assert bridge == []
        denied = service.send("no")
        assert denied.metadata["development_need_dialogue"]["status"] == "denied"
        assert bridge == []

    def test_without_a_coordinator_the_existing_clarification_is_unchanged(self):
        service, bridge, cognition = _service(_context(), coordinator=None)
        message = service.send(UNRESOLVED_ACTION)
        assert "development_need_dialogue" not in message.metadata
        assert "more detail" in message.content
        assert bridge == []
        assert cognition.calls == []


class TestGovernanceBoundary:
    """Activation remains gated, and language rules are not a data surface."""

    @pytest.mark.parametrize("scope", [ScopeType.CODE, ScopeType.IDENTITY,
                                       ScopeType.UNKNOWN])
    def test_non_state_scopes_are_rejected_by_the_governed_rail(self, scope):
        report = EvolutionValidator().validate(SimpleNamespace(target_scope=scope))
        assert report.valid is False
        assert report.violations

    def test_language_cue_families_are_not_runtime_injectable(self):
        """Documents the L10 boundary: language behaviour is code-owned today.

        A language expansion therefore travels the GOVERNED development/code
        rail (proposal -> approval -> sandbox -> promotion), not a data file:
        there is no constructor parameter, config section or registry through
        which a cue/pattern/vocabulary could be supplied at runtime.
        """
        import atlas.conversation.task_intake as task_intake

        forbidden = ("cue", "pattern", "vocab", "lexicon", "synonym",
                     "intent_rules", "rules")
        for target in (TaskIntake.__init__, BuiltinResponseService.__init__):
            names = [
                name for name in inspect.signature(target).parameters
                if name != "self"
            ]
            assert not [
                name for name in names
                if any(token in name.lower() for token in forbidden)
            ], (target, names)
        assert isinstance(task_intake._DEVELOPMENT_CUE_FORMS, frozenset)  # noqa: SLF001

    def test_loop_modules_are_provider_free(self):
        """The loop is pure: no AI provider, no network, no filesystem."""
        forbidden = ("atlas.ai", "openai", "anthropic", "requests", "urllib",
                     "socket", "http.client", "subprocess")
        for module in (detector_module, dialogue_module, router_module):
            tree = ast.parse(inspect.getsource(module))
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            for name in imported:
                assert not any(
                    name == bad or name.startswith(bad + ".")
                    for bad in forbidden
                ), (module.__name__, name)


class TestDeterminism:
    def _chain(self) -> dict:
        context = _context()
        coordinator = DevelopmentNeedCoordinator()
        coordinator.detect_unresolved_action(_spec(UNRESOLVED_ACTION, context))
        spec = coordinator.handle_reply("yes", context)
        payload = spec.to_dict()
        payload.pop("created_at", None)
        return payload

    def test_loop_is_deterministic(self):
        assert self._chain() == self._chain()

    def test_detection_record_is_deterministic(self):
        need = DevelopmentNeedDetector().detect(
            _spec(UNRESOLVED_ACTION, _context()), resolution=False
        )
        again = DevelopmentNeedDetector().detect(
            _spec(UNRESOLVED_ACTION, _context()), resolution=False
        )
        assert need.to_dict() == again.to_dict()
