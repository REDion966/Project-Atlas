"""Atlas Built-In Conversational Response Service (Phase 1 + Phase 3).

Deterministic, model-independent conversational response path. It answers a
bounded set of conversational intents without calling any external AI
provider:

- greeting
- help
- identity / self-description
- capabilities (grounded in the injected ToolRegistry + CapabilityRegistry)
- capability-explain (a named registered capability/tool, or honest unknown)
- status (grounded in injected collaborators + caller-supplied counts)
- memory/knowledge recall (deterministic lookup; honest when unavailable)
- commands (supported CLI surfaces + safe next steps)
- resolved-reference restatement (bounded: restates evidence the deterministic
  resolver has ALREADY bound, never re-resolves, guesses, or invents)
- unsupported-request notice (bounded, fail-closed)

Pure logic: no AI imports, no network, no storage/schema changes, no
RuntimeCoordinator changes. All collaborators are optional and injected;
when absent the service degrades gracefully instead of inventing content.
Every answer distinguishes confirmed state (what is registered/stored/
running) from unavailable or unknown state.

Boundary: this service only handles conversational turns whose classified
``TaskSpec`` is casual (CONVERSATION / UNKNOWN / QUESTION, and never a
needs-clarification spec). Governed lifecycle types (development,
investigation, planning, approval, execution, autonomy, orchestration
requests, ...) always return ``None`` so they continue through the existing
governed pipeline. Nothing here authorizes, executes, mutates, or approves.
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from atlas.conversation.message import Message
from atlas.conversation.normalization import canonicalize_surface

if TYPE_CHECKING:
    from atlas.conversation.conversation_context import ConversationContext
    from atlas.conversation.task_intake import TaskSpec
    from atlas.knowledge.knowledge_manager import KnowledgeManager
    from atlas.memory.service.memory_manager_service import MemoryManagerService
    from atlas.reasoning.execution.registry import CapabilityRegistry
    from atlas.session.context import SessionContext
    from atlas.tools.registry import ToolRegistry

#: Intents this service answers. Anything else returns None (unsupported
#: inputs receive the bounded unsupported notice instead).
BUILTIN_INTENT_GREETING = "greeting"
BUILTIN_INTENT_HELP = "help"
BUILTIN_INTENT_IDENTITY = "identity"
BUILTIN_INTENT_CAPABILITIES = "capabilities"
BUILTIN_INTENT_CAPABILITY_DETAIL = "capability_detail"
BUILTIN_INTENT_ARCHITECTURE = "architecture"
BUILTIN_INTENT_SELF_DESCRIPTION = "self_description"
#: C5.1 — bounded self-knowledge question families (architecture/components,
#: reference resolution, evidence/failure behaviour, current limitations,
#: research process), answered from verified internal knowledge only.
BUILTIN_INTENT_SELF_KNOWLEDGE = "self_knowledge"
#: C6.1 — bounded, READ-ONLY conversational access to EXISTING validated
#: knowledge (the kernel's ``validated_knowledge`` capability / the existing
#: ``ValidatedKnowledgeRetriever``). It answers only from claims an authorized
#: source already SUPPORTED, never acquires, never writes, never promotes a user
#: assertion, and never invents a fact.
BUILTIN_INTENT_VALIDATED_KNOWLEDGE = "validated_knowledge"
BUILTIN_INTENT_STATUS = "status"
BUILTIN_INTENT_RECALL = "recall"
BUILTIN_INTENT_CONVERSATION_RECALL = "conversation_recall"
BUILTIN_INTENT_REFERENCE = "reference"
BUILTIN_INTENT_ACKNOWLEDGEMENT = "acknowledgement"
BUILTIN_INTENT_COMMANDS = "commands"
BUILTIN_INTENT_UNSUPPORTED = "unsupported"

#: Task types this service may answer. Every governed lifecycle type is
#: excluded so the existing pipeline keeps full authority over it.
_BUILTIN_TASK_TYPES: frozenset[str] = frozenset(
    {"conversation", "unknown", "question"}
)

#: L9 — additional task types eligible for the bounded conversational-turn
#: recall surface only. Intake types the finding-recall phrases ("what did we
#: find?") as a research/information request because of the research cue
#: "find", which previously placed them outside ``_BUILTIN_TASK_TYPES`` and
#: made the deterministic recall unreachable end to end. Nothing else about an
#: information request changes: recall is still claimed only when a bounded
#: phrase matches AND a deterministic candidate exists (otherwise this service
#: declines and the existing orchestrated path applies unchanged).
_RECALL_ELIGIBLE_TASK_TYPES: frozenset[str] = frozenset({"information_request"})

#: Task types eligible for the SELF-KNOWLEDGE precedence exception only. Intake
#: types a question about Atlas's own architecture as an information/research
#: request when it merely mentions a word such as "research" or "memory" (both
#: are bounded research cues). Such a self-referential question must still be
#: answered by the deterministic self-knowledge surface rather than being sent
#: into research/orchestration. The exception is deliberately narrow: it needs
#: an Atlas self-reference AND an architecture cue AND an available model, so
#: genuine external research requests are never captured.
_SELF_KNOWLEDGE_TASK_TYPES: frozenset[str] = frozenset({"information_request"})

#: C6.1 — task types eligible for the validated-knowledge bridge only. Intake
#: types a verified-knowledge question ("what verified information do you have
#: about X?") as an information/research request because of its cue word, so the
#: bridge must also be reachable from that non-builtin task type. It is claimed
#: only by the bounded cue family below AND only with an extractable,
#: non-self-referential topic, so no other request of that type is affected.
_VALIDATED_KNOWLEDGE_TASK_TYPES: frozenset[str] = frozenset({"information_request"})

#: NLU-1 — a LEADING "help me <verb> ..." turn is a request for assistance with
#: a concrete task ("Help me create a systematic plan for reviewing a
#: smartphone camera."), not a request for Atlas's usage/help information. The
#: help intent therefore matches "help" everywhere EXCEPT when it opens the turn
#: as a "help me <something>" assistance request. Bare "help" / "help me" and
#: usage phrasings ("What can Atlas help me with?", "how do I use this?") are
#: preserved exactly.
_HELP_RE = re.compile(
    r"(?!^\s*help\s+me\s+\S)\bhelp\b|what can you do\b"
    r"|how do i (use|talk to|chat with)\b"
    r"|\bcommands\b|\busage\b|^\s*help\s*[?!.\s]*$"
)

#: Bounded identity questions. The bare "what are you" alternative is
#: TERMINAL: an identity turn is the complete question ("what are you?",
#: optionally with an identity qualifier), never a prefix of a predicate
#: question. Without the anchor, "what are you good at" was claimed as
#: identity before any capability form could be recognised.
_IDENTITY_RE = re.compile(
    r"who are you\b|what is atlas\b|your name\b|introduce yourself\b"
    r"|about yourself\b|tell me about yourself\b"
    r"|what are you(?:\s+(?:exactly|really|precisely|then))?\s*[?!.]*\s*$"
)

_CAPABILITIES_RE = re.compile(
    r"\bcapabilit(y|ies)\b|\bcapable\b|list tools\b|tools do you have\b"
    r"|what (tools|features) (do|can) you\b|show .*tools\b"
)

#: "explain/describe/tell me about <name>" — the named capability detail
#: intent. Handled conservatively: the name must resolve against a
#: registered capability or tool, otherwise the standard unsupported
#: response is used. "tell me about yourself" stays identity (checked
#: by the identity pattern first).
#:
#: The optional determiner/qualifier prefix ("the capability", "the tool")
#: is DELIBERATELY excluded from the ``name`` group, so an adorned request
#: resolves the actual registered name ("reasoning.causal") rather than
#: greedily capturing the surrounding words. An unresolved name still
#: declines (fail-closed).
_CAPABILITY_DETAIL_RE = re.compile(
    r"(?:explain|describe|what is|tell me about|how does|details? (?:on|about|for))\s+"
    r"(?:(?:the\s+)?(?:capabilit(?:y|ies)|tools?)\s+)?"
    r"(?P<name>[a-zA-Z0-9_][a-zA-Z0-9_.:\-/ ]{0,60})"
)

#: "what does <name> do?" — the natural singular capability/tool-purpose form.
#: Bounded and explicit: the ``name`` is a single identifier token (so a dotted
#: name such as ``toolchain.execute_chain`` is never split), an optional
#: determiner/qualifier prefix and an optional trailing qualifier ("the tool
#: <name>") are consumed but excluded from the name, and the request must end
#: with a whole-word "do". The name must still resolve against a registered
#: capability/tool, so an unknown name declines (fail-closed) exactly like the
#: other detail forms.
_CAPABILITY_DETAIL_DO_RE = re.compile(
    r"what does\s+"
    r"(?:the\s+)?"
    r"(?:(?:capabilit(?:y|ies)|tools?)\s+)?"
    r"(?P<name>[a-zA-Z0-9_][a-zA-Z0-9_.:\-/]*)"
    r"(?:\s+(?:capabilit(?:y|ies)|tool|tools))?"
    r"\s+do\b"
)

#: Bounded deterministic self-knowledge recognition. Selects the EXISTING
#: architecture self-knowledge surface for questions about Atlas itself
#: (architecture / components / subsystems / module dependencies). It never
#: parses arbitrary natural language and never invents facts: the renderer
#: answers only from the injected ArchitectureModel.
_ARCHITECTURE_RE = re.compile(
    r"\barchitectur(?:e|al)\b"
    r"|\bsubsystems?\b"
    r"|\bcomponents?\b"
    r"|\bsystems?\s+that\s+make\s+up\s+atlas\b"
    r"|\bmake\s+up\s+atlas\b"
    r"|\bdependenc(?:y|ies)\b"
    r"|\bdependent\s+modules?\b"
    r"|\bhow\s+(?:do|does)\s+(?:your\s+)?(?:modules|components|subsystems|systems)\b"
    r"|\bmodules?\s+(?:depend|relate|connect|fit)(?:s|d|ed|ing)?\b"
)

#: Dotted module/package identifiers inside a self-knowledge question, used to
#: resolve a SPECIFIC target through ``ArchitectureModel.locate()``. Absent a
#: resolvable target, the renderer stays bounded and reports only model counts.
_ARCHITECTURE_TARGET_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
)

#: Atlas self-reference. The literal name, or a second-person possessive bound
#: to a self-knowledge noun ("your architecture", "your components"). Bounded:
#: it identifies WHO the question is about, not an arbitrary keyword.
_SELF_REFERENCE_RE = re.compile(
    r"\batlas\b"
    r"|\byour\s+(?:architectur(?:e|al)|components?|subsystems?|modules?|"
    r"dependenc(?:y|ies)|design|structure|systems?)\b"
)

#: A leading imperative research verb. A self-referential turn that *begins*
#: with one is a genuine request to research something external, so the
#: self-knowledge precedence exception must not capture it.
_LEADING_RESEARCH_RE = re.compile(
    r"^\s*(?:research|find|search|look\s*up|lookup|investigate)\b"
)

#: Process/flow wording for "how does a request move through Atlas?". Broader
#: than a structural noun, so the caller additionally requires an Atlas
#: self-reference — a generic "how does a request flow" question about some
#: other system must not become self-knowledge.
_ARCHITECTURE_PROCESS_RE = re.compile(
    r"\b(?:request|message|prompt|turn|input)s?\s+"
    r"(?:mov|flow|travel|pass|get\s+processed|get\s+handled)\w*\b"
    r"|\bprocess(?:es|ed|ing)?\s+(?:a\s+|the\s+|my\s+)?"
    r"(?:request|message|prompt|input)s?\b"
)

#: C5.1 — bounded self-reference for a self-knowledge question. Only the
#: question families below use it; it identifies WHO the question is about.
_SELF_REFERENCE_ANY_RE = re.compile(r"\b(?:you|your|yours|yourself|atlas)\b")

#: C5.1 — the capability WORDS that caused the C3 domain misroute. The
#: first-person capability aliases (e.g. "what can you do") are deliberately
#: NOT covered here, so their existing behaviour is untouched.
_CAPABILITY_WORD_RE = re.compile(r"\bcapabilit(?:y|ies)\b|\bcapable\b")

#: C5.1 — a DOMAIN (non-Atlas) capability reference: a third-person possessive
#: or a demonstrative bound to a product/device noun. Used only to keep domain
#: questions ("its cameras are capable", "this phone's capabilities") out of the
#: Atlas self-inventory.
_CAPABILITY_DOMAIN_REFERENCE_RE = re.compile(
    r"\b(?:its|their)\s+\w+"
    r"|\b(?:this|that|these|those)\s+(?:phone|phones|smartphone|smartphones|"
    r"device|devices|product|products|laptop|laptops|tablet|tablets|camera|"
    r"cameras|model|models|gadget|gadgets|item|items|monitor|display|console)\b"
)

#: C5.1 — the bounded self-knowledge question families evidenced by C3. Each
#: entry is ``(topic, cue pattern, verified anchor module paths)``. The cue
#: pattern must be paired with an Atlas self-reference, and the anchors are
#: VERIFIED against the ArchitectureModel before any behaviour is described, so
#: an answer is only produced from knowledge the architecture actually records.
#: (The architecture/components family is served by the EXISTING architecture
#: surface; see ``_ARCHITECTURE_PARTS_RE``.)
_SELF_KNOWLEDGE_TOPICS: tuple[
    tuple[str, "re.Pattern[str]", tuple[str, ...]], ...
] = (
    (
        "reference resolution",
        re.compile(
            r"\breference\s+resolution\b"
            r"|\bresolve\s+(?:references?|pronouns?)\b"
            r"|\bresolve\s+(?:its|it|this|that)\b"
            r"|\bhow\s+(?:do|does)\s+(?:you|atlas)\s+resolve\b"
        ),
        (
            "atlas.conversation.reference_resolution",
            "atlas.conversation.entity_capture",
        ),
    ),
    (
        "evidence and failure behaviour",
        re.compile(
            r"\b(?:not\s+enough|no|insufficient|lack\w*|without)\s+"
            r"(?:authorized\s+|relevant\s+|available\s+|enough\s+)?evidence\b"
            r"|\bwhen\s+you\s+(?:don'?t|cannot|can'?t)\s+"
            r"(?:have|find|get|obtain)\b"
            r"|\bcannot\s+find\s+evidence\b"
        ),
        (
            "atlas.orchestration.executor",
            "atlas.research.relevance",
            "atlas.research.acquisition",
        ),
    ),
    (
        "current limitations",
        re.compile(
            r"\blimitations?\b"
            r"|\bwhat\s+(?:can'?t|cannot)\s+you\s+(?:currently\s+|presently\s+)?do\b"
            r"|\bwhat\s+are\s+you\s+(?:not\s+able|unable)\s+to\s+do\b"
        ),
        (
            "atlas.self_knowledge.architecture_model",
            "atlas.self_knowledge.capability_model",
        ),
    ),
    (
        "research process",
        re.compile(
            r"\bresearch\s+(?:process|pipeline|flow|workflow)\b"
            r"|\bhow\s+(?:do|does)\s+(?:you|atlas)\b[^.?]{0,60}\bresearch\b"
            r"|\bhow\s+(?:you|atlas)\s+(?:do|perform|conduct|run)s?\s+research\b"
        ),
        (
            "atlas.research.acquisition",
            "atlas.research.coordinator",
            "atlas.research.sources.web",
            "atlas.orchestration.executor",
        ),
    ),
)


def _match_self_knowledge_topic(lowered: str) -> str | None:
    """Return the bounded self-knowledge topic for ``lowered``, or None.

    A topic is claimed only when its cue pattern AND an Atlas self-reference are
    both present, so a domain question about some other system is never captured.
    """
    if not _SELF_REFERENCE_ANY_RE.search(lowered):
        return None
    for topic, pattern, _anchors in _SELF_KNOWLEDGE_TOPICS:
        if pattern.search(lowered):
            return topic
    return None


def _self_knowledge_anchors(topic: str) -> tuple[str, ...]:
    """Return the verified anchor module paths recorded for ``topic``."""
    for name, _pattern, anchors in _SELF_KNOWLEDGE_TOPICS:
        if name == topic:
            return anchors
    return ()


#: C5.1 — plain-language structural phrasing evidenced by C3 ("what parts of
#: your system handle conversation?"). Self-referential by construction ("your"),
#: so it cannot capture a question about some other system.
_ARCHITECTURE_PARTS_RE = re.compile(
    r"\bparts?\s+of\s+your\s+(?:system|architecture|codebase|design|framework)\b"
)

_STATUS_RE = re.compile(
    r"\bstatus\b|how are you\b|are you (ok|okay|online|working|up|running)\b"
    r"|system (status|health)\b|how is atlas\b"
)

#: Deterministic memory/knowledge recall. Conservative trigger phrases
#: only; the lookup itself is a verbatim keyword search over the injected
#: stores. Anything genuinely ambiguous falls through to unsupported.
_RECALL_RE = re.compile(
    r"\b(?:do you )?(?:remember|recall)\b|what do you (?:know|remember) about\b"
    r"|\b(?:can you\s+)?remind me\b"
    r"|\bwhat did we (?:discover|find|learn)(?: about)?\b"
    r"|search (?:your )?(?:memory|knowledge)(?: for)?\b"
    r"|look up .*?(?:in|from) (?:your )?(?:memory|knowledge)\b"
)

# ---------------------------------------------------------------------------
# C6.1 — bounded conversational access to EXISTING validated knowledge.
#
# The kernel already owns an evidence-validated, provenance-carrying, persistent
# knowledge store and exposes it read-only through ``validated_knowledge(query)``.
# This bridge makes that EXISTING capability reachable from a turn, and nothing
# more: it is a bounded cue vocabulary + a bounded topic extraction, answered
# exclusively by the injected validated-knowledge provider.
#
# Two cue tiers, because precedence must be preserved exactly:
#
#   * EXPLICIT cues ("what did you find/learn about X", "what verified
#     information do you have about X") are NOT claimed by any existing intent.
#     They are claimed whenever a usable topic exists, and report the retrieval's
#     own authoritative outcome (validated claims / empty / store unavailable).
#
#   * SHARED cues ("what do you know about X", "what do you remember about X",
#     "do you remember X") ARE claimed by the existing memory/knowledge recall.
#     They are therefore bridged ONLY when an already-validated claim actually
#     matches; otherwise this matcher declines and the existing recall path
#     answers exactly as before.
# ---------------------------------------------------------------------------

#: C6.1 — explicit verified-knowledge cues (no existing intent claims these).
#: Every cue requires the bounded "about" topic marker, so topic-less phrasings
#: ("what did you learn from that research?", "what did you find?") are NOT
#: bridged and keep their existing behaviour exactly.
_VALIDATED_KNOWLEDGE_EXPLICIT_CUES: tuple["re.Pattern[str]", ...] = (
    re.compile(
        r"what\s+(?:information|knowledge)\s+(?:did|have)\s+you\s+"
        r"(?:verif(?:y|ied)|validat(?:e|ed)|confirm(?:ed)?)\s+about\b"
    ),
    re.compile(
        r"what\s+did\s+you\s+(?:verif(?:y|ied)|validat(?:e|ed)|confirm)\s+about\b"
    ),
    re.compile(
        r"what\s+have\s+you\s+(?:verif(?:y|ied)|validat(?:e|ed)|confirm)\s+about\b"
    ),
    re.compile(
        r"what\s+(?:verified|validated|confirmed)\s+(?:information|knowledge|facts?)\b"
    ),
    re.compile(r"what\s+did\s+you\s+(?:find(?:\s+out)?|learn|discover)\s+about\b"),
    re.compile(
        r"what\s+facts?\s+did\s+you\s+(?:verif(?:y|ied)|validat(?:e|ed))\s+about\b"
    ),
)

#: C6.1 — cues shared with the existing memory/knowledge recall. Bridged only on
#: an actual validated match, so recall behaviour is unchanged otherwise.
_VALIDATED_KNOWLEDGE_SHARED_CUES: tuple["re.Pattern[str]", ...] = (
    re.compile(r"what\s+do\s+you\s+(?:know|remember)\s+about\b"),
    re.compile(r"\bdo\s+you\s+remember\b"),
    re.compile(r"what\s+(?:information|knowledge)\s+do\s+you\s+have\s+about\b"),
)

#: C6.1 — determiners/lead words dropped from a validated-knowledge topic.
_TOPIC_LEAD_WORDS: frozenset[str] = frozenset({"about", "on", "regarding", "the", "a", "an"})

#: C6.1 — bounded function words dropped from a topic so the query stays a tight
#: token set (the retriever matches only claims containing every query token).
#: "you" is dropped because a cue's own tail ("…do you have about X") would
#: otherwise leave an assistant-reference token inside the topic.
_TOPIC_STOP_WORDS: frozenset[str] = frozenset(
    {
        "about", "and", "any", "are", "at", "be", "been", "by", "did", "do",
        "does", "for", "from", "had", "has", "have", "how", "in", "is", "it",
        "its", "of", "on", "or", "that", "the", "their", "them", "these",
        "this", "those", "to", "was", "were", "what", "when", "where", "which",
        "who", "why", "with", "you",
    }
)

#: C6.1 — a topic about Atlas ITSELF belongs to the existing self-knowledge /
#: identity surfaces, never to this bridge.
_TOPIC_SELF_REFERENCE_RE = re.compile(
    r"\b(?:you|your|yours|yourself|yourselves|your\s+own)\b"
)

#: C6.1 — a bare "atlas" topic, or "atlas <self-noun>", is a self-question. A
#: third-party subject that merely begins with the word (a device/test subject
#: named "Atlas …") is not captured here.
_TOPIC_ATLAS_SELF_RE = re.compile(
    r"^atlas$"
    r"|\batlas\b(?:\s+\w+){0,2}\s+"
    r"(?:architectur\w*|components?|subsystems?|modules?|design|codebase|"
    r"systems?|implementation|internals?|limitations?|capabilit(?:y|ies))\b"
)

#: C6.1 — bounds applied to an extracted topic.
_MAX_VALIDATED_TOPIC_TOKENS: int = 8
_MAX_VALIDATED_TOPIC_CHARS: int = 60

#: C6.1 — bounded render bound for a validated claim statement.
_MAX_VALIDATED_CLAIM_CHARS: int = 500


def _validated_knowledge_topic(remainder: str) -> str | None:
    """Extract a bounded topic from the text following a cue, or None.

    Deterministic and conservative: the topic never crosses a clause boundary,
    is reduced to a small token set, and is REJECTED whenever it refers to Atlas
    itself (those questions belong to the existing self-knowledge surfaces).
    A cue without a usable topic fails closed (``None``) — the store is never
    queried with an empty or arbitrary input merely to produce an answer.
    """
    text = remainder
    for stop in ("?", ".", "!", ";", ":"):
        index = text.find(stop)
        if index != -1:
            text = text[:index]
    tokens = [
        token
        for token in re.split(r"[^a-z0-9_]+", text)
        if token and token not in _TOPIC_STOP_WORDS
    ]
    while tokens and tokens[0] in _TOPIC_LEAD_WORDS:
        tokens.pop(0)
    tokens = [token for token in tokens if len(token) >= 2 or token.isdigit()]
    if not tokens:
        return None
    topic = " ".join(tokens[:_MAX_VALIDATED_TOPIC_TOKENS])
    if len(topic) > _MAX_VALIDATED_TOPIC_CHARS:
        topic = topic[:_MAX_VALIDATED_TOPIC_CHARS].rstrip()
    if _TOPIC_SELF_REFERENCE_RE.search(topic) or _TOPIC_ATLAS_SELF_RE.search(topic):
        return None
    return topic


def _match_validated_knowledge_cue(lowered: str) -> tuple[str, bool] | None:
    """Return ``(query, explicit)`` for a bounded validated-knowledge turn.

    Explicit cues are checked first. ``explicit`` is True when no existing
    intent claims the phrasing, so the turn reports the retrieval's own outcome
    directly; shared cues are bridged only on an actual validated match.
    """
    for explicit, cues in (
        (True, _VALIDATED_KNOWLEDGE_EXPLICIT_CUES),
        (False, _VALIDATED_KNOWLEDGE_SHARED_CUES),
    ):
        for cue in cues:
            match = cue.search(lowered)
            if match is None:
                continue
            query = _validated_knowledge_topic(lowered[match.end() :])
            if query is None:
                return None
            return (query, explicit)
    return None


# ---------------------------------------------------------------------------
# Phase 5 — bounded conversational-turn recall.
#
# A capability DISTINCT from the ``_RECALL_RE`` memory/knowledge-store recall
# above. These patterns ask about the recent CONVERSATION itself; they are
# answered only from the bounded ConversationContext plus structured state,
# never from the memory/knowledge stores, and never by inventing content.
# ---------------------------------------------------------------------------

#: "What did I ask/say previously?" — previous user request.
_CONVERSATION_RECALL_USER_RE = re.compile(
    r"\bwhat did i (?:ask|ask you|say|request|mention)\b"
    r"|\bwhat was my (?:last|previous|earlier) (?:question|request|message|ask)\b"
    r"|\bremind me what i (?:asked|said)\b"
)

#: "What did you just tell me?" — previous Atlas response.
_CONVERSATION_RECALL_ASSISTANT_RE = re.compile(
    r"\bwhat did you (?:just )?(?:say|tell me)\b"
    r"|\bwhat was your (?:last|previous|earlier) (?:response|answer|message|reply)\b"
    r"|\bremind me what you (?:said|told me)\b"
)

#: "What were we discussing?" — recent conversation topic.
_CONVERSATION_RECALL_TOPIC_RE = re.compile(
    r"\bwhat (?:were|are) we (?:discussing|talking about|chatting about)\b"
    r"|\bwhat did we discuss\b"
    r"|\bwhat have we been (?:discussing|talking about)\b"
    r"|\bwhat was the recent (?:topic|subject)\b"
    r"|\bremind me what we (?:were discussing|discussed)\b"
    # L10 — evidenced in L9: "Do you remember what we discussed?" is a topic
    # recall, not a store lookup for the literal phrase "what discussed".
    r"|\b(?:do you )?remember what we (?:were discussing|discussed)\b"
)

#: "What did we find?" — recent governed finding/result.
_CONVERSATION_RECALL_FINDING_RE = re.compile(
    r"\bwhat did we (?:just )?find\b"
    r"|\bwhat (?:issue|problem|finding) did we (?:find|discuss)\b"
    r"|\bwhat was the (?:issue|problem) we (?:just )?discussed\b"
)

#: Bounded lead cues marking a prior user turn as a conversation subject.
_CONVERSATION_SUBJECT_LEAD_RE = re.compile(
    r"\b(?:investigate|investigation|analyze|analyse|diagnose|inspect"
    r"|examine|trace|debug)\b"
)

#: Provenance label per conversational-recall source.
_CONVERSATION_RECALL_LABELS: dict[str, str] = {
    "user": "You asked earlier:",
    "assistant": "I said:",
    "topic": "We were discussing:",
    "finding": "The most recent result:",
}

#: Bound applied to recalled turn content in the rendered answer.
_MAX_CONVERSATION_RECALL_CHARS: int = 400

# ---------------------------------------------------------------------------
# Stage A — consume already-bound contextual evidence.
#
# When the deterministic resolver ALREADY resolved a conversational reference,
# the referent is attached to ``TaskSpec.context`` as ``resolved_reference``
# (``{"field": ..., "value": ...}``). This layer only *restates* that bound
# fact. It never re-resolves, never guesses, and never consults a referent the
# resolver did not bind.
# ---------------------------------------------------------------------------

#: Restatement label per consumable referent field. Only genuine
#: :class:`ConversationState` facts that the resolver can bind are listed, so a
#: referent outside this bounded set declines and the unchanged unsupported
#: behavior applies. The Phase 4 contextual label ``context_subject`` is
#: deliberately absent: it is a derived contextual referent, not a stored state
#: fact, and restating it would assert an identity rather than report state.
_REFERENCE_LABELS: dict[str, str] = {
    "latest_result": "The most recent result:",
    "current_investigation": "The active investigation:",
    "current_task": "The active task:",
    "current_subject": "The current subject:",
    "development_intent": "The current development intent:",
    "relevant_prior_action": "The most recent action:",
    "pending_question": "The question awaiting an answer:",
    "pending_confirmation": "The pending confirmation:",
}

#: Bound applied to the restated referent value in the rendered answer.
_MAX_REFERENCE_CHARS: int = 400

#: Supported-command inquiry. Answered from the fixed, actually-existing
#: CLI command surfaces (never invented).
_COMMANDS_RE = re.compile(
    r"\bcommands?\b|what (?:can|should) i (?:type|say|ask|do)(?: next)?\b"
    r"|how do i (?:use|talk to|chat with|operate) (?:you|atlas)\b"
    r"|safe next steps?\b|what .*options? do i have\b"
)

#: Same greeting vocabulary as TaskIntake; greetings are the weakest match
#: and are only answered when no stronger intent matched.
_GREETING_RE = re.compile(
    r"\b(?:hello|hi|hey)\b|how are you\b|good morning|good afternoon"
    r"|good evening|nice to meet you"
)

# ---------------------------------------------------------------------------
# Bounded intent aliases (Phase 2).
#
# Explicit, readable phrase families for EXISTING conversational intents. Each
# alias is a bounded, word-boundary regex — never a fuzzy/substring match — so
# unrelated sentences are not captured. Aliases only select an existing
# intent; they never grant authority or execute anything.
# ---------------------------------------------------------------------------

#: Capability questions clearly equivalent to the canonical capability surface.
#: The "what can you <adverb> do" family deliberately requires the adverb so the
#: canonical "what can you do" help phrasing is left unchanged.
_CAPABILITY_ALIAS_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat can you (?:currently|actually|really|now|presently) do\b"),
    re.compile(r"\bwhat can you help(?: me)? with\b"),
    re.compile(r"\bwhat can atlas help(?: me)? with\b"),
    re.compile(r"\bwhat are you (?:able|capable)\b"),
    re.compile(r"\bwhat are you (?:good|best|better) at\b"),
    re.compile(
        r"\bwhat (?:are|is) your (?:current |present |existing |main )?"
        r"(?:abilities|capabilities|skills)\b"
    ),
    re.compile(
        r"\b(?:give me )?an? overview of your (?:current )?"
        r"(?:abilities|capabilities|skills)\b"
    ),
    re.compile(
        r"\btell me what you can (?:actually |really |currently |now )?do\b"
    ),
    # L10 — evidenced in L9: "Can you tell me what you're able to do?" is the
    # same capability question, phrased with a contraction and "able to do".
    re.compile(r"\bwhat (?:you're|you are) able to do\b"),
)

#: Narrow identity phrasings equivalent to the canonical identity surface.
_IDENTITY_ALIAS_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat (?:exactly )?is atlas\b"),
)

#: Phase 2.9 — bounded natural self-description phrasings ("what does Atlas
#: do", "how does Atlas work"). These ask what Atlas IS/DOES rather than a
#: structural architecture question, and are answered from the EXISTING
#: self-knowledge models (never a second, drift-prone hand-written
#: description). Word-boundary and bounded by construction.
_SELF_DESCRIPTION_RE = re.compile(
    r"\bwhat\s+(?:does\s+atlas\s+do|atlas\s+does)\b"
    r"|\bexplain\s+(?:what\s+)?atlas\s+(?:does|is)\b"
    r"|\bhow\s+(?:does|do)\s+(?:atlas|you)\s+(?:work|operate|function)\b"
)

#: Status phrasings equivalent to the canonical status surface.
_STATUS_ALIAS_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bhow are things (?:looking|going)\b"),
    re.compile(
        r"\bwhat(?:'s| is) (?:going on|happening) with (?:your|the) system\b"
    ),
    # L10 — evidenced in L9: "what's going on right now" is a status question.
    re.compile(r"\bwhat(?:'s| is) going on(?: right now| right here)?\b"),
)

#: Bounded casual acknowledgement/gratitude exchanges (L10). Anchored to the
#: WHOLE turn: a turn that carries an instruction after the acknowledgement
#: ("ok, now investigate X") is not an acknowledgement and keeps its handling.
_ACKNOWLEDGEMENT_RE = re.compile(
    r"^\s*(?:"
    r"thanks(?:\s+(?:a lot|so much|very much))?|"
    r"thank you(?:\s+(?:very much|so much))?|many thanks|cheers|ta|"
    r"ok|okay|got it|understood|noted|"
    r"nice one|perfect|great|cool|awesome|brilliant|"
    r"sorry|my mistake|no problem|no worries"
    r")"
    r"(?:\s*[,\-]?\s*(?:that helps|that's helpful|thanks|"
    r"thank you(?:\s+very much)?|cheers|nice one|my mistake))?"
    r"\s*[.!?]*\s*$"
)

#: Gratitude sub-form of an acknowledgement (selects the rendering only).
_GRATITUDE_RE = re.compile(r"\b(?:thanks|thank you|cheers|ta)\b")


def _alias_hit(
    patterns: tuple[re.Pattern[str], ...],
    text: str,
) -> bool:
    """True when ``text`` matches one of the bounded alias patterns."""
    return any(pattern.search(text) for pattern in patterns)

_MAX_TOOLS_LISTED = 20

#: Bounds applied to the self-knowledge renderer so an architecture answer is a
#: concise, bounded summary and never a raw repository dump.
_MAX_ARCHITECTURE_SUBSYSTEMS = 8
_MAX_ARCHITECTURE_RELATIONS = 8
_MAX_ARCHITECTURE_LIMITATIONS = 3

#: C5.1 — bounded bare-token topic lookup for the architecture renderer.
#: The stop-set keeps question/self/structural words out, so a generic
#: "what are Atlas's components?" question is not turned into a lookup of the
#: literal top-level package, and only a genuine TOPIC token is tried.
_ARCHITECTURE_TOPIC_TOKEN_RE = re.compile(r"[a-z][a-z_]{3,}")
_MAX_ARCHITECTURE_TOPIC_TOKENS = 6
_ARCHITECTURE_TOPIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "atlas", "you", "your", "yours", "yourself", "what", "which", "who",
        "whom", "does", "do", "are", "is", "was", "the", "and", "for", "with",
        "that", "this", "these", "those", "from", "into", "over", "under",
        "handle", "handles", "handled", "implement", "implements", "implemented",
        "component", "components", "module", "modules", "subsystem",
        "subsystems", "part", "parts", "system", "systems", "about", "tell",
        "explain", "describe", "current", "currently", "work", "works",
        "working", "made", "make", "madeup", "consist", "consists", "comprise",
        "comprises", "include", "includes", "included", "structure", "design",
        "codebase", "framework", "architecture",
    }
)


def _enum_values(enum_cls: object) -> str:
    """Return an enum's value set as a bounded comma-separated string (C5.1).

    Used to state only the value vocabulary the architecture itself defines; an
    unavailable enum yields "(unavailable)" rather than an invented value.
    """
    try:
        return ", ".join(sorted(str(member.value) for member in enum_cls))
    except Exception:  # noqa: BLE001
        return "(unavailable)"


def _format_names(names: object) -> str:
    """Render a bounded sequence of identifiers as ``a, `b` ...`` (or '')."""
    items = [f"`{name}`" for name in (names or ())]
    return ", ".join(items)


class BuiltinResponseService:
    """Deterministic built-in conversational responder.

    Answers the bounded intent set from injected Atlas state only. Never
    calls a model, never invents capabilities, never mutates anything.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        knowledge_manager: KnowledgeManager | None = None,
        capability_registry: CapabilityRegistry | None = None,
        memory_service: MemoryManagerService | None = None,
        service_names: (
            list[str]
            | tuple[str, ...]
            | Callable[[], list[str] | tuple[str, ...]]
            | None
        ) = None,
        started: bool | None = None,
        architecture_model_provider: Callable[[], Any] | None = None,
        validated_knowledge_provider: Callable[[str], Any] | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._knowledge_manager = knowledge_manager
        self._capability_registry = capability_registry
        self._memory_service = memory_service
        self._service_names = service_names
        self._started = started
        #: WS — optional zero-argument callable returning an already-built
        #: ``ArchitectureModel`` (or None). Read-only and advisory: it supplies
        #: structural self-knowledge for the bounded architecture intent only,
        #: is never mutated or persisted, and fails soft to the unsupported
        #: floor when absent, None, non-model, or raising.
        self._architecture_model_provider = architecture_model_provider
        #: C6.1 — optional one-argument callable delegating to the EXISTING
        #: kernel validated-knowledge capability (``kernel.validated_knowledge``).
        #: Read-only by contract: it is called for retrieval only, its result is
        #: never mutated, and the bridge is simply declined when it is absent or
        #: raises (fail closed — no fallback to memory, state, or a model).
        self._validated_knowledge_provider = validated_knowledge_provider

    def _resolve_service_names(self) -> tuple[str, ...] | None:
        """Resolve the container/service snapshot for the status answer.

        A sequence is used as the eager snapshot it has always been; a lazy
        zero-argument provider is resolved on demand, so a kernel that
        registers services after construction is still observed accurately.
        """
        names = self._service_names
        if callable(names):
            try:
                names = names()
            except Exception:
                return None
        if names is None:
            return None
        return tuple(sorted(names))

    @property
    def tool_registry(self) -> ToolRegistry | None:
        return self._tool_registry

    @property
    def knowledge_manager(self) -> KnowledgeManager | None:
        return self._knowledge_manager

    @property
    def capability_registry(self) -> CapabilityRegistry | None:
        return self._capability_registry

    @property
    def memory_service(self) -> MemoryManagerService | None:
        return self._memory_service

    @property
    def architecture_model_provider(self) -> Callable[[], Any] | None:
        return self._architecture_model_provider

    @property
    def validated_knowledge_provider(self) -> Callable[[str], Any] | None:
        return self._validated_knowledge_provider

    def handles(
        self,
        text: str,
        spec: TaskSpec | None = None,
    ) -> bool:
        """True when this service should answer ``text`` deterministically."""
        return self._classify(text, spec) is not None

    def respond(
        self,
        text: str,
        spec: TaskSpec | None = None,
        session_context: SessionContext | None = None,
        message_count: int | None = None,
        context: ConversationContext | None = None,
    ) -> Message | None:
        """Build a deterministic assistant Message, or None to continue.

        Returns None when the turn belongs to the governed pipeline (typed
        lifecycle request, needs-clarification spec), so ``send``/``stream``
        fall through to the existing handling unchanged.

        ``context`` is the bounded, read-only :class:`ConversationContext`
        projection of recent conversation history/state. Phase 3 only
        *accepts* it: the deterministic responses are unchanged, and the value
        is never mutated, executed, or used to authorize anything.
        """
        classified = self._classify(text, spec, context)
        if classified is None:
            return None
        if isinstance(classified, tuple):
            intent, detail = classified
        else:
            intent, detail = classified, None
        content = self._render(intent, message_count=message_count, detail=detail)
        metadata: dict[str, Any] = {
            "builtin_response": True,
            "builtin_intent": intent,
            "model_used": False,
        }
        if intent == BUILTIN_INTENT_CONVERSATION_RECALL and isinstance(detail, tuple):
            metadata["recall_source"] = detail[0]
        if intent == BUILTIN_INTENT_VALIDATED_KNOWLEDGE and isinstance(detail, tuple):
            metadata["validated_query"] = detail[0]
            metadata["validated_knowledge_status"] = self._validated_knowledge_status(
                detail[1]
            )
        if intent == BUILTIN_INTENT_REFERENCE and isinstance(detail, tuple):
            metadata["reference_field"] = detail[0]
        return Message(
            role="assistant",
            content=content,
            metadata=metadata,
        )

    def respond_stream(
        self,
        text: str,
        spec: TaskSpec | None = None,
        session_context: SessionContext | None = None,
        message_count: int | None = None,
        context: ConversationContext | None = None,
    ) -> Iterator[str]:
        """Yield the deterministic response content as a single chunk."""
        msg = self.respond(
            text,
            spec=spec,
            session_context=session_context,
            message_count=message_count,
            context=context,
        )
        if msg is None:
            return
        yield msg.content

    def _classify(
        self,
        text: str,
        spec: TaskSpec | None,
        context: ConversationContext | None = None,
    ) -> str | tuple[str, object] | None:
        """Classify a turn into a builtin intent.

        Returns an intent name, an ``(intent, detail)`` tuple for intents
        that carry a resolved argument (capability detail, store recall query,
        conversational-turn recall), or ``None`` when the turn belongs
        elsewhere. Conservative by design: anything that does not match a
        bounded trigger with a resolvable argument becomes the honest
        unsupported response.

        ``context`` is the bounded, read-only :class:`ConversationContext`; it
        is consulted only for conversational-turn recall (Phase 5).
        """
        lowered = canonicalize_surface(text).lower()
        if not lowered:
            return BUILTIN_INTENT_UNSUPPORTED
        if spec is not None:
            task_type = getattr(spec.task_type, "value", "") or ""
            if task_type not in _BUILTIN_TASK_TYPES:
                # L9 — the bounded conversational-turn recall stays reachable
                # for recall-eligible task types. Only an already-deterministic
                # candidate is claimed; every other turn of these types is
                # returned to its existing path unchanged (fail closed).
                if task_type in _RECALL_ELIGIBLE_TASK_TYPES:
                    recall = self._match_conversation_recall(lowered, context)
                    if recall is not None:
                        return (BUILTIN_INTENT_CONVERSATION_RECALL, recall)
                # SELF-KNOWLEDGE PRECEDENCE (routing seam). Intake types a
                # question about Atlas's own architecture as an external
                # information/research request whenever it merely mentions a
                # bounded research cue ("research", "memory", "find", ...).
                # Such a self-referential question must be answered by the
                # deterministic self-knowledge surface, not sent into
                # research/orchestration. Narrow by construction: an Atlas
                # self-reference AND an architecture cue AND an available
                # model. A genuine external research request has no Atlas
                # self-reference, so it is never captured here.
                # C5.1 — the same precedence extends to the bounded
                # self-knowledge question families (reference resolution,
                # evidence/failure behaviour, current limitations, research
                # process), so a self-referential question that Intake typed as
                # a research request is answered by the self-knowledge surface
                # instead of being sent into research/orchestration.
                if (
                    task_type in _SELF_KNOWLEDGE_TASK_TYPES
                    and not _LEADING_RESEARCH_RE.search(lowered)
                    and self._resolve_architecture_model() is not None
                ):
                    if _SELF_REFERENCE_RE.search(
                        lowered
                    ) and self._matches_architecture(lowered):
                        return (BUILTIN_INTENT_ARCHITECTURE, text)
                    topic = _match_self_knowledge_topic(lowered)
                    if topic is not None:
                        return (BUILTIN_INTENT_SELF_KNOWLEDGE, topic)
                # C6.1 — the same precedence seam carries the bounded
                # validated-knowledge bridge: Intake types a verified-knowledge
                # question ("what verified information do you have about X?") as
                # an information/research request, and it must be answered from
                # the EXISTING validated store instead of being sent into
                # research/orchestration. A leading research verb keeps its
                # authority, and a topic about Atlas itself was already left to
                # the self-knowledge surfaces above.
                if task_type in _VALIDATED_KNOWLEDGE_TASK_TYPES and not (
                    _LEADING_RESEARCH_RE.search(lowered)
                ):
                    validated = self._match_validated_knowledge(lowered)
                    if validated is not None:
                        return (BUILTIN_INTENT_VALIDATED_KNOWLEDGE, validated)
                return None
            if bool(getattr(spec, "needs_clarification", False)):
                return None
        if _COMMANDS_RE.search(lowered):
            return BUILTIN_INTENT_COMMANDS
        # A *resolvable* named-capability/tool detail request outranks the
        # generic inventory matcher: the bare word "capability"/"tool" in an
        # adorned request ("explain the capability reasoning.causal") must not
        # steal a genuinely named request. An unresolved name returns None here
        # and falls through unchanged, so inventory/help/identity behavior and
        # fail-closed semantics are preserved exactly.
        detail = self._match_capability_detail(lowered)
        if detail is not None:
            return (BUILTIN_INTENT_CAPABILITY_DETAIL, detail)
        # Bounded capability aliases precede help/identity: genuinely
        # equivalent capability questions must not be captured by the help
        # word ("... help me with") or by the identity predicate's
        # "what are you" ("what are you capable of").
        # C5.1 — the bare capability WORD must be a first-person/Atlas question:
        # a domain question about an external subject's capabilities is not an
        # Atlas self-capability question (C3 finding). The first-person aliases
        # below are unaffected.
        capabilities_word = _CAPABILITIES_RE.search(lowered) is not None
        if capabilities_word and not self._capabilities_intent_applies(
            lowered, context
        ):
            capabilities_word = False
        if capabilities_word or _alias_hit(_CAPABILITY_ALIAS_RES, lowered):
            return BUILTIN_INTENT_CAPABILITIES
        if _HELP_RE.search(lowered):
            return BUILTIN_INTENT_HELP
        if _IDENTITY_RE.search(lowered) or _alias_hit(
            _IDENTITY_ALIAS_RES, lowered
        ):
            return BUILTIN_INTENT_IDENTITY
        # Phase 2.9 — bounded natural self-description ("what does Atlas do",
        # "how does Atlas work"). Placed after the established identity /
        # capability / help surfaces so their precedence is preserved, and
        # answered from the EXISTING self-knowledge models (no second
        # description). Claimed only when a model is available; otherwise the
        # turn falls through to the existing unsupported floor (fail-soft).
        if _SELF_DESCRIPTION_RE.search(lowered) and (
            self._resolve_architecture_model() is not None
        ):
            return (BUILTIN_INTENT_SELF_DESCRIPTION, text)
        # C5.1 — bounded self-knowledge question families (reference
        # resolution, evidence/failure behaviour, current limitations, research
        # process). Claimed only when an already-built ArchitectureModel is
        # available, so the answer is grounded in verified knowledge or the turn
        # falls soft to the existing unsupported floor.
        self_knowledge_topic = _match_self_knowledge_topic(lowered)
        if self_knowledge_topic is not None and (
            self._resolve_architecture_model() is not None
        ):
            return (BUILTIN_INTENT_SELF_KNOWLEDGE, self_knowledge_topic)
        # Bounded architecture self-knowledge (WS). Reached only by turns the
        # inventory/help/identity surfaces above did not claim, so it cannot
        # steal them. It is claimed ONLY when an already-built ArchitectureModel
        # is actually available; otherwise the turn falls through to the
        # existing unsupported floor (fail-soft, no partial/empty claim).
        if self._matches_architecture(lowered) and (
            self._resolve_architecture_model() is not None
        ):
            return (BUILTIN_INTENT_ARCHITECTURE, text)
        if _STATUS_RE.search(lowered) or _alias_hit(
            _STATUS_ALIAS_RES, lowered
        ):
            return BUILTIN_INTENT_STATUS
        # Conversational-turn recall (Phase 5) precedes store recall: it claims
        # only phrases about the recent conversation, and only when a
        # deterministic candidate exists (otherwise it falls through to the
        # unchanged store/memory recall path).
        conversation_recall = self._match_conversation_recall(lowered, context)
        if conversation_recall is not None:
            return (BUILTIN_INTENT_CONVERSATION_RECALL, conversation_recall)
        # C6.1 — bounded bridge to EXISTING validated knowledge. Reached only
        # after every self/inventory/help/identity/self-knowledge surface above,
        # so all of them keep their precedence, and before store recall. Shared
        # recall phrasings ("what do you know about X") are bridged ONLY when an
        # already-validated claim matches; otherwise this declines and the
        # existing memory/knowledge recall answers exactly as before.
        validated = self._match_validated_knowledge(lowered)
        if validated is not None:
            return (BUILTIN_INTENT_VALIDATED_KNOWLEDGE, validated)
        recall_query = self._match_recall(lowered)
        if recall_query is not None:
            return (BUILTIN_INTENT_RECALL, recall_query)
        if _GREETING_RE.search(lowered):
            return BUILTIN_INTENT_GREETING
        # Bounded casual acknowledgement (L10). No action, no state change.
        if _ACKNOWLEDGEMENT_RE.search(lowered):
            return (
                BUILTIN_INTENT_ACKNOWLEDGEMENT,
                "thanks" if _GRATITUDE_RE.search(lowered) else "acknowledged",
            )
        # Stage A — restate an ALREADY-resolved reference last: every existing
        # intent above keeps precedence, and only evidence the deterministic
        # resolver actually bound is consumed. Weakest match, fail closed.
        resolved_reference = self._match_resolved_reference(spec)
        if resolved_reference is not None:
            return (BUILTIN_INTENT_REFERENCE, resolved_reference)
        task_type = (
            getattr(spec.task_type, "value", "") if spec is not None else ""
        )
        if task_type in ("", "conversation", "unknown", "question"):
            return BUILTIN_INTENT_UNSUPPORTED
        return None

    def _match_capability_detail(self, lowered: str) -> str | None:
        """Resolve a named-capability reference, or None when unknown.

        Conservative: the candidate name must resolve — case-insensitively,
        allowing ``.``/``_``/``-``/space variants — to a registered
        capability handler or tool. Anything else is not a confident
        match, so the caller falls through to the unsupported response.
        """
        for pattern in (_CAPABILITY_DETAIL_RE, _CAPABILITY_DETAIL_DO_RE):
            match = pattern.search(lowered)
            if match is None:
                continue
            resolved = self._resolve_detail_name(match.group("name"))
            if resolved is not None:
                return resolved
        return None

    def _resolve_detail_name(self, raw_name: str) -> str | None:
        """Resolve a raw candidate against the registered capabilities/tools.

        Conservative: an unresolvable candidate returns None so the caller
        falls through to the unsupported response (fail-closed).
        """
        candidate = raw_name.strip().strip("?.!.,;:'\"()")
        if not candidate:
            return None
        normalized = candidate.lower().replace("-", "_").replace(" ", "_")
        candidates = {normalized}
        if "." not in normalized and "_" not in normalized:
            candidates.add(normalized)
        for name in self._capability_names() | self._tool_names():
            folded = name.lower().replace("-", "_").replace(" ", "_")
            if folded in candidates or normalized in (
                folded,
                folded.replace(".", "_"),
                folded.replace("_", "."),
            ):
                return name
        return None

    def _match_validated_knowledge(self, lowered: str) -> tuple[str, Any] | None:
        """Claim a bounded validated-knowledge turn, or None to fall through.

        C6.1 — the ONLY operation performed is the read-only retrieval already
        exposed by the kernel. Nothing is acquired, written, promoted, updated,
        or inferred. Returns ``(query, result)``; ``result`` is the existing
        capability's own result object, rendered verbatim (including its
        authoritative ``empty`` / ``store_unavailable`` outcome).

        Returns ``None`` when no provider is wired, when no bounded cue with a
        usable topic matches, when the provider fails (fail closed), or — for a
        cue that the existing recall also claims — when nothing validated
        matched, so the existing recall path keeps the turn unchanged.
        """
        if self._validated_knowledge_provider is None:
            return None
        matched = _match_validated_knowledge_cue(lowered)
        if matched is None:
            return None
        query, explicit = matched
        result = self._retrieve_validated_knowledge(query)
        if result is None:
            return None
        if not explicit and not self._validated_knowledge_items(result):
            return None
        return (query, result)

    def _retrieve_validated_knowledge(self, query: str) -> Any | None:
        """Delegate the read-only retrieval, or None when it cannot be read."""
        provider = self._validated_knowledge_provider
        if provider is None:
            return None
        try:
            return provider(query)
        except Exception:
            return None

    @staticmethod
    def _validated_knowledge_items(result: Any) -> tuple[Any, ...]:
        """Existing validated claims on ``result`` (never synthesized)."""
        items = getattr(result, "items", None)
        if not items:
            return ()
        try:
            return tuple(items)
        except TypeError:
            return ()

    @staticmethod
    def _validated_knowledge_status(result: Any) -> str:
        """The retrieval's own authoritative status value."""
        status = getattr(result, "status", None)
        return str(getattr(status, "value", status) or "")

    def _match_recall(self, lowered: str) -> str | None:
        """Extract a recall query, or None when no confident trigger exists.

        Requires one of the conservative trigger phrases AND a non-trivial
        query remainder (>= 3 alphanumeric characters). A bare "do you
        remember?" with nothing to look up is not a confident recall — it
        falls through to unsupported.
        """
        match = _RECALL_RE.search(lowered)
        if match is None:
            return None
        remainder = _RECALL_RE.sub(" ", lowered)
        remainder = re.sub(r"[^a-z0-9_ ]", " ", remainder)
        tokens = [t for t in remainder.split() if len(t) >= 3]
        if not tokens:
            return None
        return " ".join(tokens[:8])

    def _match_conversation_recall(
        self,
        lowered: str,
        context: ConversationContext | None,
    ) -> tuple[str, str, str] | None:
        """Return ``(source, label, content)`` for a bounded turn recall.

        Consumes only the immutable :class:`ConversationContext` and its
        structured state. Returns ``None`` when the phrase is not a
        conversational-turn recall request, or when no deterministic candidate
        exists — fail closed; the unchanged store recall path then applies.
        """
        if context is None:
            return None

        state = getattr(context, "state", None)
        prior_user = self._prior_turns(context, "user", lowered)
        prior_assistant = self._prior_turns(context, "assistant", lowered)

        if _CONVERSATION_RECALL_USER_RE.search(lowered):
            if prior_user:
                return ("user", _CONVERSATION_RECALL_LABELS["user"], prior_user[-1])
            return None

        if _CONVERSATION_RECALL_ASSISTANT_RE.search(lowered):
            if prior_assistant:
                return (
                    "assistant",
                    _CONVERSATION_RECALL_LABELS["assistant"],
                    prior_assistant[-1],
                )
            return None

        if _CONVERSATION_RECALL_TOPIC_RE.search(lowered):
            subject = self._recent_conversation_subject(prior_user, state)
            if subject:
                return ("topic", _CONVERSATION_RECALL_LABELS["topic"], subject)
            return None

        if _CONVERSATION_RECALL_FINDING_RE.search(lowered):
            if state is not None:
                finding = getattr(state, "latest_result", None)
                if isinstance(finding, str) and finding.strip():
                    return (
                        "finding",
                        _CONVERSATION_RECALL_LABELS["finding"],
                        finding.strip(),
                    )
            return None

        return None

    @staticmethod
    def _match_resolved_reference(
        spec: TaskSpec | None,
    ) -> tuple[str, str, str] | None:
        """Return ``(field, label, value)`` for an already-resolved reference.

        Stage A consumption: reads ONLY the deterministic evidence the resolver
        already attached to ``TaskSpec.context`` (``resolved_reference``). The
        referent must be a consumable :class:`ConversationState` field and its
        bound value a non-empty string; anything else declines, so turns with
        no applicable evidence keep the unchanged unsupported behavior.

        Nothing is re-resolved, guessed, executed, or authorized here, and the
        bound value is restated verbatim (never interpreted).
        """
        if spec is None:
            return None
        context = getattr(spec, "context", None)
        if not isinstance(context, dict):
            return None
        payload = context.get("resolved_reference")
        if not isinstance(payload, dict):
            return None
        field = payload.get("field")
        value = payload.get("value")
        if not isinstance(field, str) or not isinstance(value, str):
            return None
        label = _REFERENCE_LABELS.get(field)
        if label is None or not value.strip():
            return None
        return (field, label, value.strip())

    @staticmethod
    def _prior_turns(
        context: ConversationContext,
        role: str,
        lowered: str,
    ) -> list[str]:
        """Return bounded prior turns of ``role``, excluding the current turn."""
        query_key = " ".join(lowered.split())
        turns: list[str] = []
        for turn in getattr(context, "recent_turns", ()) or ():
            if getattr(turn, "role", "") != role:
                continue
            content = getattr(turn, "content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            # Exclude the current turn (its text matches the live query).
            if " ".join(content.split()).lower() == query_key:
                continue
            turns.append(content.strip())
        return turns

    @staticmethod
    def _recent_conversation_subject(prior_user: list[str], state: Any) -> str:
        """Return the deterministic recent conversation subject, or ''."""
        if state is not None:
            investigation = getattr(state, "current_investigation", None)
            if isinstance(investigation, str) and investigation.strip():
                return investigation.strip()
        for content in reversed(prior_user):
            if _CONVERSATION_SUBJECT_LEAD_RE.search(content.lower()):
                return content
        # L5 — bounded last-resort fallback: the subject established explicitly
        # in an earlier turn. Investigation subjects and lead-cue turns keep
        # precedence, so existing recall behaviour is unchanged.
        if state is not None:
            established = getattr(state, "current_subject", None)
            if isinstance(established, str) and established.strip():
                return established.strip()
        return ""

    @staticmethod
    def _render_conversation_recall(detail: tuple[str, str, str]) -> str:
        """Render a bounded, provenance-labelled conversational recall."""
        _source, label, content = detail
        body = content.strip()
        if len(body) > _MAX_CONVERSATION_RECALL_CHARS:
            body = body[:_MAX_CONVERSATION_RECALL_CHARS].rstrip() + "..."
        return f"{label} {body}"

    @staticmethod
    def _render_reference(detail: tuple[str, str, str]) -> str:
        """Restate a bounded referent the deterministic resolver already bound."""
        _field, label, value = detail
        body = value.strip()
        if len(body) > _MAX_REFERENCE_CHARS:
            body = body[:_MAX_REFERENCE_CHARS].rstrip() + "..."
        return f"{label} {body}"

    def _render(
        self,
        intent: str,
        message_count: int | None = None,
        detail: object | None = None,
    ) -> str:
        if intent == BUILTIN_INTENT_GREETING:
            return self._render_greeting()
        if intent == BUILTIN_INTENT_HELP:
            return self._render_help()
        if intent == BUILTIN_INTENT_IDENTITY:
            return self._render_identity()
        if intent == BUILTIN_INTENT_CAPABILITIES:
            return self._render_capabilities()
        if intent == BUILTIN_INTENT_CAPABILITY_DETAIL:
            return self._render_capability_detail(detail or "")
        if intent == BUILTIN_INTENT_ARCHITECTURE:
            return self._render_architecture(str(detail or ""))
        if intent == BUILTIN_INTENT_SELF_KNOWLEDGE:
            return self._render_self_knowledge(str(detail or ""))
        if intent == BUILTIN_INTENT_SELF_DESCRIPTION:
            return self._render_self_description()
        if intent == BUILTIN_INTENT_STATUS:
            return self._render_status(message_count=message_count)
        if intent == BUILTIN_INTENT_RECALL:
            return self._render_recall(detail or "")
        if intent == BUILTIN_INTENT_VALIDATED_KNOWLEDGE:
            return self._render_validated_knowledge(detail)
        if intent == BUILTIN_INTENT_CONVERSATION_RECALL and isinstance(detail, tuple):
            return self._render_conversation_recall(detail)
        if intent == BUILTIN_INTENT_REFERENCE and isinstance(detail, tuple):
            return self._render_reference(detail)
        if intent == BUILTIN_INTENT_COMMANDS:
            return self._render_commands()
        if intent == BUILTIN_INTENT_ACKNOWLEDGEMENT:
            return self._render_acknowledgement(detail)
        return self._render_unsupported()

    @staticmethod
    def _render_greeting() -> str:
        return (
            "Hello. I am Atlas, a model-independent operating framework. "
            "I answer deterministically without calling an external AI model. "
            "Ask 'help' to see what I can do."
        )

    @staticmethod
    def _render_acknowledgement(detail: object) -> str:
        """Deterministic reply to a casual acknowledgement (L10).

        States plainly that nothing was acted on, so an acknowledgement can
        never be mistaken for an instruction or an authorization.
        """
        if detail == "thanks":
            return (
                "You're welcome. Nothing further is needed for that. "
                "Ask 'help' to see what I can do deterministically."
            )
        return (
            "Noted, and no action taken. "
            "Ask 'help' to see what I can do deterministically."
        )

    @staticmethod
    def _render_help() -> str:
        return (
            "I can help deterministically (no external AI model needed):\n"
            "- Greet me ('hello').\n"
            "- Ask who I am ('who are you').\n"
            "- Ask what I can do ('what capabilities do you have').\n"
            "- Ask about one capability ('explain code_inspector').\n"
            "- Ask for status ('status').\n"
            "- Ask what I remember ('do you remember <topic>').\n"
            "- Ask for commands ('what commands can I use').\n"
            "- Ask me to investigate an issue ('investigate ...').\n"
            "- Ask me to prepare a development proposal ('plan ...' after an "
            "investigation). Proposals always require your explicit approval; "
            "approval never executes anything by itself."
        )

    @staticmethod
    def _render_identity() -> str:
        return (
            "I am Atlas, a long-term, modular AI operating framework — not a "
            "chatbot and not a model wrapper. I coordinate memory, knowledge, "
            "reasoning, planning, learning, tools, and evolution under human "
            "ownership. AI models are tools I may use; they are not my "
            "intelligence. I operate deterministically, fail closed, and "
            "never modify anything without governed approval."
        )

    def _capability_names(self) -> set[str]:
        if self._capability_registry is None:
            return set()
        try:
            return set(self._capability_registry.registered_names)
        except Exception:
            return set()

    def _tool_names(self) -> set[str]:
        return {getattr(t, "name", "") for t in self._listed_tools()}

    def _find_tool(self, name: str) -> Any | None:
        if self._tool_registry is None:
            return None
        try:
            return self._tool_registry.get(name)
        except Exception:
            return None

    def _render_capabilities(self) -> str:
        tools = self._listed_tools()
        capabilities = sorted(self._capability_names())
        if not tools and not capabilities:
            return (
                "No tools or capabilities are currently registered. "
                "Deterministic conversational intents I always support: "
                "greeting, help, identity, status, commands. Governed flows "
                "(investigation, planning, approval, execution) are handled "
                "by the conversation pipeline when wired."
            )
        lines = [
            "Confirmed registered capabilities (deterministic, no model used):",
            "",
        ]
        if capabilities:
            lines.append("Reasoning capabilities:")
            for name in capabilities[:_MAX_TOOLS_LISTED]:
                lines.append(f"- `{name}`")
            extra = len(capabilities) - _MAX_TOOLS_LISTED
            if extra > 0:
                lines.append(f"  ... and {extra} more registered capabilit(ies).")
            lines.append("")
        if tools:
            lines.append("Tools:")
            for tool in tools[:_MAX_TOOLS_LISTED]:
                name = getattr(tool, "name", "?")
                category = getattr(tool, "category", "?")
                desc = getattr(tool, "description", "") or "No description."
                lines.append(f"- **{name}** ({category}): {desc}")
            extra = len(tools) - _MAX_TOOLS_LISTED
            if extra > 0:
                lines.append(f"... and {extra} more registered tool(s).")
        lines.append("")
        lines.append(
            "Ask 'explain <name>' for a registered capability or tool."
        )
        return "\n".join(lines)

    def _render_capability_detail(self, name: str) -> str:
        tool = self._find_tool(name)
        if tool is not None:
            desc = getattr(tool, "description", "") or "No description."
            category = getattr(tool, "category", "?")
            tags = getattr(tool, "tags", ()) or ()
            lines = [
                f"**{name}** (tool, category `{category}`):",
                desc,
            ]
            if tags:
                lines.append(f"Tags: {', '.join(tags)}.")
            lines.append(
                "This is a confirmed registration — the tool exists in the "
                "tool registry. Running it is a governed step, not something "
                "I do from conversation alone."
            )
            return "\n".join(lines)
        if name in self._capability_names():
            return (
                f"`{name}` is a confirmed registered reasoning capability "
                "(capability registry). It is invoked only through the "
                "governed capability path (registry → router → dispatcher), "
                "never directly from conversation."
            )
        return self._render_unsupported()

    # ------------------------------------------------------------------
    # Self-description (Phase 2.9) — bounded, read-only, model-grounded
    # ------------------------------------------------------------------

    def _render_self_description(self) -> str:
        """Answer "what does Atlas do / how does Atlas work" deterministically.

        Composed from Atlas's EXISTING authoritative self-knowledge: the
        established identity statement plus bounded facts projected from the
        injected ``ArchitectureModel`` (itself built from the component
        registry, the capability model, and the cached repository map). No
        second, drift-prone description is maintained, and no external AI
        model is required or contacted. Fails soft to the unsupported floor
        when no model is available.
        """
        model = self._resolve_architecture_model()
        if model is None:
            return self._render_unsupported()

        lines = [
            self._render_identity(),
            "",
            "What I do, from my own self-knowledge "
            "(deterministic, read-only; no external AI model used):",
            f"- Components (registered): {model.component_count}",
            f"- Subsystems (packages): {model.subsystem_count}",
            f"- Repository modules: {model.module_count}",
            f"- Internal import edges: {model.edge_count}",
        ]

        capabilities = sorted(
            {
                capability
                for component in model.components
                for capability in component.provided_capabilities
                if capability
            }
        )
        lines.append(
            f"- Capabilities provided by registered components: {len(capabilities)}"
        )
        if capabilities:
            lines.append(
                "- Representative capabilities: "
                + _format_names(capabilities[:_MAX_ARCHITECTURE_RELATIONS])
            )
        if model.limitations:
            lines.append(
                "- Scope boundary: " + model.limitations[0]
            )

        lines.append("")
        lines.append(
            "Ask 'what can you do' for the conversational capability list, or "
            "name a module (for example 'atlas.research.repository_map') for "
            "its dependency facts."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Architecture self-knowledge (WS) — bounded, read-only
    # ------------------------------------------------------------------

    @staticmethod
    def _has_established_subject(context: Any) -> bool:
        """True when the conversation already carries a captured subject (C5.1)."""
        state = getattr(context, "state", None)
        if state is None:
            return False
        return bool(getattr(state, "captured_entities", ()) or ())

    def _capabilities_intent_applies(self, lowered: str, context: Any = None) -> bool:
        """True when a capability-WORD turn is an ATLAS capability question.

        C5.1 — bounded distinction for the C3 finding: a third-person possessive
        or a demonstrative bound to a product/device noun, or an established
        conversational subject with no first-person Atlas reference, means the
        turn is about an EXTERNAL subject's capabilities and must not be answered
        with Atlas's own inventory. Never guesses: an unclear turn in a
        conversation that already has an external subject declines the inventory.
        """
        if _CAPABILITY_DOMAIN_REFERENCE_RE.search(lowered):
            return False
        if _SELF_REFERENCE_ANY_RE.search(lowered):
            return True
        return not self._has_established_subject(context)

    @staticmethod
    def _matches_architecture(lowered: str) -> bool:
        """True when the turn is an Atlas self-knowledge/architecture question.

        The structural vocabulary is the existing ``_ARCHITECTURE_RE``. The
        process/flow wording (``_ARCHITECTURE_PROCESS_RE``) is broader, so it
        additionally requires an Atlas self-reference: "how does a request
        flow" about some other system is not Atlas self-knowledge.
        """
        if _ARCHITECTURE_RE.search(lowered):
            return True
        if _ARCHITECTURE_PARTS_RE.search(lowered):
            return True
        return bool(
            _ARCHITECTURE_PROCESS_RE.search(lowered)
            and _SELF_REFERENCE_RE.search(lowered)
        )

    def _resolve_architecture_model(self) -> Any | None:
        """Return the injected ArchitectureModel, or None (fail-soft).

        Never triggers a scan and never mutates: the provider is expected to be
        cache-only (see the kernel wiring). A missing provider, a None snapshot,
        a non-``ArchitectureModel`` value, or a raising provider all decline.
        """
        if self._architecture_model_provider is None:
            return None
        try:
            model = self._architecture_model_provider()
        except Exception:
            return None
        if model is None:
            return None
        from atlas.self_knowledge.architecture_model import ArchitectureModel

        if not isinstance(model, ArchitectureModel):
            return None
        return model

    @staticmethod
    def _locate_architecture_target(model: Any, query: str) -> Any | None:
        """Resolve the first dotted module/package identifier in ``query``.

        Uses the model's existing evidence-only ``locate()``. Returns None when
        the question names no resolvable target, so the caller renders only
        bounded model counts rather than inventing a relationship.
        """
        if not query:
            return None
        seen: list[str] = []
        for match in _ARCHITECTURE_TARGET_RE.finditer(query):
            token = match.group(0).strip(".")
            if token and token not in seen:
                seen.append(token)
        # C5.1 — plain-language questions name a topic, not a dotted identifier
        # ("... handle conversation?"). Also try the bounded bare tokens so the
        # answer can resolve to the component the model actually records. Only
        # tokens the model VERIFIES are used, so this cannot invent a component.
        for token in _ARCHITECTURE_TOPIC_TOKEN_RE.findall(query.lower()):
            if token not in seen and token not in _ARCHITECTURE_TOPIC_STOPWORDS:
                seen.append(token)
        for token in seen[:_MAX_ARCHITECTURE_TOPIC_TOKENS]:
            located = model.locate(token)
            if located.found:
                return located
        return None

    @staticmethod
    def _verify_anchor(path: str) -> bool:
        """True when the anchor module actually exists (C5.1).

        Verified through the import system rather than a repository scan, so the
        check is deterministic, read-only, model-free and available even before
        a repository map has been built. An unverified anchor is never stated.
        """
        try:
            return importlib.util.find_spec(path) is not None
        except Exception:
            return False

    def _self_knowledge_bullets(self, topic: str, model: Any) -> tuple[str, ...]:
        """Bounded behaviour bullets for a self-knowledge topic (C5.1).

        Every bullet is derived from a VERIFIED source: the injected
        ArchitectureModel, the live capability registry, or the enumerated value
        sets the architecture actually defines. No free-form prose is invented.
        """
        try:
            if topic == "reference resolution":
                from atlas.conversation.reference_resolution import (
                    ConversationReferenceResolver,
                    ReferenceResolutionStatus,
                )

                return (
                    "References are resolved by the existing "
                    f"{ConversationReferenceResolver.__name__}, which resolves a "
                    "bounded set of reference forms against conversation state and "
                    "captured entities.",
                    "Resolution statuses defined by the architecture: "
                    + _enum_values(ReferenceResolutionStatus)
                    + ".",
                    "Resolution is fail-closed: an ambiguous or unresolvable reference "
                    "is never guessed — Atlas asks for clarification, or proceeds "
                    "without attaching a referent.",
                )
            if topic == "evidence and failure behaviour":
                from atlas.orchestration.execution_models import (
                    ExecutionStatus,
                    StepFailureKind,
                )

                return (
                    "Research/execution outcomes are mapped to explicit failure kinds "
                    "defined by the architecture: "
                    + _enum_values(StepFailureKind)
                    + ".",
                    "Run results are represented as: "
                    + _enum_values(ExecutionStatus)
                    + ".",
                    "No evidence and no relevant evidence are never reported as success; "
                    "an authority/governance denial is represented as a rejected result.",
                )
            if topic == "current limitations":
                bullets: list[str] = []
                if model.limitations:
                    bullets.append(
                        "Limitations recorded by the architecture model: "
                        + "; ".join(
                            model.limitations[:_MAX_ARCHITECTURE_LIMITATIONS]
                        )
                    )
                else:
                    bullets.append(
                        "The architecture model records no additional limitations."
                    )
                bullets.append(
                    f"Registered capabilities: {len(self._capability_names())}."
                )
                bullets.append(
                    "Verified self-knowledge currently covers only these question "
                    "families: architecture/components, reference resolution, "
                    "evidence/failure behaviour, current limitations, research "
                    "process. Anything else is reported as not verified, not guessed."
                )
                return tuple(bullets)
            if topic == "research process":
                from atlas.research.acquisition import InformationAcquisitionService
                from atlas.research.coordinator import ConcreteResearchCoordinator

                return (
                    "A research request becomes a bounded orchestration RESEARCH step "
                    "whose question is the research objective.",
                    "The existing "
                    f"{ConcreteResearchCoordinator.__name__} decomposes the objective, "
                    "resolves only already-authorized sources, extracts claims, and "
                    "verifies them.",
                    "The existing "
                    f"{InformationAcquisitionService.__name__} maps the outcome "
                    "honestly and external (web) sources remain deny-by-default unless "
                    "explicitly allowlisted.",
                    "Completion is reported only when authorized evidence addresses "
                    "the objective; otherwise no_evidence / no_relevant_evidence / "
                    "partial are reported.",
                )
        except Exception:  # noqa: BLE001 - never fabricate: emit no bullets
            return ()
        return ()

    def _render_self_knowledge(self, topic: str) -> str:
        """Render a bounded, evidence-grounded self-knowledge answer (C5.1).

        Consumes ONLY verified read-only sources: the injected ArchitectureModel
        (anchors), the live capability registry (counts), and the enumerated
        value sets the architecture defines. Every anchor is verified present
        before it is stated; when no anchor is verified the answer is an honest
        bounded unknown. Nothing is mutated and no model is called.
        """
        model = self._resolve_architecture_model()
        if model is None:
            return self._render_unsupported()

        anchors = _self_knowledge_anchors(topic)
        verified = [path for path in anchors if self._verify_anchor(path)]
        if not verified:
            return (
                "Atlas self-knowledge is bounded to verified internal sources, and "
                "I don't have verified self-knowledge for that yet: the documented "
                "component(s) that would substantiate an answer are not present. "
                "Nothing was guessed."
            )

        lines = [
            f"Atlas self-knowledge — {topic} "
            "(deterministic, read-only; no external AI model used):",
            "",
            "Verified architectural anchors:",
        ]
        for path in verified:
            lines.append(
                f"- `{path.replace('.', '/')}.py` (module verified present)"
            )
        lines.append("")
        lines.append("Bounded behaviour (from the verified architecture):")
        for bullet in self._self_knowledge_bullets(topic, model):
            lines.append(f"- {bullet}")
        lines.append("")
        lines.append(
            "This is a bounded projection of verified internal sources; anything "
            "not listed is not asserted. Nothing was modified."
        )
        return "\n".join(lines)

    def _render_architecture(self, query: str = "") -> str:
        """Render a bounded, read-only architecture self-knowledge answer.

        Consumes ONLY the injected, already-built ArchitectureModel (and any
        repository map it already carries). Deterministic, provider-free and
        network-free. When no usable model is available it fails soft to the
        existing unsupported floor instead of inventing an answer, and it never
        claims a fact the model does not record.
        """
        model = self._resolve_architecture_model()
        if model is None:
            return self._render_unsupported()

        lines = [
            "Atlas architecture self-knowledge "
            "(deterministic, read-only; no external AI model used):",
        ]

        located = self._locate_architecture_target(model, query)
        if located is not None:
            if located.module:
                lines.append(f"- Matched module: `{located.module}`")
            lines.append(f"- Match kind: {located.matched_kind}")
            if located.packages:
                lines.append(f"- Package(s): {_format_names(located.packages)}")
            if located.components:
                lines.append(
                    f"- Component(s): {_format_names(located.components)}"
                )
            lines.append(
                f"- Direct dependencies ({len(located.dependencies)}): "
                + (
                    _format_names(located.dependencies[:_MAX_ARCHITECTURE_RELATIONS])
                    or "none"
                )
            )
            lines.append(
                f"- Direct dependents ({len(located.dependents)}): "
                + (
                    _format_names(located.dependents[:_MAX_ARCHITECTURE_RELATIONS])
                    or "none"
                )
            )
            lines.append(
                f"- Transitive impact ({len(located.impact)}): "
                + (
                    _format_names(located.impact[:_MAX_ARCHITECTURE_RELATIONS])
                    or "none"
                )
            )
        else:
            lines.append(f"- Components (registered): {model.component_count}")
            lines.append(f"- Subsystems (packages): {model.subsystem_count}")
            lines.append(f"- Repository modules: {model.module_count}")
            lines.append(f"- Internal import edges: {model.edge_count}")
            if model.subsystems:
                lines.append("")
                lines.append("Representative subsystems:")
                for subsystem in model.subsystems[:_MAX_ARCHITECTURE_SUBSYSTEMS]:
                    lines.append(
                        f"- `{subsystem.package}` — "
                        f"{len(subsystem.components)} component(s), "
                        f"{subsystem.module_count} module(s), "
                        f"{len(subsystem.provided_capabilities)} capabilit(ies)"
                    )
                extra = len(model.subsystems) - _MAX_ARCHITECTURE_SUBSYSTEMS
                if extra > 0:
                    lines.append(f"  ... and {extra} more subsystem(s).")

        if model.limitations:
            lines.append("")
            lines.append("Known scope boundaries (from the model):")
            for limitation in model.limitations[:_MAX_ARCHITECTURE_LIMITATIONS]:
                lines.append(f"- {limitation}")

        lines.append("")
        lines.append(
            "This is a bounded projection of Atlas's existing structural "
            "sources; nothing was modified. Ask about a specific module "
            "(e.g. 'what depends on atlas.research.repository_map') for its "
            "dependency facts."
        )
        return "\n".join(lines)

    def _listed_tools(self) -> list[Any]:
        if self._tool_registry is None:
            return []
        try:
            return list(self._tool_registry.list())
        except Exception:
            return []

    def _render_status(self, message_count: int | None = None) -> str:
        tool_count: int | None = None
        if self._tool_registry is not None:
            try:
                tool_count = len(self._tool_registry.list())
            except Exception:
                tool_count = None
        knowledge_count: int | None = None
        if self._knowledge_manager is not None:
            try:
                base = getattr(self._knowledge_manager, "base", None)
                entries = base.all() if base is not None else None
                knowledge_count = len(entries) if entries is not None else None
            except Exception:
                knowledge_count = None
        lines = [
            "Atlas status (deterministic, no external model contacted):",
            "- Mode: built-in deterministic responses.",
        ]
        lines.append(
            f"- Registered tools: {tool_count}."
            if tool_count is not None
            else "- Registered tools: unknown (no tool registry wired)."
        )
        lines.append(
            f"- Knowledge entries: {knowledge_count}."
            if knowledge_count is not None
            else "- Knowledge entries: unknown (no knowledge manager wired)."
        )
        memory_count: int | None = None
        if self._memory_service is not None:
            try:
                memory_count = len(self._memory_service.list_memories())
            except Exception:
                memory_count = None
        lines.append(
            f"- Stored memories: {memory_count}."
            if memory_count is not None
            else "- Stored memories: unknown (no memory service wired)."
        )
        service_names = self._resolve_service_names()
        if service_names is not None:
            lines.append(
                f"- Registered services ({len(service_names)}): "
                + ", ".join(f"`{n}`" for n in service_names[:24])
                + ("" if len(service_names) <= 24 else ", ...")
            )
        else:
            lines.append("- Registered services: unknown (no container snapshot).")
        if self._started is True:
            lines.append("- Runtime: started.")
        elif self._started is False:
            lines.append("- Runtime: not started (limited surface).")
        else:
            lines.append("- Runtime: unknown (no lifecycle snapshot).")
        if message_count is not None:
            lines.append(f"- Messages in this conversation: {message_count}.")
        return "\n".join(lines)

    def _render_validated_knowledge(self, detail: object) -> str:
        """Render the EXISTING validated-knowledge result honestly (C6.1).

        Presents only already-validated (SUPPORTED) claims with their
        validation status and source attribution, and reports the retrieval's
        own authoritative outcome when nothing matched or the store cannot be
        read. Nothing is acquired, inferred, or invented.
        """
        if not isinstance(detail, tuple) or len(detail) != 2:
            return self._render_unsupported()
        query, result = detail
        status = self._validated_knowledge_status(result)
        items = self._validated_knowledge_items(result)
        if status == "ok" and items:
            lines = [
                f"Validated knowledge for '{query}' "
                "(read-only retrieval from the validated knowledge store; "
                "no model used):",
                "",
                f"{len(items)} validated (SUPPORTED) claim(s) matched.",
                "",
            ]
            for item in items[:3]:
                statement = str(getattr(item, "statement", "") or "").strip()
                if len(statement) > _MAX_VALIDATED_CLAIM_CHARS:
                    statement = statement[:_MAX_VALIDATED_CLAIM_CHARS].rstrip() + "..."
                lines.append(
                    "### Validated claim "
                    f"({getattr(item, 'validation_status', 'SUPPORTED')})"
                )
                lines.append(statement)
                confidence = getattr(item, "claim_confidence", None)
                if isinstance(confidence, (int, float)):
                    lines.append(f"- Claim confidence: {confidence}")
                score = getattr(item, "verification_score", None)
                if isinstance(score, (int, float)):
                    lines.append(f"- Verification score: {score}")
                for citation in self._validated_knowledge_citations(item):
                    lines.append(f"- Source: {citation}")
                lines.append("")
            return "\n".join(lines).strip()
        if status in ("store_unavailable", "store_error"):
            message = str(getattr(result, "message", "") or "").strip()
            return (
                f"Validated knowledge for '{query}': the validated knowledge "
                f"store is unavailable (status: {status or 'store_unavailable'})."
                + (f" {message}" if message else "")
                + " I fail closed rather than answer from memory, conversation "
                "state, or a model."
            )
        message = str(getattr(result, "message", "") or "").strip()
        lines = [
            f"No validated knowledge matched '{query}' "
            f"(status: {status or 'empty'}).",
        ]
        if message:
            lines.append(message)
        lines.append(
            "Only claims an authorized source already SUPPORTED are reported; "
            "nothing is acquired, inferred, or invented for this answer."
        )
        return " ".join(lines)

    @staticmethod
    def _validated_knowledge_citations(item: Any) -> tuple[str, ...]:
        """Source attribution for a validated claim (provenance preserved)."""
        rendered: list[str] = []
        for citation in tuple(getattr(item, "citations", ()) or ())[:3]:
            uri = str(getattr(citation, "source_uri", "") or "")
            title = str(getattr(citation, "source_title", "") or "")
            label = title or uri
            if not label:
                label = str(getattr(citation, "record_id", "") or "unknown source")
            location = str(getattr(citation, "page_or_line", "") or "")
            section = str(getattr(citation, "section", "") or "")
            suffix = ", ".join(part for part in (section, location) if part)
            rendered.append(f"{label} ({suffix})" if suffix else label)
        return tuple(rendered)

    def _render_recall(self, query: str) -> str:
        memories = self._search_memories(query)
        entries = self._search_knowledge(query)
        if not memories and not entries:
            sources: list[str] = []
            if self._memory_service is None:
                sources.append("memory service is not wired")
            if self._knowledge_manager is None:
                sources.append("knowledge manager is not wired")
            if sources:
                return (
                    f"No deterministic recall available ({' and '.join(sources)}). "
                    "I cannot invent an answer, so I will not guess."
                )
            return (
                f"No memory or knowledge entry matched '{query}'. "
                "Stored entries are searched verbatim (case-insensitive "
                "keyword match); try different words, or ask 'help' for "
                "what I can do."
            )
        lines = [
            f"Deterministic recall for '{query}' (verbatim keyword match, "
            "no model used):",
            "",
        ]
        for memory in memories[:3]:
            title = getattr(memory, "title", "Memory")
            content = getattr(memory, "content", "")
            source = getattr(memory, "source", "unknown")
            lines.append(f"### Memory: {title}")
            lines.append(str(content)[:500])
            lines.append(f"- Source: {source}")
            lines.append("")
        for entry in entries[:3]:
            title = getattr(entry, "title", "Knowledge")
            content = getattr(entry, "content", "")
            source = getattr(entry, "source", "unknown")
            lines.append(f"### Knowledge: {title}")
            lines.append(str(content)[:500])
            lines.append(f"- Source: {source}")
            lines.append("")
        return "\n".join(lines).strip()

    def _search_memories(self, query: str) -> list[Any]:
        if self._memory_service is None or not query:
            return []
        try:
            results = self._memory_service.search(keyword=query, limit=3)
        except Exception:
            return []
        return list(results or [])

    def _search_knowledge(self, query: str) -> list[Any]:
        if self._knowledge_manager is None or not query:
            return []
        try:
            results = self._knowledge_manager.query(query)
        except Exception:
            return []
        return list(results or [])[:3]

    def _render_commands(self) -> str:
        return (
            "Supported commands and safe next steps (deterministic surfaces only):\n"
            "- Conversational: 'hello', 'help', 'who are you', "
            "'what can you do', 'status', 'explain <capability>', "
            "'do you remember <topic>'.\n"
            "- CLI subcommands (read-only unless noted): `atlas capabilities`, "
            "`atlas validated-knowledge <query>`, `atlas memory search <query>`, "
            "`atlas reasoning trace|causal|hypotheses|verify|meta`, "
            "`atlas toolchain plan|execute`, `atlas research query|verify`, "
            "`atlas proposals list|show|audit`, `atlas evolution pending|show|status`.\n"
            "- Governed development: 'investigate <issue>' produces a read-only "
            "report; 'plan ...' prepares a proposal that requires your explicit "
            "approval; approval never executes; execution needs a separate "
            "explicit step. Nothing here modifies the repository."
        )

    @staticmethod
    def _render_unsupported() -> str:
        return (
            "I operate deterministically without an external AI model, so I "
            "cannot answer that conversationally yet. I do support: greeting, "
            "help, identity ('who are you'), capabilities ('what can you do'), "
            "capability detail ('explain <name>'), status, memory/knowledge "
            "recall ('do you remember <topic>'), and commands ('what commands "
            "can I use'). I can also investigate an issue ('investigate ...') "
            "or prepare a governed development proposal after an "
            "investigation — both require your explicit approval steps."
        )
