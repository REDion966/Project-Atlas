"""Atlas Conversation — G1 semantic frame matcher.

The G1 language-understanding layer. It turns an ordinary utterance into a
bounded, inspectable, deterministic **semantic frame**:

    role      — what the turn IS (new objective / follow-up / correction /
                acknowledgement / recall / continuation / clarification /
                reference / casual)
    domain    — which existing Atlas capability OWNS it (capabilities,
                capability detail, self-knowledge, status, knowledge,
                investigation, work, development, governance, casual)
    operation — the requested operation, when the turn names one
    subject   — the bounded subject span
    subrequests — bounded compound decomposition (operation + domain each)

Rules are expressed over word CLASSES (:mod:`atlas.conversation.lexicon`), not
literal phrases, so ordinary synonymy and inflection resolve to the same frame
("What can you do?" / "What's within your capabilities?" / "Tell me what you're
able to handle." -> CAPABILITIES).

Boundaries (mandatory):
  * interpretation ONLY — it never routes, approves, authorizes, executes,
    promotes, or mutates anything, and it carries no authority;
  * it identifies the OWNER domain and leaves behaviour to the existing
    services (D3 knowledge decision, D4/D5 orchestration, capability registry,
    governance/authority, the builtin response surfaces);
  * deterministic and model-independent: standard library only, no clock, no
    randomness, no I/O, no network, no model, no embeddings;
  * fail-closed: when the evidence is insufficient the frame is AMBIGUOUS
    (clarification) or UNSUPPORTED rather than a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from atlas.conversation.lexicon import (
    ACK_FILLERS,
    ACK_WORDS,
    ACT_VERBS,
    CAPABILITY_NOUNS,
    CAPABILITY_VERBS,
    COMPARE_VERBS,
    COMPOUND_CONNECTORS,
    CONTINUATION_FILLERS,
    CONTINUATION_VERBS,
    DEVELOP_VERBS,
    EXPLAIN_VERBS,
    FOLLOW_UP_VERBS,
    FOLLOW_UP_WORDS,
    GOVERNANCE_VERBS,
    GREETING_WORDS,
    INVESTIGATE_VERBS,
    KNOWLEDGE_NOUNS,
    LEARN_VERBS,
    RECALL_NOUNS,
    RECALL_VERBS,
    REFERENCE_WORDS,
    RESEARCH_VERBS,
    SELF_ARCHITECTURE_CONCEPTS,
    SELF_APPROVAL_CONCEPTS,
    SELF_AUTHORIZATION_CONCEPTS,
    SELF_COMPONENT_CONCEPTS,
    SELF_DEVELOPMENT_CONCEPTS,
    SELF_EVIDENCE_CONCEPTS,
    SELF_EXTENSION_CONCEPTS,
    SELF_FAILURE_TRIGGERS,
    SELF_FLOW_CONCEPTS,
    INTEREST_WORDS,
    SELF_GOVERNANCE_CONCEPTS,
    SELF_RESEARCH_CONCEPTS,
    SELF_REFERENCE_RES_CONCEPTS,
    SELF_SANDBOX_CONCEPTS,
    SELF_SUFFICIENCY_CONCEPTS,
    SELF_WORDS,
    has_any,
    normalize_token,
    tokens,
)

#: Hard bounds.
MAX_SUBJECT_TOKENS: int = 10
MAX_SUBREQUESTS: int = 4

#: True interrogation words (a leading auxiliary alone is NOT a question marker).
_WH_WORDS: frozenset[str] = frozenset(
    {"what", "which", "who", "whom", "whose", "why", "when", "where", "how"}
)

#: Acknowledgement signals: an ack word, or a bounded ack idiom.
_ACK_IDIOMS: frozenset[str] = frozenset(
    {"make", "sense", "problem", "worry", "mistake", "help"}
)
_ACK_WORDS: frozenset[str] = ACK_WORDS | _ACK_IDIOMS
_ACK_FILLERS: frozenset[str] = ACK_FILLERS
_ACK_SIGNALS: frozenset[str] = _ACK_WORDS

#: Concrete work objects (a capability verb aimed at one is a WORK request).
_WORK_OBJECTS: frozenset[str] = frozenset(
    {"this", "that", "it", "task", "problem", "issue", "objective", "goal", "job", "request"}
)

#: Assistance verbs. Bound to a CONCRETE object ("help me with scheduling"),
#: they signal a request FOR ASSISTANCE with that object, not a question about
#: Atlas's capability inventory; bare ("what can you help with") or generic
#: ("which things can you help me with") they stay inventory questions.
_ASSIST_VERBS: frozenset[str] = frozenset({"help", "support", "assist"})

#: Generic placeholder objects that carry no specific subject, so an assistance
#: frame aimed at one of them stays a capability-scope question.
_GENERIC_OBJECTS: frozenset[str] = frozenset(
    {"thing", "anything", "something", "everything", "nothing", "stuff", "matter", "case"}
)

#: Self-knowledge concepts for the evidence/failure/limitations family.
_SELF_FAILURE_CONCEPTS: frozenset[str] = frozenset(
    {"limitation", "failure", "fail", "cannot", "unable", "unknown", "unsure",
     "denied", "deny", "insufficient"}
)

#: Words that make a component question GENERIC (about some other system).
_GENERIC_MARKERS: frozenset[str] = frozenset(
    {"normally", "generally", "usually", "typically", "kind", "other", "industry"}
)

#: Actor signals that make a component question a "who does what" question.
_COMPONENT_ACTORS: frozenset[str] = frozenset(
    {"handle", "decide", "responsible", "perform", "do", "own", "manage", "run"}
)

#: Modals that express "Atlas should acquire this".
_GAP_MODALS: frozenset[str] = frozenset(
    {"need", "should", "want", "require", "must", "ought"}
)

#: Replacement signals: the turn REPLACES the active reading with a new subject.
#: Detected on the raw surface (the lemma map collapses "meant" onto "mean", and
#: the replacement/refinement distinction is a tense distinction).
_REPLACEMENT_PHRASES: tuple[str, ...] = (
    "actually", "meant", "correction", "instead", "sorry", "rather",
    "rephrase", "forget the",
)

#: Refinement signals: the turn REFINES/qualifies the active reading (it stays).
_REFINEMENT_PHRASES: tuple[str, ...] = (
    "i mean", "mean it", "mean the", "mean you", "specifically", "precisely",
    "referring", "clarify",
)

#: Function words dropped from a bounded subject span.
_SUBJECT_STOP: frozenset[str] = frozenset(
    {
        "a", "about", "all", "an", "and", "any", "are", "as", "at", "be",
        "been", "by", "can", "could", "current", "detail", "do", "for", "from",
        "get", "give", "had", "has", "have", "how", "i", "in", "info",
        "information", "into", "is", "it", "its", "me", "more", "my", "now",
        "of", "on", "or", "our", "please", "some", "tell", "that", "the",
        "their", "them", "then", "there", "these", "this", "those", "to", "up",
        "us", "was", "we", "were", "what", "when", "where", "which", "who",
        "why", "will", "with", "would", "you", "your",
    }
)

#: External-subject STATUS vocabulary ("any updates on X", "the state of X").
_EXTERNAL_STATUS_WORDS: frozenset[str] = frozenset(
    {"status", "state", "update", "news", "happening", "progress", "development"}
)

#: Prepositions that BIND a knowledge/interest word to its subject.
_INFO_BOUND_WORDS: frozenset[str] = frozenset(
    {"about", "on", "in", "into", "regarding", "concerning", "of"}
)

#: External-subject STATUS vocabulary ("the state of X", "updates on X").
_EXTERNAL_STATUS_WORDS: frozenset[str] = frozenset(
    {"status", "state", "update", "news", "happening", "progress"}
)

#: Words ignored when deciding whether a request names a resolvable object.
_OBJECT_IGNORE: frozenset[str] = _SUBJECT_STOP | FOLLOW_UP_WORDS | {
    "out", "into", "up", "here", "now", "again", "difference", "detail", "care",
    "like", "want", "wish", "prefer", "kindly", "anything", "something",
    "everything", "nothing",
}

#: Every operation verb class, unioned (used by object resolution).
_OPERATION_VERBS: frozenset[str] = (
    RESEARCH_VERBS
    | INVESTIGATE_VERBS
    | DEVELOP_VERBS
    | EXPLAIN_VERBS
    | COMPARE_VERBS
    | ACT_VERBS
    | LEARN_VERBS
    | CAPABILITY_VERBS
)

#: Verbs that can follow a compound connector as a second instruction
#: ("... and list the sources", "... and tell me more").
_COMPOUND_VERBS: frozenset[str] = _OPERATION_VERBS | {
    "list", "show", "give", "cite", "mention", "cover", "note", "report",
}

#: Substring replacement markers for correction-subject extraction (unchanged
#: from the Improvement-2 contract: the extraction behaviour is pinned).
_SUBSTRING_REPLACEMENT_MARKERS: tuple[str, ...] = (
    "actually",
    "i meant",
    "no, i meant",
    "i didn't mean",
    "i did not mean",
    "not that",
    "forget the previous",
    "forget that",
    "let me rephrase",
    "i mean",
    "to clarify",
    "instead",
    "correction",
    "sorry, i meant",
    "rather",
)

#: Bounded leading fillers stripped from a corrected subject tail.
_TAIL_LEAD_RE_ORDER: tuple[str, ...] = (
    "i was asking about",
    "i am asking about",
    "i'm asking about",
    "i was referring to",
    "i meant",
    "i mean",
    "about",
)
_MAX_SUBJECT_CHARS: int = 200


class SemanticRole(str, Enum):
    """What the turn IS (bounded conversational role)."""

    NEW_OBJECTIVE = "new_objective"
    FOLLOW_UP = "follow_up"
    CORRECTION = "correction"
    CLARIFICATION = "clarification"
    REFERENCE = "reference"
    RECALL = "recall"
    ACKNOWLEDGEMENT = "acknowledgement"
    META_CONVERSATION = "meta_conversation"
    CONTINUATION = "continuation"
    CASUAL = "casual"


class SemanticDomain(str, Enum):
    """Which existing Atlas capability OWNS the turn."""

    CASUAL = "casual"
    CAPABILITIES = "capabilities"
    CAPABILITY_DETAIL = "capability_detail"
    SELF_KNOWLEDGE = "self_knowledge"
    STATUS = "status"
    KNOWLEDGE = "knowledge"
    INVESTIGATION = "investigation"
    WORK = "work"
    DEVELOPMENT = "development"
    GOVERNANCE = "governance"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class SubRequest:
    """One bounded clause of a compound request."""

    operation: str
    domain: str
    subject: str = ""
    governance_sensitive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "domain": self.domain,
            "subject": self.subject,
            "governance_sensitive": self.governance_sensitive,
        }


@dataclass(frozen=True, slots=True)
class SemanticFrame:
    """Bounded, deterministic semantic interpretation of one turn.

    Structured meaning (G1/Step 1): ``domain`` is the owning Atlas
    capability, ``operation`` the requested intention, ``subject``/``concept``
    the bounded entity slot, ``arguments`` the same evidence as explicit
    ``(role, value)`` pairs, ``reference`` any bounded reference cue the turn
    carried, and ``subrequests`` the bounded compound decomposition.
    ``confidence``/``needs_clarification`` carry the uncertainty contract.
    The representation is model-independent: it is produced deterministically
    and carries no authority.
    """

    role: SemanticRole = SemanticRole.NEW_OBJECTIVE
    domain: SemanticDomain = SemanticDomain.UNSUPPORTED
    operation: str = ""
    subject: str = ""
    concept: str = ""
    subrequests: tuple[SubRequest, ...] = ()
    needs_clarification: bool = False
    governance_sensitive: bool = False
    confidence: float = 0.0
    evidence: tuple[str, ...] = field(default=())
    #: Bounded entity/argument evidence as explicit ``(role, value)`` pairs.
    arguments: tuple[tuple[str, str], ...] = ()
    #: Bounded reference cue the turn carried (e.g. "that", "it", "previous").
    reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Deterministic, JSON-safe serialization."""
        return {
            "role": self.role.value,
            "domain": self.domain.value,
            "operation": self.operation,
            "subject": self.subject,
            "concept": self.concept,
            "subrequests": [s.to_dict() for s in self.subrequests],
            "needs_clarification": self.needs_clarification,
            "governance_sensitive": self.governance_sensitive,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "arguments": [list(pair) for pair in self.arguments],
            "reference": self.reference,
        }


# ---------------------------------------------------------------------------
# Bounded subject span + correction extraction
# ---------------------------------------------------------------------------


def is_development_shaped(text: Any) -> bool:
    """Public: True when the frame classifies the turn as DEVELOPMENT.

    Used by the routing layer to keep a capability-GAP request ("Atlas needs a
    new capability for X") away from the capability INVENTORY surface.
    """
    return interpret(text).domain is SemanticDomain.DEVELOPMENT


def is_reference_or_follow_up(text: Any) -> bool:
    """Public: True when the frame classifies the turn as a reference/follow-up."""
    return interpret(text).role in (
        SemanticRole.REFERENCE,
        SemanticRole.FOLLOW_UP,
    )


def subject_span(text: Any) -> str:
    """Return the bounded subject span of ``text`` (deterministic).

    Function/lead words are dropped and the remainder is capped, so the span is
    a tight token expression rather than a sentence. It is never resolved here:
    the caller decides whether it is a reference, a new subject, or nothing.
    """
    if not isinstance(text, str) or not text.strip():
        return ""
    keep: list[str] = []
    for token in tokens(text):
        if token in _SUBJECT_STOP or len(token) < 2 and not token.isdigit():
            continue
        keep.append(token)
        if len(keep) >= MAX_SUBJECT_TOKENS:
            break
    return " ".join(keep)[:_MAX_SUBJECT_CHARS]


def knowledge_subject(text: Any) -> str:
    """Return the bounded KNOWLEDGE subject of ``text`` (operation verbs dropped).

    Used by the conversation layer to feed the EXISTING local-first knowledge
    path with a tight subject expression rather than a whole sentence.
    """
    if not isinstance(text, str) or not text.strip():
        return ""
    keep: list[str] = []
    for token in tokens(text):
        if token in _OBJECT_IGNORE or token in _OPERATION_VERBS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        keep.append(token)
        if len(keep) >= MAX_SUBJECT_TOKENS:
            break
    return " ".join(keep)[:_MAX_SUBJECT_CHARS]


def corrected_subject(text: Any) -> str:
    """Extract the bounded replacement subject after a correction marker.

    Deterministic: the LATEST replacement marker wins, then bounded leading
    fillers/articles are stripped. Returns ``""`` when nothing usable remains
    (the caller keeps its existing fallback).
    """
    if not isinstance(text, str) or not text.strip():
        return ""
    lowered = text.lower()
    best_end: int | None = None
    for marker in _SUBSTRING_REPLACEMENT_MARKERS:
        idx = lowered.find(marker)
        if idx == -1:
            continue
        end = idx + len(marker)
        if best_end is None or end > best_end:
            best_end = end
    if best_end is None:
        return ""
    subject = text[best_end:].lstrip(" \t:,-–—")
    lowered_subject = subject.lower()
    for lead in _TAIL_LEAD_RE_ORDER:
        if lowered_subject.startswith(lead + " "):
            subject = subject[len(lead):].lstrip()
            lowered_subject = subject.lower()
    subject = subject.strip()
    for article in ("the ", "a ", "an "):
        if subject.lower().startswith(article):
            subject = subject[len(article):].strip()
            break
    subject = subject.rstrip(" .!?,;:").strip()
    return subject[:_MAX_SUBJECT_CHARS]


# ---------------------------------------------------------------------------
# Frame rules
# ---------------------------------------------------------------------------


def _is_question(order: tuple[str, ...], raw: str) -> bool:
    """Question-shaped turn: explicit ``?``, a leading question word, or a
    bounded question word anywhere in an utterance-length turn."""
    if raw.rstrip().endswith("?"):
        return True
    if not order:
        return False
    if order[0] in _WH_WORDS:
        return True
    return bool(set(order) & _WH_WORDS) and len(order) <= 12


def _has_self_reference(lemmas: frozenset[str]) -> bool:
    return has_any(lemmas, SELF_WORDS)


def _has_strong_self_reference(lemmas: frozenset[str]) -> bool:
    """Second-person possessive / the literal name: Atlas OWNS the subject."""
    return has_any(lemmas, {"your", "yours", "yourself", "yourselves", "atlas"})


def _is_acknowledgement(order: tuple[str, ...], lemmas: frozenset[str]) -> bool:
    if not order or len(order) > 7:
        return False
    if not (lemmas & _ACK_SIGNALS):
        return False
    return all(token in _ACK_WORDS or token in _ACK_FILLERS for token in order)


def _looks_like_continuation(order: tuple[str, ...], lemmas: frozenset[str]) -> bool:
    if not order or len(order) > 7:
        return False
    if not (lemmas & CONTINUATION_VERBS):
        return False
    # A continuation never introduces a new subject: every token must be a
    # continuation or function word.
    allowed = CONTINUATION_VERBS | CONTINUATION_FILLERS
    return all(token in allowed for token in order)


def _is_recall(order: tuple[str, ...], lemmas: frozenset[str], raw: str) -> bool:
    if "remind" not in lemmas and not _is_question(order, raw):
        return False
    if lemmas & (RESEARCH_VERBS | INVESTIGATE_VERBS | DEVELOP_VERBS):
        return False
    if has_any(lemmas, CAPABILITY_NOUNS | CAPABILITY_VERBS):
        return False
    if has_any(lemmas, SELF_COMPONENT_CONCEPTS | SELF_ARCHITECTURE_CONCEPTS):
        return False
    return has_any(lemmas, RECALL_VERBS | RECALL_NOUNS)


def _capability_frame(
    order: tuple[str, ...], lemmas: frozenset[str], raw: str
) -> SemanticFrame | None:
    if not _is_question(order, raw) and not (lemmas & {"list", "show"}):
        return None
    # A capability INVENTORY question is asked ABOUT Atlas ("what can you do"),
    # so a self reference is required: "what does nope_tool do?" is not one.
    if not _has_self_reference(lemmas):
        return None
    # An extension/development question ("how would you add a capability?") is a
    # self-knowledge or development concern, never an inventory request.
    if lemmas & DEVELOP_VERBS:
        return None
    # "Atlas should learn how to do X" / "needs a capability" is a gap request.
    if lemmas & _GAP_MODALS and lemmas & (LEARN_VERBS | DEVELOP_VERBS | {"support"}):
        return None
    # A capability verb aimed at a concrete work object is a WORK request.
    if lemmas & _WORK_OBJECTS:
        return None
    # Assistance framing: a CAPABILITY_VERB bound to a concrete object
    # ("can you help me with scheduling?", "could you support the loader?") is
    # a request for assistance with that object, never a capability INVENTORY
    # question. A bare "what can you help with" carries no object and keeps its
    # inventory reading (and its dedicated alias).
    if lemmas & _ASSIST_VERBS:
        object_tokens = {
            lemma
            for lemma in lemmas
            if lemma not in _OBJECT_IGNORE
            and lemma not in _OPERATION_VERBS
            and lemma not in CAPABILITY_VERBS
            and lemma not in _ASSIST_VERBS
            and lemma not in _GENERIC_OBJECTS
        }
        if object_tokens and not object_tokens <= REFERENCE_WORDS:
            return None
    # A third-person/external possessive subject belongs to the external subject,
    # never to Atlas's own inventory (C3 finding, preserved).
    if lemmas & {"their", "his", "her"}:
        return None
    # The turn must not be some OTHER operation in disguise ("what do you know
    # about X", "do you remember X"). Function verbs ("do"/"have"/"be"/"get")
    # are not operations for this purpose.
    if lemmas & ((_OPERATION_VERBS - CAPABILITY_VERBS) - {
        "do", "have", "be", "get", "tell", "say"
    }):
        return None
    if lemmas & RECALL_VERBS:
        return None
    noun_hit = bool(lemmas & CAPABILITY_NOUNS)
    verb_hit = bool(lemmas & CAPABILITY_VERBS)
    # The canonical capability question shape: a self reference plus a request
    # modal with "do" as its only verb ("what can you do?").
    modal_shape = bool(
        lemmas & {"can", "could", "would"}
        and lemmas & {"do"}
        and not (lemmas & (KNOWLEDGE_NOUNS | _WORK_OBJECTS))
    )
    if not noun_hit and not verb_hit and not modal_shape:
        return None
    return SemanticFrame(
        role=SemanticRole.NEW_OBJECTIVE,
        domain=SemanticDomain.CAPABILITIES,
        operation="capabilities",
        confidence=0.9,
        evidence=("capability-class",),
    )


def _unresolved_object(lemmas: frozenset[str]) -> bool:
    """True when the turn names no resolvable object (only references/verb).

    Bounded: tokens that are neither the operation verb, a function word, nor a
    follow-up word are the object. An empty object, or one made only of bounded
    reference tokens, is unresolved (the caller asks rather than guessing).
    """
    remaining = {
        lemma
        for lemma in lemmas
        if lemma not in _OBJECT_IGNORE and lemma not in _OPERATION_VERBS
    }
    if not remaining:
        return True
    return remaining <= REFERENCE_WORDS


def _self_knowledge_frame(
    order: tuple[str, ...], lemmas: frozenset[str], raw: str
) -> SemanticFrame | None:
    if not _is_question(order, raw):
        return None
    self_ref = _has_self_reference(lemmas)
    governance_q = bool(
        lemmas & SELF_GOVERNANCE_CONCEPTS
        and lemmas & {"who", "where", "how", "what"}
    )
    # Atlas-only operational concepts (sandbox / approval / authorization) are
    # asked without a second-person reference ("how is code executed safely?").
    atlas_specific_q = bool(
        lemmas
        & (
            SELF_SANDBOX_CONCEPTS
            | SELF_APPROVAL_CONCEPTS
            | SELF_AUTHORIZATION_CONCEPTS
            | SELF_REFERENCE_RES_CONCEPTS
        )
        and lemmas & {"how", "where", "who", "what", "when", "is", "does"}
    )
    # G2 — an ATLAS-CONCEPT mechanism question carries no second-person
    # reference ("how does the knowledge decision work?") yet is still Atlas
    # self-knowledge: the concept noun IS the Atlas concept, and the answer comes
    # from the existing verified component/topic anchor. Bounded to the
    # knowledge-sufficiency family, so no external subject is ever claimed; a
    # LOCATION question of the same family ("which part/component ... decides")
    # keeps its existing architecture route.
    concept_mechanism_q = bool(
        lemmas & SELF_SUFFICIENCY_CONCEPTS
        and lemmas
        & {"knowledge", "sufficiency", "decision", "decide", "external", "information"}
        and lemmas & {"how", "what"}
        and lemmas
        & {"work", "operate", "function", "behave", "happen", "decision", "decide"}
    )
    if not self_ref and not governance_q and not atlas_specific_q and not (
        concept_mechanism_q
    ):
        return None
    # A knowledge question ABOUT a subject is not a self-knowledge question
    # ("what do we know about the investigation system?").
    if lemmas & (RESEARCH_VERBS | LEARN_VERBS | RECALL_VERBS) and "about" in lemmas:
        return None
    if governance_q and not lemmas & {
        "change", "proposal", "sandbox", "capability", "development"
    }:
        return None
    # A topicless question ("what do you verify about?") must stay fail-closed.
    if "about" in lemmas and _unresolved_object(lemmas):
        return None
    # A capability inventory question is not a self-knowledge question.
    if lemmas & CAPABILITY_NOUNS and not lemmas & DEVELOP_VERBS:
        return None
    # G1 — fine-grained concepts, most-specific first, each mapping onto an
    # EXISTING self-knowledge topic so the grounded response is preserved.
    if lemmas & SELF_SANDBOX_CONCEPTS:
        return _self_frame("sandbox_execution", 0.9, "sandbox-concept")
    if lemmas & SELF_APPROVAL_CONCEPTS:
        return _self_frame("owner_approval", 0.9, "approval-concept")
    if lemmas & SELF_AUTHORIZATION_CONCEPTS:
        return _self_frame("authorization_boundary", 0.9, "authorization-concept")
    if lemmas & SELF_EVIDENCE_CONCEPTS and lemmas & SELF_FAILURE_TRIGGERS:
        return _self_frame("evidence_failure", 0.88, "evidence-concept")
    if "development" in lemmas:
        return _self_frame("development_process", 0.88, "development-concept")
    if lemmas & SELF_EXTENSION_CONCEPTS & {"capability", "capabilities", "feature",
                                            "extension"} and lemmas & (
        DEVELOP_VERBS | {"would", "could", "should"}
    ):
        return _self_frame("extension_points", 0.86, "extension-concept")
    if has_any(lemmas, SELF_COMPONENT_CONCEPTS):
        return _self_frame("component", 0.88, "component-concept")
    if lemmas & SELF_RESEARCH_CONCEPTS:
        return _self_frame("research_process", 0.86, "research-concept")
    if lemmas & SELF_REFERENCE_RES_CONCEPTS:
        return _self_frame("reference_resolution", 0.86, "reference-concept")
    if lemmas & SELF_FLOW_CONCEPTS and _has_strong_self_reference(lemmas):
        return _self_frame("request_flow", 0.86, "flow-concept")
    if lemmas & SELF_SUFFICIENCY_CONCEPTS and lemmas & {
        "knowledge", "information", "sufficient", "sufficiency", "external"
    }:
        return _self_frame("knowledge_sufficiency", 0.84, "sufficiency-concept")
    if has_any(lemmas, SELF_ARCHITECTURE_CONCEPTS) and _has_strong_self_reference(
        lemmas
    ):
        return _self_frame("architecture", 0.88, "architecture-concept")
    if lemmas & {"work", "operation", "behave", "behaviour", "behavior"}:
        return SemanticFrame(
            role=SemanticRole.META_CONVERSATION,
            domain=SemanticDomain.SELF_KNOWLEDGE,
            operation="self_knowledge",
            concept="operation",
            confidence=0.8,
            evidence=("self-reference", "operation-concept"),
        )
    if self_ref and (
        lemmas & _SELF_FAILURE_CONCEPTS
        or (
            lemmas & {"happen", "need", "lack"}
            and lemmas & {"information", "knowledge", "know", "evidence"}
        )
    ):
        return _self_frame("limitations", 0.8, "failure-concept")
    # A development/extension REQUEST ("how would we extend Atlas to support X")
    # belongs to the DEVELOPMENT frame, not to self-knowledge.
    if lemmas & DEVELOP_VERBS:
        return None
    return None


def _self_frame(concept: str, confidence: float, label: str) -> SemanticFrame:
    return SemanticFrame(
        role=SemanticRole.NEW_OBJECTIVE,
        domain=SemanticDomain.SELF_KNOWLEDGE,
        operation="self_knowledge",
        concept=concept,
        confidence=confidence,
        evidence=("self-reference", label),
    )


def _capability_gap_frame(lemmas: frozenset[str]) -> SemanticFrame | None:
    """A request that Atlas acquire a new capability -> DEVELOPMENT (design)."""
    if not (_has_self_reference(lemmas) or lemmas & {"i", "we"}):
        return None
    if not (lemmas & _GAP_MODALS):
        return None
    if not (
        lemmas
        & (CAPABILITY_NOUNS | DEVELOP_VERBS | LEARN_VERBS | {"support", "capability"})
    ):
        return None
    # G2 — "I want to know / learn about X" is an INFORMATION request, not a
    # capability gap: the existing knowledge surface owns it (the preposition
    # binds the interest verb to a subject, so a bare "I want a capability"
    # still reaches this frame).
    if "about" in lemmas and lemmas & (
        KNOWLEDGE_NOUNS | {"know", "learn", "information", "info"}
    ):
        return None
    return SemanticFrame(
        role=SemanticRole.NEW_OBJECTIVE,
        domain=SemanticDomain.DEVELOPMENT,
        operation="develop",
        subject=subject_span(" ".join(sorted(lemmas))),
        confidence=0.82,
        evidence=("capability-gap",),
    )


def _greeting_frame(lemmas: frozenset[str]) -> SemanticFrame | None:
    if not (lemmas & GREETING_WORDS):
        return None
    if lemmas & (RESEARCH_VERBS | INVESTIGATE_VERBS | DEVELOP_VERBS | ACT_VERBS):
        return None
    return SemanticFrame(
        role=SemanticRole.CASUAL,
        domain=SemanticDomain.CASUAL,
        operation="greet",
        confidence=0.9,
        evidence=("greeting-class",),
    )


def _status_frame(
    order: tuple[str, ...], lemmas: frozenset[str], raw: str
) -> SemanticFrame | None:
    health = lemmas & {"status", "health", "state", "ok", "okay", "online", "alive"}
    how_are_you = bool(
        len(order) <= 6
        and order
        and order[0] == "how"
        and (_has_self_reference(lemmas) or lemmas & {"you", "things", "it", "everything"})
    )
    if not health and not how_are_you:
        return None
    # An ATLAS status question never carries an external subject; a "status of X"
    # / "how is X doing" turn is handled by the external-status rule instead.
    if not _has_self_reference(lemmas) and not lemmas <= (health | _SUBJECT_STOP):
        return None
    return SemanticFrame(
        role=SemanticRole.NEW_OBJECTIVE,
        domain=SemanticDomain.STATUS,
        operation="status",
        confidence=0.9,
        evidence=("status-class",),
    )


def _operation_of(lemmas: frozenset[str]) -> tuple[str, SemanticDomain, int]:
    """Return ``(operation, domain, priority)`` for the leading operation class."""
    if has_any(lemmas, INVESTIGATE_VERBS):
        return "investigate", SemanticDomain.INVESTIGATION, 5
    if has_any(lemmas, DEVELOP_VERBS):
        return "develop", SemanticDomain.DEVELOPMENT, 4
    if has_any(lemmas, COMPARE_VERBS):
        return "compare", SemanticDomain.KNOWLEDGE, 3
    if has_any(lemmas, RESEARCH_VERBS | LEARN_VERBS):
        return "research", SemanticDomain.KNOWLEDGE, 2
    if has_any(lemmas, EXPLAIN_VERBS):
        return "explain", SemanticDomain.KNOWLEDGE, 1
    # G1 — a SUBJECT-AWARE information shape: a knowledge/interest word bound to
    # a prepositional subject ("get me information on X", "I'd like information
    # about X", "I am interested in X", "the details on X"). The preposition is
    # required, so a bare noun cannot claim the turn.
    if lemmas & (KNOWLEDGE_NOUNS | INTEREST_WORDS) and (
        lemmas & _INFO_BOUND_WORDS or lemmas & RESEARCH_VERBS
    ):
        return "research", SemanticDomain.KNOWLEDGE, 2
    if has_any(lemmas, ACT_VERBS):
        return "act", SemanticDomain.WORK, 1
    return "", SemanticDomain.UNSUPPORTED, 0


def _governance_sensitive(
    lemmas: frozenset[str], raw: str, order: tuple[str, ...]
) -> bool:
    """True when the turn DIRECTS a governance-sensitive act.

    A QUESTION about governance ("who approves development changes?") is not a
    directive and is never flagged. Flagging grants nothing: it only marks the
    frame so no downstream layer may treat the language as authority.
    """
    lowered = raw.lower()
    if (
        "without asking" in lowered
        or "without approval" in lowered
        or "without permission" in lowered
    ):
        return True
    if not (lemmas & GOVERNANCE_VERBS):
        return False
    if _is_question(order, raw):
        return False
    return bool(
        _has_self_reference(lemmas)
        or lemmas
        & {
            "approval", "permission", "authority", "change", "proposal", "step",
            "owner", "yourself", "it", "this", "promotion",
        }
        or len(order) <= 5
    )


def decompose(text: Any) -> tuple[SubRequest, ...]:
    """Return bounded subrequests of a compound turn (deterministic).

    Clauses are split on a bounded connector set; each clause is interpreted
    independently and only its bounded (operation, domain, subject) is kept.
    Representation only — it never plans, authorizes, or executes anything, and
    a governance-sensitive clause is FLAGGED so the caller cannot silently run it.
    """
    if not isinstance(text, str) or not text.strip():
        return ()
    lowered = text.lower()
    boundaries: list[int] = []
    for connector in COMPOUND_CONNECTORS:
        phrase = " " + " ".join(connector) + " "
        start = 0
        while True:
            idx = lowered.find(phrase, start)
            if idx == -1:
                break
            boundaries.append(idx + 1)
            start = idx + len(phrase)
    # G1 — "and"/"then" followed by an OPERATION verb is a subrequest boundary
    # ("Research X and summarize what you find"): a reusable rule over the
    # operation vocabulary rather than a phrase list.
    for marker in (" and ", " then "):
        start = 0
        while True:
            idx = lowered.find(marker, start)
            if idx == -1:
                break
            start = idx + len(marker)
            rest = lowered[start:].split(" ", 1)[0].strip(" ,;.")
            if normalize_token(rest) in _COMPOUND_VERBS:
                boundaries.append(idx + 1)
    if not boundaries:
        return ()
    cuts = sorted(set(boundaries))[: MAX_SUBREQUESTS - 1]
    parts: list[str] = []
    previous = 0
    for cut in cuts:
        parts.append(text[previous:cut].strip(" ,;."))
        previous = cut
    parts.append(text[previous:].strip(" ,;."))
    clauses = [part for part in parts if part]
    if len(clauses) < 2:
        return ()
    subs: list[SubRequest] = []
    for part in clauses[:MAX_SUBREQUESTS]:
        lemmas = frozenset(tokens(part))
        operation, domain, _priority = _operation_of(lemmas)
        part_tokens = tokens(part)
        governance = _governance_sensitive(lemmas, part, part_tokens)
        if not operation:
            # A clause led by a connector verb ("... and list the sources") or a
            # governance verb ("... and approve your own proposal") is still a
            # bounded subrequest; it is represented (and flagged) rather than
            # dropped, so the compound does not escape to a generic route.
            head = part_tokens[0] if part_tokens else ""
            if head in _COMPOUND_VERBS:
                operation, domain, governance = "report", SemanticDomain.KNOWLEDGE, governance
            elif governance:
                operation, domain = "governance", SemanticDomain.GOVERNANCE
            else:
                continue
        subs.append(
            SubRequest(
                operation=operation,
                domain=domain.value,
                subject=subject_span(part),
                governance_sensitive=governance,
            )
        )
    return tuple(subs[:MAX_SUBREQUESTS])


def interpret(
    text: Any,
    *,
    has_prior_objective: bool = False,
    has_knowledge_context: bool = False,
) -> SemanticFrame:
    """Interpret one turn into a bounded :class:`SemanticFrame`. Deterministic.

    ``has_prior_objective`` / ``has_knowledge_context`` let CONTEXT influence the
    interpretation: a bare bounded reference is a FOLLOW_UP when there is prior
    context and an AMBIGUOUS clarification request when there is none.

    The deterministic :func:`_interpret_core` produces the (role, domain,
    operation) reading; this wrapper additionally attaches the bounded
    structured-meaning evidence (``arguments`` / ``reference``) so callers get a
    complete, model-independent representation without a second pass.
    """
    return _enrich(_interpret_core(
        text,
        has_prior_objective=has_prior_objective,
        has_knowledge_context=has_knowledge_context,
    ), text)


def _enrich(frame: SemanticFrame, text: Any) -> SemanticFrame:
    """Attach the bounded ``arguments`` / ``reference`` evidence to ``frame``.

    Purely additive: it never changes ``role``/``domain``/``operation``,
    ``needs_clarification``, ``confidence``, or any routing decision, and it
    grants no authority. ``reference`` is the strongest bounded reference cue
    the turn actually carried (never a guess).
    """
    arguments: list[tuple[str, str]] = []
    if frame.subject:
        arguments.append(("subject", frame.subject))
    if frame.concept:
        arguments.append(("concept", frame.concept))
    cues = sorted(frozenset(tokens(text)) & REFERENCE_WORDS)
    return replace(
        frame,
        arguments=tuple(arguments),
        reference=cues[0] if cues else "",
    )


def _interpret_core(
    text: Any,
    *,
    has_prior_objective: bool = False,
    has_knowledge_context: bool = False,
) -> SemanticFrame:
    """The deterministic frame rules (see :func:`interpret`)."""
    if not isinstance(text, str) or not text.strip():
        return SemanticFrame(evidence=("empty",))
    order = tokens(text)
    lemmas = frozenset(order)
    raw = text.strip()

    # 1. Governance-sensitive DIRECTIVE: flagged, never authorized.
    if _governance_sensitive(lemmas, raw, order):
        operation, domain, _ = _operation_of(lemmas)
        return SemanticFrame(
            role=SemanticRole.NEW_OBJECTIVE,
            domain=SemanticDomain.GOVERNANCE if not operation else domain,
            operation=operation or "governance",
            subject=subject_span(text),
            governance_sensitive=True,
            confidence=0.95,
            evidence=("governance-sensitive",),
        )

    # 2. Correction (REPLACES the reading) / clarification (REFINES it). Both
    #    need a prior objective; only a correction installs a new subject.
    lowered_raw = raw.lower()
    if has_prior_objective and any(
        phrase in lowered_raw for phrase in _REPLACEMENT_PHRASES
    ):
        corrected = corrected_subject(text)
        operation, domain, _ = _operation_of(lemmas)
        return SemanticFrame(
            role=SemanticRole.CORRECTION,
            domain=(
                domain
                if domain is not SemanticDomain.UNSUPPORTED
                else SemanticDomain.KNOWLEDGE
            ),
            operation=operation or "correct",
            subject=corrected or subject_span(text),
            confidence=0.9,
            evidence=("correction-marker",),
        )
    if has_prior_objective and any(
        phrase in lowered_raw for phrase in _REFINEMENT_PHRASES
    ):
        return SemanticFrame(
            role=SemanticRole.CLARIFICATION,
            domain=SemanticDomain.KNOWLEDGE,
            operation="clarify",
            subject=corrected_subject(text) or subject_span(text),
            confidence=0.85,
            evidence=("clarification-marker",),
        )

    # 3. Acknowledgement (whole-turn class membership).
    if _is_acknowledgement(order, lemmas):
        return SemanticFrame(
            role=SemanticRole.ACKNOWLEDGEMENT,
            domain=SemanticDomain.CASUAL,
            operation="acknowledge",
            confidence=0.92,
            evidence=("acknowledgement-class",),
        )

    # 4. Recall of the recent conversation itself.
    if _is_recall(order, lemmas, raw):
        return SemanticFrame(
            role=SemanticRole.RECALL,
            domain=SemanticDomain.CASUAL,
            operation="recall",
            subject=subject_span(text),
            confidence=0.9,
            evidence=("recall-class",),
        )

    # 5. Continuation.
    if _looks_like_continuation(order, lemmas):
        return SemanticFrame(
            role=SemanticRole.CONTINUATION,
            domain=SemanticDomain.CASUAL,
            operation="continue",
            confidence=0.9,
            evidence=("continuation-class",),
        )

    # 6. Greeting (a casual opening, not an objective).
    frame = _greeting_frame(lemmas)
    if frame is not None:
        return frame

    # 7. Self-knowledge (self/governance question + a concept class).
    frame = _self_knowledge_frame(order, lemmas, raw)
    if frame is not None:
        return frame

    # 8. Capability inventory.
    frame = _capability_frame(order, lemmas, raw)
    if frame is not None:
        return frame

    # 9. Capability gap ("Atlas needs a capability that ...") -> development.
    gap = _capability_gap_frame(lemmas)
    if gap is not None:
        return gap

    # 10. Status (Atlas's own).
    frame = _status_frame(order, lemmas, raw)
    if frame is not None:
        return frame

    # 10b. An EXTERNAL subject's status is a knowledge request, not Atlas's own.
    external_status = bool(not _has_self_reference(lemmas)) and bool(
        lemmas & _EXTERNAL_STATUS_WORDS
    )
    if external_status:
        return SemanticFrame(
            role=SemanticRole.NEW_OBJECTIVE,
            domain=SemanticDomain.KNOWLEDGE,
            operation="status",
            subject=subject_span(text),
            confidence=0.85,
            evidence=("external-status-class",),
        )
    # A non-self "how is X doing" is external status too (bounded to short turns).
    if (
        not _has_self_reference(lemmas)
        and "how" in lemmas
        and "doing" in raw.lower()
        and len(order) <= 8
    ):
        return SemanticFrame(
            role=SemanticRole.NEW_OBJECTIVE,
            domain=SemanticDomain.KNOWLEDGE,
            operation="status",
            subject=subject_span(text),
            confidence=0.8,
            evidence=("external-status-shape",),
        )

    # 10. Bounded reference / follow-up forms that introduce no operation.
    operation, domain, _priority = _operation_of(lemmas)
    subject = subject_span(text)
    reference_like = bool(lemmas & REFERENCE_WORDS)
    follow_up_like = bool(lemmas & (FOLLOW_UP_VERBS | FOLLOW_UP_WORDS))
    if reference_like and (follow_up_like or operation in ("", "explain")):
        return _reference_or_follow_up(
            subject, has_prior_objective, has_knowledge_context
        )

    # 11. Operation classes (investigation / development / knowledge / work).
    if domain is SemanticDomain.INVESTIGATION:
        return SemanticFrame(
            role=SemanticRole.NEW_OBJECTIVE,
            domain=domain,
            operation=operation,
            subject=subject,
            confidence=0.88,
            evidence=("investigate-class",),
        )
    if domain is SemanticDomain.DEVELOPMENT:
        if has_any(
            lemmas,
            SELF_WORDS
            | {"need", "should", "want", "require", "capability", "feature"},
        ) or has_any(lemmas, DEVELOP_VERBS):
            return SemanticFrame(
                role=SemanticRole.NEW_OBJECTIVE,
                domain=domain,
                operation=operation,
                subject=subject,
                confidence=0.85,
                evidence=("develop-class",),
            )
    if domain is SemanticDomain.KNOWLEDGE:
        if "about" in lemmas or operation in ("research", "compare"):
            frame = SemanticFrame(
                role=SemanticRole.NEW_OBJECTIVE,
                domain=domain,
                operation=operation,
                subject=subject,
                confidence=0.85,
                evidence=("knowledge-class",),
            )
            if not has_prior_objective and _unresolved_object(lemmas):
                return _with_clarification(frame)
            return frame
    if domain is SemanticDomain.WORK and (lemmas & _WORK_OBJECTS):
        frame = SemanticFrame(
            role=SemanticRole.NEW_OBJECTIVE,
            domain=domain,
            operation=operation,
            subject=subject,
            confidence=0.8,
            evidence=("work-class",),
        )
        if not has_prior_objective and _unresolved_object(lemmas):
            return _with_clarification(frame)
        return frame

    # 12. Loose follow-up words with no operation ("Find out more.").
    if follow_up_like and (has_prior_objective or has_knowledge_context):
        return _reference_or_follow_up(
            subject, has_prior_objective, has_knowledge_context
        )
    if reference_like or follow_up_like:
        return _reference_or_follow_up(
            subject, has_prior_objective, has_knowledge_context
        )

    return SemanticFrame(
        role=SemanticRole.NEW_OBJECTIVE,
        domain=SemanticDomain.UNSUPPORTED,
        subject=subject,
        evidence=("no-rule",),
    )


def _with_clarification(frame: SemanticFrame) -> SemanticFrame:
    """Mark a frame that names no resolvable object as needing clarification."""
    return SemanticFrame(
        role=SemanticRole.REFERENCE,
        domain=frame.domain,
        operation=frame.operation,
        subject=frame.subject,
        concept=frame.concept,
        needs_clarification=True,
        confidence=frame.confidence,
        evidence=frame.evidence + ("unresolved-object",),
    )


def _reference_or_follow_up(
    subject: str, has_prior_objective: bool, has_knowledge_context: bool
) -> SemanticFrame:
    if has_prior_objective or has_knowledge_context:
        return SemanticFrame(
            role=SemanticRole.FOLLOW_UP,
            domain=(
                SemanticDomain.KNOWLEDGE
                if has_knowledge_context
                else SemanticDomain.CASUAL
            ),
            operation="follow_up",
            subject=subject,
            confidence=0.8,
            evidence=("follow-up",),
        )
    return SemanticFrame(
        role=SemanticRole.REFERENCE,
        domain=SemanticDomain.UNSUPPORTED,
        operation="reference",
        subject=subject,
        needs_clarification=True,
        confidence=0.5,
        evidence=("unresolved-reference",),
    )
