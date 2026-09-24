"""Atlas Conversation — Deterministic Task Intake (B2).

Converts a casual natural-language instruction into a bounded, structured
:class:`TaskSpec` WITHOUT executing anything and WITHOUT a mandatory model
call. This is the intake half of conversational understanding: the TaskSpec
is data that flows into the existing cognitive pipeline through its
``goal`` / ``metadata`` parameters.

Design contract:
  * Deterministic-first, model-independent, no mandatory LLM.
  * Optional model assistance exists only as an injected
    :class:`IntentParser` protocol; it is OFF by default, and any model
    output is untrusted (``verified=False``) and sanitized/bounded.
  * The module is pure: no ``atlas.ai``, no kernel, no storage, no EventBus,
    no capability execution, no governance surface.
  * Raw user input is data, never an instruction to the framework.

No infrastructure dependencies.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from atlas.conversation.normalization import (
    canonicalize_surface,
    collapse_whitespace,
)
from atlas.conversation.repository_impact import (
    looks_like_repository_impact_request,
)
from atlas.conversation.utterance_meaning import (
    MAX_TARGET_CHARS,
    UTTERANCE_MEANING_KEY,
    Illocution,
    Operation,
    UtteranceMeaning,
)

# ---------------------------------------------------------------------------
# Bounds (all derived fields are hard-capped so oversized input cannot
# produce oversized state).
# ---------------------------------------------------------------------------

_MAX_INTENT_CHARS: int = 400
_MAX_GOAL_CHARS: int = 500
_MAX_ITEM_CHARS: int = 200
_MAX_ITEM_COUNT: int = 8
_MAX_CONTEXT_VALUES: int = 24

#: Control characters are stripped from every derived text field.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

#: Alphanumeric token pattern (mirrors the deterministic semantic-recall
#: tokenization approach: lowercase alnum tokens, length >= 2).
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN: int = 2

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskType(Enum):
    """Deterministic classification of what a human instruction asks for."""

    CONVERSATION = "conversation"
    QUESTION = "question"
    INFORMATION_REQUEST = "information_request"
    ACTION_REQUEST = "action_request"
    DEVELOPMENT_REQUEST = "development_request"
    INVESTIGATION_REQUEST = "investigation_request"
    APPROVAL = "approval"
    EXECUTION_REQUEST = "execution_request"
    PLANNING_REQUEST = "planning_request"
    REJECTION_REQUEST = "rejection_request"
    RECOVERY_REQUEST = "recovery_request"
    VERIFICATION_REQUEST = "verification_request"
    REPORT_REQUEST = "report_request"
    REPOSITORY_IMPACT_REQUEST = "repository_impact_request"
    AUTONOMY_REQUEST = "autonomy_request"
    L2_AUTONOMY_REQUEST = "l2_autonomy_request"
    L3_AUTONOMY_REQUEST = "l3_autonomy_request"
    L4_AUTONOMY_REQUEST = "l4_autonomy_request"
    L5_AUTONOMY_REQUEST = "l5_autonomy_request"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Cue vocabularies (deterministic, order-independent).
# ---------------------------------------------------------------------------

_QUESTION_CUES: frozenset[str] = frozenset(
    {"how", "what", "why", "when", "where", "who", "which", "?"}
)

_RESEARCH_CUES: frozenset[str] = frozenset(
    {"find", "look up", "lookup", "research", "search", "latest", "investigate"}
)

#: Word-boundary greeting regex: short tokens ("hi", "hey") must not match
#: inside "this" / "they", while multi-word greetings match as phrases. The
#: "how are you" alternative carries a trailing word boundary so it does not
#: match the possessive prefix "how are your ..." (e.g. "How are your modules
#: connected?"), which is a question, not a greeting. This mirrors the
#: builtin-response greeting vocabulary exactly.
_GREETING_RE = re.compile(
    r"\b(?:hello|hi|hey)\b|how are you\b|good morning|good afternoon|good evening|nice to meet you"
)

#: Explicit accepted development cue FORMS. Every entry is matched as a WHOLE
#: word (or a fixed phrase), never as a substring, so the development family is
#: a bounded, auditable list of accepted forms rather than a containment test.
#: A word that merely contains a cue ("address" for "add", "prefix" for "fix")
#: and a nominal/inflected form that merely contains one ("implementation",
#: "improvement", "fixing", "modifying", "refactoring", "building") are not
#: development signals. "rebuild" is an explicit accepted form rather than
#: "build" found inside it.
_DEVELOPMENT_CUE_FORMS: frozenset[str] = frozenset(
    {
        "add",
        "build",
        "rebuild",
        "create a capability",
        "create a module",
        "extend",
        "fix",
        "implement",
        "improve",
        "modify",
        "refactor",
    }
)

#: Natural-language development verbs. Matched as WHOLE words only, so the
#: standalone verb "develop" is recognized without capturing the unrelated
#: "development"/"developer"/"developing" (which merely contain "develop" as a
#: substring and are not, on their own, development requests).
_DEVELOPMENT_VERB_CUES: frozenset[str] = frozenset({"develop"})

_SELF_TARGETS: frozenset[str] = frozenset(
    {"atlas", "yourself", "your self", "a module", "a capability", "the framework"}
)

_INVESTIGATION_CUES: frozenset[str] = frozenset(
    {
        "investigate",
        "investigation",
        "diagnose",
        "diagnosis",
        "inspect",
        "examine",
        "analyze",
        "analysis",
        "trace",
        "debug",
    }
)

#: Imperative investigation cues that can lead a compound request. Noun
#: forms ("investigation", "diagnosis", "analysis") are excluded: they
#: refer to a prior investigation artifact ("convert this investigation")
#: rather than requesting the investigation stage.
_INVESTIGATION_LEAD_CUES: frozenset[str] = frozenset(
    {
        "investigate",
        "diagnose",
        "inspect",
        "examine",
        "analyze",
        "trace",
        "debug",
    }
)

#: Explicit conversational-recall phrasing. A request that asks Atlas to
#: recall/remember an existing result is not a request for a NEW
#: investigation, even when its target mentions an "investigation",
#: "analysis", or "diagnosis".
_RECALL_PHRASE_RE = re.compile(
    r"\b(?:do you\s+)?(?:remember|recall)\b"
    r"|\bremind me\b"
    r"|\bwhat (?:did|have) we\b"
)

#: Explicit planning phrases that indicate the user wants to convert an
#: investigation proposal into a development proposal.
#: NOTE: Phrases containing "approval" are excluded because they conflict
#: with APPROVAL classification (checked earlier in the ordering).
_PLANNING_CUES: frozenset[str] = frozenset(
    {
        "plan this",
        "plan this improvement",
        "prepare a proposal",
        "prepare a development proposal",
        "convert this proposal",
        "convert this investigation",
        "prepare a development plan",
        "create a development proposal",
        "make this a development proposal",
        "plan the improvement",
    }
)

#: Phrases that negate the following cue, preventing misclassification.
_NEGATION_PREFIXES: tuple[str, ...] = (
    "don't",
    "dont",
    "do not",
    "never",
    "no",
)

#: Explicit approval phrases that indicate the user is approving a proposal.
_APPROVAL_CUES: frozenset[str] = frozenset(
    {
        "approve",
        "approved",
        "approval",
        "accept",
        "accepted",
        "authorize",
        "authorized",
    }
)

#: Ambiguous responses that must NOT be treated as approval.
_AMBIGUOUS_RESPONSES: frozenset[str] = frozenset(
    {
        "ok",
        "okay",
        "sure",
        "fine",
        "sounds good",
        "looks good",
        "looks fine",
        "makes sense",
        "go ahead",
        "do it",
        "proceed",
    }
)

#: Explicit rejection phrases that indicate the user is rejecting a proposal.
#: Symmetric with _APPROVAL_CUES. Ambiguous responses must NOT be treated
#: as rejection. NOTE: "disapprove" variants are excluded because they
#: contain "approve" as a substring and APPROVAL is checked first.
_REJECTION_CUES: frozenset[str] = frozenset(
    {
        "reject",
        "rejected",
        "rejection",
        "decline",
        "declined",
        "deny",
        "denied",
    }
)

#: Explicit recovery phrases that indicate the user wants to recover from a
#: previous development execution failure. Checked after execution so that
#: "execute" recovery language does not collide with execution requests.
_RECOVERY_CUES: frozenset[str] = frozenset(
    {
        "recover",
        "recovery",
        "recover from the failure",
        "recover from that failure",
        "try again",
        "retry the development",
        "attempt recovery",
    }
)

#: Noun-form ("mention") variants of the lifecycle cues above. A bare mention
#: of a subsystem must not reclassify an explicitly requested investigation
#: ("Investigate the approval flow." / "Investigate the recovery flow."),
#: whereas an explicit instruction form ("approve it", "reject the proposal",
#: "Examine the proposal and approve it.") keeps its existing classification.
_APPROVAL_MENTION_CUES: frozenset[str] = frozenset({"approval"})
_REJECTION_MENTION_CUES: frozenset[str] = frozenset({"rejection"})
_RECOVERY_MENTION_CUES: frozenset[str] = frozenset({"recovery"})

#: Explicit verification phrases that indicate the user wants to verify an
#: already-completed development result. Checked after recovery so that
#: "verify" recovery language does not collide with verification requests.
_VERIFICATION_CUES: frozenset[str] = frozenset(
    {
        "verify the development",
        "verify the result",
        "check the development result",
        "check whether the development succeeded",
        "verify the completed development",
        "verify development result",
        "confirm the development succeeded",
        "check the result",
    }
)

#: Explicit report phrases that indicate the user wants a final lifecycle
#: report. Checked after verification so that "verify" report language does
#: not collide with verification requests.
_REPORT_CUES: frozenset[str] = frozenset(
    {
        "report on the development",
        "give me the development report",
        "give me the final report",
        "show the final development report",
        "summarize the development lifecycle",
        "what happened with the development",
        "final development report",
        "development lifecycle report",
    }
)

#: Explicit L1 autonomy phrases that indicate the user wants Atlas to proceed
#: autonomously with an already-approved development plan. Checked after
#: report so that "report" autonomy language does not collide.
_AUTONOMY_CUES: frozenset[str] = frozenset(
    {
        "proceed autonomously",
        "continue autonomously",
        "execute autonomously",
        "run the approved plan",
        "continue with the development",
        "proceed with the approved",
        "continue the development",
        "run autonomously",
    }
)

#: Explicit L2 autonomy phrases that indicate the user wants Atlas to chain
#: multiple approved workflows or make bounded plan adjustments.
_L2_AUTONOMY_CUES: frozenset[str] = frozenset(
    {
        "chain the workflows",
        "chain approved workflows",
        "continue to next workflow",
        "proceed to next workflow",
        "adjust the plan",
        "optimize the plan",
        "reorder the steps",
        "skip redundant steps",
    }
)

#: Explicit L3 autonomy phrases that indicate the user wants Atlas to
#: execute recovery autonomously, generate sub-plans, or handle HIGH risk.
_L3_AUTONOMY_CUES: frozenset[str] = frozenset(
    {
        "execute recovery",
        "autonomous recovery",
        "recover autonomously",
        "generate sub plan",
        "create sub plan",
        "handle high risk",
        "modify configuration",
        "adjust configuration",
    }
)

#: Explicit L4 autonomy phrases that indicate the user wants Atlas to
#: acquire new capabilities, modify memory/knowledge, or handle CRITICAL risk.
_L4_AUTONOMY_CUES: frozenset[str] = frozenset(
    {
        "acquire capability",
        "acquire new capability",
        "modify memory",
        "modify knowledge",
        "handle critical risk",
        "critical risk operation",
        "information level operation",
        "capability acquisition",
    }
)

#: Explicit L5 autonomy phrases that indicate the user wants Atlas to
#: coordinate across multiple objectives, prioritize work, or manage dependencies.
_L5_AUTONOMY_CUES: frozenset[str] = frozenset(
    {
        "coordinate objectives",
        "coordinate across objectives",
        "prioritize objectives",
        "schedule objectives",
        "manage dependencies",
        "cross objective coordination",
        "multi objective orchestration",
        "objective prioritization",
    }
)

#: Explicit execution request phrases.
#: These cues indicate the user wants to execute an already-approved proposal.
#: NOTE: Bare "implement" or "apply" without "approved" context is ambiguous
#: and may indicate development intent (Level 2). Only unambiguous execution
#: language or "implement/apply the approved" triggers Level 3.
_EXECUTION_CUES: frozenset[str] = frozenset(
    {
        "execute",
        "execute the approved",
        "run the approved",
        "perform the approved",
        "implement the approved",
        "apply the approved",
        "begin implementation",
        "start implementation",
        "proceed with implementation",
        "carry out the approved",
    }
)

#: Explicit accepted action cue FORMS. Every entry is matched as a WHOLE word,
#: never as a substring, so a word that merely contains a cue ("runtime" for
#: "run", "writer" for "write", "compiler" for "compile", "computer" for
#: "compute", "makefile" for "make", "unclean" for "clean") and an inflected or
#: nominal form that merely contains one ("generated", "produced", "summarized",
#: "compiled", "computed", "deployed", "cleaned", "building") are not action
#: signals. Nominalizations ("summary", "generation", "analysis", ...) are
#: deliberately NOT added here.
_ACTION_CUE_FORMS: frozenset[str] = frozenset(
    {
        "create",
        "write",
        "run",
        "build",
        "organize",
        "make",
        "generate",
        "produce",
        "summarize",
        "analyze",
        "compute",
        "calculate",
        "compile",
        "deploy",
        "clean",
    }
)

#: Narrow, explicit compatibility forms for the already-observed compound
#: action wording. "long-running tasks" is the hyphenated compound phrase whose
#: internal "run" was previously matched by substring; the observed singular and
#: plural forms are listed explicitly here so the load-bearing phrasings keep
#: their existing ACTION classification WITHOUT restoring substring matching for
#: ordinary words ("runtime", "rerun", "runway", "running") and WITHOUT turning a
#: bare statement such as "The project is long-running." into an action. This is
#: a bounded phrase list, not a rule about hyphenated words.
_ACTION_COMPOUND_FORMS: frozenset[str] = frozenset(
    {"long-running task", "long-running tasks"}
)

#: NLU-1 — bounded planning/assistance artifacts. A request that asks Atlas to
#: produce one of these artifacts ("help me create a systematic plan ...",
#: "create a review checklist ...") is an ANSWERABLE request for planning
#: assistance, not a request to execute a tool/capability. Such a request must
#: not enter the development-need (capability-gap) path merely because Atlas
#: has no registered tool named after its subject. Whole-word matched; the
#: explicit self-development family above always keeps precedence, so
#: "create a module/capability" stays a DEVELOPMENT_REQUEST.
_PLANNING_ARTIFACT_CUES: frozenset[str] = frozenset(
    {
        "plan",
        "plans",
        "checklist",
        "check list",
        "roadmap",
        "road map",
        "outline",
        "process",
    }
)

# ---------------------------------------------------------------------------
# L3 — minimal structured utterance meaning.
#
# Illocution (question / request / statement) and the LEADING requested
# operation are derived from bounded surface evidence plus the already
# validated cue families. Cue presence is EVIDENCE, never the verdict: the
# operation is whichever operation family is attested EARLIEST in the
# utterance, so a later development cue can no longer outrank the sentence's
# leading operation.
# ---------------------------------------------------------------------------

#: Bounded "explain" evidence for the L3 operation domain. No existing cue
#: family carries an explain operation, and these two verbs are the bounded,
#: already-used surface of the built-in capability-detail path. They are NOT
#: added to any classification cue family, so classification is unchanged.
_EXPLAIN_CUE_FORMS: frozenset[str] = frozenset({"explain", "describe"})

#: NLU-1 — bounded "compare" evidence for the L3 operation domain. A leading
#: comparison ("Compare the camera systems ... and tell me what matters ...")
#: is an ordinary information/comparison REQUEST, not a bare statement. Like
#: the explain forms, these verbs are NOT added to any classification cue
#: family, so TaskType classification is unchanged; only the L3 operation (and
#: therefore the illocution) is attested.
_COMPARE_CUE_FORMS: frozenset[str] = frozenset({"compare", "contrast"})

#: Ordered operation evidence sources: ``(cues, word_boundary, operation)``.
#: Each entry reuses an already-validated cue family with its EXISTING matching
#: mode. Earliest position wins; the declared order only breaks ties at the same
#: position (so a leading development form outranks the action cue it shares).
_UTTERANCE_OPERATION_SOURCES: tuple[tuple[frozenset[str], bool, Operation], ...] = (
    (_DEVELOPMENT_CUE_FORMS, True, Operation.DEVELOP),
    (_DEVELOPMENT_VERB_CUES, True, Operation.DEVELOP),
    (_INVESTIGATION_LEAD_CUES, True, Operation.INVESTIGATE),
    (_RESEARCH_CUES, False, Operation.RESEARCH),
    (_EXPLAIN_CUE_FORMS, True, Operation.EXPLAIN),
    (_COMPARE_CUE_FORMS, True, Operation.COMPARE),
    (_ACTION_CUE_FORMS, True, Operation.ACT),
    (_ACTION_COMPOUND_FORMS, True, Operation.ACT),
)

#: Leading words that make an utterance a question even without "?".
_UTTERANCE_QUESTION_WORDS: frozenset[str] = frozenset(
    {"who", "what", "when", "where", "why", "which", "whose", "whom", "how"}
)

#: Bounded request frames (checked at the START of the utterance only).
_UTTERANCE_REQUEST_FRAMES: tuple[str, ...] = (
    "help me",
    "i'd like",
    "i would like",
    "i want",
    "i need",
    "i wish",
    "it would be useful",
    "it would help",
    "would be useful",
    "would be helpful",
    "please",
    "could you",
    "can you",
    "would you",
    "will you",
)

#: Bounded request modals (checked inside the leading window only).
_UTTERANCE_REQUEST_MODALS: frozenset[str] = frozenset(
    {"should", "needs", "need", "want", "wish", "please", "useful"}
)

#: Window (in tokens) in which a request modal counts.
_UTTERANCE_MODAL_WINDOW: int = 4

#: Auxiliaries dropped after a leading question word when extracting a target.
_UTTERANCE_AUXILIARIES: frozenset[str] = frozenset(
    {
        "is", "are", "was", "were", "do", "does", "did", "can", "could",
        "would", "will", "should", "has", "have", "had",
    }
)

#: Ordered objective-extraction cue sources, as ``(cues, word_boundary)``.
#: Every eligible cue is located at its ACTUAL position in the input and the
#: earliest position wins; this declared order only breaks ties at the same
#: position (equal positions yield the same bounded text anyway). Development
#: and action cues are whole-word (including the explicit "long-running"
#: compatibility form); the research verbs keep their substring semantics.
_OBJECTIVE_CUE_SOURCES: tuple[tuple[frozenset[str], bool], ...] = (
    (_DEVELOPMENT_VERB_CUES, True),
    (_DEVELOPMENT_CUE_FORMS, True),
    (_ACTION_CUE_FORMS, True),
    (_ACTION_COMPOUND_FORMS, True),
    (frozenset({"research", "find", "look up", "lookup", "search"}), False),
)

_CONSTRAINT_CUES: tuple[str, ...] = (
    "must",
    "without",
    "using",
    "only",
    "keep",
    "do not",
    "don't",
    "do not use",
    "avoid",
)

_PRIORITY_CUES: tuple[str, ...] = (
    "first",
    "urgent",
    "priority",
    "important",
    "most important",
    "asap",
)

_SUCCESS_CUES: tuple[str, ...] = (
    "done when",
    "so that",
    "verify",
    "verified",
    "success when",
    "make sure",
    "ensure",
    "when it",
    "until",
)

#: Word-boundary pronoun detection for unresolved reference ambiguity.
#: A word-boundary regex avoids false positives such as "it" inside "priority".
_AMBIGUOUS_PRONOUN_RE = re.compile(r"\b(it|that|this|them|those)\b")

#: Bounded relative/complementizer context for "that" (L6): a determiner or
#: quantifier, one word, then "that" ("a module that tracks ..."). A "that"
#: occurrence in this exact closed function-word context is a complementizer —
#: a different lexeme from a demonstrative/pronoun "that" — so it must not raise
#: the reference ambiguity reason. No POS tagging, no parser, no content-word
#: vocabulary: this is a bounded function-word pattern only.
_RELATIVE_THAT_RE = re.compile(
    r"\b(?:a|an|the|any|every|some|each|this|that)\s+\w+\s+(that)\b"
)

#: Ambiguity score at or above which a governed request must be clarified first.
#: Unchanged: this is the single global threshold, used both when the report is
#: first scored and when a resolved reference is reconciled (B).
_CLARIFICATION_THRESHOLD: float = 0.5

#: Weight contributed by each ambiguity reason. Single source of truth: the
#: initial scoring and the resolved-reference reconciliation (B) both read this
#: table, so the two can never drift apart.
_AMBIGUITY_WEIGHTS: dict[str, float] = {
    "objective": 0.25,
    "success": 0.25,
    "reference": 0.3,
    "task_type": 0.35,
}

#: Wh-words used to build deterministic clarification questions.
_CLARIFY_CUES: dict[str, str] = {
    "success": "What outcome would tell you this is done?",
    "objective": "What is the exact objective you want Atlas to achieve?",
    "reference": "What does the ambiguous reference refer to?",
    "task_type": "What kind of task is this?",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bounded_text(value: str, limit: int) -> str:
    """Strip control chars and cap a derived string to ``limit`` chars."""
    if not value:
        return ""
    return _CONTROL_RE.sub(" ", value).strip()[:limit]


def _clauses(text: str) -> list[str]:
    """Split normalized text into non-empty, bounded clauses."""
    return [
        clause.strip()
        for clause in re.split(r"[;,\n]", text)
        if clause.strip()
    ]


def _first_hit(
    text: str,
    cues: frozenset[str] | tuple[str, ...],
    *,
    word_boundary: bool = False,
) -> bool:
    """Return True when any cue is present (whole-cue match).

    When ``word_boundary`` is False (default), a cue matches if it appears
    anywhere in ``text`` as a substring. When True, the cue must appear as
    a whole word (word-boundary match) so that tool/action identifiers such
    as ``code_inspector`` do not trigger broad investigation cues such as
    ``inspect``.
    """
    lowered = text.lower()
    if not word_boundary:
        return any(cue in lowered for cue in cues)
    return any(re.search(rf"\b{re.escape(cue)}\b", lowered) for cue in cues)


def _extract_items(text: str, cues: tuple[str, ...]) -> tuple[str, ...]:
    """Extract bounded, deduplicated cue-anchored clauses in appearance order.

    Every cue occurrence is located, sorted by position, then each clause is
    taken from the cue to the next clause boundary. Overlapping occurrences
    (e.g. "do not" inside "do not use") are collapsed so one cue produces one
    clause.
    """
    matches: list[tuple[int, str]] = []
    lowered = text.lower()
    for cue in cues:
        start = 0
        while True:
            idx = lowered.find(cue, start)
            if idx < 0:
                break
            matches.append((idx, cue))
            start = idx + 1
    matches.sort(key=lambda m: m[0])

    items: list[str] = []
    seen: set[str] = set()
    covered_until = -1
    for idx, _cue in matches:
        if idx < covered_until:
            continue
        clause = text[idx:]
        boundary = min(
            [b for b in (clause.find(";"), clause.find(", "), clause.find("\n")) if b >= 0]
            or [len(clause)]
        )
        item = _bounded_text(clause[:boundary], _MAX_ITEM_CHARS)
        if item:
            covered_until = idx + len(item)
            if item not in seen:
                seen.add(item)
                items.append(item)
        if len(items) >= _MAX_ITEM_COUNT:
            break
    return tuple(items)


def _tokens(text: str) -> tuple[str, ...]:
    """Return deduplicated, order-preserving lowercase alnum tokens."""
    seen: dict[str, None] = {}
    for raw in _TOKEN_RE.findall(text.lower()):
        if len(raw) >= _MIN_TOKEN_LEN:
            seen.setdefault(raw, None)
    return tuple(seen)


def _is_negated(text: str, cue: str) -> bool:
    """Return True when ``cue`` appears in ``text`` immediately after a
    negation prefix (e.g. "don't modify" -> ``modify`` is negated).

    This is intentionally narrow: it only detects the common contraction/
    adverb negation patterns required to prevent misclassification of
    explicit read-only boundaries such as "don't modify anything yet".
    """
    lowered = text.lower()
    idx = lowered.find(cue)
    if idx <= 0:
        return False
    return _occurrence_is_negated(lowered, idx)


def _occurrence_is_negated(lowered: str, idx: int) -> bool:
    """Return True when the cue occurrence at ``idx`` is immediately
    preceded by a negation prefix."""
    if idx <= 0:
        return False
    prefix = lowered[:idx].rstrip()
    return any(prefix.endswith(neg) for neg in _NEGATION_PREFIXES)


def _word_cue_is_negated(lowered: str, cue: str) -> bool:
    """Return True when ``cue`` occurs as a whole word AND that occurrence is
    immediately negated (e.g. "don't modify" -> ``modify`` is negated).

    Locating the cue as a whole word keeps the negation check aligned with the
    accepted-form development policy: an occurrence inside an unrelated word
    ("prefix" for ``fix``) never counts, and a cue that is absent returns False.
    """
    match = re.search(rf"\b{re.escape(cue)}\b", lowered)
    return match is not None and _occurrence_is_negated(lowered, match.start())


def _has_reference_ambiguity(lowered: str) -> bool:
    """Return True when the utterance still carries a genuine reference guess.

    L6 — evaluated PER OCCURRENCE. A ``that`` occurrence in the bounded
    relative/complementizer context (:data:`_RELATIVE_THAT_RE`) is excluded, so
    "Build a module that tracks ..." no longer raises the reference reason.
    Every OTHER occurrence — "it", "this", "them", "those", and every "that"
    outside that context — still raises it, so a mixed utterance keeps the
    reason contributed by its genuine reference, and unresolvable or
    demonstrative cases stay fail-closed exactly as before.
    """
    complementizer_spans = {
        match.start(1) for match in _RELATIVE_THAT_RE.finditer(lowered)
    }
    for match in _AMBIGUOUS_PRONOUN_RE.finditer(lowered):
        if match.start(1) in complementizer_spans:
            continue
        return True
    return False


def _first_cue_index(
    lowered: str,
    cues: frozenset[str],
    *,
    word_boundary: bool = False,
) -> int | None:
    """Return the earliest index of any cue, or None when absent.

    When ``word_boundary`` is True the cue must appear as a whole word,
    mirroring :func:`_first_hit`, so a standalone development verb such as
    ``develop`` is located without matching inside ``development`` or
    ``developed``.
    """
    best: int | None = None
    for cue in cues:
        if word_boundary:
            match = re.search(rf"\b{re.escape(cue)}\b", lowered)
            idx = match.start() if match is not None else -1
        else:
            idx = lowered.find(cue)
        if idx >= 0 and (best is None or idx < best):
            best = idx
    return best


def _leading_operation(lowered: str) -> tuple[Operation | None, int | None]:
    """Return the earliest attested operation and its index, or ``(None, None)``.

    Every source is evaluated at its ACTUAL position in the utterance; the
    earliest position wins and the declared order breaks ties. Selection never
    depends on the iteration order of an unordered collection, so the result is
    stable across processes.
    """
    best: tuple[int, int] | None = None
    best_operation: Operation | None = None
    for rank, (cues, word_boundary, operation) in enumerate(
        _UTTERANCE_OPERATION_SOURCES
    ):
        idx = _first_cue_index(lowered, cues, word_boundary=word_boundary)
        if idx is None:
            continue
        candidate = (idx, rank)
        if best is None or candidate < best:
            best = candidate
            best_operation = operation
    if best is None:
        return None, None
    return best_operation, best[0]


def _utterance_illocution(normalized: str, operation_index: int | None) -> Illocution:
    """Return the utterance's illocution from bounded surface evidence.

    A question is an explicit ``?`` or a leading question word. A request is a
    leading imperative operation, a bounded request frame, or a bounded request
    modal inside the leading window. Anything else is a statement.

    There is deliberately NO separate "desire" value: a non-imperative desire
    ("I'd like ...", "I want Atlas to ...", "It would be useful ...") is a
    request.
    """
    lowered = normalized.lower()
    tokens = _tokens(normalized)
    if "?" in normalized:
        return Illocution.QUESTION
    if tokens and tokens[0] in _UTTERANCE_QUESTION_WORDS:
        return Illocution.QUESTION
    for frame in _UTTERANCE_REQUEST_FRAMES:
        if lowered.startswith(frame):
            return Illocution.REQUEST
    if operation_index == 0:
        return Illocution.REQUEST
    if any(
        token in _UTTERANCE_REQUEST_MODALS
        for token in tokens[:_UTTERANCE_MODAL_WINDOW]
    ):
        return Illocution.REQUEST
    return Illocution.STATEMENT


def _utterance_target(
    normalized: str,
    illocution: Illocution,
    operation_index: int | None,
) -> str | None:
    """Return the bounded target expression, or ``None`` when there is none.

    Bounded rule: start from the L2-canonicalized surface (frame-stripped),
    then drop ONE leading operator — for a question, a leading question word
    plus one auxiliary; for a request whose operation starts the utterance, the
    leading imperative token. The remainder is the target.

    Nothing is resolved or typed here: the target is an UNRESOLVED text
    expression. Entity identification and reference resolution stay in L4.
    """
    surface = canonicalize_surface(normalized)
    if not surface:
        return None
    text = surface.strip()
    if illocution is Illocution.QUESTION:
        text = text.rstrip("?").strip()
        match = re.match(
            r"^(?:" + "|".join(sorted(_UTTERANCE_QUESTION_WORDS)) + r")\b\s*",
            text,
            re.IGNORECASE,
        )
        if match is not None:
            text = text[match.end():]
        match = re.match(
            r"^(?:" + "|".join(sorted(_UTTERANCE_AUXILIARIES)) + r")\b\s*",
            text,
            re.IGNORECASE,
        )
        if match is not None:
            text = text[match.end():]
    elif operation_index == 0:
        first, _, remainder = text.partition(" ")
        text = remainder or first
    bounded = _bounded_text(text, MAX_TARGET_CHARS)
    return bounded or None


def build_utterance_meaning(normalized: str) -> UtteranceMeaning:
    """Build the deterministic L3 interpretation of one normalized utterance.

    Deterministic and model-independent: no clock, no randomness, no I/O, no
    provider, no embedding. Identical input yields identical output.
    """
    operation, operation_index = _leading_operation(normalized.lower())
    illocution = _utterance_illocution(normalized, operation_index)
    return UtteranceMeaning(
        illocution=illocution,
        operation=operation,
        target=_utterance_target(normalized, illocution, operation_index),
    )


def _leading_operation_is_research(meaning: UtteranceMeaning | None) -> bool:
    """True when L3 determined the LEADING requested operation is research."""
    return meaning is not None and meaning.operation is Operation.RESEARCH


def _utterance_is_question(meaning: UtteranceMeaning | None) -> bool:
    """True when L3 determined the utterance is a question."""
    return meaning is not None and meaning.illocution is Illocution.QUESTION


def _investigation_leads_compound(normalized: str) -> bool:
    """Return True when a compound request asks for investigation FIRST.

    A compound development request ("Investigate X, create a development
    proposal, and present it for my approval") names investigation as its
    first stage; its forward-looking planning/approval language must not
    hijack classification into APPROVAL/PLANNING_REQUEST. The request is
    compound only when a planning cue is also present, and investigation
    leads only when a non-negated imperative investigation cue occurs
    BEFORE that planning cue. Noun forms ("investigation", "diagnosis",
    "analysis") refer to a prior artifact and never lead a compound
    request, so single-intent planning requests such as "convert this
    investigation" remain PLANNING_REQUEST.
    """
    lowered = normalized.lower()
    planning_index = _first_cue_index(lowered, _PLANNING_CUES)
    if planning_index is None:
        return False
    for cue in _INVESTIGATION_LEAD_CUES:
        match = re.search(rf"\b{re.escape(cue)}\b", lowered)
        if match is None:
            continue
        idx = match.start()
        if idx < planning_index and not _occurrence_is_negated(lowered, idx):
            return True
    return False


def _investigation_lead_present(normalized: str) -> bool:
    """Return True when a non-negated imperative investigation lead is present.

    A request that explicitly asks for an investigation must not be
    reclassified as APPROVAL/REJECTION/RECOVERY by a bare *mention* of that
    subsystem ("Investigate the approval flow.") or by a boundary statement
    about it ("Investigate X. Priority: don't break the approval boundary.").
    Only imperative lead cues count — noun forms ("investigation", "analysis")
    refer to a prior artifact — and a negated lead ("don't investigate,
    approve it") does not count.

    This is the protection already applied to planning via
    :func:`_investigation_leads_compound`, without additionally requiring a
    planning cue to be present.
    """
    lowered = normalized.lower()
    for cue in _INVESTIGATION_LEAD_CUES:
        for match in re.finditer(rf"\b{re.escape(cue)}\b", lowered):
            if not _occurrence_is_negated(lowered, match.start()):
                return True
    return False


def _has_word_cue(text: str, cues: frozenset[str]) -> bool:
    """Return True when any cue appears in ``text`` as a whole word."""
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(cue)}\b", lowered) for cue in cues)


def _mention_only_hijack(
    normalized: str,
    lowered: str,
    mention_cues: frozenset[str],
    instruction_cues: frozenset[str],
) -> bool:
    """Return True when a bare subsystem *mention* must not override an
    explicit investigation lead.

    A subsystem counts as a mention only when its noun form is present and no
    instruction form is: an explicit instruction ("approve it", "reject the
    proposal", "Examine the proposal and approve it.") keeps its existing
    classification, while a mention used as an investigation target or as a
    constraint ("Investigate the approval flow.", "... don't break the
    approval boundary.") must not authorize or reject anything.
    """
    if not _investigation_lead_present(normalized):
        return False
    return _has_word_cue(lowered, mention_cues) and not _has_word_cue(
        lowered, instruction_cues
    )


def _is_explicit_approval(text: str) -> bool:
    """Return True when the text contains explicit approval language.

    Explicit approval requires unambiguous approval cues (e.g. "approve",
    "accept", "authorize"). Ambiguous responses like "okay", "sounds good",
    "go ahead" are NOT treated as approval.

    Word-boundary matching prevents false positives such as "unauthorized"
    matching "authorized".

    Args:
        text: the normalized request text.

    Returns:
        True if the text contains explicit approval language.
    """
    lowered = text.lower()
    # Must contain an explicit approval cue (word-boundary match)
    has_approval_cue = any(
        re.search(rf"\b{re.escape(cue)}\b", lowered) for cue in _APPROVAL_CUES
    )
    if not has_approval_cue:
        return False
    # Must NOT be negated (e.g. "don't approve")
    for cue in _APPROVAL_CUES:
        if re.search(rf"\b{re.escape(cue)}\b", lowered) and _is_negated(lowered, cue):
            return False
    return True


def _is_explicit_rejection(text: str) -> bool:
    """Return True when the text contains explicit rejection language.

    Explicit rejection requires unambiguous rejection cues (e.g. "reject",
    "decline", "deny"). Ambiguous responses like "okay", "sounds good"
    are NOT treated as rejection.

    Word-boundary matching prevents false positives such as "unrejected"
    matching "rejected".

    Args:
        text: the normalized request text.

    Returns:
        True if the text contains explicit rejection language.
    """
    lowered = text.lower()
    # Must contain an explicit rejection cue (word-boundary match)
    has_rejection_cue = any(
        re.search(rf"\b{re.escape(cue)}\b", lowered) for cue in _REJECTION_CUES
    )
    if not has_rejection_cue:
        return False
    # Must NOT be negated (e.g. "don't reject")
    for cue in _REJECTION_CUES:
        if re.search(rf"\b{re.escape(cue)}\b", lowered) and _is_negated(lowered, cue):
            return False
    return True


def _is_explicit_execution(text: str) -> bool:
    """Return True when the text contains explicit execution language.

    Explicit execution requires unambiguous execution cues (e.g. "execute",
    "implement", "apply the approved proposal"). Ambiguous responses like
    "okay", "go ahead", "do it" are NOT treated as execution.

    Word-boundary matching prevents false positives such as "unexecuted"
    matching "execute".

    Args:
        text: the normalized request text.

    Returns:
        True if the text contains explicit execution language.
    """
    lowered = text.lower()
    # Must contain an explicit execution cue (word-boundary match)
    has_execution_cue = any(
        re.search(rf"\b{re.escape(cue)}\b", lowered) for cue in _EXECUTION_CUES
    )
    if not has_execution_cue:
        return False
    # Must NOT be negated (e.g. "don't execute")
    for cue in _EXECUTION_CUES:
        if re.search(rf"\b{re.escape(cue)}\b", lowered) and _is_negated(lowered, cue):
            return False
    return True


def _stable_hash(text: str) -> str:
    """Deterministic SHA-256 short hash of the raw input."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AmbiguityReport:
    """Deterministic ambiguity assessment for a parsed instruction."""

    ambiguity_score: float = 0.0
    ambiguities: tuple[str, ...] = ()
    clarification_questions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ambiguity_score": self.ambiguity_score,
            "ambiguities": list(self.ambiguities),
            "clarification_questions": list(self.clarification_questions),
        }


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Structured, provenance-carrying representation of one instruction."""

    task_id: str
    task_type: TaskType
    intent: str
    goal: str
    constraints: tuple[str, ...]
    priorities: tuple[str, ...]
    success_criteria: tuple[str, ...]
    context: dict[str, Any]
    ambiguity: AmbiguityReport
    confidence: float
    needs_clarification: bool
    source: str
    verified: bool
    model_metadata: dict[str, Any]
    created_at: datetime
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe deterministic serialization (no raw prompt/response)."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "intent": self.intent,
            "goal": self.goal,
            "constraints": list(self.constraints),
            "priorities": list(self.priorities),
            "success_criteria": list(self.success_criteria),
            "context": self.context,
            "ambiguity": self.ambiguity.to_dict(),
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "source": self.source,
            "verified": self.verified,
            "model_metadata": self.model_metadata,
            "created_at": self.created_at.isoformat(),
            "input_hash": self.input_hash,
        }

    def goal_string(self) -> str:
        """Render the bounded goal for the existing ``CognitionState.goal``."""
        return self.goal


@runtime_checkable
class IntentParser(Protocol):
    """Optional model-assisted parsing seam.

    Implementations live outside this pure module and are injected by the
    composition layer through an existing provider seam. They never receive
    capability/execution access; their output is untrusted data that this
    module validates, bounds, and marks ``verified=False``.
    """

    def parse(self, text: str, context: dict[str, Any]) -> dict[str, Any] | None:
        """Return a bounded parse dict, or None to fall back deterministically."""
        ...


# ---------------------------------------------------------------------------
# TaskIntake
# ---------------------------------------------------------------------------


class TaskIntake:
    """Deterministic conversational task intake (optional model assist).

    Args:
        parser: Optional :class:`IntentParser`. When absent (default), intake
            is deterministic-only and no model is ever consulted. When
            present, its output is treated as untrusted, validated, and used
            only to fill the spec fields; any failure falls back to the
            deterministic result.
    """

    def __init__(self, parser: IntentParser | None = None, now: datetime | None = None) -> None:
        self._parser = parser
        self._now = now

    def intake(self, text: str, history_length: int = 0) -> TaskSpec:
        """Parse one instruction into a bounded, deterministic-first TaskSpec.

        Never raises: malformed/empty/non-string input produces a minimal,
        high-ambiguity ``UNKNOWN`` spec.
        """
        if not isinstance(text, str):
            text = ""
        raw = text
        normalized = collapse_whitespace(text)
        context = self._build_context(raw, history_length)

        model_fields: dict[str, Any] | None = None
        if self._parser is not None:
            try:
                parsed = self._parser.parse(raw, context)
                if isinstance(parsed, dict):
                    model_fields = self._sanitize_model_fields(parsed)
            except Exception:
                model_fields = None

        return self._build_spec(
            raw=raw,
            normalized=normalized,
            context=context,
            model_fields=model_fields,
        )

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def _build_context(self, raw: str, history_length: int) -> dict[str, Any]:
        """Derive bounded, non-secret context from the instruction."""
        tokens = _tokens(raw)
        return {
            "history_length": max(0, min(history_length, 10_000)),
            "concepts": list(tokens[:_MAX_CONTEXT_VALUES]),
            "token_count": len(tokens),
            "length": len(raw),
        }

    # ------------------------------------------------------------------
    # Model-assist sanitization (untrusted data)
    # ------------------------------------------------------------------

    def _sanitize_model_fields(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """Validate and bound an injected parser's output.

        Returns a dict of only the fields the deterministic path understands;
        malformed values are dropped. The raw model prompt/response never
        enters this structure.
        """
        fields: dict[str, Any] = {}

        task_type_raw = parsed.get("task_type")
        if isinstance(task_type_raw, str) and task_type_raw in _TASK_TYPE_BY_VALUE:
            fields["task_type"] = _TASK_TYPE_BY_VALUE[task_type_raw]

        for key, limit in (
            ("intent", _MAX_INTENT_CHARS),
            ("goal", _MAX_GOAL_CHARS),
        ):
            value = parsed.get(key)
            if isinstance(value, str):
                cleaned = _bounded_text(value, limit)
                if cleaned:
                    fields[key] = cleaned

        for key in ("constraints", "priorities", "success_criteria"):
            value = parsed.get(key)
            if isinstance(value, list):
                cleaned = []
                seen: set[str] = set()
                for item in value:
                    if not isinstance(item, str):
                        continue
                    text_item = _bounded_text(item, _MAX_ITEM_CHARS)
                    if text_item and text_item not in seen:
                        seen.add(text_item)
                        cleaned.append(text_item)
                    if len(cleaned) >= _MAX_ITEM_COUNT:
                        break
                fields[key] = cleaned

        return fields

    # ------------------------------------------------------------------
    # Deterministic classification / extraction
    # ------------------------------------------------------------------

    def _classify(
        self,
        normalized: str,
        meaning: UtteranceMeaning | None = None,
    ) -> TaskType:
        lowered = normalized.lower()
        if not normalized:
            return TaskType.UNKNOWN
        if not _tokens(normalized):
            return TaskType.UNKNOWN

        # Explicit execution is checked first. It requires unambiguous execution
        # language and cannot be ambiguous conversational responses.
        if _is_explicit_execution(normalized):
            return TaskType.EXECUTION_REQUEST

        # Explicit approval is checked next. It requires unambiguous approval
        # language and cannot be ambiguous conversational responses. An
        # investigation-first compound request ("Investigate X, create a
        # development proposal, and present it for my approval") names
        # investigation as its first stage, so its forward-looking approval
        # language must not hijack the classification. The same applies when
        # the investigation is the whole request and merely names or constrains
        # the approval subsystem ("Investigate the approval flow."), which must
        # never authorize a pending proposal; an explicit approval instruction
        # ("... and approve it.") keeps its existing classification.
        if _is_explicit_approval(normalized) and not (
            _investigation_leads_compound(normalized)
            or _utterance_is_question(meaning)
            or _mention_only_hijack(
                normalized,
                lowered,
                _APPROVAL_MENTION_CUES,
                _APPROVAL_CUES - _APPROVAL_MENTION_CUES,
            )
        ):
            return TaskType.APPROVAL

        # Explicit rejection is checked next, symmetric with approval.
        # It requires unambiguous rejection language and cannot be
        # ambiguous conversational responses. A bare mention of the rejection
        # subsystem must not reject a pending proposal by naming it.
        if _is_explicit_rejection(normalized) and not (
            _utterance_is_question(meaning)
            or _mention_only_hijack(
                normalized,
                lowered,
                _REJECTION_MENTION_CUES,
                _REJECTION_CUES - _REJECTION_MENTION_CUES,
            )
        ):
            return TaskType.REJECTION_REQUEST

        # Explicit recovery phrases are checked next. They indicate the user
        # wants to recover from a previous development execution failure.
        # Checked before planning so that "recover" is not misclassified. An
        # investigation that merely names the recovery subsystem stays an
        # investigation.
        recovery = _first_hit(lowered, _RECOVERY_CUES) and not _mention_only_hijack(
            normalized,
            lowered,
            _RECOVERY_MENTION_CUES,
            _RECOVERY_CUES - _RECOVERY_MENTION_CUES,
        )
        if recovery:
            return TaskType.RECOVERY_REQUEST

        # Explicit verification phrases are checked next. They indicate the
        # user wants to verify an already-completed development result.
        # Checked before planning so that "verify" is not misclassified.
        verification = _first_hit(lowered, _VERIFICATION_CUES)
        if verification:
            return TaskType.VERIFICATION_REQUEST

        # Explicit report phrases are checked next. They indicate the user
        # wants a final lifecycle report. Checked before planning so that
        # "report" is not misclassified.
        report = _first_hit(lowered, _REPORT_CUES)
        if report:
            return TaskType.REPORT_REQUEST

        # Explicit L1 autonomy phrases are checked next. They indicate the user
        # wants Atlas to proceed autonomously with an already-approved plan.
        # Checked before planning so that "proceed" is not misclassified.
        autonomy = _first_hit(lowered, _AUTONOMY_CUES)
        if autonomy:
            return TaskType.AUTONOMY_REQUEST

        # Explicit L2 autonomy phrases are checked next. They indicate the user
        # wants Atlas to chain workflows or make bounded plan adjustments.
        l2_autonomy = _first_hit(lowered, _L2_AUTONOMY_CUES)
        if l2_autonomy:
            return TaskType.L2_AUTONOMY_REQUEST

        # Explicit L3 autonomy phrases are checked next. They indicate the user
        # wants Atlas to execute recovery, generate sub-plans, or handle HIGH risk.
        l3_autonomy = _first_hit(lowered, _L3_AUTONOMY_CUES)
        if l3_autonomy:
            return TaskType.L3_AUTONOMY_REQUEST

        # Explicit L4 autonomy phrases are checked next. They indicate the user
        # wants Atlas to acquire capabilities, modify memory/knowledge, or handle CRITICAL risk.
        l4_autonomy = _first_hit(lowered, _L4_AUTONOMY_CUES)
        if l4_autonomy:
            return TaskType.L4_AUTONOMY_REQUEST

        # Explicit L5 autonomy phrases are checked next. They indicate the user
        # wants Atlas to coordinate across objectives, prioritize work, or manage dependencies.
        l5_autonomy = _first_hit(lowered, _L5_AUTONOMY_CUES)
        if l5_autonomy:
            return TaskType.L5_AUTONOMY_REQUEST

        # Explicit planning phrases are checked next. They indicate the user
        # wants to convert an investigation proposal into a development
        # proposal. Checked before investigation because some planning phrases
        # contain investigation-related words (e.g., "convert this investigation").
        # An investigation-first compound request skips planning so that its
        # forward-looking proposal language classifies as investigation.
        planning = _first_hit(lowered, _PLANNING_CUES)
        if planning and not _investigation_leads_compound(normalized):
            return TaskType.PLANNING_REQUEST

        # Investigation cues are checked next and take precedence.
        # They are read-only by intent and must not be routed to development.
        # Word-boundary matching prevents tool/action identifiers such as
        # "code_inspector" from triggering broad investigation cues such as
        # "inspect"; genuine investigation language ("inspect the repo") still
        # matches because the cue appears as a standalone word.
        investigation = _first_hit(
            lowered, _INVESTIGATION_CUES, word_boundary=True
        )
        # Only an imperative investigation cue marks the requested operation.
        # A recall/remembrance request targets an existing conversation result,
        # so an investigation noun in its target must not hijack it.
        recall_phrased = bool(
            _RECALL_PHRASE_RE.search(lowered)
        ) and not _first_hit(
            lowered, _INVESTIGATION_LEAD_CUES, word_boundary=True
        )
        if investigation and not recall_phrased:
            return TaskType.INVESTIGATION_REQUEST

        # C4.2 — bounded repository impact-analysis exposure. Recognized only
        # when an explicit impact cue AND a deterministically resolvable
        # repository target token are both present; otherwise this falls
        # through to the existing question/fallback behavior. No general
        # natural-language understanding and no reference resolution.
        if looks_like_repository_impact_request(normalized):
            return TaskType.REPOSITORY_IMPACT_REQUEST

        # Development cues are matched as explicit accepted WHOLE-WORD forms
        # (never as broad substrings) and are only treated as development when
        # NOT negated. "don't modify" must not become a development request,
        # and "address"/"prefix"/"implementation" must not match add/fix/implement.
        development_cue_hit = _first_hit(
            lowered, _DEVELOPMENT_CUE_FORMS, word_boundary=True
        ) or _first_hit(lowered, _DEVELOPMENT_VERB_CUES, word_boundary=True)
        development_negated = any(
            _word_cue_is_negated(lowered, cue)
            for cue in (*_DEVELOPMENT_CUE_FORMS, *_DEVELOPMENT_VERB_CUES)
        )
        development = (development_cue_hit and not development_negated) and (
            _first_hit(lowered, _SELF_TARGETS)
            or "capability" in lowered
            or "module" in lowered
        )
        research = _first_hit(lowered, _RESEARCH_CUES)
        greeting = bool(_GREETING_RE.search(lowered))
        question = "?" in normalized or (
            _first_hit(lowered, _QUESTION_CUES) and len(_tokens(normalized)) <= 20
        )
        action = _first_hit(
            lowered, _ACTION_CUE_FORMS, word_boundary=True
        ) or _first_hit(lowered, _ACTION_COMPOUND_FORMS, word_boundary=True)

        # Development wins over generic research/action because it names
        # Atlas itself or its capabilities as the target.
        # L3 — the LEADING requested operation outranks a later development cue:
        # "Research how Atlas could improve ..." is research, not development.
        # The precedence table itself is unchanged; only the structured
        # evidence supplied to it is.
        if development and not _leading_operation_is_research(meaning):
            return TaskType.DEVELOPMENT_REQUEST
        if research:
            return TaskType.INFORMATION_REQUEST
        if greeting:
            return TaskType.CONVERSATION
        if question:
            return TaskType.QUESTION
        # NLU-1 — a request for a bounded planning/assistance artifact (a plan,
        # checklist, roadmap, or process) is an ANSWERABLE request, not an
        # executable tool action. Routing it as a casual question keeps it out
        # of the orchestration/development-need path, which would otherwise
        # misread "no registered tool for this subject" as an Atlas
        # capability gap. Explicit self-development evidence above keeps
        # precedence, so "create a module/capability" remains DEVELOPMENT.
        if action and not development and _has_word_cue(
            lowered, _PLANNING_ARTIFACT_CUES
        ):
            return TaskType.QUESTION
        if action:
            return TaskType.ACTION_REQUEST
        return TaskType.CONVERSATION

    def _extract_objective(self, normalized: str) -> str:
        lowered = normalized.lower()
        # Every eligible cue is evaluated at its actual position in the input and
        # the earliest position wins. Selection never depends on the iteration
        # order of an unordered collection, so the objective is stable across
        # processes (Python hash randomization) as well as within one.
        best: tuple[int, int] | None = None
        for rank, (cues, word_boundary) in enumerate(_OBJECTIVE_CUE_SOURCES):
            idx = _first_cue_index(lowered, cues, word_boundary=word_boundary)
            if idx is None:
                continue
            candidate = (idx, rank)
            if best is None or candidate < best:
                best = candidate
        if best is not None:
            return _bounded_text(normalized[best[0]:], _MAX_INTENT_CHARS)
        return _bounded_text(normalized, _MAX_INTENT_CHARS)

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _build_spec(
        self,
        raw: str,
        normalized: str,
        context: dict[str, Any],
        model_fields: dict[str, Any] | None,
    ) -> TaskSpec:
        # Deterministic fields (always computed, even when model assist is on,
        # so there is always a safe fallback).
        # L3 — minimal structured utterance meaning. Computed once from the
        # PRE-canonicalization surface, so request frames ("I'd like ...",
        # "I want ...", "It would be useful ...") are still visible to L3 even
        # though canonicalization strips them for the existing consumers. It is
        # additional structured interpretation: it never replaces task_type,
        # intent, ambiguity or reference handling, and it grants no authority.
        meaning = build_utterance_meaning(normalized)
        context = {**context, UTTERANCE_MEANING_KEY: meaning.to_dict()}

        deterministic_type = self._classify(
            canonicalize_surface(normalized), meaning
        )
        deterministic_intent = self._extract_objective(normalized)
        deterministic_constraints = _extract_items(normalized, _CONSTRAINT_CUES)
        deterministic_priorities = _extract_items(normalized, _PRIORITY_CUES)
        deterministic_success = _extract_items(normalized, _SUCCESS_CUES)

        using_model = model_fields is not None
        task_type = (
            model_fields.get("task_type", deterministic_type)
            if using_model
            else deterministic_type
        )
        intent = (
            model_fields.get("intent", deterministic_intent)
            if using_model
            else deterministic_intent
        )
        constraints = (
            tuple(model_fields.get("constraints", ()))
            if using_model and "constraints" in model_fields
            else deterministic_constraints
        )
        priorities = (
            tuple(model_fields.get("priorities", ()))
            if using_model and "priorities" in model_fields
            else deterministic_priorities
        )
        success_criteria = (
            tuple(model_fields.get("success_criteria", ()))
            if using_model and "success_criteria" in model_fields
            else deterministic_success
        )

        ambiguity = self._assess_ambiguity(
            normalized=normalized,
            task_type=task_type,
            objective=intent,
            constraints=constraints,
            success_criteria=success_criteria,
        )
        confidence = self._confidence(
            task_type=task_type,
            objective=intent,
            success_criteria=success_criteria,
            using_model=using_model,
        )

        goal = self._render_goal(
            task_type=task_type,
            objective=intent,
            constraints=constraints,
            priorities=priorities,
            success_criteria=success_criteria,
        )
        needs_clarification = (
            task_type in (TaskType.ACTION_REQUEST, TaskType.DEVELOPMENT_REQUEST)
            and ambiguity.ambiguity_score >= _CLARIFICATION_THRESHOLD
        )

        source = "model_assisted" if using_model else "deterministic"
        verified = not using_model
        model_metadata: dict[str, Any] = {}
        if using_model:
            model_metadata = {
                "task_type": task_type.value,
                "intent_provided": "intent" in model_fields,
            }

        return TaskSpec(
            task_id=_stable_hash(raw),
            task_type=task_type,
            intent=intent,
            goal=goal,
            constraints=constraints,
            priorities=priorities,
            success_criteria=success_criteria,
            context=context,
            ambiguity=ambiguity,
            confidence=confidence,
            needs_clarification=needs_clarification,
            source=source,
            verified=verified,
            model_metadata=model_metadata,
            created_at=self._now if self._now is not None else datetime.now(),
            input_hash=_stable_hash(raw),
        )

    def _assess_ambiguity(
        self,
        normalized: str,
        task_type: TaskType,
        objective: str,
        constraints: tuple[str, ...],
        success_criteria: tuple[str, ...],
    ) -> AmbiguityReport:
        reasons: list[str] = []
        lowered = normalized.lower()

        if task_type in (TaskType.ACTION_REQUEST, TaskType.DEVELOPMENT_REQUEST) and not objective:
            reasons.append("objective")

        if task_type in (TaskType.ACTION_REQUEST, TaskType.DEVELOPMENT_REQUEST) and not success_criteria:
            reasons.append("success")

        if task_type == TaskType.UNKNOWN:
            reasons.append("task_type")

        if _has_reference_ambiguity(lowered):
            reasons.append("reference")

        reasons = sorted(set(reasons))
        weight = 0.0
        for reason in reasons:
            weight += _AMBIGUITY_WEIGHTS.get(reason, 0.0)
        score = round(min(1.0, weight), 4)

        questions: list[str] = []
        seen: set[str] = set()
        for reason in reasons:
            template = _CLARIFY_CUES.get(reason)
            if template and template not in seen:
                seen.add(template)
                questions.append(template)

        return AmbiguityReport(
            ambiguity_score=score,
            ambiguities=tuple(reasons),
            clarification_questions=tuple(questions),
        )

    def _confidence(
        self,
        task_type: TaskType,
        objective: str,
        success_criteria: tuple[str, ...],
        using_model: bool,
    ) -> float:
        """Deterministic confidence (never inflates model-assist trust)."""
        score = 0.0
        if task_type is not TaskType.UNKNOWN:
            score += 0.3
        if objective:
            score += 0.3
        if success_criteria:
            score += 0.4
        if using_model:
            score = min(score, 0.5)
        return round(score, 4)

    def _render_goal(
        self,
        task_type: TaskType,
        objective: str,
        constraints: tuple[str, ...],
        priorities: tuple[str, ...],
        success_criteria: tuple[str, ...],
    ) -> str:
        """Render the bounded, prioritized goal string for CognitionState.goal."""
        verb = "respond" if task_type in (TaskType.CONVERSATION, TaskType.UNKNOWN) else "respond"
        parts = [f"{verb}: {objective}" if objective else f"{verb}"]
        if constraints:
            parts.append("constraints: " + "; ".join(constraints))
        if priorities:
            parts.append("priorities: " + "; ".join(priorities))
        if success_criteria:
            parts.append("success: " + "; ".join(success_criteria))
        return _bounded_text(" | ".join(parts), _MAX_GOAL_CHARS)


def reconcile_resolved_reference_ambiguity(spec: TaskSpec) -> TaskSpec:
    """Clear the *resolved* reference component of an ambiguity report (B).

    Integration seam, not a scorer. Called by the conversation service at the
    single point where the existing deterministic reference pipeline has
    returned ``RESOLVED`` and attached a valid ``resolved_reference`` to the
    spec. The ``reference`` reason is a *guess* signal ("the turn contains an
    ambiguous pronoun"), so once the reference is actually bound it is no
    longer a genuine ambiguity and must not block a governed request.

    Bounded by construction:

      * only the ``reference`` reason is removed, together with its own weight
        and its own clarification question;
      * every other reason is retained verbatim, so unrelated ambiguity still
        blocks;
      * the score is recomputed from the retained reasons using the same
        :data:`_AMBIGUITY_WEIGHTS` table, and ``needs_clarification`` is
        re-derived with the same global :data:`_CLARIFICATION_THRESHOLD` — the
        threshold and every other weight are untouched.

    Fail closed: a spec with no ``reference`` reason (including one whose
    reference stayed UNRESOLVED or AMBIGUOUS, which never reaches this seam) is
    returned unchanged, byte for byte.
    """
    ambiguity = getattr(spec, "ambiguity", None)
    reasons = tuple(getattr(ambiguity, "ambiguities", ()) or ())
    if "reference" not in reasons:
        return spec

    remaining = tuple(reason for reason in reasons if reason != "reference")
    weight = 0.0
    for reason in remaining:
        weight += _AMBIGUITY_WEIGHTS.get(reason, 0.0)
    score = round(min(1.0, weight), 4)

    questions = tuple(_CLARIFY_CUES[r] for r in remaining if r in _CLARIFY_CUES)
    reconciled = AmbiguityReport(
        ambiguity_score=score,
        ambiguities=remaining,
        clarification_questions=questions,
    )
    needs_clarification = (
        spec.task_type in (TaskType.ACTION_REQUEST, TaskType.DEVELOPMENT_REQUEST)
        and score >= _CLARIFICATION_THRESHOLD
    )
    return replace(
        spec,
        ambiguity=reconciled,
        needs_clarification=needs_clarification,
    )


_TASK_TYPE_BY_VALUE: dict[str, TaskType] = {
    member.value: member for member in TaskType
}
