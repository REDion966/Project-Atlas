"""Deterministic extraction internals (Phase 17.4).

Pure functions used by :mod:`atlas.research.extractor`: deterministic text
chunking, claim normalization, duplicate removal, claim-id generation, and
provisional confidence. No AI, no infrastructure.
"""

import hashlib
import re

from atlas.research._text import source_text
from atlas.research._verification import norm_alpha
from atlas.research.models import ResearchSource

_SENTENCE_SPLIT_RE: re.Pattern[str] = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE: re.Pattern[str] = re.compile(r"\s+")

# Above this many characters a claim statement is treated as malformed.
MAX_CLAIM_LENGTH: int = 500

# Provisional confidence is deliberately capped below any "verified" level;
# verification (Phase 17.5) is what raises confidence.
MAX_PROVISIONAL_CONFIDENCE: float = 0.8


def chunk_text(text: str, chunk_size: int) -> list[str]:
    """Deterministically split text into sentence-based chunks.

    Chunks are built sentence-by-sentence; a chunk is sealed once the next
    sentence would push it past ``chunk_size`` characters. Over-long single
    sentences become their own chunk. Boundaries depend only on the input.
    """
    if not text:
        return []
    sentences: list[str] = [
        s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()
    ]
    chunks: list[str] = []
    current: list[str] = []
    current_length: int = 0
    for sentence in sentences:
        if current and current_length + len(sentence) + 1 > chunk_size:
            chunks.append(" ".join(current))
            current = []
            current_length = 0
        if len(sentence) > chunk_size:
            if current:
                chunks.append(" ".join(current))
                current = []
                current_length = 0
            chunks.append(sentence)
        else:
            current.append(sentence)
            current_length += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def normalize_claim_statement(raw: str) -> str:
    """Collapse whitespace and strip surrounding punctuation from a claim."""
    return _WHITESPACE_RE.sub(" ", raw.strip()).strip(" .,;:!?\"'()[]")


def deduplicate_statements(statements: list[str]) -> list[str]:
    """Remove duplicates by canonical alphanumeric key, keeping first order."""
    seen: set[str] = set()
    keep: list[str] = []
    for statement in statements:
        key = norm_alpha(statement)
        if key not in seen:
            seen.add(key)
            keep.append(statement)
    return keep


def claim_id_for(statement: str) -> str:
    """Deterministic stable claim id: sha256 of the canonical statement."""
    digest: str = hashlib.sha256(norm_alpha(statement).encode("utf-8")).hexdigest()
    return f"claim:{digest[:16]}"


def provisional_confidence(statement: str, source: ResearchSource) -> float:
    """Deterministic provisional confidence in ``[0, MAX_PROVISIONAL_CONFIDENCE]``.

    Heuristic, capped well below verification-level confidence. Pure —
    callers can always compute it for any claim.

    - base 0.5
    - +0.2 if the claim text appears in the source text
    - +0.1 if the claim length is in the sane band ``[20, MAX_CLAIM_LENGTH]``
    """
    normalized: str = normalize_claim_statement(statement)
    if not normalized:
        return 0.0
    confidence: float = 0.5
    text: str = source_text(source)
    key: str = norm_alpha(normalized)
    if key and key in norm_alpha(text):
        confidence += 0.2
    if 20 <= len(normalized) <= MAX_CLAIM_LENGTH:
        confidence += 0.1
    return round(min(confidence, MAX_PROVISIONAL_CONFIDENCE), 4)
