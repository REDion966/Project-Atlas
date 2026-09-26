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

    A self-referential topic is claimed only when its cue pattern AND an Atlas
    self-reference are both present, so a domain question about some other
    system is never captured. Atlas-specific topics (request flow, development,
    OWNER approval, sandbox, authorization boundary, extension points) name
    Atlas-only concepts, so they do not require the generic self-reference.
    """
    for topic, pattern, _anchors in _SELF_KNOWLEDGE_TOPICS:
        if pattern.search(lowered) and _SELF_REFERENCE_ANY_RE.search(lowered):
            return topic
    for topic, pattern, _anchors in _SELF_KNOWLEDGE_TOPICS_ATLAS_SPECIFIC:
        if pattern.search(lowered):
            return topic
    return None


#: Evidence-driven self-knowledge topics whose cue patterns are Atlas-specific
#: by construction (they name request flow / development / OWNER / sandbox /
#: authorization / extension points). Anchors are verified present before any
#: prose is emitted — the same contract as ``_SELF_KNOWLEDGE_TOPICS``.
_SELF_KNOWLEDGE_TOPICS_ATLAS_SPECIFIC: tuple[
    tuple[str, "re.Pattern[str]", tuple[str, ...]], ...
] = (
    (
        "request flow",
        re.compile(
            r"\bhow\s+(?:does|do)\s+a\s+user\s+request\b"
            r"|\buser\s+request\s+(?:travel|move|flow)\w*\b"
            r"|\brequest\s+flow\b"
            r"|\bbetween\s+conversation\s+intake\b"
        ),
        (
            "atlas.conversation.conversation_service",
            "atlas.conversation.engine",
            "atlas.research.knowledge_decision",
            "atlas.orchestration.work_orchestrator",
        ),
    ),
    (
        "development process",
        re.compile(
            r"\bdevelopment\s+(?:process|pipeline|lifecycle|flow|workflow)\b"
            r"|\bwhat\s+happens\s+after\s+a\s+proposal\s+is\s+created\b"
            r"|\bhow\s+would\s+you\s+develop\s+a\s+new\s+capabilit"
        ),
        (
            "atlas.evolution.development_cycle",
            "atlas.orchestration.development_orchestrator",
            "atlas.evolution.promotion_gate",
        ),
    ),
    (
        "owner approval",
        re.compile(
            r"\bowner\s+approval\b"
            r"|\bwhere\s+does\s+(?:the\s+)?owner\s+approv"
            r"|\bwho\s+approves\b"
            r"|\bapproval\s+boundary\b"
        ),
        ("atlas.evolution.approval_manager", "atlas.authority.service"),
    ),
    (
        "sandbox execution",
        re.compile(
            r"\bsandbox\s+(?:execution|boundary|isolation|enforce\w*)\b"
            r"|\bhow\s+is\s+sandbox"
        ),
        (
            "atlas.evolution.autonomy.code_sandbox",
            "atlas.evolution.self_development_loop",
        ),
    ),
    (
        "authorization boundary",
        re.compile(
            r"\bprevent\w*\b[^.?]{0,60}\bauthoriz\w*\b"
            r"|\bauthoriz\w*\s+itself\b"
            r"|\bself[-\s]?authoriz\w*\b"
            r"|\bnatural[- ]language\b[^.?]{0,40}\bauthoriz\w*\b"
        ),
        ("atlas.authority.service", "atlas.kernel.atlas"),
    ),
    (
        "extension points",
        re.compile(
            r"\bif\s+you\s+needed\s+a\s+new\s+capabilit"
            r"|\bwhere\s+would\s+(?:a\s+new\s+capabilit\w*|it)\s+fit\b"
            r"|\breuse\b[^.?]{0,40}\badd\s+a\s+capabilit"
            r"|\bhow\s+would\s+you\s+verify\s+such\s+a\s+change\b"
        ),
        (
            "atlas.reasoning.execution.registry",
            "atlas.evolution.development_cycle",
            "atlas.evolution.development_verification",
        ),
    ),
)


_ALL_SELF_KNOWLEDGE_TOPICS = (
    _SELF_KNOWLEDGE_TOPICS + _SELF_KNOWLEDGE_TOPICS_ATLAS_SPECIFIC
)

#: G1 — the semantic frame's self-knowledge CONCEPT -> the EXISTING self-knowledge
#: topic that owns it. The frame supplies the operational distinction; the
#: existing verified-anchor topic renderers still produce the answer.
_FRAME_CONCEPT_TOPICS: dict[str, str] = {
    "evidence_failure": "evidence and failure behaviour",
    "research_process": "research process",
    "request_flow": "request flow",
    "reference_resolution": "reference resolution",
    "owner_approval": "owner approval",
    "sandbox_execution": "sandbox execution",
    "authorization_boundary": "authorization boundary",
    "extension_points": "extension points",
    "development_process": "development process",
    "limitations": "current limitations",
}


def is_store_recall_shaped(text: str) -> bool:
    """True when the turn is a bounded memory/knowledge-store recall cue."""
    if not isinstance(text, str) or not text:
        return False
    return _RECALL_RE.search(text.lower()) is not None


def is_validated_knowledge_shaped(text: str) -> bool:
    """True when the turn matches an EXISTING validated-knowledge cue (either tier)."""
    if not isinstance(text, str) or not text:
        return False
    return _match_validated_knowledge_cue(text.lower()) is not None


#: G2 — leading interrogatives that mark an EXPLANATORY question rather than an
#: imperative directive. Combined with the shared frame's SELF_KNOWLEDGE domain
#: by :func:`is_explanatory_self_knowledge`.
_EXPLANATION_LEADS_RE = re.compile(r"^(?:how|what|which|where|who|why)\b")


def explanatory_self_knowledge_concept(text: str) -> str | None:
    """G2 — the frame's self-knowledge CONCEPT for an explanatory question.

    Uses the SHARED semantic frame (the single semantic source) instead of a new
    cue list: the turn must LEAD with an interrogative AND the frame must record
    the SELF_KNOWLEDGE domain. Returns that frame's concept, or ``None`` when the
    turn is not an explanatory self-knowledge question (an imperative directive
    such as "Add a new capability that ..." never matches, so the development
    path keeps it).
    """
    if not isinstance(text, str) or not text.strip():
        return None
    if _EXPLANATION_LEADS_RE.match(text.strip().lower()) is None:
        return None
    from atlas.conversation import semantic_frame as _frame

    frame = _frame.interpret(text)
    if frame.domain is not _frame.SemanticDomain.SELF_KNOWLEDGE:
        return None
    return frame.concept or None


def is_explanatory_self_knowledge(text: str) -> bool:
    """G2 — True for an explanatory QUESTION about Atlas's own mechanism."""
    return explanatory_self_knowledge_concept(text) is not None


def is_compound_shaped(text: str) -> bool:
    """True when the turn carries a second instruction after the first clause."""
    if not isinstance(text, str) or not text:
        return False
    return _COMPOUND_CONNECTOR_RE.search(text.lower()) is not None


#: Evidence-driven bounded component knowledge: a natural-language description
#: of a responsibility resolves to the ACTUAL existing component (verified
#: present before it is reported). This is metadata about existing components —
#: not a second registry, database, or model.
_COMPONENT_HINTS: tuple[tuple["re.Pattern[str]", str, str, str], ...] = (
    (
        re.compile(
            r"\bknowledge\s+(?:decision|sufficienc\w*)\b"
            r"|\bdecides?\s+whether\b[^.?]{0,40}\bexternal\s+knowledge\b"
            r"|\bexternal\s+knowledge\s+(?:is\s+)?necessary\b"
            r"|\bdecide\w*\b[^.?]{0,30}\bknowledge\b[^.?]{0,20}\bneed\w*\b"
            r"|\bknow\w*\b[^.?]{0,20}\benough\b"
        ),
        "atlas.research.knowledge_decision",
        "KnowledgeDecisionService",
        "Decides knowledge sufficiency and integrates governed external "
        "acquisition (D3). Reuses the existing validated-knowledge retriever "
        "and the D2 acquisition boundary.",
    ),
    (
        re.compile(
            r"\bwork\s+orchestrat\w*\b"
            r"|\bcoordinates?\s+work\s+execution\b"
            r"|\bcoordinar?t\w*\s+work\s+execution\b"
        ),
        "atlas.orchestration.work_orchestrator",
        "WorkOrchestrator",
        "Coordinates one objective across the existing knowledge decision, "
        "capability registry/dispatcher, and authorization boundary (D4).",
    ),
    (
        re.compile(r"\bdevelopment\s+orchestrat\w*\b"),
        "atlas.orchestration.development_orchestrator",
        "DevelopmentOrchestrator",
        "Coordinates the governed development lifecycle (D5) over the existing "
        "proposal, OWNER approval, sandbox, verification, and promotion "
        "components.",
    ),
    (
        re.compile(
            r"\bconversation\s+engine\b"
            r"|\bhandles\s+conversation\b"
            r"|\bconversation\s+system\b"
        ),
        "atlas.conversation.engine",
        "ConversationEngine",
        "Deterministic interpretation/orchestration boundary that projects a "
        "bounded SemanticIntake (D1); it holds no authority.",
    ),
)


def _match_component_hint(lowered: str) -> tuple[str, str, str] | None:
    """Return ``(module_path, class_name, responsibility)`` or None.

    Deterministic and bounded; the caller verifies the module is actually
    present before reporting it.
    """
    for pattern, module, cls, responsibility in _COMPONENT_HINTS:
        if pattern.search(lowered):
            return (module, cls, responsibility)
    return None


def _match_atlas_specific_self_knowledge_topic(lowered: str) -> str | None:
    """Return an Atlas-specific self-knowledge topic, or None.

    Bounded to the evidence-driven topics that name Atlas-only concepts, so a
    question such as "if you needed a new capability, where would it fit?" is
    answered as self-knowledge rather than as a generic capability inventory.
    """
    for topic, pattern, _anchors in _SELF_KNOWLEDGE_TOPICS_ATLAS_SPECIFIC:
        if pattern.search(lowered):
            return topic
    return None


def _self_knowledge_anchors(topic: str) -> tuple[str, ...]:
    """Return the verified anchor module paths recorded for ``topic``."""
    for name, _pattern, anchors in _ALL_SELF_KNOWLEDGE_TOPICS:
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

#: Evidence-driven external-knowledge phrasing about an EXTERNAL subject. The
#: subject is extracted deterministically; Atlas-self subjects are excluded so
#: "what is your status" stays Atlas status. This runs BEFORE ``_STATUS_RE`` so
#: an external subject's "current status" is never answered as Atlas's status.
_EXTERNAL_KNOWLEDGE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*(?:what(?:'s| is)?\s+)?(?:the\s+)?(?:current\s+)?status\s+of\s+"
        r"(?P<topic>.+?)\s*\??\s*$"
    ),
    re.compile(
        r"^\s*what(?:'s| is)?\s+happening\s+(?:with|to)\s+(?P<topic>.+?)\s*\??\s*$"
    ),
    re.compile(
        r"^\s*(?:what(?:'s| is)?\s+)?(?:the\s+)?latest\s+"
        r"(?:information|news|updates?|developments?)\s+"
        r"(?:about|on|for|regarding)\s+(?P<topic>.+?)\s*\??\s*$"
    ),
    re.compile(
        r"^\s*(?:can\s+you\s+|please\s+|could\s+you\s+)?(?:find|get|tell\s+me)\s+"
        r"(?:the\s+)?latest\s+(?:information|news|updates?|developments?)\s+"
        r"(?:about|on|for|regarding)\s+(?P<topic>.+?)\s*\??\s*$"
    ),
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


# ---------------------------------------------------------------------------
# Evidence-Driven Improvement 3 — explicit conversational research/knowledge
# requests ("Research X.", "Can you look into X?", "Find information about X.").
#
# These are REQUESTS FOR INFORMATION, so they enter the SAME local-first
# knowledge path as the validated-knowledge bridge (existing retrieval, then the
# existing D3 knowledge decision which owns the governed D2 boundary). Inventory
# only — no new engine, store, provider, or acquisition surface.
# ---------------------------------------------------------------------------

#: Bounded single-clause research/knowledge request forms. Anchored to the WHOLE
#: turn, and the caller additionally declines a compound turn, so no instruction
#: that continues after the subject is captured here.
_RESEARCH_REQUEST_RES: tuple["re.Pattern[str]", ...] = (
    re.compile(
        r"^\s*(?:can you\s+|could you\s+|please\s+|i'?d like you to\s+)?"
        r"research\s+(?:about\s+|on\s+|into\s+)?(?P<topic>.+?)\s*[.!?]*\s*$"
    ),
    re.compile(
        r"^\s*i'?d\s+like\s+(?:some\s+)?research\s+(?:on|about|into)\s+"
        r"(?P<topic>.+?)\s*[.!?]*\s*$"
    ),
    re.compile(
        r"^\s*(?:can you\s+|could you\s+|please\s+)?look\s+into\s+"
        r"(?P<topic>.+?)\s*[.!?]*\s*$"
    ),
    re.compile(
        r"^\s*(?:can you\s+|could you\s+|please\s+)?find\s+(?:information|info)"
        r"\s+(?:about|on)\s+(?P<topic>.+?)\s*[.!?]*\s*$"
    ),
    re.compile(
        r"^\s*(?:can you\s+|could you\s+|please\s+)?find\s+out\s+(?:about\s+)?"
        r"(?P<topic>.+?)\s*[.!?]*\s*$"
    ),
    re.compile(
        r"^\s*(?:can you\s+|could you\s+|please\s+)?look\s+up\s+"
        r"(?P<topic>.+?)\s*[.!?]*\s*$"
    ),
    re.compile(
        r"^\s*(?:can you\s+|could you\s+|please\s+)?search\s+for\s+"
        r"(?P<topic>.+?)\s*[.!?]*\s*$"
    ),
)

#: A redundant information lead inside a captured research subject
#: ("search for information about X" -> "X").
_INFORMATION_LEAD_RE = re.compile(r"^(?:information|info|knowledge|details?)\s+(?:about|on|for|regarding)\s+")

#: A second-instruction connector marks a COMPOUND turn. Compound handling is
#: out of scope for this improvement, so those turns keep their existing path.
_COMPOUND_CONNECTOR_RE = re.compile(
    r";"
    r"|\b(?:and|then)\s+(?:also\s+)?"
    r"(?:tell|summari[sz]e|explain|report|show|list|compare|check|verify|"
    r"write|give|describe|analy[sz]e|investigate|find)\b"
    r"|\balso\s+(?:tell|summari[sz]e|explain|report|show|list)\b"
)

#: Bounded demonstrative/possessive subjects that must be resolved from the
#: active conversational subject instead of being passed literally.
BOUNDED_REFERENCE_HEADS: frozenset[str] = frozenset(
    {"that", "this", "it", "its", "these", "those", "the same"}
)


def knowledge_topic(text: str) -> str | None:
    """Public bounded topic reduction (C6.1 rules; reused by I3).

    Case-insensitive: the reduction is defined over the lowercase token form, so
    the input is lowercased here (the existing internal callers already pass an
    already-lowercased remainder).
    """
    if not isinstance(text, str):
        return None
    return _validated_knowledge_topic(text.lower())


def research_request_subject(text: str) -> str | None:
    """Return the bounded RAW subject of a research/knowledge request, or None.

    ``None`` for a non-research turn and for a compound turn (a turn that
    continues with a second instruction keeps its existing path). The returned
    subject is the single-clause text after the request cue, BEFORE topic
    reduction, so the caller can apply bounded reference substitution first.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = text.strip()
    if _COMPOUND_CONNECTOR_RE.search(stripped.lower()):
        return None
    lowered = stripped.lower()
    for pattern in _RESEARCH_REQUEST_RES:
        match = pattern.search(lowered)
        if match is None:
            continue
        topic = _INFORMATION_LEAD_RE.sub("", match.group("topic").strip()).strip()
        return topic or None
    return None


def substitute_reference_subject(raw_subject: str, active_subject: str) -> str:
    """Replace a leading bounded reference with the active subject.

    Deterministic: the leading reference token (``that``/``this``/``it``/
    ``its``/``the same``) is replaced by ``active_subject``; any trailing words
    are kept ("its latest activity" -> "<active> latest activity"). Returns the
    subject unchanged when it does not begin with a bounded reference.
    """
    if not isinstance(raw_subject, str) or not raw_subject.strip():
        return raw_subject
    tokens = raw_subject.split()
    head = tokens[0].lower()
    if head == "the" and len(tokens) > 1 and tokens[1].lower() == "same":
        rest = tokens[2:]
        return " ".join([active_subject, *rest]).strip()
    rest = tokens[1:]
    if head in BOUNDED_REFERENCE_HEADS or head in {"it", "its", "that", "this"}:
        return " ".join([active_subject, *rest]).strip()
    return raw_subject


def is_bounded_reference_subject(raw_subject: str) -> bool:
    """True when ``raw_subject`` begins with a bounded reference token."""
    if not isinstance(raw_subject, str) or not raw_subject.strip():
        return False
    tokens = raw_subject.split()
    return tokens[0].lower() in BOUNDED_REFERENCE_HEADS


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


#: Classification must be INVARIANT under surface punctuation/formatting: a
#: pause comma or a doubled "?" must not change which intent owns the turn
#: ("What, can you do?" == "What can you do?"). The comparison form strips
#: punctuation and collapses whitespace deterministically; these are the
#: closed canonical phrases whose reading must therefore not depend on it.
_PUNCTUATION_RE = re.compile(r"[^a-z0-9\s]+")
_CANONICAL_HELP_PHRASES: frozenset[str] = frozenset({"what can you do"})
#: Same invariance for the canonical status questions whose phrase patterns are
#: otherwise punctuation-sensitive ("How are things looking?" vs "How, are
#: things looking?").
_CANONICAL_STATUS_PHRASES: frozenset[str] = frozenset(
    {"how are you", "how are things looking", "how are things going"}
)


def _punctuation_insensitive(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace (deterministic)."""
    return " ".join(_PUNCTUATION_RE.sub(" ", text.lower()).split())

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
        knowledge_decision_provider: Callable[[str], Any] | None = None,
        architecture_relationship_provider: Callable[[], Any] | None = None,
        knowledge_status_provider: Callable[[str], Any] | None = None,
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
        #: D3 — optional one-argument callable returning validated knowledge for
        #: a query, LOCAL-FIRST and possibly acquiring through the governed D2
        #: boundary. It is consulted ONLY when the local validated store already
        #: has nothing, and its result is used only when it actually carries
        #: validated claims — otherwise the existing (C6.1) outcome is rendered
        #: unchanged. External content it returns is data, never authority.
        self._knowledge_decision_provider = knowledge_decision_provider
        #: G2 — optional zero-argument callable returning the SAME
        #: ``ArchitectureModel`` built from the kernel's bounded, once-only
        #: repository map (``Atlas.architecture_model()``). It is consulted ONLY
        #: for an EXPLICIT named-target relationship question and only when the
        #: cache-only snapshot carries no module evidence, so a casual
        #: architecture question can never trigger a repository scan. Read-only
        #: and fail-soft: absent, None, non-model, or raising all decline.
        self._architecture_relationship_provider = architecture_relationship_provider
        #: G2 — optional one-argument callable delegating to the EXISTING
        #: knowledge-decision SERVICE (``KnowledgeDecisionService.decide``, the
        #: same decision the ``answer_knowledge_question`` API seam uses). It is
        #: consulted only to REPORT sufficiency and governed-acquisition status
        #: for a knowledge question the local store could not answer. It grants
        #: no authority, and its result is data, never instruction.
        self._knowledge_status_provider = knowledge_status_provider

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

    @property
    def architecture_relationship_provider(self) -> Callable[[], Any] | None:
        return self._architecture_relationship_provider

    @property
    def knowledge_status_provider(self) -> Callable[[str], Any] | None:
        return self._knowledge_status_provider

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
        return self._build_message(intent, detail, message_count=message_count)

    def match_self_knowledge_topic(self, text: str) -> Message | None:
        """Evidence-driven: claim an Atlas-specific self-knowledge topic.

        Deterministic, read-only, and provider-free: the topic's module anchors
        are verified before any prose is emitted. Returns None when the turn is
        not such a topic or no architecture model is available, so existing
        behaviour then applies unchanged. Grants no authority.
        """
        if not isinstance(text, str) or self._resolve_architecture_model() is None:
            return None
        topic = _match_atlas_specific_self_knowledge_topic(text.strip().lower())
        if topic is None:
            return None
        return self._build_message(BUILTIN_INTENT_SELF_KNOWLEDGE, topic)

    def match_external_knowledge(self, text: str) -> Message | None:
        """Evidence-driven: claim an external-knowledge request early.

        Routes through the same local-first retrieval + D3 knowledge-decision
        provider (and, when required and authorized, the D2 boundary) as the
        validated-knowledge bridge — never a direct provider call. Returns None
        when no provider is wired or the turn is not an external-knowledge
        request, so existing behaviour then applies unchanged.
        """
        if not isinstance(text, str):
            return None
        detail = self._match_external_knowledge(text.strip().lower())
        if detail is None:
            return None
        return self._build_message(BUILTIN_INTENT_VALIDATED_KNOWLEDGE, detail)

    def _build_message(
        self,
        intent: str,
        detail: Any,
        message_count: int | None = None,
    ) -> Message:
        """Build a deterministic assistant Message for ``intent``/``detail``."""
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

    def match_registered_capability_detail(self, text: str) -> Message | None:
        """Return the capability-detail reply for an EXPLICIT detail request
        that names a REGISTERED capability/tool, or ``None``.

        Narrower than :meth:`respond`: it claims ONLY the capability-detail
        intent, and only when the candidate name resolves against the
        authoritative capability/tool registries. It exists so the conversation
        layer can honour the advertised ``explain <name>`` form for a
        registered name BEFORE generic investigation/research cue matching can
        preempt it when the name itself contains a cue token (``analysis``,
        ``trace``, ``research``). It performs no other classification, invents
        nothing, and grants no authority: an unresolved name returns ``None``
        (fail-closed), exactly like the existing detail matcher.
        """
        lowered = canonicalize_surface(text).lower()
        if not lowered:
            return None
        name = self._match_capability_detail(lowered)
        if name is None:
            return None
        return Message(
            role="assistant",
            content=self._render_capability_detail(name),
            metadata={
                "builtin_response": True,
                "builtin_intent": BUILTIN_INTENT_CAPABILITY_DETAIL,
                "model_used": False,
            },
        )

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
                # G2 — an EXPLANATORY question about Atlas's own mechanism is
                # self-knowledge even when Intake typed it as a development
                # request ("how would you add a new capability?"). Narrow by
                # construction: the turn must lead with an interrogative, the
                # shared frame must record SELF_KNOWLEDGE, and the frame's
                # concept must map onto an EXISTING verified-anchor topic (or the
                # architecture surface); an imperative directive never matches.
                concept = explanatory_self_knowledge_concept(text)
                if concept is not None:
                    topic = _FRAME_CONCEPT_TOPICS.get(concept)
                    if topic is not None:
                        return (BUILTIN_INTENT_SELF_KNOWLEDGE, topic)
                    if concept in ("component", "architecture", "knowledge_sufficiency"):
                        return (BUILTIN_INTENT_ARCHITECTURE, text)
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
        # Evidence-driven: Atlas-specific self-knowledge topics (request flow /
        # development / OWNER / sandbox / authorization boundary / extension
        # points) are checked before the capability inventory so an
        # extension-point question is not answered as a generic capability list.
        atlas_topic = _match_atlas_specific_self_knowledge_topic(lowered)
        if atlas_topic is not None and (
            self._resolve_architecture_model() is not None
        ):
            return (BUILTIN_INTENT_SELF_KNOWLEDGE, atlas_topic)
        capabilities_word = _CAPABILITIES_RE.search(lowered) is not None
        if capabilities_word and not self._capabilities_intent_applies(
            lowered, context
        ):
            capabilities_word = False
        # G1 — a capability GAP request ("Atlas needs a new capability for X") is
        # a development request, never an inventory request.
        if capabilities_word and self._frame_is_development(text):
            capabilities_word = False
        if capabilities_word or _alias_hit(_CAPABILITY_ALIAS_RES, lowered):
            return BUILTIN_INTENT_CAPABILITIES
        # Formatting invariance: the canonical usage question is owned by help
        # regardless of interior punctuation ("What, can you do?").
        if _HELP_RE.search(lowered) or (
            _punctuation_insensitive(lowered) in _CANONICAL_HELP_PHRASES
        ):
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
        # G1 — semantic-frame seam. Placed AFTER every self-knowledge /
        # capability / help / identity / architecture surface above, so a frame
        # classification can never steal a more specific existing route; it only
        # claims the paraphrases those bounded surfaces left unclaimed, and the
        # answer still comes from the existing topic renderer.
        frame_intent = self._match_frame_self_or_capability(text, context)
        if frame_intent is not None:
            return frame_intent
        # Evidence-driven: an EXTERNAL subject's "current status" (or equivalent
        # external-knowledge phrasing) is not Atlas's own status. Route it to the
        # governed knowledge path (D3 local-first; D2 acquisition when
        # authorized) instead of the status report.
        external_knowledge = self._match_external_knowledge(lowered)
        if external_knowledge is not None:
            return (BUILTIN_INTENT_VALIDATED_KNOWLEDGE, external_knowledge)
        if (
            _STATUS_RE.search(lowered)
            or _alias_hit(_STATUS_ALIAS_RES, lowered)
            or _punctuation_insensitive(lowered) in _CANONICAL_STATUS_PHRASES
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
        # The shared semantic frame's acknowledgement class is honoured too, so
        # the frame and the floor cannot disagree ("That makes sense.").
        if _ACKNOWLEDGEMENT_RE.search(lowered) or self._frame_is_acknowledgement(
            text
        ):
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

    @staticmethod
    def _frame_is_development(text: str) -> bool:
        """G1 — does the semantic frame classify this turn as DEVELOPMENT?"""
        from atlas.conversation import semantic_frame as _frame

        return _frame.is_development_shaped(text)

    @staticmethod
    def _frame_is_acknowledgement(text: str) -> bool:
        """G1 — does the semantic frame classify this turn as an acknowledgement?"""
        from atlas.conversation import semantic_frame as _frame

        if not isinstance(text, str) or not text.strip():
            return False
        return _frame.interpret(text).role is _frame.SemanticRole.ACKNOWLEDGEMENT

    def _match_frame_self_or_capability(
        self, text: str, context: Any = None
    ) -> str | tuple[str, object] | None:
        """G1 — claim a SELF_KNOWLEDGE / CAPABILITIES turn from its semantic frame.

        Additive and precedence-preserving by CONSTRUCTION: it is consulted only
        after every existing self-knowledge / atlas-topic / capability / help /
        identity / self-description / architecture surface, so it can only claim
        turns those surfaces left unclaimed. The frame supplies the operational
        concept; the EXISTING verified-anchor topic renderers produce the answer.

        Returns ``None`` for every other domain, for a governance-sensitive
        directive, and whenever the owning surface has no injected model.
        """
        from atlas.conversation import semantic_frame as _frame

        if not isinstance(text, str) or not text.strip():
            return None
        frame = _frame.interpret(text)
        if frame.governance_sensitive:
            return None
        # A turn the ESTABLISHED self-description surface already defines ("what
        # Atlas does", "how does Atlas work") keeps that surface: it answers from
        # the existing models when they are available and otherwise fails soft to
        # the unsupported floor. The frame seam must never claim such a turn as a
        # generic capability inventory.
        lowered = canonicalize_surface(text).lower()
        if _SELF_DESCRIPTION_RE.search(lowered):
            return None
        # A turn an EXISTING knowledge bridge already owns keeps that bridge
        # (its cue tiers and renderings are pinned).
        if is_validated_knowledge_shaped(text) or is_store_recall_shaped(text):
            return None
        if frame.domain is _frame.SemanticDomain.SELF_KNOWLEDGE:
            if self._resolve_architecture_model() is None:
                return None
            topic = _FRAME_CONCEPT_TOPICS.get(frame.concept)
            if topic is not None:
                return (BUILTIN_INTENT_SELF_KNOWLEDGE, topic)
            if frame.concept in ("component", "architecture", "knowledge_sufficiency"):
                return (BUILTIN_INTENT_ARCHITECTURE, text)
            # The generic "how do you work" concept stays UNROUTED: the existing
            # self-description surface keeps its own bounded cues, so a broader
            # question ("how does your memory system work?") still reaches its
            # existing deterministic floor behaviour.
            return None
        if frame.domain is _frame.SemanticDomain.CAPABILITIES:
            lowered = canonicalize_surface(text).lower()
            if not self._capabilities_intent_applies(lowered, context):
                return None
            return BUILTIN_INTENT_CAPABILITIES
        if frame.domain is _frame.SemanticDomain.STATUS:
            # A paraphrase of the Atlas status question (an external subject's
            # status is classified KNOWLEDGE and never reaches here).
            return BUILTIN_INTENT_STATUS
        return None

    def match_knowledge_request(self, subject: str) -> Message | None:
        """G1 — answer a knowledge request from the EXISTING local-first path.

        The subject must already be a bounded, reference-resolved topic. The
        answer comes from the existing validated-knowledge retrieval, then the
        existing D3 knowledge-decision provider (which owns the governed D2
        boundary); the retrieval's own honest outcome is reported verbatim.
        """
        if self._validated_knowledge_provider is None:
            return None
        if not isinstance(subject, str) or not subject.strip():
            return None
        resolved = self._knowledge_result(subject.strip(), require_items=False)
        if resolved is None:
            return None
        return self._build_message(BUILTIN_INTENT_VALIDATED_KNOWLEDGE, resolved)

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
        resolved = self._knowledge_result(query, require_items=not explicit)
        if resolved is None:
            return None
        return resolved

    def match_knowledge_request(self, subject: str) -> Message | None:
        """Evidence-Driven Improvement 3 — answer a research/knowledge request.

        ``subject`` is the bounded, reference-resolved subject of the turn. The
        answer is produced by the SAME local-first path as the validated-
        knowledge bridge: the existing retrieval first, then the existing D3
        knowledge-decision provider (which owns the governed D2 boundary and is
        consulted only when the local store has nothing). The retrieval's own
        authoritative outcome is reported verbatim — including the honest
        ``empty``/``store_unavailable`` outcome — so nothing is acquired,
        inferred, or invented here, and no completion report is fabricated.
        """
        if self._validated_knowledge_provider is None:
            return None
        if not isinstance(subject, str) or not subject.strip():
            return None
        resolved = self._knowledge_result(subject.strip(), require_items=False)
        if resolved is None:
            return None
        return self._build_message(BUILTIN_INTENT_VALIDATED_KNOWLEDGE, resolved)

    def _knowledge_result(
        self, query: str, *, require_items: bool
    ) -> tuple[str, Any] | None:
        """Resolve ``query`` local-first, then through D3/D2, or None.

        Returns ``(query, result)``; ``result`` is the existing capability's own
        result object. ``require_items`` fails closed for cues the existing
        recall also claims (unchanged C6.1 behaviour), while an explicit
        knowledge request reports the retrieval's own outcome even when empty.
        """
        result = self._retrieve_validated_knowledge(query)
        if result is None:
            return None
        # D3 — local-first, then governed acquisition. Only when the local store
        # has nothing is the knowledge-decision provider consulted; it is used
        # only when it returns validated claims. In every other case (including
        # the default deny-by-default configuration) the local result is
        # returned unchanged, so C6.1 behaviour is preserved verbatim.
        if (
            self._knowledge_decision_provider is not None
            and not self._validated_knowledge_items(result)
        ):
            enriched = self._try_knowledge_decision(query)
            if enriched is not None and self._validated_knowledge_items(enriched):
                result = enriched
        if require_items and not self._validated_knowledge_items(result):
            return None
        return (query, result)

    def _match_external_knowledge(self, lowered: str) -> tuple[str, Any] | None:
        """Resolve an external-knowledge turn to ``(query, result)`` or None.

        Uses the same local-first retrieval + D3/D2 knowledge-decision provider
        as the validated-knowledge bridge. Atlas-self subjects are excluded, so
        it cannot capture "what is your status".
        """
        if self._validated_knowledge_provider is None:
            return None
        for pattern in _EXTERNAL_KNOWLEDGE_RES:
            match = pattern.search(lowered)
            if match is None:
                continue
            topic = _validated_knowledge_topic(match.group("topic"))
            if topic is None:
                return None
            result = self._retrieve_validated_knowledge(topic)
            if result is None:
                return None
            enriched = self._try_knowledge_decision(topic)
            if enriched is not None and self._validated_knowledge_items(enriched):
                result = enriched
            return (topic, result)
        return None

    def _try_knowledge_decision(self, query: str) -> Any | None:
        """Consult the D3 knowledge-decision provider (fail-soft, read-only)."""
        provider = self._knowledge_decision_provider
        if provider is None:
            return None
        try:
            return provider(query)
        except Exception:  # fail closed -> existing behaviour unchanged
            return None

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
        # G1 — bounded structured-state candidates (LOWEST precedence, so every
        # candidate above keeps its behaviour): the subject of the retained
        # knowledge answer, then the active objective. Both are structured
        # conversation state, which this surface is documented to consult.
        if state is not None:
            recorded = getattr(state, "last_knowledge", None)
            if isinstance(recorded, dict):
                query = recorded.get("query")
                if isinstance(query, str) and query.strip():
                    return query.strip()
            objective = getattr(state, "current_objective", None)
            if isinstance(objective, str) and objective.strip():
                return objective.strip()
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

    def _resolve_relationship_model_for(self, query: str, model: Any) -> Any | None:
        """G2 — bounded relationship snapshot for an EXPLICIT named target.

        The cache-only model omits module-level facts until a repository map has
        been built, so a dependency/impact question about a named module would
        report only "none". This consults the injected relationship provider —
        the SAME ``ArchitectureModel`` built from the kernel's bounded, once-only
        repository map — and only when BOTH hold:

        * the turn names an explicit dotted module/package target, and
        * the cache-only model carries no module evidence.

        A casual architecture question ("what are the main systems that make up
        Atlas?") names no target, so no build is ever triggered for it. Fail-soft:
        absent provider, None, non-model, or raising all return None and the
        caller keeps the cache-only model.
        """
        provider = self._architecture_relationship_provider
        if provider is None:
            return None
        if not isinstance(query, str) or not _ARCHITECTURE_TARGET_RE.search(query):
            return None
        if getattr(model, "module_count", 0):
            return None
        try:
            candidate = provider()
        except Exception:
            return None
        if candidate is None or not hasattr(candidate, "locate"):
            return None
        return candidate

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
            if topic == "request flow":
                return (
                    "A turn enters through ConversationService "
                    "(Atlas.chat / Atlas.stream), which builds a bounded "
                    "ConversationContext and runs the deterministic TaskIntake.",
                    "The D1 ConversationEngine projects a bounded SemanticIntake; "
                    "the existing routing cascade then applies reference "
                    "resolution and the governed handlers.",
                    "Knowledge-bearing turns consult the D3 "
                    "KnowledgeDecisionService: existing validated knowledge first, "
                    "then the governed D2 acquisition boundary (authorized hosts "
                    "only).",
                    "Read-only capability work is coordinated by the D4 "
                    "WorkOrchestrator; governed development is coordinated by the "
                    "D5 DevelopmentOrchestrator.",
                    "Free-text conversation currently connects intake, knowledge "
                    "decision, and the governed handlers; the D4/D5 orchestrators "
                    "are reachable through their explicit kernel APIs, not as an "
                    "automatic free-text path.",
                )
            if topic == "development process":
                return (
                    "A development objective is prepared by the existing "
                    "DevelopmentDriver (gap assessment then a bounded proposal) as "
                    "a DRAFT EvolutionProposal.",
                    "It stops at the existing approval boundary (PENDING_APPROVAL). "
                    "The D5 DevelopmentOrchestrator only coordinates; it never "
                    "approves.",
                    "After OWNER approval, implementation runs in the existing "
                    "disposable sandbox (SelfDevelopmentLoop / CodeSandbox); the "
                    "live repository is never modified.",
                    "Verification (DevelopmentVerification) is required before "
                    "promotion; promotion is OWNER-only through the existing "
                    "PromotionGate / PromotionExecutor.",
                )
            if topic == "owner approval":
                return (
                    "OWNER approval is enforced by the existing authority "
                    "boundary (AuthorityService + SessionManager) and recorded "
                    "through the existing ApprovalManager.",
                    "Approving is a separate explicit step from planning: a "
                    "proposal can never approve itself, and approval alone never "
                    "executes anything.",
                )
            if topic == "sandbox execution":
                return (
                    "Development implementation runs inside the existing "
                    "disposable CodeSandbox via SelfDevelopmentLoop; the live "
                    "repository is never modified.",
                    "Only bounded, registered sandbox tools run; promotion to the "
                    "live repository is a separate OWNER-only step.",
                )
            if topic == "authorization boundary":
                return (
                    "Natural-language interpretation never grants authority: the "
                    "D1 SemanticIntake carries no authority field and records "
                    "provenance authority as 'none'.",
                    "Only the existing AuthorityService / SessionManager and "
                    "ApprovalManager can authorize; approval requires an OWNER "
                    "session and a fingerprint-bound proposal.",
                )
            if topic == "extension points":
                return (
                    "A new capability is registered through the existing "
                    "CapabilityRegistry (the DEFAULT_HANDLERS / factory pattern); "
                    "the existing CapabilityRouter and CapabilityDispatcher remain "
                    "authoritative.",
                    "Prefer reusing existing services (knowledge decision, "
                    "capability registry/dispatcher, authority boundary) instead "
                    "of adding parallel systems.",
                    "Such a change is verified through the existing governed "
                    "development lifecycle: proposal, OWNER approval, sandbox "
                    "implementation, DevelopmentVerification, then promotion.",
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
        # G2 — a RELATIONSHIP question about an EXPLICIT named target may use the
        # bounded relationship snapshot, so dependency/impact facts are reported
        # from the existing repository map instead of an empty "none". Casual
        # architecture questions are unaffected (no target -> no build).
        relationship_model = self._resolve_relationship_model_for(query, model)
        if relationship_model is not None:
            model = relationship_model

        lines = [
            "Atlas architecture self-knowledge "
            "(deterministic, read-only; no external AI model used):",
        ]

        # Evidence-driven component identity: resolve an evidenced
        # natural-language responsibility to the ACTUAL component. The module is
        # verified present before it is reported; nothing is invented.
        hint = _match_component_hint((query or "").lower())
        if hint is not None:
            module, cls, responsibility = hint
            if self._verify_anchor(module):
                lines.append(
                    f"- Component: `{cls}` in `{module.replace('.', '/')}.py`"
                )
                lines.append(f"- Responsibility: {responsibility}")
                lines.append("")
                lines.append(
                    "This is a bounded projection of Atlas's existing structural "
                    "sources; nothing was modified."
                )
                return "\n".join(lines)

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
        lines.extend(self._knowledge_sufficiency_note(str(query)))
        lines.append(
            "Only claims an authorized source already SUPPORTED are reported; "
            "nothing is acquired, inferred, or invented for this answer."
        )
        return " ".join(lines)

    def _knowledge_sufficiency_note(self, query: str) -> tuple[str, ...]:
        """G2 — structured sufficiency/acquisition report for an unmatched query.

        Consults the EXISTING knowledge-decision service (the same decision the
        ``answer_knowledge_question`` API seam exposes) and renders ONLY its own
        fields: sufficiency status, governed-acquisition status, and its own
        message. Nothing is acquired, inferred, invented, or authorized here —
        the note states the boundary and what would be required to answer.
        Fail-soft: no provider, a raising provider, or an unusable result all
        render nothing, so the existing (C6.1) answer is unchanged.
        """
        provider = self._knowledge_status_provider
        if provider is None or not isinstance(query, str) or not query.strip():
            return ()
        try:
            decision = provider(query.strip())
        except Exception:
            return ()
        if decision is None:
            return ()
        status = getattr(decision, "status", "") or ""
        status = str(getattr(status, "value", status) or "")
        acquisition = str(getattr(decision, "acquisition_status", "") or "")
        message = str(getattr(decision, "message", "") or "").strip()
        lines = [
            f"- Knowledge decision (D3): sufficiency {status or 'unsupported'}."
        ]
        if acquisition:
            lines.append(f"- Governed acquisition: {acquisition}.")
        if message:
            lines.append(f"- Decision note: {message}")
        lines.append(
            "- Required to answer: validated claims from an authorized source; "
            "none is invented or acquired on my own."
        )
        return tuple(lines)

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
