"""
Atlas Evolution Knowledge — Normalizer — Phase 13.5

Deterministic canonicalization of evolution records into stable
knowledge keys.

The normalizer converts raw evolution data (weaknesses, proposals,
insights) into canonical, repeatable group keys so the consolidator can
aggregate "the same thing" across many occurrences. The same input
always produces the same key — no randomness, no AI, no state.

Pure logic. No infrastructure. No AI. Deterministic.

Phase 13.5 — Persistent Evolution Knowledge Foundation.
"""

import hashlib
import re

from atlas.evolution.models import (
    EvolutionInsight,
    Weakness,
)

# ---------------------------------------------------------------------------
# Canonical area mapping
# ---------------------------------------------------------------------------

_AREA_ALIASES: dict[str, str] = {
    "runtime": "runtime",
    "performance": "runtime",
    "latency": "runtime",
    "response": "runtime",
    "reasoning": "reasoning",
    "analysis": "reasoning",
    "capability": "reasoning",
    "tools": "tools",
    "tool": "tools",
    "executor": "tools",
    "selector": "tools",
    "memory": "memory",
    "retrieval": "memory",
    "ranking": "memory",
    "context": "memory",
    "system_health": "system_health",
    "health": "system_health",
    "stability": "system_health",
    "reliability": "system_health",
    "component": "system_health",
    "planning": "planning",
    "understanding": "understanding",
    "learning": "learning",
    "identity": "identity",
    "goals": "goals",
    "governance": "governance",
    "storage": "storage",
    "persistence": "storage",
}

_CANONICAL_AREAS = frozenset(_AREA_ALIASES.values())


# ---------------------------------------------------------------------------
# Public normalization API
# ---------------------------------------------------------------------------


def normalize_area(area: str) -> str:
    """
    Canonicalize an area string into a stable knowledge area.

    Aliases are mapped to canonical names. Unknown areas are kept as-is
    (lowercased, trimmed) so novel areas remain aggregateable without
    being lost.

    Args:
        area: The raw area string (e.g. "Runtime", "Tools").

    Returns:
        The canonical area name.
    """
    if area is None:
        return "unknown"
    key = area.strip().lower().replace(" ", "_")
    return _AREA_ALIASES.get(key, key or "unknown")


def is_canonical_area(area: str) -> bool:
    """Return True if the area is one of the known canonical areas."""
    return area in _CANONICAL_AREAS


def normalize_strategy(insight: EvolutionInsight) -> str:
    """
    Derive a canonical strategy key from an evolution insight.

    The strategy key is built from the insight's proposal title keywords
    so that insights from similar proposals group together.

    Args:
        insight: The EvolutionInsight to derive a strategy from.

    Returns:
        A stable strategy key string.
    """
    title = insight.proposal_title or ""
    summary = insight.proposal_summary or ""
    text = f"{title} {summary}"
    keywords = _significant_keywords(text)
    if not keywords:
        return "general_improvement"
    return "_".join(keywords[:4])


def normalize_capability(insight: EvolutionInsight) -> str | None:
    """
    Derive a canonical capability name from an evolution insight.

    Scans the insight's proposal title and summary for a known
    capability area (reasoning, planning, tools, memory, understanding,
    learning, etc.). Returns None when no capability is identifiable.

    Args:
        insight: The EvolutionInsight to derive a capability from.

    Returns:
        A canonical capability name, or None.
    """
    text = f"{insight.proposal_title} {insight.proposal_summary}".lower()
    capability_keywords = [
        "reasoning",
        "planning",
        "tool",
        "memory",
        "understanding",
        "learning",
        "identity",
        "world_model",
        "goal",
        "governance",
    ]
    for keyword in capability_keywords:
        if keyword in text:
            return normalize_area(keyword)
    return None


def normalize_weakness_key(weakness: Weakness) -> str:
    """
    Compute a stable knowledge key for a weakness.

    The key is derived from the canonical area and a deterministic
    description template, so the "same" weakness detected at different
    times maps to the same key.

    Args:
        weakness: The Weakness to key.

    Returns:
        A stable hash-based key string.
    """
    area = normalize_area(weakness.area)
    template = _description_template(weakness.description)
    raw = f"{area}|{template}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{area}:{digest}"


def normalize_outcome_key(outcome: str) -> str:
    """
    Canonicalize an outcome classification.

    Maps "success"/"failure"/"partial" and their aliases to the single
    canonical strings used across the knowledge layer.

    Args:
        outcome: The raw outcome string.

    Returns:
        One of "success", "partial", "failure", "inconclusive".
    """
    if outcome is None:
        return "inconclusive"
    key = outcome.strip().lower()
    if key in ("success", "succeeded", "successful"):
        return "success"
    if key in ("failure", "failed", "fail"):
        return "failure"
    if key in ("partial", "partially", "mixed"):
        return "partial"
    return "inconclusive"


def insight_area(insight: EvolutionInsight) -> str:
    """
    Determine the canonical area for an evolution insight.

    Uses keyword matching against the insight's proposal title and
    summary, following the same mapping used by ImprovementPlanner.

    Args:
        insight: The EvolutionInsight to classify.

    Returns:
        A canonical area name.
    """
    text = f"{insight.proposal_title} {insight.proposal_summary}".lower()
    area_keywords = {
        "runtime": ["runtime", "performance", "response", "latency"],
        "reasoning": ["reasoning", "capability", "analysis"],
        "tools": ["tool", "executor", "selector"],
        "memory": ["memory", "retrieval", "ranking", "context"],
        "system_health": ["health", "stability", "component", "reliability"],
        "planning": ["planning", "plan", "decomposition"],
        "understanding": ["understanding", "concept", "pattern"],
        "learning": ["learning", "insight", "strategy"],
    }
    for area, keywords in area_keywords.items():
        if any(kw in text for kw in keywords):
            return area
    return "general"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _significant_keywords(text: str, limit: int = 8) -> list[str]:
    """
    Extract significant keywords from a text string.

    Words are lowercased, stripped of punctuation, length-filtered
    (>= 5 chars), deduplicated, and sorted for determinism.

    Args:
        text: The text to scan.
        limit: Maximum number of keywords to return.

    Returns:
        A list of at most `limit` significant keywords.
    """
    words = re.findall(r"[a-z0-9_]+", text.lower())
    significant = [
        w for w in words
        if len(w) >= 5 and w not in _STOPWORDS
    ]
    unique = list(dict.fromkeys(significant))
    return sorted(unique)[:limit]


def _description_template(description: str) -> str:
    """
    Build a canonical template from a weakness description.

    Strips numeric values and long free-form tails so the same type of
    weakness with different measurements maps to the same template.

    Args:
        description: The raw weakness description.

    Returns:
        A normalized template string.
    """
    if not description:
        return "general"
    lowered = description.lower()
    # Replace numbers and percentages with placeholders
    lowered = re.sub(r"\b\d+(?:\.\d+)?%?\b", "N", lowered)
    words = re.findall(r"[a-z0-9_]+", lowered)
    significant = [w for w in words if len(w) >= 5 and w not in _STOPWORDS]
    if not significant:
        return "general"
    return "_".join(significant[:5])


_STOPWORDS = frozenset({
    "about", "above", "across", "after", "again", "against", "being",
    "below", "between", "could", "does", "down", "each", "from",
    "have", "into", "more", "most", "must", "over", "same", "than",
    "that", "their", "them", "then", "there", "these", "they",
    "this", "through", "under", "very", "were", "when", "where",
    "which", "while", "with", "would", "your", "also", "have",
    "threshold", "currently", "improvement", "system",
})
