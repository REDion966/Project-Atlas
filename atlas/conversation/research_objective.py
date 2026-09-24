"""Atlas Conversation — Research Objective Completeness (NLU-2).

A small, pure, deterministic check for whether a research request carries
enough subject information to be fulfilled WITHOUT guessing.

Atlas must ask a bounded clarification when a materially necessary part of the
research subject is missing — an unspecified generic product ("a phone"), an
unspecified comparison set ("three flagship phones") — and must NOT ask when
the request is sufficiently specified (a named product, or a broad general
domain such as "smartphone cameras").

It never invents an entity, never chooses a product/comparison set, and never
executes anything. It only returns a bounded clarification question, or None.

Pure: standard library only, no AI, no network, no storage, no clock.
"""

from __future__ import annotations

import re

#: Bounded research-shape cue vocabulary (mirrors the existing research cues
#: used by the orchestration target resolver). A gap is only reported for a
#: research-shaped request.
_CUE: str = r"(?:research|investigate|acquire|find|search|look\s+up|lookup|latest)"

_RESEARCH_CUE_RE = re.compile(rf"\b{_CUE}\b")

#: Generic product nouns eligible for the "unspecified subject" patterns.
_GENERIC_NOUNS: str = (
    r"phone|smartphone|mobile|camera|product|device|gadget|laptop|notebook"
    r"|tablet|monitor|display|television|tv|appliance|headphone|earbud|watch"
    r"|console|drone|printer|router|keyboard|mouse|speaker|model"
)

#: Bounded optional qualifiers allowed between a determiner/count and the noun.
_QUALIFIERS: str = (
    r"(?:\w+\s+){0,3}?"
)

#: Indefinite singular subject OF the research request: "research a phone",
#: "find an affordable flagship phone". Anchored to the research cue so a
#: generic singular inside a broader question ("what matters when reviewing a
#: smartphone camera") is NOT treated as a missing subject.
_INDEFINITE_RE = re.compile(
    rf"\b{_CUE}\b\s+(?:a|an|some)\s+{_QUALIFIERS}(?:{_GENERIC_NOUNS})\b"
)

#: Demonstrative subject of the research request: "research this product".
_DEMONSTRATIVE_RE = re.compile(
    rf"\b{_CUE}\b\s+(?:this|that|these|those)\s+{_QUALIFIERS}(?:{_GENERIC_NOUNS})\b"
)

#: Unresolved possessive subject: "research its camera system". Only treated as
#: a gap when the existing reference machinery did NOT bind a referent for the
#: turn (see ``reference_resolved``), so a genuinely resolved follow-up is not
#: blocked.
_POSSESSIVE_RE = re.compile(rf"\b{_CUE}\b\s+(?:its|their)\b")

#: Unspecified comparison set: "three flagship phones", "2 cameras".
_COUNT_RE = re.compile(
    rf"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d{{1,2}})\s+"
    rf"{_QUALIFIERS}(?:{_GENERIC_NOUNS})s\b"
)

#: A likely concrete named entity: two or more consecutive capitalised words
#: (e.g. "Samsung Galaxy S26 Ultra"). Its presence means the subject is
#: specified enough that no clarification is needed.
_NAMED_ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)+")

#: Bounded clarification questions (no fabrication of the missing value).
_QUESTION_INDEFINITE: str = (
    "Which specific product or model should I research for this?"
)
_QUESTION_COMPARISON: str = "Which specific items should I compare?"


def looks_like_research_request(text: str) -> bool:
    """True when ``text`` carries a bounded research-shape cue."""
    return isinstance(text, str) and _RESEARCH_CUE_RE.search(text.lower()) is not None


def research_subject_gap(text: str, *, reference_resolved: bool = False) -> str | None:
    """Return a bounded clarification question, or None when no gap exists.

    Fail-closed toward NOT asking: a request naming a concrete entity (two or
    more capitalised words, e.g. "Samsung Galaxy S26 Ultra") is treated as
    sufficiently specified; a broad general domain ("smartphone cameras") is
    likewise accepted. Only an unspecified generic singular subject, an
    unresolvable demonstrative/possessive subject, or an unspecified comparison
    set produces a question. ``reference_resolved`` suppresses the possessive
    case when the existing reference machinery already bound a referent.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    if not looks_like_research_request(text):
        return None
    if _NAMED_ENTITY_RE.search(text):
        return None
    lowered = text.lower()
    if _INDEFINITE_RE.search(lowered):
        return _QUESTION_INDEFINITE
    if not reference_resolved and (
        _DEMONSTRATIVE_RE.search(lowered) or _POSSESSIVE_RE.search(lowered)
    ):
        return _QUESTION_INDEFINITE
    if _COUNT_RE.search(lowered):
        return _QUESTION_COMPARISON
    return None
