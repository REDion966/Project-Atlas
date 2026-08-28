"""Atlas Long-Term Learning — Deterministic Semantic Recall (Track C).

Pure, deterministic recall over the EXISTING episodic and procedural
repositories. A free-text query is tokenized into lowercase alphanumeric
tokens (length >= 2) and matched against the fields Atlas already stores
(tags, name/title, tool names, category/kind/outcome, summary/description)
using fixed weights and a coverage multiplier. Results are bounded, ordered,
fully explained (matched tokens and fields), and carry the complete
``to_dict()`` provenance of the underlying Episode/Procedure.

No scoring beyond these fixed weights: no embeddings, no AI, no model calls.
Read-only: repositories and storage are never mutated.

No infrastructure dependencies. No SQLite. No kernel. No gateway. No events.
"""

from __future__ import annotations

import re
from typing import Any

from atlas.longterm.episode_repository import EpisodicRepository
from atlas.longterm.procedure_repository import ProceduralRepository

#: Hard upper bound on returned results.
_MAX_RECALL_LIMIT: int = 500

#: Lowercase alphanumeric token pattern (applied to lowercased text).
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

#: Minimum accepted token length; shorter tokens are ignored.
_MIN_TOKEN_LENGTH: int = 2

# Approved field weights.
_WEIGHT_TAGS: float = 3.0
_WEIGHT_NAME: float = 2.0
_WEIGHT_TOOL: float = 2.0
_WEIGHT_CLASS: float = 1.5
_WEIGHT_TEXT: float = 1.0

#: Weight per scorable field name.
_FIELD_WEIGHTS: dict[str, float] = {
    "tags": _WEIGHT_TAGS,
    "name": _WEIGHT_NAME,
    "title": _WEIGHT_NAME,
    "tool": _WEIGHT_TOOL,
    "category": _WEIGHT_CLASS,
    "kind": _WEIGHT_CLASS,
    "outcome": _WEIGHT_CLASS,
    "description": _WEIGHT_TEXT,
    "summary": _WEIGHT_TEXT,
}


def tokenize(text: str) -> tuple[str, ...]:
    """Return deduplicated lowercase alphanumeric tokens (length >= 2).

    Order-preserving and deterministic for a given input.
    """
    if not isinstance(text, str):
        return ()
    seen: dict[str, None] = {}
    for raw in _TOKEN_PATTERN.findall(text.lower()):
        if len(raw) >= _MIN_TOKEN_LENGTH:
            seen.setdefault(raw, None)
    return tuple(seen)


def _hits(field_tokens: set[str], query_tokens: tuple[str, ...]) -> list[str]:
    """Return the query tokens present in a field's tokens (sorted)."""
    return sorted(token for token in query_tokens if token in field_tokens)


def _tag_tokens(tags: tuple[str, ...]) -> set[str]:
    """Tokenize every tag into one token set."""
    tokens: set[str] = set()
    for tag in tags:
        tokens.update(tokenize(tag))
    return tokens


def _finalize(
    field_hits: dict[str, list[str]],
    query_tokens: tuple[str, ...],
) -> tuple[float, tuple[str, ...], tuple[str, ...]] | None:
    """Compute (score, matched_tokens, matched_fields) or None when no match.

    Score = sum(weight * matched-token count per field) * coverage, where
    coverage = distinct matched query tokens / total distinct query tokens.
    """
    matched = sorted({t for hits in field_hits.values() for t in hits})
    if not matched:
        return None
    raw = sum(
        _FIELD_WEIGHTS[field] * len(hits)
        for field, hits in field_hits.items()
        if hits
    )
    coverage = len(matched) / len(query_tokens)
    matched_fields = tuple(
        sorted(field for field, hits in field_hits.items() if hits)
    )
    return round(raw * coverage, 4), tuple(matched), matched_fields


def _score_episode(
    episode: Any,
    query_tokens: tuple[str, ...],
) -> tuple[float, tuple[str, ...], tuple[str, ...]] | None:
    """Score one Episode against the query tokens."""
    return _finalize(
        {
            "tags": _hits(_tag_tokens(tuple(episode.tags)), query_tokens),
            "title": _hits(set(tokenize(episode.title)), query_tokens),
            "kind": _hits(set(tokenize(episode.kind.name)), query_tokens),
            "outcome": _hits(set(tokenize(episode.outcome)), query_tokens),
            "summary": _hits(set(tokenize(episode.summary)), query_tokens),
        },
        query_tokens,
    )


def _score_procedure(
    procedure: Any,
    query_tokens: tuple[str, ...],
) -> tuple[float, tuple[str, ...], tuple[str, ...]] | None:
    """Score one Procedure against the query tokens."""
    tool_tokens: set[str] = set()
    for step in procedure.steps:
        tool_tokens.update(tokenize(step.tool_name))
    return _finalize(
        {
            "tags": _hits(_tag_tokens(tuple(procedure.tags)), query_tokens),
            "name": _hits(set(tokenize(procedure.name)), query_tokens),
            "tool": _hits(tool_tokens, query_tokens),
            "category": _hits(set(tokenize(procedure.category)), query_tokens),
            "kind": _hits(set(tokenize(procedure.kind.name)), query_tokens),
            "description": _hits(
                set(tokenize(procedure.description)), query_tokens
            ),
        },
        query_tokens,
    )


def _resolve_limit(limit: int | None) -> int:
    """Resolve the requested limit against the hard cap."""
    if limit is None:
        return _MAX_RECALL_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if limit <= 0:
        raise ValueError("limit must be positive")
    return min(limit, _MAX_RECALL_LIMIT)


class SemanticRecallEngine:
    """Deterministic ranked recall over episodic and procedural memory.

    Args:
        episodes: The existing :class:`EpisodicRepository`.
        procedures: The existing :class:`ProceduralRepository`.
    """

    def __init__(
        self,
        episodes: EpisodicRepository,
        procedures: ProceduralRepository,
    ) -> None:
        self._episodes = episodes
        self._procedures = procedures

    def recall(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return bounded, ordered, explained recall results for a query.

        Empty/whitespace queries return an empty list. Items with zero
        matched query tokens are excluded. Results are sorted by
        ``(-score, type, id)`` and each result carries the complete
        ``to_dict()`` representation of the underlying item.

        Read-only: the repositories are never mutated.
        """
        query_tokens = tokenize(query) if isinstance(query, str) else ()
        if not query_tokens:
            return []
        bound = _resolve_limit(limit)

        candidates: list[tuple[float, str, str, tuple[str, ...], tuple[str, ...], dict[str, Any]]] = []
        for episode in self._episodes.get_episodes(n=_MAX_RECALL_LIMIT):
            scored = _score_episode(episode, query_tokens)
            if scored is not None:
                score, matched, fields = scored
                candidates.append(
                    (score, "episode", episode.episode_id, matched, fields, episode.to_dict())
                )
        for procedure in self._procedures.get_procedures(n=_MAX_RECALL_LIMIT):
            scored = _score_procedure(procedure, query_tokens)
            if scored is not None:
                score, matched, fields = scored
                candidates.append(
                    (score, "procedure", procedure.procedure_id, matched, fields, procedure.to_dict())
                )

        candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
        return [
            {
                "type": item_type,
                "score": score,
                "matched_tokens": matched,
                "matched_fields": matched_fields,
                "item": item,
            }
            for score, item_type, _, matched, matched_fields, item in candidates[:bound]
        ]
