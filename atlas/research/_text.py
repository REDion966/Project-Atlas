"""Shared deterministic text utilities for the research layer (Phase 17.4–17.5).

Pure, locale-independent helpers used by the knowledge extractor and the
claim verifier. No AI, no infrastructure.
"""

import re
from typing import Iterable

from atlas.research.models import ResearchSource

_WORD_RE: re.Pattern[str] = re.compile(r"[a-zA-Z0-9_]+")
_SENTENCE_SPLIT_RE: re.Pattern[str] = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE: re.Pattern[str] = re.compile(r"\s+")

STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "of", "in", "on", "at", "to", "for", "with",
        "and", "or", "by", "is", "are", "was", "were", "be", "been",
        "how", "what", "when", "who", "which", "does", "do", "can",
        "we", "us", "our", "should", "must", "its", "it", "this", "that",
    }
)


def source_text(source: ResearchSource) -> str:
    """Extract the normalized text of a research source.

    Works for both :class:`~atlas.research.models.ResearchSource` (no text
    attribute → empty) and :class:`~atlas.research.models.SourceProfile`
    (carries the normalized text). Never raises.
    """
    text = getattr(source, "text", None)
    if isinstance(text, str):
        return text
    return ""


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs into single spaces and strip."""
    return _WHITESPACE_RE.sub(" ", text.strip())


def split_sentences(text: str) -> list[str]:
    """Deterministically split text into non-empty sentences."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def significant_tokens(text: str) -> set[str]:
    """Lowercased, non-stopword, 3+ character word tokens."""
    words: list[str] = _WORD_RE.findall(text.lower())
    return {word for word in words if word not in STOPWORDS and len(word) > 2}
