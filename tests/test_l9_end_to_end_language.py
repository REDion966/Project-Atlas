"""L9 — end-to-end real-world language validation regressions.

Two genuine integration defects were found by driving the public entry points
(``Atlas.chat`` / ``Atlas.stream``) with realistic human language:

1. An explicitly requested *investigation* was reclassified by a bare mention
   of another subsystem's name. With a pending development proposal,
   "Investigate the approval flow." **approved it** — an unintended
   authorization that the human never gave. Root cause: intake checked the
   approval/rejection/recovery cues before the investigation cue, with no
   investigation-lead guard (planning already had one).

2. The bounded conversational-turn recall (L5/Phase 5) was unreachable for its
   own finding phrases ("What did we find?"): intake types them as
   ``information_request`` (research cue "find"), which the builtin responder's
   task-type gate excluded, so the turn fell through to the orchestrated
   clarification ("I need a bit more detail ...") despite Atlas holding the
   deterministic result. The unit tests had bypassed the gate with
   ``spec=None``.

Both fixes are bounded, deterministic, model-independent, and fail closed. No
provider is contacted anywhere in this module.
"""

from __future__ import annotations

import unittest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.kernel.atlas import Atlas

# Phrasings where an explicit investigation is the request and the subsystem
# is only *mentioned* (as the target or as a boundary/constraint).
INVESTIGATION_LEAD_PHRASES = (
    "Investigate the approval flow.",
    "Investigate the approval manager.",
    "Investigate the rejection flow.",
    "Investigate the recovery flow.",
    "Investigate the memory architecture. Priority: don't break the approval boundary.",
    "Investigate the memory architecture and the approval manager.",
    "Look at the approval boundary. Investigate it.",
)

# Legitimate lifecycle requests that must be untouched by the guard.
EXPLICIT_LIFECYCLE_PHRASES = (
    ("approve it", TaskType.APPROVAL),
    ("Approve the proposal.", TaskType.APPROVAL),
    ("Approve the investigation.", TaskType.APPROVAL),
    ("Reject the proposal.", TaskType.REJECTION_REQUEST),
    ("reject that", TaskType.REJECTION_REQUEST),
    ("Recover from the failure.", TaskType.RECOVERY_REQUEST),
    ("Plan this improvement.", TaskType.PLANNING_REQUEST),
    ("Execute the approved proposal.", TaskType.EXECUTION_REQUEST),
    ("Verify the development.", TaskType.VERIFICATION_REQUEST),
)

FINDING_PHRASES = (
    "What did we find?",
    "What did we just find?",
    "what issue did we find",
)


class _FailingAI:
    """Any provider contact is a failure."""

    def chat(self, prompt, routing_context=None):
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


def _service() -> ConversationService:
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
    )


class TestInvestigationLeadProtection(unittest.TestCase):
    """An explicit investigation is never hijacked by a named subsystem."""

    def test_investigation_lead_wins_over_subsystem_mentions(self):
        for text in INVESTIGATION_LEAD_PHRASES:
            with self.subTest(text=text):
                spec = TaskIntake().intake(text)
                self.assertEqual(spec.task_type, TaskType.INVESTIGATION_REQUEST)

    def test_explicit_lifecycle_requests_are_unchanged(self):
        for text, expected in EXPLICIT_LIFECYCLE_PHRASES:
            with self.subTest(text=text):
                spec = TaskIntake().intake(text)
                self.assertEqual(spec.task_type, expected)

    def test_negated_investigation_lead_does_not_shield_approval(self):
        # "Don't investigate, approve it." is an approval, not an investigation.
        spec = TaskIntake().intake("Don't investigate, approve it.")
        self.assertEqual(spec.task_type, TaskType.APPROVAL)

    def test_instruction_forms_keep_their_classification(self):
        # A verb-form lifecycle instruction keeps its existing classification
        # even alongside an investigation lead ("Examine the proposal and
        # approve it." is pinned by the existing suite). Binding such an
        # instruction to the *right object* ("Reject any bad ideas" vs the
        # pending proposal) is a broader capability and is recorded as an
        # L10 candidate rather than changed here.
        expectations = {
            "Examine the proposal and approve it.": TaskType.APPROVAL,
            "Investigate the memory architecture. Reject any bad ideas.": (
                TaskType.REJECTION_REQUEST
            ),
            "Investigate the memory architecture. Recover from any failure.": (
                TaskType.RECOVERY_REQUEST
            ),
        }
        for text, expected in expectations.items():
            with self.subTest(text=text):
                self.assertEqual(TaskIntake().intake(text).task_type, expected)

    def test_recall_phrasing_guard_is_preserved(self):
        spec = TaskIntake().intake("Do you remember our investigation?")
        self.assertEqual(spec.task_type, TaskType.QUESTION)

    def test_investigation_first_compound_planning_guard_is_preserved(self):
        spec = TaskIntake().intake(
            "Investigate the memory architecture. Plan this improvement."
        )
        self.assertEqual(spec.task_type, TaskType.INVESTIGATION_REQUEST)


class TestPendingProposalIsNotAuthorizedByAnInvestigation(unittest.TestCase):
    """End-to-end: a named subsystem can no longer authorize a proposal."""

    def test_investigation_mentioning_the_approval_flow_does_not_approve(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.chat("Investigate the memory architecture.")
            atlas.chat("Prepare a proposal.")
            state = atlas._conversation.state_manager.state
            pending = state.pending_approval_id
            self.assertIsNotNone(pending)

            response = atlas.chat("Investigate the approval flow.")

            metadata = response.metadata or {}
            self.assertIn("investigation", metadata)
            self.assertNotIn("approval", metadata)
            self.assertIn("Investigation", response.content)
            after = atlas._conversation.state_manager.state
            self.assertEqual(after.pending_approval_id, pending)
        finally:
            atlas.shutdown()

    def test_constraint_wording_does_not_approve(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.chat("Investigate the memory architecture.")
            atlas.chat("Prepare a proposal.")
            pending = atlas._conversation.state_manager.state.pending_approval_id
            self.assertIsNotNone(pending)

            response = atlas.chat(
                "Investigate the memory architecture. "
                "Priority: don't break the approval boundary."
            )

            self.assertNotIn("approval", response.metadata or {})
            self.assertEqual(
                atlas._conversation.state_manager.state.pending_approval_id, pending
            )
        finally:
            atlas.shutdown()

    def test_approval_still_works_when_explicitly_requested(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.chat("Investigate the memory architecture.")
            atlas.chat("Prepare a proposal.")
            response = atlas.chat("approve it")
            approval = (response.metadata or {}).get("approval", {})
            self.assertEqual(approval.get("status"), "approved")
        finally:
            atlas.shutdown()


class TestBoundedRecallReachability(unittest.TestCase):
    """The deterministic finding recall is reachable through the real intake."""

    def test_finding_recall_is_reachable_end_to_end(self):
        for text in FINDING_PHRASES:
            with self.subTest(text=text):
                service = _service()
                service.state_manager.update(latest_result="Finding Alpha")
                service.send("Investigate the memory architecture.")
                message = service.send(text)
                self.assertEqual(
                    (message.metadata or {}).get("builtin_intent"),
                    "conversation_recall",
                )
                self.assertEqual(
                    (message.metadata or {}).get("recall_source"), "finding"
                )
                self.assertIn("Finding Alpha", message.content)

    def test_finding_recall_is_intake_typed_as_information_request(self):
        # Pins the reason the gate needed widening: intake says information_request.
        self.assertEqual(
            TaskIntake().intake("What did we find?").task_type,
            TaskType.INFORMATION_REQUEST,
        )

    def test_recall_without_a_candidate_declines(self):
        service = _service()
        message = service.send("What did we find?")
        self.assertNotEqual(
            (message.metadata or {}).get("builtin_intent"), "conversation_recall"
        )

    def test_send_and_stream_share_the_finding_recall(self):
        sent_service = _service()
        sent_service.state_manager.update(latest_result="Finding Alpha")
        sent_service.send("Investigate the memory architecture.")
        sent = sent_service.send("What did we find?")

        streamed_service = _service()
        streamed_service.state_manager.update(latest_result="Finding Alpha")
        streamed_service.send("Investigate the memory architecture.")
        chunks = list(streamed_service.stream("What did we find?"))

        self.assertEqual("".join(chunks), sent.content)
        self.assertEqual(
            (streamed_service.conversation.messages[-1].metadata or {}).get(
                "builtin_intent"
            ),
            "conversation_recall",
        )

    def test_other_information_requests_are_unchanged(self):
        # A genuinely research-shaped information request is not recalled: the
        # turn behaves identically whether or not a result is recorded.
        recorded_service = _service()
        recorded_service.state_manager.update(latest_result="Finding Alpha")
        recorded = recorded_service.send(
            "Search the repository for the runtime coordinator"
        )

        plain_service = _service()
        plain = plain_service.send("Search the repository for the runtime coordinator")

        self.assertNotEqual(
            (recorded.metadata or {}).get("builtin_intent"), "conversation_recall"
        )
        self.assertEqual(recorded.content, plain.content)
        self.assertEqual(recorded.metadata, plain.metadata)

    def test_governed_turns_are_never_recalled(self):
        # The recall gate must not claim a governed lifecycle task type.
        service = _service()
        service.state_manager.update(latest_result="Finding Alpha")
        spec = TaskIntake().intake("Investigate the memory architecture.")
        self.assertIs(spec.task_type, TaskType.INVESTIGATION_REQUEST)
        self.assertIsNone(
            service._builtin_response.respond("What did we find?", spec=spec)
        )

    def test_recall_does_not_contact_the_provider(self):
        service = _service()
        service.state_manager.update(latest_result="Finding Alpha")
        service.send("What did we find?")  # _FailingAI would raise on contact


class TestRealWorldScenarioMatrix(unittest.TestCase):
    """A bounded end-to-end matrix through the public entry points."""

    def setUp(self):
        self.atlas = Atlas()
        self.atlas.start()

    def tearDown(self):
        self.atlas.shutdown()

    def test_casual_and_informational_turns_stay_deterministic(self):
        expectations = {
            "hello": "greeting",
            "hi there!": "greeting",
            "What can you currently do?": "capabilities",
            "what are you capable of": "capabilities",
            "Who are you?": "identity",
            "What is the current status?": "status",
            "help": "help",
        }
        for text, intent in expectations.items():
            with self.subTest(text=text):
                message = self.atlas.chat(text)
                metadata = message.metadata or {}
                self.assertEqual(metadata.get("builtin_intent"), intent)
                self.assertIs(metadata.get("model_used"), False)

    def test_ambiguous_action_asks_for_clarification_and_never_guesses(self):
        message = self.atlas.chat("Build it.")
        self.assertIn("I need a bit more detail", message.content)
        pending = self.atlas._conversation.state_manager.state.pending_question
        self.assertIn("ambiguous reference", pending)

    def test_governed_operations_fail_closed_without_state(self):
        expectations = {
            "Execute the approved proposal.": ("execution", "no_active_proposal"),
            "approve": ("approval", "no_active_proposal"),
            "Verify the development.": ("verification", "no_result"),
            "Recover from the failure.": ("recovery", "no_failed_run"),
        }
        for text, (key, status) in expectations.items():
            with self.subTest(text=text):
                message = self.atlas.chat(text)
                self.assertEqual((message.metadata or {}).get(key, {}).get("status"), status)

    def test_repository_impact_is_deterministic_and_structured(self):
        text = "What would be affected if I change atlas/memory/manager.py?"
        first = self.atlas.chat(text)
        second = self.atlas.chat(text)
        self.assertEqual(first.content, second.content)
        payload = (first.metadata or {}).get("repository_impact")
        self.assertEqual(payload.get("status"), "resolved")
        self.assertEqual(payload.get("resolved_module"), "atlas.memory.manager")

    def test_development_need_confirmation_fails_closed(self):
        self.atlas.chat("Summarize the tradeoffs of caching.")
        self.assertTrue(
            self.atlas._conversation._development_need_coordinator.has_pending
        )
        response = self.atlas.chat("yes")
        self.assertFalse(
            self.atlas._conversation._development_need_coordinator.has_pending
        )
        # G3 reconciliation (documented): the confirmed need now rides the EXISTING
        # governed DevelopmentDriver, which adjudicates the gap honestly
        # ("already supported" / "no authoring content available") instead of
        # failing at the supplier. The invariant is unchanged — the outcome is an
        # honest governed terminal, never a fabricated success, and nothing is
        # approved, executed, or promoted.
        self.assertRegex(
            response.content,
            r"Outcome: (already_supported|author_unavailable|envelope_disabled|"
            r"insufficient_evidence|proposed|validated|failed)",
        )
        self.assertNotIn("approval", (response.metadata or {}))
        # Promotion remains OWNER-only: no proposal reaches the APPROVED state.
        proposals = tuple(self.atlas._evolution_memory.get_all_proposals())
        self.assertTrue(
            all(proposal.status.name != "APPROVED" for proposal in proposals)
        )

    def test_governed_lifecycle_reaches_planning_and_approval(self):
        investigation = self.atlas.chat("Investigate the memory architecture.")
        self.assertIn("investigation", investigation.metadata or {})

        prepared = self.atlas.chat("Prepare a proposal.")
        self.assertEqual(
            (prepared.metadata or {}).get("planning", {}).get("status"), "prepared"
        )

        approved = self.atlas.chat("approve it")
        self.assertEqual(
            (approved.metadata or {}).get("approval", {}).get("status"), "approved"
        )


class TestStreamParity(unittest.TestCase):
    """The user-facing stream boundary composes the same behaviour as chat."""

    def _compare(self, turns, state=None):
        chat_atlas = Atlas()
        chat_atlas.start()
        stream_atlas = Atlas()
        stream_atlas.start()
        try:
            if state:
                chat_atlas._conversation.state_manager.update(**state)
                stream_atlas._conversation.state_manager.update(**state)
            results = []
            for text in turns:
                chat_message = chat_atlas.chat(text)
                streamed = "".join(stream_atlas.stream(text))
                results.append(
                    (
                        chat_message.content,
                        streamed,
                        dict(chat_message.metadata or {}),
                        dict(stream_atlas._conversation._conversation.messages[-1].metadata or {}),
                    )
                )
            return results
        finally:
            chat_atlas.shutdown()
            stream_atlas.shutdown()

    def test_semantics_match_for_representative_turns(self):
        pairs = self._compare(
            [
                "hello",
                "What can you currently do?",
                "Build it.",
                "What would be affected if I change atlas/memory/manager.py?",
            ]
        )
        for chat_content, streamed, chat_meta, stream_meta in pairs:
            self.assertEqual(streamed, chat_content)
            self.assertEqual(sorted(stream_meta), sorted(chat_meta))

    def test_finding_recall_matches_on_both_paths(self):
        pairs = self._compare(
            ["Investigate the memory architecture.", "What did we find?"],
            state=None,
        )
        chat_content, streamed, _, stream_meta = pairs[-1]
        self.assertEqual(streamed, chat_content)
        self.assertEqual(stream_meta.get("builtin_intent"), "conversation_recall")


class TestInvestigationEvidenceDeterminism(unittest.TestCase):
    """Investigation evidence is a deterministic function of the repository.

    ``_grep`` shells out to ripgrep, which emits matches in parallel-traversal
    completion order. Bounding that raw output made the retained evidence set
    (and therefore the report and its ``affected_files``) differ for identical
    input and identical repository state. Ordering must therefore happen
    before bounding.
    """

    def setUp(self):
        self.service = InvestigationService()

    def test_grep_matches_are_ordered_and_stable(self):
        first = self.service._grep("memory", directory="atlas/memory", max_results=3)
        self.assertTrue(first)
        self.assertEqual(first, sorted(first))
        for _ in range(5):
            self.assertEqual(
                self.service._grep(
                    "memory", directory="atlas/memory", max_results=3
                ),
                first,
            )

    def test_bounded_evidence_is_a_prefix_of_the_ordered_matches(self):
        bounded = self.service._grep("memory", directory="atlas/memory", max_results=2)
        wider = self.service._grep("memory", directory="atlas/memory", max_results=10)
        self.assertEqual(bounded, wider[:2])

    def test_python_fallback_is_ordered(self):
        results = self.service._python_grep("def ", "atlas/memory", 3)
        self.assertEqual(results, sorted(results))

    def test_investigation_evidence_is_reproducible(self):
        target = "Investigate the memory architecture"
        first = self.service.investigate(target)
        second = self.service.investigate(target)
        self.assertEqual(first.affected_files, second.affected_files)
        self.assertEqual(
            [finding.evidence for finding in first.findings],
            [finding.evidence for finding in second.findings],
        )


if __name__ == "__main__":
    unittest.main()
