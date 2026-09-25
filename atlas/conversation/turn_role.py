"""Conversational turn role (Evidence-Driven Improvement 2).

The smallest explicit representation of *what kind of turn* a user utterance is,
so the D1 conversation layer can decide whether the turn may replace the active
``ConversationState.current_objective`` or must preserve it.

This is deliberately NOT a general-purpose NLU layer: every cue set is bounded,
deterministic, and reused from existing Atlas machinery where one already exists
(the builtin acknowledgement/conversation-recall cues and the bounded
reference/repeat recognition). It carries no authority and performs no routing —
it only classifies the turn for bounded conversational-state handling.

Roles whose turns are follow-ups/meta/acknowledgements NEVER replace the active
objective; only :attr:`TurnRole.NEW_OBJECTIVE` (and a
:attr:`TurnRole.CORRECTION`, which replaces the reading with the corrected
subject) may update it.
"""

from __future__ import annotations

import re
from enum import Enum

# Reuse the EXISTING canonical cue sets rather than duplicating them:
#  * L10 acknowledgement and Phase-5 conversation-recall cues (builtin surface)
#  * Phase-4/C7 bounded reference + repeat recognition (reference resolution)
from atlas.conversation.builtin_response import (
    _CONVERSATION_RECALL_ASSISTANT_RE,
    _CONVERSATION_RECALL_FINDING_RE,
    _CONVERSATION_RECALL_TOPIC_RE,
    _CONVERSATION_RECALL_USER_RE,
)
from atlas.conversation.reference_resolution import is_repeat_request


class TurnRole(str, Enum):
    """Bounded conversational role of one turn."""

    NEW_OBJECTIVE = "new_objective"
    FOLLOW_UP = "follow_up"
    CORRECTION = "correction"
    CLARIFICATION = "clarification"
    REFERENCE = "reference"
    RECALL = "recall"
    ACKNOWLEDGEMENT = "acknowledgement"
    META_CONVERSATION = "meta_conversation"
    CONTINUATION = "continuation"


#: Bounded correction/amendment markers used by the existing Correction record
#: (superseded-reading evidence). D1's set plus the explicit ``correction``
#: marker (Evidence-Driven Improvement 2), so an explicit "Correction: ..."
#: turn is recorded AND classified as a correction rather than a new objective.
CORRECTION_MARKERS: tuple[str, ...] = (
    "actually",
    "i meant",
    "i mean",
    "no, i meant",
    "i didn't mean",
    "i did not mean",
    "not that",
    "forget the previous",
    "forget that",
    "let me rephrase",
    "to clarify",
    "instead",
    "correction",
    "rather",
)

#: Explicit REPLACEMENT cues: the turn replaces the active reading with a new
#: subject. A correction changes the active interpretation.
REPLACEMENT_MARKERS: tuple[str, ...] = (
    "actually",
    "i meant",
    "no, i meant",
    "i didn't mean",
    "i did not mean",
    "not that",
    "forget the previous",
    "forget that",
    "let me rephrase",
    "correction",
    "instead",
)

#: REFINEMENT cues: the turn refines/qualifies the active context. A
#: clarification preserves the active objective (it does not replace it).
REFINEMENT_MARKERS: tuple[str, ...] = (
    "i mean",
    "to clarify",
    "what i meant",
    "what i mean",
    "i was asking about",
    "i am asking about",
    "i'm asking about",
    "specifically",
    "more specifically",
    "to be more specific",
)

#: Role-level acknowledgement surface. Deliberately slightly wider than the
#: L10 rendering cue (e.g. "okay, understood.") because it only decides that the
#: active objective must be preserved — it does not change any rendering.
_ACK_ROLE_RE = re.compile(
    r"^\s*(?:"
    r"thanks(?:\s+(?:a lot|so much|very much))?|"
    r"thank you(?:\s+very much)?|many thanks|cheers|"
    r"ok(?:ay)?|got it|understood|noted|alright|all right|fine|"
    r"sounds good|makes sense|perfect|great|cool|nice one|brilliant"
    r")"
    r"(?:\s*[,\-]?\s*(?:that helps|that'?s helpful|thanks|understood|"
    r"makes sense|got it|noted|ok(?:ay)?))*"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

#: Whole-turn continuation requests.
_CONTINUATION_RE = re.compile(
    r"^\s*(?:can you\s+|please\s+|let'?s\s+)?"
    r"(?:continue|go on|keep going|carry on)"
    r"(?:\s+with\s+(?:that|this|it|the\s+[a-z0-9_-]+))?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

#: Bounded demonstrative/pronoun reference forms. Anchored to the WHOLE turn so
#: a genuine instructed request that merely mentions "it"/"that" ("Research X
#: and summarize it") keeps its new-objective status.
_DEMONSTRATIVE_REF_RE = re.compile(
    r"^\s*what\s+about\b.*$"
    r"|^\s*(?:tell me\s+)?(?:more\s+)?(?:about|regarding)\s+"
    r"(?:that|this|it|its)\b.*$"
    r"|^\s*(?:explain|clarify|restate|summarize)\s+(?:that|this|it)"
    r"(?:\s+part)?(?:\s+again)?\s*[.!?]*\s*$"
    r"|^\s*(?:that|this|its)\s+(?:latest|last|previous|next|status|result)\b.*$",
    re.IGNORECASE,
)

#: Bounded follow-up forms that continue the active work.
_FOLLOW_UP_RE = re.compile(
    r"^\s*(?:and\s+)?what\s+did\s+(?:you|we)\s+"
    r"(?:find|learn|discover|conclude)\b.*$"
    r"|^\s*(?:and\s+)?what\s+have\s+you\b.*\b(?:found|learned|discovered)\b.*$"
    r"|^\s*how\s+did\s+(?:that|it)\s+go\s*[.!?]*\s*$",
    re.IGNORECASE,
)

#: Bounded meta-conversation (the turn is about Atlas/this conversation itself,
#: not about doing work).
_META_RE = re.compile(
    r"^\s*(?:explain\s+|tell me\s+)?how\s+(?:do\s+)?you\s+work\b"
    r"|\bwhat\s+can\s+you\s+do\b"
    r"|\bwho\s+are\s+you\b"
    r"|\bwhat\s+are\s+you\b"
    r"|\bhow\s+are\s+you\b",
    re.IGNORECASE,
)

_RECALL_RES: tuple[re.Pattern[str], ...] = (
    _CONVERSATION_RECALL_USER_RE,
    _CONVERSATION_RECALL_ASSISTANT_RE,
    _CONVERSATION_RECALL_TOPIC_RE,
    _CONVERSATION_RECALL_FINDING_RE,
)

#: G1 — the correction-subject extractor is owned by the shared semantic layer
#: and re-exported here so existing importers keep working (one implementation).
from atlas.conversation.semantic_frame import (  # noqa: E402  (re-export)
    corrected_subject,
)


def _has_marker(lowered: str, markers: tuple[str, ...]) -> bool:
    return any(marker in lowered for marker in markers)


def detect_turn_role(
    text: str,
    *,
    has_prior_objective: bool = False,
) -> TurnRole:
    """Classify one turn's bounded conversational role. Deterministic.

    G1 — the bounded roles are now derived from the shared semantic frame
    (:mod:`atlas.conversation.semantic_frame`), whose word-CLASS rules generalize
    over ordinary synonymy and inflection instead of enumerating phrases. The
    mapping preserves the Improvement-2 contract exactly:

      * only ``NEW_OBJECTIVE`` and ``CORRECTION`` may replace the active
        objective; every other role preserves it;
      * a recognition is only made from bounded evidence — anything unclear
        falls back to the safe default (a new objective) or to the bounded
        cue-based roles below.

    The previous cue sets remain as a fallback for roles the frame declines, so
    no previously recognized role is lost.
    """
    from atlas.conversation import semantic_frame as _frame

    if not isinstance(text, str) or not text.strip():
        return TurnRole.NEW_OBJECTIVE
    frame = _frame.interpret(
        text, has_prior_objective=bool(has_prior_objective)
    )
    mapping = {
        _frame.SemanticRole.ACKNOWLEDGEMENT: TurnRole.ACKNOWLEDGEMENT,
        _frame.SemanticRole.RECALL: TurnRole.RECALL,
        _frame.SemanticRole.CONTINUATION: TurnRole.CONTINUATION,
        _frame.SemanticRole.CORRECTION: TurnRole.CORRECTION,
        _frame.SemanticRole.CLARIFICATION: TurnRole.CLARIFICATION,
        _frame.SemanticRole.FOLLOW_UP: TurnRole.FOLLOW_UP,
        _frame.SemanticRole.REFERENCE: TurnRole.REFERENCE,
        _frame.SemanticRole.META_CONVERSATION: TurnRole.META_CONVERSATION,
        # A greeting/casual turn is not a new objective: preserve the objective.
        _frame.SemanticRole.CASUAL: TurnRole.META_CONVERSATION,
    }
    mapped = mapping.get(frame.role)
    if mapped is not None:
        return mapped
    return _detect_turn_role_by_cues(text, has_prior_objective)


def _detect_turn_role_by_cues(
    text: str, has_prior_objective: bool
) -> TurnRole:
    """The bounded cue-based role detection (pre-G1 fallback, unchanged)."""
    stripped = text.strip()
    lowered = stripped.lower()
    if _ACK_ROLE_RE.match(stripped):
        return TurnRole.ACKNOWLEDGEMENT
    if any(pattern.search(lowered) for pattern in _RECALL_RES):
        return TurnRole.RECALL
    if _CONTINUATION_RE.match(stripped):
        return TurnRole.CONTINUATION
    if has_prior_objective and _has_marker(lowered, REPLACEMENT_MARKERS):
        return TurnRole.CORRECTION
    if has_prior_objective and _has_marker(lowered, REFINEMENT_MARKERS):
        return TurnRole.CLARIFICATION
    if is_repeat_request(stripped) or _DEMONSTRATIVE_REF_RE.match(stripped):
        return TurnRole.REFERENCE
    if _FOLLOW_UP_RE.match(stripped):
        return TurnRole.FOLLOW_UP
    if _META_RE.search(lowered):
        return TurnRole.META_CONVERSATION
    return TurnRole.NEW_OBJECTIVE
