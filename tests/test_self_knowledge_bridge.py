"""Natural-language self-knowledge / architecture-reasoning bridge.

Focused tests for the bounded bridge that makes EXISTING Atlas self-knowledge,
architecture, capability-contract, repository-intelligence, external-research,
evidence, gap, lifecycle and model-independence surfaces reachable from natural
language — through the EXISTING semantic frame + verified-anchor topic renderers
(no new registry, no new knowledge store, deterministic, model-free).

Assertions target semantic ROUTING/SOURCE (intent + topic), not exact prose.
"""

from __future__ import annotations

import pytest

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_ARCHITECTURE,
    BUILTIN_INTENT_CONVERSATION_RECALL,
    BUILTIN_INTENT_SELF_KNOWLEDGE,
    BUILTIN_INTENT_UNSUPPORTED,
    BuiltinResponseService,
)
from atlas.conversation.conversation_context import build_conversation_context
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model


def _svc() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _classify(text: str, context=None):
    return _svc()._classify(text, TaskIntake().intake(text), context)


def _topic(text: str) -> str | None:
    classified = _classify(text)
    if isinstance(classified, tuple) and classified[0] == BUILTIN_INTENT_SELF_KNOWLEDGE:
        return classified[1]
    return None


# ---------------------------------------------------------------------------
# 1. Previously-failing questions now route to the correct existing surface
# ---------------------------------------------------------------------------


ROUTING = (
    ("How do capability contracts work?", "capability contracts"),
    ("What are capability contracts?", "capability contracts"),
    ("Can you explain your capability contracts?", "capability contracts"),
    ("How are your capabilities described?", "capability contracts"),
    ("What is the difference between your capability model and architecture model?",
     "capability and architecture models"),
    ("How do you find symbols inside your source code?",
     "repository symbol intelligence"),
    ("What happens to code you download from GitHub?",
     "external repository research"),
    ("Can external code directly modify you?",
     "external repository research"),
    ("Who is allowed to authorize promotion?", "owner approval"),
    ("What happens if you discover a capability gap?",
     "capability gap assessment"),
    ("How do you determine whether something found externally is useful?",
     "evidence and trust"),
    ("After a capability is promoted, how do you learn that the capability now exists?",
     "governed development lifecycle"),
    ("What happens when you find something useful on GitHub?",
     "external repository research"),
    ("What happens next after external research finds something useful?",
     "external repository research"),
    ("What happens after successful verification?", "governed development lifecycle"),
    ("What happens before promotion?", "governed development lifecycle"),
    ("How does Atlas update its self-knowledge after integration?",
     "governed development lifecycle"),
    ("What prevents external code from directly modifying Atlas?",
     "external repository research"),
    ("What prevents an unverified research finding from becoming trusted knowledge?",
     "evidence and trust"),
    ("What prevents an external AI model from becoming the authority?",
     "model independence"),
    ("Where can implementation happen?", "sandbox execution"),
    ("What happens if sandbox verification fails?", "sandbox execution"),
)


class TestRouting:
    @pytest.mark.parametrize("text,topic", ROUTING)
    def test_routes_to_expected_existing_topic(self, text, topic):
        assert _topic(text) == topic

    def test_an_existing_topic_is_preserved(self):
        # Bounded reference-resolution / limitations behaviour is unchanged.
        assert _topic("What are your current limitations?") == "current limitations"

    def test_unsupported_questions_still_fail_closed(self):
        # A subject Atlas genuinely cannot answer stays an honest refusal.
        assert _classify("What is the airspeed velocity of an unladen swallow?") == (
            BUILTIN_INTENT_UNSUPPORTED
        )


# ---------------------------------------------------------------------------
# 2. Paraphrase convergence (subject families, not exact sentences)
# ---------------------------------------------------------------------------


class TestParaphraseConvergence:
    @pytest.mark.parametrize(
        "text",
        (
            "How are capability contracts structured?",
            "What do capability contracts contain?",
            "Can you explain your capability contracts?",
        ),
    )
    def test_capability_contract_paraphrases(self, text):
        # Question forms resolve through the shared frame...
        assert sf.interpret(text).concept == "capability_contracts"
        # ...and route to the same existing topic.
        assert _topic(text) == "capability contracts"

    def test_capability_contract_imperative_routes(self):
        # An imperative request ("Describe your capability contracts.") is claimed
        # by the existing bounded phrase surface, not the question-only frame.
        assert _topic("Describe your capability contracts.") == "capability contracts"

    @pytest.mark.parametrize(
        "text",
        (
            "What do you do with useful mechanisms found in external repositories?",
            "How does external repository research lead to work?",
            "What is your process for external repositories?",
        ),
    )
    def test_external_research_paraphrases(self, text):
        assert _topic(text) == "external repository research"

    @pytest.mark.parametrize(
        "text",
        (
            "How do you locate symbols in the codebase?",
            "Can you find symbols in your own source code?",
        ),
    )
    def test_repository_symbol_paraphrases(self, text):
        assert sf.interpret(text).concept == "repository_symbols"


# ---------------------------------------------------------------------------
# 3. Architecture relationship questions reconstruct the governed lifecycle
# ---------------------------------------------------------------------------


class TestLifecycleReasoning:
    @pytest.mark.parametrize(
        "text",
        (
            "Suppose you find a useful mechanism in an external repository. What happens next?",
            "How do you validate knowledge before trusting it?",
            "What happens after successful verification?",
        ),
    )
    def test_relationship_questions_are_claimed(self, text):
        classified = _classify(text)
        assert isinstance(classified, tuple)
        assert classified[0] in (BUILTIN_INTENT_SELF_KNOWLEDGE, BUILTIN_INTENT_ARCHITECTURE)

    def test_lifecycle_answer_preserves_order_and_governance(self):
        rendered = _svc()._render_self_knowledge("governed development lifecycle")
        lowered = rendered.lower()
        for stage in ("understand", "gap", "sandbox", "test", "verif", "promotion"):
            assert stage in lowered
        assert "owner" in lowered
        assert "sandbox" in lowered
        # The boundary is stated, never bypassed.
        assert "pending_approval" in lowered or "stop" in lowered
        # Verified anchors are present (not invented).
        assert "development_driver.py" in rendered

    def test_external_code_cannot_modify_atlas_answer(self):
        rendered = _svc()._render_self_knowledge("external repository research")
        lowered = rendered.lower()
        assert "never executed" in lowered
        assert "deny-by-default" in lowered
        assert "sources/github.py" in rendered


# ---------------------------------------------------------------------------
# 4. Conversational continuity (existing recall surface; no new memory)
# ---------------------------------------------------------------------------


class TestContinuity:
    def test_recent_topic_recall_with_context(self):
        state = ConversationState(current_investigation="capability contracts")
        context = build_conversation_context([], state)
        classified = _classify("What were we just talking about?", context)
        assert isinstance(classified, tuple)
        assert classified[0] == BUILTIN_INTENT_CONVERSATION_RECALL
        assert "capability contracts" in classified[1][2]

    def test_recent_topic_recall_from_prior_turns(self):
        # The subject comes from EXISTING structured conversation state (no new
        # memory system); the recall cue itself is the existing bounded phrase.
        state = ConversationState(current_objective="vector databases")
        messages = [
            Message(role="user", content="Please research vector databases for me."),
            Message(role="assistant", content="Here is what I found."),
        ]
        context = build_conversation_context(messages, state)
        classified = _classify("what were we just discussing?", context)
        assert isinstance(classified, tuple)
        assert classified[0] == BUILTIN_INTENT_CONVERSATION_RECALL
        assert "vector databases" in classified[1][2]

    def test_no_reliable_context_does_not_fabricate(self):
        context = build_conversation_context([], ConversationState())
        classified = _classify("What were we just talking about?", context)
        # No antecedent: never invented. Falls through to the honest floor.
        assert classified != (
            BUILTIN_INTENT_CONVERSATION_RECALL,
            ("topic", "recent conversation topic", ""),
        )
        if isinstance(classified, tuple):
            assert classified[0] != BUILTIN_INTENT_CONVERSATION_RECALL


# ---------------------------------------------------------------------------
# 5. Determinism / no authority
# ---------------------------------------------------------------------------


class TestDeterminismAndSafety:
    def test_classification_is_deterministic(self):
        text = "How do capability contracts work?"
        assert _classify(text) == _classify(text)

    def test_self_knowledge_answer_grants_no_authority(self):
        rendered = _svc()._render_self_knowledge("capability contracts").lower()
        for banned in ("i have approved", "i have promoted", "authorized to develop"):
            assert banned not in rendered

    def test_bridge_is_model_free(self):
        import ast
        from pathlib import Path

        for module in (
            "atlas/conversation/semantic_frame.py",
            "atlas/conversation/lexicon.py",
            "atlas/conversation/builtin_response.py",
        ):
            tree = ast.parse(Path(module).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                elif isinstance(node, ast.Import):
                    imported.update(a.name for a in node.names)
            assert not any(n.startswith("atlas.ai") for n in imported), module
