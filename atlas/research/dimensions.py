"""Atlas Research — Requested Dimensions & Coverage (NLU-3).

Bounded, deterministic representation of the *requested aspects* of a research
objective, and a token-coverage test of whether acquired evidence supports each
one.

It solves the NLU-2 gap where a multi-dimension research request was reported
complete on subject relevance alone ("subject_relevant == complete"). It
deliberately does NOT try to understand arbitrary research: it recognizes an
EXPLICITLY ENUMERATED aspect list and checks each named aspect against the
evidence by bounded token coverage.

Design contract:
  * Pure: standard library only (reuses :mod:`atlas.research._text`). No AI, no
    network, no storage, no kernel, no execution, no authorization surface.
  * Deterministic: identical inputs yield identical output.
  * Bounded: at most ``MAX_DIMENSIONS`` dimensions, each at most
    ``MAX_DIMENSION_WORDS`` words.
  * Conservative: dimensions are only recognized when the request EXPLICITLY
    enumerates two or more aspects. A single-aspect request yields no
    dimensions, so its behaviour is unchanged (NLU-2 relevance decides).
  * Token-based (explicit limitation): a dimension is supported only when ALL
    of its significant tokens appear in the evidence. This is a bounded
    lexical check, not semantic understanding — a dimension phrased with a
    synonym of the evidence text will not be matched.
"""

from __future__ import annotations

import re

from atlas.research._text import normalize_whitespace, significant_tokens

#: Upper bound on requested dimensions retained.
MAX_DIMENSIONS: int = 8

#: Upper bound on words per dimension phrase. Kept small so an ordinary
#: comma-heavy sentence is not mistaken for an explicit aspect list.
MAX_DIMENSION_WORDS: int = 4

#: A fragment beginning with a question word or auxiliary is prose, not an
#: aspect name; it is skipped.
_NON_NOUN_LEAD_RE = re.compile(
    r"^(?:how|what|why|when|where|which|who|whom|whose|is|are|was|were|do"
    r"|does|did|should|would|could|can|will|may|might|must)\b",
    re.IGNORECASE,
)

#: Bounded research-request cue. Dimensions are only extracted from a request
#: that explicitly asks for research.
_RESEARCH_CUE_RE = re.compile(
    r"\b(?:research|investigate|find|search|look\s+up|lookup|acquire)\b",
    re.IGNORECASE,
)

#: The aspect list follows the research cue + an optional article ("Research
#: the X, Y, and Z of ..."). Anchoring the enumeration here prevents an ordinary
#: comma-heavy sentence with no research cue from being read as an aspect list.
_CUE_ANCHOR_RE = re.compile(
    r"\b(?:research|investigate|find|search|look\s+up|lookup|acquire)\b"
    r"\s+(?:the\s+|a\s+|an\s+)?",
    re.IGNORECASE,
)

#: Bounded markers that introduce an explicit aspect list ("... including A,
#: B, and C"). When present, only the text AFTER the marker is the list.
_LIST_MARKERS: tuple[str, ...] = ("including", "such as")

#: Bounded leading research-request frames stripped from a fragment.
_LEADING_FRAME_RE = re.compile(
    r"^\s*(?:research|investigate|acquire|find|search|look\s+up|lookup|latest"
    r"|including|such\s+as|and|the|a|an|its|their|this|that|these|those)\s+",
    re.IGNORECASE,
)

#: Trailing subject/purpose clause stripped from a fragment ("... of the X",
#: "... for a review").
_TRAILING_CLAUSE_RE = re.compile(r"\s+(?:of|for)\s+.*$", re.IGNORECASE)

#: NLU-5 — a leading possessive descriptor before the aspect ("the Samsung
#: phone's camera system" -> "camera system"), so a descriptive reference does
#: not become part of the dimension name.
_POSSESSIVE_LEAD_RE = re.compile(r"^(?:\w+\s+){0,2}\w+'s\s+", re.IGNORECASE)

#: Fragment splitter: commas, semicolons, and the conjunction "and".
_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b)\s*", re.IGNORECASE)

#: Trailing punctuation trimmed from a dimension phrase.
_TRIM = " \t.!?:;,\"'"


def extract_dimensions(question: str) -> tuple[str, ...]:
    """Return the explicitly enumerated requested dimensions, or ``()``.

    Recognizes only an explicit aspect list (two or more comma/``and``
    separated fragments). A single-aspect request returns ``()`` so its
    behaviour is unchanged.
    """
    if not isinstance(question, str) or not question.strip():
        return ()

    text = normalize_whitespace(question)
    lowered = text.lower()
    # Dimensions are only recognized for an explicit research request.
    if _RESEARCH_CUE_RE.search(lowered) is None:
        return ()

    marker_index = -1
    for marker in _LIST_MARKERS:
        index = lowered.find(marker)
        if index >= 0 and (marker_index < 0 or index < marker_index):
            marker_index = index
            marker_length = len(marker)
    if marker_index >= 0:
        text = text[marker_index + marker_length:]
    else:
        anchor = _CUE_ANCHOR_RE.search(text)
        text = text[anchor.end():] if anchor is not None else text

    fragments: list[str] = []
    seen: set[str] = set()
    for raw in _SPLIT_RE.split(text):
        fragment = normalize_whitespace(raw)
        # Strip bounded leading frames iteratively ("and the camera system").
        while True:
            stripped = _LEADING_FRAME_RE.sub("", fragment, count=1)
            if stripped == fragment:
                break
            fragment = stripped
        fragment = _TRAILING_CLAUSE_RE.sub("", fragment).strip(_TRIM)
        fragment = _POSSESSIVE_LEAD_RE.sub("", fragment).strip(_TRIM)
        if not fragment:
            continue
        if len(fragment.split()) > MAX_DIMENSION_WORDS:
            continue
        if _NON_NOUN_LEAD_RE.match(fragment):
            continue
        key = fragment.lower()
        if key in seen:
            continue
        seen.add(key)
        fragments.append(fragment)
        if len(fragments) >= MAX_DIMENSIONS:
            break

    # An explicit enumeration requires at least two aspects.
    if len(fragments) < 2:
        return ()
    return tuple(fragments)


def dimension_coverage(
    dimensions: tuple[str, ...],
    evidence_texts,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split ``dimensions`` into ``(supported, unsupported)``.

    A dimension is supported only when ALL of its significant tokens appear in
    the evidence (bounded lexical coverage). A dimension with no significant
    tokens cannot be confirmed and is reported unsupported.
    """
    evidence: set[str] = set()
    for text in evidence_texts or ():
        if isinstance(text, str) and text:
            evidence |= significant_tokens(text)

    supported: list[str] = []
    unsupported: list[str] = []
    for dimension in dimensions:
        tokens = significant_tokens(dimension)
        if tokens and tokens <= evidence:
            supported.append(dimension)
        else:
            unsupported.append(dimension)
    return tuple(supported), tuple(unsupported)
