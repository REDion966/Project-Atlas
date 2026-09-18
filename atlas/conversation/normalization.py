"""Atlas Conversation — Shared deterministic surface normalization (L2.2).

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
