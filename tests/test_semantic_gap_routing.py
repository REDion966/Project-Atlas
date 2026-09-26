"""Evidenced semantic-routing repair — the capability-gap / insufficiency family (L10).

A live-kernel investigation proved four deterministic defects behind the real
conversation failures:

1. the tokenizer's lemma for "missing" ("mis") and "lacking" ("lack") did not
   match the concept classes that declare those surface forms, and the
   contraction "can't" split into "can" + "not" instead of the one-word "cannot"
   the insufficiency vocabulary already uses;
2. ``_is_recall`` treated the bare word "ask" plus a terminal question as a
   recall of the conversation, so "I asked you to do something you can't
   currently do. ..." was classified RECALL/casual;
3. the knowledge-complement ("about") guard blocked an Atlas-sufficiency reading
   of a turn that also named a gap ("... what can you do about it?");
4. the response floor consulted the generic capability-inventory/help patterns
   BEFORE the frame's already-recognized gap/limitation meaning.

These tests pin the repaired routing, and — equally important — the negatives:
genuine recall, external knowledge questions, capability inventory, help,
governance language and the governed investigation/development cascade must all
behave exactly as before. Assertions target semantic ROUTING/SOURCE (frame
concept, builtin intent, topic, task type), never prose.
"""

from __future__ import annotations

import pytest

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_SELF_KNOWLEDGE,
    BuiltinResponseService,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

GAP_TOPIC = "capability gap assessment"
LIMITATIONS_TOPIC = "current limitations"
LIFECYCLE_TOPIC = "governed development lifecycle"
EXTENSION_TOPIC = "extension points"

#: The evidenced real-world turns plus the paraphrases that must converge on the
#: SAME existing meaning.
GAP_PARAPHRASES = (
    "I asked you to do something you can't currently do. How would you figure out what you're missing?",
    "If you discover that you're missing a capability, what can you do about it?",
    "What capabilities are you missing?",
    "Which capabilities do you lack?",
    "How do you figure out what you're missing?",
    "How do you acquire a capability you don't have yet?",
)

#: Governed ACTION requests. They must keep the existing cascade (investigation /
#: research / development) and must never be claimed as informational answers.
#:
#: Checkpoint 2 note: "Can you research what capabilities you're missing?" was
#: listed here in Checkpoint 1. Live evidence then showed that phrasing asks
#: about Atlas's OWN sufficiency (an information request, not a governed
#: action) and that the external-knowledge path answered it with an empty store
#: miss; it is now pinned with the other Atlas-sufficiency phrasings in
#: ``TestAtlasSufficiencyPhrasings``.
ACTION_REQUESTS = (
    "Suppose I asked you to gain a capability that you don't currently have. "
    "Could you investigate what's missing, research possible ways to implement "
    "it, and develop it under your normal safety rules?",
    "Can you investigate a new technology and see whether it would help you?",
    "If you don't know how to solve a problem, can you investigate possible solutions?",
    "Add a capability you're missing.",
    "Research how Atlas currently handles references.",
)

GENUINE_RECALL = (
    "What did we just discuss?",
    "What were we just talking about?",
    "Do you remember what we discussed?",
)


class _FailingAI:
    """Any provider contact is a failure: the path under test is model-free."""

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


def _svc() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _classify(text: str):
    return _svc()._classify(text, TaskIntake().intake(text), None)


def _topic(text: str) -> str | None:
    classified = _classify(text)
    if isinstance(classified, tuple) and classified[0] == BUILTIN_INTENT_SELF_KNOWLEDGE:
        return classified[1]
    return None


def _flat_intent(classified) -> str | None:
    return classified[0] if isinstance(classified, tuple) else classified


def _service() -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
    )


# ---------------------------------------------------------------------------
# 1. Tokenizer / concept-class alignment
# ---------------------------------------------------------------------------


class TestTokenizerVocabularyAlignment:
    """The evidenced surface forms must reach the classes that declare them."""

    def test_missing_reaches_the_gap_family(self):
        assert sf.tokens("missing") == ("missing",)
        assert "missing" in sf.SELF_GAP_CONCEPTS

    def test_lack_and_lacking_reach_the_gap_family(self):
        assert sf.tokens("lacking") == ("lack",)
        assert sf.tokens("lack") == ("lack",)
        assert "lack" in sf.SELF_GAP_CONCEPTS

    def test_cannot_contraction_reaches_the_insufficiency_vocabulary(self):
        assert sf.tokens("can't") == ("cannot",)
        assert sf.tokens("cannot") == ("cannot",)
        assert "cannot" in sf.SELF_FAILURE_TRIGGERS

    @pytest.mark.parametrize(
        "surface", ["gap", "gaps", "absent", "missing", "lack", "lacking"]
    )
    def test_every_declared_gap_form_is_reachable(self, surface):
        produced = sf.tokens(surface)
        assert produced, surface
        assert set(produced) & sf.SELF_GAP_CONCEPTS, (surface, produced)


# ---------------------------------------------------------------------------
# 2. Gap paraphrases reach the EXISTING gap surface
# ---------------------------------------------------------------------------


class TestGapParaphraseRouting:
    @pytest.mark.parametrize("text", GAP_PARAPHRASES)
    def test_frame_reads_the_gap_family(self, text):
        frame = sf.interpret(text)
        assert frame.domain is sf.SemanticDomain.SELF_KNOWLEDGE, text
        assert frame.concept == "capability_gap", text
        assert frame.role is not sf.SemanticRole.RECALL, text

    @pytest.mark.parametrize("text", GAP_PARAPHRASES)
    def test_floor_answers_from_the_existing_gap_topic(self, text):
        assert _topic(text) == GAP_TOPIC, text

    @pytest.mark.parametrize("text", GAP_PARAPHRASES)
    def test_no_longer_reaches_inventory_help_or_the_unsupported_floor(self, text):
        assert _flat_intent(_classify(text)) not in (
            "capabilities",
            "help",
            "unsupported",
        ), text

    def test_runtime_is_deterministic_model_free_and_governance_neutral(self):
        for text in GAP_PARAPHRASES:
            service = _service()
            message = service.send(text)
            assert message.metadata.get("builtin_intent") == "self_knowledge", text
            assert message.metadata.get("model_used") is False, text
            assert "investigation" not in message.metadata, text
            assert "development" not in message.metadata, text
            state = service.state_manager.state
            assert state.pending_approval_id is None, text
            assert state.evolution_proposal_id is None, text
            assert state.last_operation is None, text
        assert _FailingAI.calls == 0

    def test_answer_cites_verified_anchors_not_invented_prose(self):
        message = _service().send(GAP_PARAPHRASES[0])
        assert "verified present" in message.content
        assert "no external AI model used" in message.content


# ---------------------------------------------------------------------------
# 3. Recall boundary
# ---------------------------------------------------------------------------


class TestRecallBoundary:
    @pytest.mark.parametrize("text", GENUINE_RECALL)
    def test_genuine_recall_is_still_recall(self, text):
        assert sf.interpret(text).role is sf.SemanticRole.RECALL, text

    def test_prior_request_reference_is_not_recall(self):
        text = GAP_PARAPHRASES[0]
        order = sf.tokens(text)
        assert sf._is_recall(order, frozenset(order), text) is False
        assert sf.interpret(text).role is not sf.SemanticRole.RECALL

    def test_bare_ask_question_is_not_recall(self):
        # "Can I ask ..." is the user asking, not a recall of the conversation.
        for text in ("Can I ask what your limitations are?", "Can I ask about X?"):
            assert sf.interpret(text).role is not sf.SemanticRole.RECALL, text

    @pytest.mark.parametrize(
        "text", ["What did I ask earlier?", "What did I ask you?"]
    )
    def test_asking_about_the_conversation_is_still_recall(self, text):
        # The pinned G1 recall contract: the wh-word object of "ask" is the
        # asking itself, which IS a recall of the conversation.
        assert sf.interpret(text).role is sf.SemanticRole.RECALL, text

    def test_recall_runtime_still_resolves_a_recent_antecedent(self):
        service = _service()
        service.state_manager.update(
            current_investigation="Investigate the memory architecture"
        )
        message = service.send("What did we just discuss?")
        assert message.metadata.get("builtin_intent") == "conversation_recall"
        assert "Investigate the memory architecture" in message.content
        assert message.metadata.get("model_used") is False

    def test_limitations_question_still_reaches_limitations(self):
        text = "Can I ask what your limitations are?"
        assert sf.interpret(text).role is not sf.SemanticRole.RECALL
        assert _topic(text) == LIMITATIONS_TOPIC


# ---------------------------------------------------------------------------
# 4. Negatives: knowledge / inventory / help / governance unchanged
# ---------------------------------------------------------------------------


class TestKnowledgeInventoryAndHelpUnchanged:
    def test_external_knowledge_question_does_not_become_gap_or_lifecycle(self):
        for text in (
            "Can I ask about the Voyager probes?",
            "What do we know about the investigation system?",
        ):
            frame = sf.interpret(text)
            assert frame.concept not in ("capability_gap", "governed_lifecycle"), text
            assert _topic(text) != GAP_TOPIC, text

    @pytest.mark.parametrize(
        "text",
        [
            "What capabilities do you have?",
            "Can you tell me what you're able to do?",
            "what capabilities do you have",
        ],
    )
    def test_capability_inventory_unchanged(self, text):
        assert _flat_intent(_classify(text)) == "capabilities", text

    @pytest.mark.parametrize("text", ["help", "what can you do", "What, can you do?"])
    def test_help_unchanged(self, text):
        assert _flat_intent(_classify(text)) == "help", text

    @pytest.mark.parametrize(
        "text",
        [
            "approve it",
            "execute the approved proposal",
            "promote the validated change",
            "reject this proposal",
        ],
    )
    def test_governance_language_is_not_captured_by_the_gap_surface(self, text):
        assert _svc().match_self_knowledge_topic(text) is None, text
        assert _flat_intent(_classify(text)) != BUILTIN_INTENT_SELF_KNOWLEDGE, text


# ---------------------------------------------------------------------------
# 5. Governing cascade: action requests keep their existing owners
# ---------------------------------------------------------------------------


class TestGovernedCascadeUnaffected:
    @pytest.mark.parametrize("text", ACTION_REQUESTS)
    def test_gap_surface_does_not_claim_action_requests(self, text):
        assert sf.interpret(text).concept != "capability_gap", text
        assert _svc().match_self_knowledge_topic(text) is None, text

    def test_intake_task_typing_is_unchanged(self):
        intake = TaskIntake()
        assert (
            intake.intake(
                "Can you investigate a new technology and see whether it would help you?"
            ).task_type
            is TaskType.INVESTIGATION_REQUEST
        )
        assert (
            intake.intake("Can you research what capabilities you're missing?").task_type
            is TaskType.INFORMATION_REQUEST
        )
        assert (
            intake.intake("Add a capability you're missing.").task_type
            is TaskType.DEVELOPMENT_REQUEST
        )
        assert (
            intake.intake(
                "Suppose I asked you to gain a capability that you don't currently "
                "have. Could you investigate what's missing, research possible ways "
                "to implement it, and develop it under your normal safety rules?"
            ).task_type
            is TaskType.INVESTIGATION_REQUEST
        )

    def test_runtime_does_not_execute_approve_or_develop_from_a_gap_question(self):
        service = _service()
        before = service.state_manager.state.to_dict()
        message = service.send("What capabilities are you missing?")
        after = service.state_manager.state.to_dict()
        for key in ("execution", "approval", "promotion"):
            assert key not in message.metadata, key
        assert after["pending_approval_id"] is None
        assert after["evolution_proposal_id"] is None
        assert after["last_operation"] is None
        assert after["last_operation"] == before["last_operation"]


# ---------------------------------------------------------------------------
# 6. Checkpoint 2 — Atlas-sufficiency questions asked with a research verb
# ---------------------------------------------------------------------------


#: Real phrasings that ask about Atlas's OWN sufficiency through a
#: research/information verb. Live evidence: these reached the external-knowledge
#: path and were answered with "No validated knowledge matched ... (status:
#: empty)", although the shared frame already recorded the sufficiency reading.
ATLAS_SUFFICIENCY = (
    "Find out what Atlas is missing to handle this.",
    "Find out what capability Atlas lacks.",
    "Can you research what capabilities you're missing?",
    "What is missing from Atlas?",
)


class TestAtlasSufficiencyPhrasings:
    @pytest.mark.parametrize("text", ATLAS_SUFFICIENCY)
    def test_frame_reads_atlas_own_gap(self, text):
        frame = sf.interpret(text)
        assert frame.domain is sf.SemanticDomain.SELF_KNOWLEDGE, text
        assert frame.concept == "capability_gap", text

    @pytest.mark.parametrize("text", ATLAS_SUFFICIENCY)
    def test_existing_gap_surface_claims_the_turn(self, text):
        # The cascade's informational self-knowledge step consults the frame
        # bridge first, so the meaning reaches the EXISTING gap topic instead of
        # an empty knowledge-store miss.
        assert _svc().match_self_knowledge_topic(text) is not None, text

    def test_runtime_answers_from_the_gap_topic_model_free(self):
        for text in ATLAS_SUFFICIENCY:
            service = _service()
            message = service.send(text)
            assert message.metadata.get("builtin_intent") == "self_knowledge", text
            assert message.metadata.get("model_used") is False, text
            assert "capability gap assessment" in message.content, text
            for key in ("execution", "approval", "promotion"):
                assert key not in message.metadata, text
            assert service.state_manager.state.pending_approval_id is None, text
        assert _FailingAI.calls == 0

    @pytest.mark.parametrize(
        "text",
        [
            "Find out what this library is missing.",
            "What capability is that framework missing?",
            "What limitations does that framework have?",
        ],
    )
    def test_external_subject_is_never_claimed_as_atlas_own_gap(self, text):
        assert sf.interpret(text).concept not in (
            "capability_gap",
            "evidence_failure",
            "limitations",
        ), text
        assert _svc().match_self_knowledge_topic(text) is None, text

    @pytest.mark.parametrize(
        "text",
        [
            "What capability is that framework missing?",
            "What limitations does that framework have?",
        ],
    )
    def test_external_subject_degrades_honestly_not_as_self_knowledge(self, text):
        # Checkpoint 5 — end-to-end: the deterministic floor must not answer an
        # external subject's insufficiency question from Atlas's own
        # self-knowledge surface; it asks/clarifies instead (never fabricates,
        # never falls through to a provider).
        service = _service()
        message = service.send(text)
        assert message.metadata.get("builtin_intent") != "self_knowledge", text
        assert message.metadata.get("model_used") is not True, text
        assert _FailingAI.calls == 0, text
        assert "Verified architectural anchors" not in message.content, text

    def test_no_self_reference_gap_question_is_still_claimed(self):
        # The pre-existing subject-question path (no self reference, an
        # Atlas-internal gap noun) is unchanged.
        assert _svc().match_self_knowledge_topic("How are capability gaps handled?")

    @pytest.mark.parametrize("text", ACTION_REQUESTS)
    def test_governed_action_requests_still_keep_their_owners(self, text):
        assert sf.interpret(text).concept != "capability_gap", text
        assert _svc().match_self_knowledge_topic(text) is None, text


# ---------------------------------------------------------------------------
# 7. Pre-existing self-knowledge surfaces keep their exact topics
# ---------------------------------------------------------------------------


class TestPreExistingTopicsUnchanged:
    @pytest.mark.parametrize(
        ("text", "topic"),
        [
            ("How would you add a new capability?", EXTENSION_TOPIC),
            ("What are your current limitations?", LIMITATIONS_TOPIC),
            ("Can I ask what your limitations are?", LIMITATIONS_TOPIC),
            ("What happens if you discover a capability gap?", GAP_TOPIC),
            ("What happens before promotion?", LIFECYCLE_TOPIC),
            ("What happens after successful verification?", LIFECYCLE_TOPIC),
            ("How do capability contracts work?", "capability contracts"),
        ],
    )
    def test_topic_unchanged(self, text, topic):
        assert _topic(text) == topic, text

    def test_bridge_requires_an_architecture_model(self):
        # Fail-soft: without the model the turn falls back to existing behaviour.
        svc = BuiltinResponseService(architecture_model_provider=lambda: None)
        assert svc._bridge_topic("What capabilities are you missing?") is None
        assert svc.match_self_knowledge_topic("What capabilities are you missing?") is None
