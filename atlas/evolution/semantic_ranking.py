"""Atlas Evolution — bounded SEMANTIC re-ranking (Command 3, optional specialist).

The consumer boundary for :mod:`atlas.semantic_similarity`.

The single most important property
----------------------------------
**A specialist may only REORDER a candidate set Atlas already produced. It can
never introduce a candidate, remove one, or create a match.** Atlas's
deterministic mechanism decides WHAT the candidates are; the optional embedding
specialist may only contribute a similarity number that re-orders them. That
keeps the specialist out of the authority path entirely: even a compromised
model can change an ordering and nothing else.

Uncertainty is preserved
------------------------
A re-ordering is applied ONLY when the semantically-best candidate is a
DIFFERENT candidate from the deterministic best AND leads it by at least
:data:`DEFAULT_SEMANTIC_MARGIN`. Anything less — no specialist, no signal, a
malformed reply, a tie, or a lead inside the margin — returns the deterministic
order unchanged with an explicit reason. ``applied`` is always reported, so a
consumer can never mistake "the specialist agreed" for "the specialist decided".

Deterministic, bounded, read-only. No model, no I/O, standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.semantic_similarity import EmbeddingResult, cosine_similarity

#: Minimum lead (in cosine similarity) the semantic best must have over the
#: deterministic best before an Atlas ordering is changed at all. Fixed at
#: module level so a re-ordering is reproducible and auditable.
DEFAULT_SEMANTIC_MARGIN: float = 0.05

#: Bound on the candidate set a single re-ordering may consider.
MAX_SEMANTIC_CANDIDATES: int = 24

#: The bounded reason vocabulary (a caller never has to parse prose).
REASON_NO_SPECIALIST: str = "no embedding specialist is available"
REASON_NO_QUERY: str = "no query to compare against"
REASON_NO_CANDIDATES: str = "no deterministic candidates to re-rank"
REASON_NO_SIGNAL: str = "the specialist returned no usable signal"
REASON_AGREES: str = "the specialist agrees with the deterministic order"
REASON_BELOW_MARGIN: str = "the semantic lead is inside the uncertainty margin"
REASON_APPLIED: str = "the specialist re-ordered Atlas's own candidate set"


@dataclass(frozen=True, slots=True)
class SemanticCandidate:
    """One candidate Atlas ALREADY produced, with the text to compare."""

    key: str
    text: str = ""


@dataclass(frozen=True, slots=True)
class SemanticRanking:
    """The bounded outcome of one optional semantic re-ranking.

    ``order`` is ALWAYS a permutation of the input keys — the invariant a caller
    may rely on. ``deterministic_order`` is retained so the decision is
    auditable and reversible.
    """

    order: tuple[str, ...] = ()
    deterministic_order: tuple[str, ...] = ()
    scores: tuple[tuple[str, float], ...] = ()
    applied: bool = False
    reason: str = ""
    margin: float = DEFAULT_SEMANTIC_MARGIN
    lead: float = 0.0
    provider_id: str = ""
    model_id: str = ""
    dimension: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": list(self.order),
            "deterministic_order": list(self.deterministic_order),
            "scores": [list(item) for item in self.scores],
            "applied": self.applied,
            "reason": self.reason,
            "margin": self.margin,
            "lead": round(self.lead, 6),
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "dimension": self.dimension,
        }


def _unchanged(
    keys: tuple[str, ...],
    reason: str,
    *,
    margin: float,
    provider_id: str = "",
    model_id: str = "",
    dimension: int = 0,
) -> SemanticRanking:
    return SemanticRanking(
        order=keys,
        deterministic_order=keys,
        applied=False,
        reason=reason,
        margin=margin,
        provider_id=provider_id,
        model_id=model_id,
        dimension=dimension,
    )


def rerank_candidates(
    candidates: Any,
    query: str,
    model: Any,
    *,
    margin: float = DEFAULT_SEMANTIC_MARGIN,
    max_candidates: int = MAX_SEMANTIC_CANDIDATES,
) -> SemanticRanking:
    """Optionally re-order Atlas's OWN candidates by semantic similarity (pure).

    Never raises. The returned ``order`` is always a permutation of the input
    candidate keys, in the input order unless a re-ordering was justified.
    """
    if not isinstance(margin, (int, float)) or isinstance(margin, bool):
        margin = DEFAULT_SEMANTIC_MARGIN
    margin = max(0.0, float(margin))
    if not isinstance(max_candidates, int) or max_candidates <= 0:
        max_candidates = MAX_SEMANTIC_CANDIDATES

    try:
        source = tuple(candidates or ())
    except TypeError:  # a non-iterable candidate set is simply no candidates
        source = ()

    items: list[SemanticCandidate] = []
    for candidate in source:
        if isinstance(candidate, SemanticCandidate):
            items.append(candidate)
        elif isinstance(candidate, (list, tuple)) and candidate:
            text = str(candidate[1]) if len(candidate) > 1 else ""
            items.append(SemanticCandidate(str(candidate[0]), text))
        elif isinstance(candidate, str):
            items.append(SemanticCandidate(candidate, candidate))
        if len(items) >= max_candidates:
            break

    keys = tuple(item.key for item in items)
    if not keys:
        return _unchanged((), REASON_NO_CANDIDATES, margin=margin)
    if not isinstance(query, str) or not query.strip():
        return _unchanged(keys, REASON_NO_QUERY, margin=margin)
    if model is None or not getattr(model, "available", False):
        return _unchanged(keys, REASON_NO_SPECIALIST, margin=margin)

    try:
        result = model.embed([query.strip()] + [item.text for item in items])
    except Exception:  # noqa: BLE001 — a broken specialist is no signal
        result = None
    if not isinstance(result, EmbeddingResult):
        return _unchanged(keys, REASON_NO_SIGNAL, margin=margin)

    query_vector = result.vector_for(0)
    if query_vector is None:
        return _unchanged(keys, REASON_NO_SIGNAL, margin=margin)

    scored: list[tuple[int, str, float]] = []
    for index, item in enumerate(items):
        vector = result.vector_for(index + 1)
        if vector is None:
            return _unchanged(keys, REASON_NO_SIGNAL, margin=margin)
        score = cosine_similarity(query_vector, vector)
        if score is None:
            return _unchanged(keys, REASON_NO_SIGNAL, margin=margin)
        scored.append((index, item.key, score))

    # Deterministic ordering: score descending, then ORIGINAL INDEX ascending, so
    # a tie can never re-order anything by itself.
    ranked = sorted(scored, key=lambda entry: (-entry[2], entry[0]))
    deterministic_top = scored[0]
    semantic_top = ranked[0]
    lead = semantic_top[2] - deterministic_top[2]

    common = {
        "margin": margin,
        "provider_id": str(getattr(result, "provider_id", "")),
        "model_id": str(getattr(result, "model_id", "")),
        "dimension": int(getattr(result, "dimension", 0)),
    }
    scores = tuple((key, round(score, 6)) for _index, key, score in ranked)

    if semantic_top[1] == deterministic_top[1]:
        return SemanticRanking(
            order=keys,
            deterministic_order=keys,
            scores=scores,
            applied=False,
            reason=REASON_AGREES,
            lead=lead,
            **common,
        )
    if lead < margin:
        return SemanticRanking(
            order=keys,
            deterministic_order=keys,
            scores=scores,
            applied=False,
            reason=REASON_BELOW_MARGIN,
            lead=lead,
            **common,
        )
    return SemanticRanking(
        order=tuple(key for _index, key, _score in ranked),
        deterministic_order=keys,
        scores=scores,
        applied=True,
        reason=REASON_APPLIED,
        lead=lead,
        **common,
    )


__all__ = [
    "DEFAULT_SEMANTIC_MARGIN",
    "MAX_SEMANTIC_CANDIDATES",
    "REASON_AGREES",
    "REASON_APPLIED",
    "REASON_BELOW_MARGIN",
    "REASON_NO_CANDIDATES",
    "REASON_NO_QUERY",
    "REASON_NO_SIGNAL",
    "REASON_NO_SPECIALIST",
    "SemanticCandidate",
    "SemanticRanking",
    "rerank_candidates",
]
