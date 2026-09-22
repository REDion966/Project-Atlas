"""L5 — contextual meaning & multi-turn interpretation tests (no provider).

Validated gap: an explicitly established subject
(``ConversationState.current_subject``, recorded deterministically by the L4
entity identification of an earlier turn) was not carried forward into the
bounded multi-turn follow-up paths:

  * bare contextual references — "Tell me more about it.", "What about that?";
  * conversational topic recall — "What were we talking about?".

Both paths are fixed by consulting the established subject as a bounded,
lower-precedence, last-resort candidate source: every previously resolving case
keeps precedence, every insufficient-context case still fails closed, and
nothing is guessed.

All tests are pure/deterministic. No provider network calls are made.
"""

from __future__ import annotations

import json
import unittest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import build_conversation_context
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import (
    ConversationState,
    ConversationStateManager,
)
from atlas.conversation.entity_identification import (
    IDENTIFIED_ENTITIES_KEY,
    EntityCatalog,
)
from atlas.conversation.message import Message
from atlas.conversation.reference_resolution import (
    ConversationReferenceResolver,
    ReferenceResolutionStatus,
)
from atlas.conversation.task_intake import _AMBIGUITY_WEIGHTS, TaskIntake
from atlas.conversation.turn_meaning import TurnMeaning, build_turn_meaning

SUBJECT = "code_inspector"
FOLLOW_UP = "Tell me more about it."

CATALOG = EntityCatalog.from_names(
    {"capability": ["code_inspector"], "tool": ["workspace_search"]}
)

EMPTY_CONTEXT = build_conversation_context([])

RESOLVED_SUBJECT_EVIDENCE = {"field": "current_subject", "value": SUBJECT}


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


def _service(catalog: EntityCatalog | None = CATALOG) -> ConversationService:
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        entity_catalog=catalog,
    )


def _spy(service: ConversationService) -> list:
    """Capture ``(context_dict, response)`` for every resolution call."""
    calls: list = []
    original = service._apply_reference_resolution

    def wrapper(spec, text):
        out_spec, response = original(spec, text)
        calls.append((dict(out_spec.context or {}), response))
        return out_spec, response

    service._apply_reference_resolution = wrapper
    return calls


def _evidence(service: ConversationService, text: str):
    """Return the reference evidence attached for ``text`` on current state."""
    spec = service._intake(text, len(service.conversation.messages))
    spec = service._apply_entity_identification(spec, text)
    out_spec, _ = service._apply_reference_resolution(spec, text)
    return out_spec.context.get("resolved_reference")


class TestEstablishedSubjectContextualResolution(unittest.TestCase):
    """Contextual resolution against the explicitly established subject."""

    def setUp(self):
        self.resolver = ConversationReferenceResolver()

    def _resolve(self, text, state=None, context=None):
        return self.resolver.resolve_contextual(
            text,
            EMPTY_CONTEXT if context is None else context,
            ConversationState(current_subject=SUBJECT) if state is None else state,
        )

    def test_bare_pronoun_followups_resolve_to_established_subject(self):
        for text in (
            FOLLOW_UP,
            "What about that?",
            "Is this ready?",
            "Can you check it?",
        ):
            with self.subTest(text=text):
                result = self._resolve(text)
                self.assertIs(result.status, ReferenceResolutionStatus.RESOLVED)
                self.assertEqual(result.resolved_field, "current_subject")
                self.assertEqual(result.resolved_value, SUBJECT)

    def test_explicit_phrase_resolves_to_established_subject(self):
        result = self._resolve("What about the code_inspector?")
        self.assertIs(result.status, ReferenceResolutionStatus.RESOLVED)
        self.assertEqual(result.resolved_field, "current_subject")
        self.assertEqual(result.resolved_value, SUBJECT)

    def test_context_absent_still_fails_closed(self):
        for text in (FOLLOW_UP, "What about that?", "Is this ready?"):
            with self.subTest(text=text):
                result = self._resolve(text, state=ConversationState())
                self.assertIs(result.status, ReferenceResolutionStatus.UNRESOLVED)

    def test_investigation_state_keeps_precedence(self):
        state = ConversationState(
            current_subject=SUBJECT, current_investigation="memory architecture"
        )
        result = self._resolve(FOLLOW_UP, state=state)
        self.assertIs(result.status, ReferenceResolutionStatus.RESOLVED)
        # The investigation subject is a STORED state fact, so it is reported
        # under its real field name (consumable); the derived
        # ``context_subject`` label remains for turn-derived referents only.
        self.assertEqual(result.resolved_field, "current_investigation")
        self.assertEqual(result.resolved_value, "memory architecture")

    def test_turn_context_candidate_keeps_precedence(self):
        context = build_conversation_context(
            [
                Message(role="user", content="Investigate the memory architecture."),
                Message(role="assistant", content="ok"),
            ]
        )
        result = self._resolve(FOLLOW_UP, context=context)
        self.assertIs(result.status, ReferenceResolutionStatus.RESOLVED)
        self.assertEqual(result.resolved_field, "context_subject")

    def test_insufficient_subject_fails_closed(self):
        for subject in ("", "   ", None, 42):
            with self.subTest(subject=subject):
                result = self._resolve(
                    FOLLOW_UP, state=ConversationState(current_subject=subject)
                )
                self.assertIs(result.status, ReferenceResolutionStatus.UNRESOLVED)

    def test_self_reference_does_not_resolve(self):
        result = self._resolve(SUBJECT)
        self.assertIs(result.status, ReferenceResolutionStatus.UNRESOLVED)

    def test_unrelated_turns_are_unaffected(self):
        for text in (
            "How is the quality of the output?",
            "We voted against the rule.",
            "What happened yesterday?",
            "Please summarise the repository structure.",
        ):
            with self.subTest(text=text):
                result = self._resolve(text)
                self.assertIs(result.status, ReferenceResolutionStatus.UNRESOLVED)

    def test_resolution_is_deterministic(self):
        first = self._resolve(FOLLOW_UP)
        for _ in range(20):
            self.assertEqual(self._resolve(FOLLOW_UP), first)

    def test_state_is_not_mutated(self):
        manager = ConversationStateManager()
        manager.update(current_subject=SUBJECT)
        state = manager.state
        self.resolver.resolve_contextual(FOLLOW_UP, EMPTY_CONTEXT, state)
        self.assertIs(manager.state, state)
        self.assertEqual(manager.state.current_subject, SUBJECT)


class TestSubjectCarryAcrossTurns(unittest.TestCase):
    """End-to-end carry-forward from an entity turn into a follow-up turn."""

    def test_followup_resolves_after_an_entity_turn(self):
        service = _service()
        service.send("What does code_inspector do?")
        self.assertEqual(service.state_manager.state.current_subject, SUBJECT)
        self.assertEqual(_evidence(service, FOLLOW_UP), RESOLVED_SUBJECT_EVIDENCE)

    def test_context_absent_followup_is_unchanged(self):
        service = _service(catalog=None)
        service.send("What does code_inspector do?")
        self.assertIsNone(service.state_manager.state.current_subject)
        self.assertIsNone(_evidence(service, FOLLOW_UP))

    def test_multi_entity_turn_carries_no_subject(self):
        service = _service()
        service.send("compare code_inspector and workspace_search")
        self.assertIsNone(service.state_manager.state.current_subject)
        self.assertIsNone(_evidence(service, FOLLOW_UP))

    def test_send_and_stream_attach_the_same_evidence(self):
        for streamed in (False, True):
            with self.subTest(streamed=streamed):
                service = _service()
                service.send("What does code_inspector do?")
                calls = _spy(service)
                if streamed:
                    content = "".join(service.stream(FOLLOW_UP))
                else:
                    content = service.send(FOLLOW_UP).content
                self.assertTrue(content)
                self.assertTrue(calls, "resolution must run on both paths")
                self.assertEqual(
                    calls[0][0].get("resolved_reference"), RESOLVED_SUBJECT_EVIDENCE
                )
                self.assertIsNone(
                    calls[0][1], "a RESOLVED follow-up must not clarify"
                )

    def test_followup_does_not_change_routing(self):
        service = _service()
        service.send("What does code_inspector do?")
        spec = service._intake(FOLLOW_UP, len(service.conversation.messages))
        spec = service._apply_entity_identification(spec, FOLLOW_UP)
        out_spec, response = service._apply_reference_resolution(spec, FOLLOW_UP)
        self.assertIs(out_spec.task_type, spec.task_type)
        self.assertEqual(out_spec.intent, spec.intent)
        self.assertEqual(out_spec.needs_clarification, spec.needs_clarification)
        self.assertEqual(out_spec.confidence, spec.confidence)
        self.assertIsNone(response)
        self.assertEqual(
            out_spec.context["resolved_reference"], RESOLVED_SUBJECT_EVIDENCE
        )

    def test_repeated_turns_are_deterministic(self):
        outcomes = set()
        for _ in range(10):
            service = _service()
            service.send("What does code_inspector do?")
            outcomes.add(json.dumps(_evidence(service, FOLLOW_UP), sort_keys=True))
            outcomes.add(service.send("What were we talking about?").content)
        self.assertEqual(len(outcomes), 2)


class TestTopicRecallUsesEstablishedSubject(unittest.TestCase):
    """The bounded recall path reports the carried-forward subject."""

    def setUp(self):
        self.svc = BuiltinResponseService()

    def _respond(self, text, state, history=()):
        messages = [
            Message(role=role, content=content) for role, content in history
        ]
        messages.append(Message(role="user", content=text))
        return self.svc.respond(
            text, context=build_conversation_context(messages, state)
        )

    def test_topic_recall_reports_the_established_subject(self):
        message = self._respond(
            "What were we talking about?", ConversationState(current_subject=SUBJECT)
        )
        self.assertEqual(message.metadata["builtin_intent"], "conversation_recall")
        self.assertEqual(message.metadata["recall_source"], "topic")
        self.assertIn(SUBJECT, message.content)
        self.assertFalse(message.metadata.get("model_used"))

    def test_investigation_precedence_unchanged(self):
        message = self._respond(
            "What were we talking about?",
            ConversationState(
                current_subject=SUBJECT, current_investigation="memory architecture"
            ),
        )
        self.assertIn("memory architecture", message.content)
        self.assertNotIn(SUBJECT, message.content)

    def test_lead_cue_turn_precedence_unchanged(self):
        message = self._respond(
            "What were we talking about?",
            ConversationState(current_subject=SUBJECT),
            history=(
                ("user", "Investigate the conversation system."),
                ("assistant", "ok"),
            ),
        )
        self.assertIn("Investigate the conversation system.", message.content)
        self.assertNotIn(SUBJECT, message.content)

    def test_insufficient_context_still_fails_honestly(self):
        message = self._respond("What were we talking about?", ConversationState())
        self.assertNotEqual(
            message.metadata.get("builtin_intent"), "conversation_recall"
        )
        self.assertNotIn(SUBJECT, message.content)

    def test_recall_does_not_mutate_context(self):
        messages = [Message(role="user", content="What were we talking about?")]
        context = build_conversation_context(
            messages, ConversationState(current_subject=SUBJECT)
        )
        before = context.to_dict()
        self.svc.respond("What were we talking about?", context=context)
        self.assertEqual(context.to_dict(), before)


class TestContractPreservation(unittest.TestCase):
    """L1–L4 contracts are unchanged by the carry-forward."""

    def setUp(self):
        self.service = _service()
        self.service.send("What does code_inspector do?")
        self.text = FOLLOW_UP
        self.spec = self.service._intake(
            self.text, len(self.service.conversation.messages)
        )
        self.identified = self.service._apply_entity_identification(
            self.spec, self.text
        )
        self.out_spec, _ = self.service._apply_reference_resolution(
            self.identified, self.text
        )

    def test_l4_identification_is_unchanged_on_a_followup(self):
        """A follow-up names no catalog entity, so L4 attaches no entity evidence."""
        self.assertNotIn(IDENTIFIED_ENTITIES_KEY, self.out_spec.context)
        self.assertEqual(
            self.out_spec.context["resolved_reference"], RESOLVED_SUBJECT_EVIDENCE
        )

    def test_l4_evidence_still_attaches_when_an_entity_is_named(self):
        service = _service()
        text = "Tell me more about code_inspector in this topic"
        spec = service._intake(text, 1)
        spec = service._apply_entity_identification(spec, text)
        self.assertEqual(
            spec.context[IDENTIFIED_ENTITIES_KEY],
            [{"name": "code_inspector", "kind": "capability"}],
        )
        out_spec, _ = service._apply_reference_resolution(spec, text)
        self.assertEqual(
            out_spec.context[IDENTIFIED_ENTITIES_KEY],
            spec.context[IDENTIFIED_ENTITIES_KEY],
        )
        self.assertEqual(
            out_spec.context["resolved_reference"], RESOLVED_SUBJECT_EVIDENCE
        )

    def test_taskspec_contract_preserved(self):
        self.assertIs(self.out_spec.task_type, self.spec.task_type)
        self.assertEqual(self.out_spec.input_hash, self.spec.input_hash)
        self.assertEqual(self.out_spec.source, self.spec.source)
        self.assertEqual(self.out_spec.verified, self.spec.verified)
        # B — a genuinely RESOLVED reference reconciles ONLY its own reason:
        # every other reason is retained in order and the score is recomputed
        # from the unchanged weight table (threshold and weights untouched).
        remaining = tuple(
            reason
            for reason in self.spec.ambiguity.ambiguities
            if reason != "reference"
        )
        self.assertIn("reference", self.spec.ambiguity.ambiguities)
        self.assertEqual(self.out_spec.ambiguity.ambiguities, remaining)
        self.assertEqual(
            self.out_spec.ambiguity.ambiguity_score,
            sum(_AMBIGUITY_WEIGHTS[reason] for reason in remaining),
        )

    def test_turn_meaning_carries_the_reference_unchanged(self):
        meaning = build_turn_meaning(self.out_spec, self.text)
        self.assertEqual(
            set(TurnMeaning.__dataclass_fields__),
            {"intent", "uncertainty", "reference", "source_text", "provenance"},
        )
        self.assertEqual(meaning.reference, RESOLVED_SUBJECT_EVIDENCE)
        self.assertEqual(meaning.source_text, self.text)
        self.assertEqual(meaning.provenance["source"], "deterministic")
        self.assertEqual(meaning.provenance["input_hash"], self.spec.input_hash)

    def test_governed_turn_gains_no_authority(self):
        text = "Add a new capability for it"

        def _resolve(service):
            spec = service._intake(text, 1)
            spec = service._apply_entity_identification(spec, text)
            return spec, service._apply_reference_resolution(spec, text)

        carried = _service()
        carried.send("What does code_inspector do?")
        baseline = _service()

        baseline_spec, (baseline_out, _) = _resolve(baseline)
        carried_spec, (carried_out, response) = _resolve(carried)

        self.assertEqual(carried_out.task_type, baseline_out.task_type)
        self.assertEqual(carried_out.task_type, baseline_spec.task_type)
        # B — the one intentional difference: the carried turn's reference is
        # genuinely bound, so its own ambiguity reason is reconciled and the
        # turn proceeds; the antecedent-free baseline still clarifies. The
        # governed outcome (type, intent, no authority) is otherwise identical.
        self.assertFalse(carried_out.needs_clarification)
        self.assertTrue(baseline_out.needs_clarification)
        self.assertEqual(carried_out.intent, baseline_out.intent)
        self.assertEqual(carried_spec.context.get("resolved_reference"), None)
        self.assertEqual(
            carried_out.context["resolved_reference"], RESOLVED_SUBJECT_EVIDENCE
        )
        self.assertIsNone(response)
        self.assertEqual(carried._active_approval_requests, {})
        self.assertEqual(carried._active_proposals, {})


if __name__ == "__main__":
    unittest.main()
