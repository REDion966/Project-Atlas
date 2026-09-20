"""Atlas Conversation — Shared deterministic surface normalization (L2.2) +
bounded surface canonicalization (Phase 2.2).

One authoritative implementation of the surface-whitespace rule used by the
conversation layer's surface-form matching (``TaskIntake``, ``BuiltinResponse
Service``, ``ConversationReferenceResolver``).

Semantics (exactly):
  * collapse every run of whitespace to a single ASCII space;
  * trim leading and trailing whitespace.

Nothing else changes: case is preserved (callers lower-case separately),
punctuation and all non-whitespace characters are untouched, and there is no
tokenization, lexical, or semantic processing. This is a matching/preprocessing
concern only — stored raw text is never replaced.

Deterministic, local, model-free: no clock, no randomness, no I/O.
"""

from __future__ import annotations

import re

#: A run of whitespace (the rule ``TaskIntake`` already applied).
_WHITESPACE_RUN_RE = re.compile(r"\s+")

#: Replacement for a run of whitespace.
_SINGLE_SPACE = " "


def collapse_whitespace(text: str) -> str:
    """Return ``text`` with whitespace runs collapsed and edges trimmed.

    Non-string input yields an empty string, preserving the existing type
    expectation of the callers (which already treat missing/non-string input
    as empty). It never coerces arbitrary objects to text.
    """
    if not isinstance(text, str):
        return ""
    return _WHITESPACE_RUN_RE.sub(_SINGLE_SPACE, text).strip()


# ---------------------------------------------------------------------------
# Bounded surface canonicalization (Phase 2.2).
#
# Addresses the validated lexical/surface-form brittleness: ordinary equivalent
# phrasings fail when they carry no recognized cue token. This layer canonicalizes
# a SMALL, explicitly bounded set of ordinary surface forms into vocabulary the
# existing deterministic pipeline already understands.
#
# Properties (all mandatory):
#   * pure and deterministic — no clock, randomness, I/O, network, or model;
#   * standard-library only; accepts and returns ``str``;
#   * extends :func:`collapse_whitespace` (never replaces it) — whitespace is
#     normalized first and the result is whitespace-normalized again;
#   * bounded — a hard input-size cap, a fixed frame list, and a fixed anchored
#     equivalence table; there is no adaptive/synonym learning;
#   * conservative — unrecognized text is preserved verbatim (only whitespace
#     changes); equivalences are anchored to the WHOLE request, so they cannot
#     overmatch inside a longer sentence; unmapped text cannot become a command;
#   * normalizing a request grants no authority — it only selects vocabulary that
#     the existing layer already recognizes, and it never changes which governed
#     handler a governed cue selects.
# ---------------------------------------------------------------------------

#: Inputs longer than this are returned unchanged (fail-safe; never rewrite big text).
MAX_SURFACE_INPUT_CHARS: int = 2000

#: Hard cap on the equivalence table size (bounded; audited, never grown at runtime).
MAX_EQUIVALENCE_ENTRIES: int = 64

#: Hard cap on each equivalence phrase length.
MAX_EQUIVALENCE_PHRASE_CHARS: int = 80

#: Leading politeness/modal request frames, longest first. At most ONE leading
#: frame is removed, and only when a non-empty remainder follows.
_FRAME_PREFIXES: tuple[str, ...] = (
    "can you please",
    "could you please",
    "would you please",
    "i would like to",
    "i'd like to",
    "i would like",
    "i'd like",
    "i want to",
    "i need to",
    "can you",
    "could you",
    "would you",
    "will you",
    "please",
)

#: Anchored whole-request equivalences -> existing canonical cue vocabulary.
#: Keys are already whitespace-normalized and lower-case. Values are existing
#: canonical phrases that the builtin intent chain already recognizes.
_SURFACE_EQUIVALENCES: tuple[tuple[str, str], ...] = (
    ("list the things atlas can do", "what capabilities do you have"),
    ("list what atlas can do", "what capabilities do you have"),
    ("tell me what's available", "what capabilities do you have"),
    ("tell me what is available", "what capabilities do you have"),
    ("what's available", "what capabilities do you have"),
    ("what is available", "what capabilities do you have"),
    ("what can atlas do", "what capabilities do you have"),
    ("what do you do", "what capabilities do you have"),
)

#: Boundary punctuation trimmed when comparing the whole request to a key.
_EQUIVALENCE_TRIM = " \t.!?,;:\"'"


def _strip_leading_frame(text: str) -> str:
    """Remove at most one bounded leading politeness/modal frame, or return text."""
    lowered = text.lower()
    for frame in _FRAME_PREFIXES:
        if lowered == frame:
            return text
        if lowered.startswith(frame + " "):
            remainder = text[len(frame):].lstrip()
            if remainder:
                return remainder
    return text


def _equivalence_key(text: str) -> str:
    """Return the whole-request comparison key (lower-case, boundary-trimmed)."""
    return text.lower().strip(_EQUIVALENCE_TRIM)


def _apply_equivalence(text: str) -> str:
    """Map a whole-request equivalence to its canonical form, or return text."""
    key = _equivalence_key(text)
    for variant, canonical in _SURFACE_EQUIVALENCES:
        if key == variant:
            return canonical
    return text


def canonicalize_surface(text: str) -> str:
    """Canonicalize an ordinary surface form onto existing Atlas cue vocabulary.

    Deterministic, bounded, standard-library-only. Extends
    :func:`collapse_whitespace`: whitespace is collapsed first, then at most one
    bounded leading politeness/modal frame is removed and a small anchored
    equivalence table maps an ordinary equivalent whole request onto canonical
    vocabulary the existing deterministic pipeline already understands.

    Unrecognized text is returned with whitespace normalized only — nothing is
    invented, dropped, or rewritten beyond the explicit table. Intended for
    *matching*; it creates no new intent and grants no execution authority.
    """
    collapsed = collapse_whitespace(text)
    if not collapsed:
        return ""
    if len(collapsed) > MAX_SURFACE_INPUT_CHARS:
        return collapsed
    result = _strip_leading_frame(collapsed)
    result = _apply_equivalence(result)
    return collapse_whitespace(result)
