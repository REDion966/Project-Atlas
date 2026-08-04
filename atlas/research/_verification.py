"""Deterministic confidence and similarity helpers (Phase 17.4–17.5).

Pure functions shared between the knowledge extractor's provisional
confidence assignment and the claim verifier's confidence scoring.
"""

import re
from difflib import SequenceMatcher

_ALPHA_RE: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


def norm_alpha(text: str) -> str:
    """Canonical comparison form: lowercased alphanumerics only."""
    return _ALPHA_RE.sub("", text.lower())


def confidence_from_evidence(
    supporting_count: int,
    contradicting_count: int,
    min_score: float = 0.0,
    max_available: float = 0.95,
) -> float:
    """Deterministic confidence from raw evidence tallies.

    Semantics (monotonically ordered for scoring):
      - base 0.5
      - +0.15 when no contradicting evidence was found
      - +0.1 per supporting source, capped at +0.3
      - capped by ``max_available`` (0.95)

    So a single supporting source scores 0.75, two 0.85, three or more
    0.95, and a contested claim (1 support + 1 contradiction) 0.6.
    """
    total: int = supporting_count + contradicting_count
    if total == 0:
        return 0.0
    score: float = 0.5
    if contradicting_count == 0:
        score += 0.15
    score += min(supporting_count, 3) * 0.1
    return round(max(min_score, min(score, max_available)), 4)


def similarity_ratio(first: str, second: str) -> float:
    """SequenceMatcher-based text similarity in ``[0, 1]`` via ratio()."""
    if not first and not second:
        return 1.0
    if not first or not second:
        return 0.0
    return SequenceMatcher(None, first, second).ratio()
