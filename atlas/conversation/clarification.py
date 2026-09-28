"""Atlas Conversation — bounded pending clarification (Step 9).

A small, deterministic representation of a *genuine* ambiguity Atlas refused to
guess through: what was ambiguous, the bounded candidate interpretations it
could see, and the turn that raised the question. It exists so the user's
follow-up clarification can be resolved deterministically and the correct
existing route can be resumed — instead of the reply falling to the generic
floor or being reinterpreted as an unrelated request.

It is deliberately NOT a general ambiguity/clarification framework, not NLU, and
not a planner: the candidate set is always produced by an existing deterministic
surface (reference resolution, the Step 8 world state, or the semantic frame),
and this module only preserves and matches it.

Design contract (mirrors :mod:`atlas.conversation.world_state`):

  * immutable frozen value object — every update produces a new value;
  * bounded — at most :data:`MAX_CLARIFICATION_CANDIDATES` candidates, every
    string length-capped;
  * deterministic — no clock, no randomness, no I/O, no model, no network;
  * authority-free — facts only. Requesting or resolving a clarification never
    executes, authorizes, approves, promotes, or mutates governed state.

Candidate matching is bounded normalized equality/containment, distinctive-token
overlap, or an explicit ordinal ("the second one"). It is never fuzzy or
semantic, and it never invents a candidate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

#: Upper bound on retained clarification candidates.
MAX_CLARIFICATION_CANDIDATES: int = 6

#: Bound applied to the bounded question text.
_MAX_QUESTION_CHARS: int = 300

#: Bound applied to each candidate label.
_MAX_CANDIDATE_CHARS: int = 200

#: Bound applied to the retained originating turn.
_MAX_TEXT_CHARS: int = 300

#: Bounded clarification kinds.
KIND_REFERENCE: str = "reference"
KIND_TOPIC: str = "topic"
KIND_SUBJECT: str = "subject"

_KINDS: frozenset[str] = frozenset({KIND_REFERENCE, KIND_TOPIC, KIND_SUBJECT})

#: Explicit ordinal selection vocabulary (1-based words -> 0-based index).
_ORDINAL_INDEX: dict[str, int] = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "sixth": 5,
    "6th": 5,
}
_ORDINAL_LAST: str = "last"

#: Bounded grammatical wrappers and generic nouns that carry no identity, so a
#: "the one" / "the thing" style reply never selects a candidate on its own.
_GENERIC_TOKENS: frozenset[str] = frozenset(
    {
        "the", "this", "that", "these", "those", "my", "your", "our", "their",
        "its", "it", "a", "an", "and", "or", "of", "for", "with", "to", "in",
        "on", "at", "from", "as", "about", "please", "one", "ones", "thing",
        "things", "item", "items", "topic", "topics", "subject", "subjects",
        "task", "tasks", "result", "results", "investigation", "investigations",
        "answer", "answers", "research", "study", "work",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")


def _key(text: Any) -> str:
    """Case/punctuation/whitespace-insensitive comparison key."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _bounded(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _bounded_candidates(values: Any) -> tuple[str, ...]:
    """Return the bounded, de-duplicated candidate labels."""
    if not isinstance(values, (list, tuple)):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _bounded(value, _MAX_CANDIDATE_CHARS)
        key = _key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= MAX_CLARIFICATION_CANDIDATES:
            break
    return tuple(out)


def _distinctive_tokens(text: Any) -> frozenset[str]:
    """Identity-bearing tokens of a phrase (generic wrappers removed)."""
    return frozenset(
        token
        for token in _TOKEN_RE.findall(str(text or "").lower())
        if len(token) > 2 and token not in _GENERIC_TOKENS
    )


@dataclass(frozen=True, slots=True)
class PendingClarification:
    """A bounded, authority-free record of an outstanding clarification.

    ``kind`` is one of :data:`KIND_REFERENCE` / :data:`KIND_TOPIC` /
    :data:`KIND_SUBJECT`, ``question`` the bounded question that was asked,
    ``candidates`` the bounded candidate interpretations (may be empty when no
    safe candidate exists), and ``original_text`` the turn that raised the
    question.
    """

    kind: str
    question: str
    candidates: tuple[str, ...] = ()
    original_text: str = ""
    turn_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "kind": self.kind,
            "question": self.question,
            "candidates": list(self.candidates),
            "original_text": self.original_text,
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["PendingClarification"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        kind = _bounded(data.get("kind"), 32) or KIND_SUBJECT
        if kind not in _KINDS:
            kind = KIND_SUBJECT
        question = _bounded(data.get("question"), _MAX_QUESTION_CHARS)
        if not question:
            return None
        turn_id = data.get("turn_id")
        return cls(
            kind=kind,
            question=question,
            candidates=_bounded_candidates(data.get("candidates")),
            original_text=_bounded(data.get("original_text"), _MAX_TEXT_CHARS),
            turn_id=turn_id if isinstance(turn_id, str) else "",
        )


def candidate_matches(text: Any, candidates: Any) -> tuple[str, ...]:
    """Return the bounded candidates that ``text`` deterministically selects.

    Bounded rules, in order:

      1. normalized equality/containment against the candidate label;
      2. an explicit ordinal selection ("the second one" -> candidates[1],
         "the last one" -> the final candidate) when an ordinal word is present;
      3. distinctive-token containment (the reply's identity-bearing tokens are
         a subset of a candidate's), so "the handling one" selects the candidate
         that names "handling" and nothing else.

    Returns ``()`` when nothing (or more than one thing) is selected, so the
    caller never guesses. Never fuzzy, never semantic, never invents a value.
    """
    bounded = _bounded_candidates(candidates)
    if not bounded or not isinstance(text, str) or not text.strip():
        return ()
    query_key = _key(text)

    # 1. normalized equality / containment.
    hits: list[str] = []
    for candidate in bounded:
        candidate_key = _key(candidate)
        if not candidate_key:
            continue
        if (
            query_key == candidate_key
            or query_key in candidate_key
            or candidate_key in query_key
        ):
            hits.append(candidate)
    if hits:
        return tuple(hits)

    # 2. explicit ordinal selection.
    for token in _TOKEN_RE.findall(text.lower()):
        if token == _ORDINAL_LAST:
            return (bounded[-1],)
        index = _ORDINAL_INDEX.get(token)
        if index is not None and index < len(bounded):
            return (bounded[index],)

    # 3. distinctive-token containment.
    query_tokens = _distinctive_tokens(text)
    if query_tokens:
        for candidate in bounded:
            if query_tokens <= _distinctive_tokens(candidate):
                hits.append(candidate)
    return tuple(hits)


def build_question(kind: str, candidates: Any, fallback: str) -> str:
    """Return a bounded clarification question that lists known candidates.

    Only the candidates provided by an existing deterministic surface are
    listed; nothing is invented. When no candidate is known the ``fallback``
    (a request for the missing information) is used verbatim.
    """
    question = _bounded(fallback, _MAX_QUESTION_CHARS)
    bounded = _bounded_candidates(candidates)
    if not bounded:
        return question
    lines = [question]
    lines.extend(f"- {candidate}" for candidate in bounded)
    return "\n".join(lines)[:_MAX_QUESTION_CHARS]
