"""Atlas Evolution — Capability/Knowledge Gap Adjudicator (Phase 5.2).

Deterministically decides, for a development request, whether Atlas already
supports it, whether a capability is genuinely missing, or whether knowledge is
missing (research is required). It reuses existing self-knowledge surfaces
(the capability model / capability registry names) and the Phase-3 validated
knowledge retriever; it fabricates nothing and fails closed to ``UNCLEAR`` on
malformed input.

Pure logic: stdlib only. No AI, no network, no storage, no kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from atlas.research._text import significant_tokens

#: Minimum length of a request token considered for capability matching.
MIN_TOKEN_LENGTH: int = 3

#: Maximum number of matched capability names recorded (boundedness).
MAX_MATCHES: int = 10


class DevelopmentGapKind(str, Enum):
    """The adjudicated nature of a development request."""

    ALREADY_SUPPORTED = "already_supported"
    MISSING_CAPABILITY = "missing_capability"
    MISSING_KNOWLEDGE = "missing_knowledge"
    UNCLEAR = "unclear"


@dataclass(frozen=True, slots=True)
class DevelopmentGapAssessment:
    """Deterministic, evidence-backed gap assessment."""

    kind: DevelopmentGapKind
    matched: tuple[str, ...] = ()
    evidence: str = ""
    rationale: str = ""
    query_tokens: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "matched": list(self.matched),
            "evidence": self.evidence,
            "rationale": self.rationale,
            "query_tokens": list(self.query_tokens),
        }


def _capability_tokens(name: Any) -> set[str]:
    """Tokenize a (possibly dotted) capability name deterministically."""
    if not isinstance(name, str) or not name:
        return set()
    return significant_tokens(name.replace(".", " ").replace("_", " "))


def _knowledge_present(knowledge_retriever: Any, query: str) -> tuple[bool, str]:
    """Best-effort: does validated knowledge exist for ``query``?

    Returns ``(present, evidence)``. A missing/failing retriever is treated as
    "no knowledge" (research is required) — never as fabricated knowledge.
    """
    if knowledge_retriever is None or not callable(
        getattr(knowledge_retriever, "retrieve", None)
    ):
        return (False, "no knowledge retriever wired")
    try:
        result = knowledge_retriever.retrieve(query)
    except Exception as exc:  # fail-soft to "no knowledge"
        return (False, f"knowledge lookup failed ({type(exc).__name__})")
    items = getattr(result, "items", None)
    if items is None and isinstance(result, (list, tuple)):
        items = result
    try:
        count = len(list(items or ()))
    except TypeError:
        count = 0
    status = getattr(getattr(result, "status", None), "value", "")
    return (count > 0, f"validated knowledge matches={count} status={status}")


def assess_development_gap(
    request: Any,
    *,
    capability_names: Iterable[str] = (),
    knowledge_retriever: Any | None = None,
) -> DevelopmentGapAssessment:
    """Classify ``request`` against Atlas's own capabilities/knowledge.

    Rules (deterministic, fail-closed):

    * blank/malformed request or no significant tokens -> ``UNCLEAR``
    * request tokens overlap a registered capability name -> ``ALREADY_SUPPORTED``
    * otherwise, if validated knowledge exists for the request ->
      ``MISSING_CAPABILITY`` (we know enough to build it, but lack the capability)
    * otherwise -> ``MISSING_KNOWLEDGE`` (research is required first)
    """
    if not isinstance(request, str) or not request.strip():
        return DevelopmentGapAssessment(
            kind=DevelopmentGapKind.UNCLEAR,
            evidence="empty or malformed request",
            rationale="A non-empty request string is required.",
        )

    tokens = {
        token
        for token in significant_tokens(request)
        if len(token) >= MIN_TOKEN_LENGTH
    }
    if not tokens:
        return DevelopmentGapAssessment(
            kind=DevelopmentGapKind.UNCLEAR,
            evidence="no significant request tokens",
            rationale="The request carried no matchable tokens.",
        )

    matched: list[str] = []
    for raw_name in capability_names or ():
        if not isinstance(raw_name, str) or not raw_name:
            continue
        if tokens & _capability_tokens(raw_name):
            if raw_name not in matched:
                matched.append(raw_name)

    if matched:
        matched.sort()
        return DevelopmentGapAssessment(
            kind=DevelopmentGapKind.ALREADY_SUPPORTED,
            matched=tuple(matched[:MAX_MATCHES]),
            evidence="capability name overlap: " + ", ".join(matched[:MAX_MATCHES]),
            rationale=(
                "The request matches an already-registered capability; no "
                "development is required."
            ),
            query_tokens=tuple(sorted(tokens)),
        )

    present, evidence = _knowledge_present(knowledge_retriever, request)
    if present:
        return DevelopmentGapAssessment(
            kind=DevelopmentGapKind.MISSING_CAPABILITY,
            evidence=evidence,
            rationale=(
                "Knowledge exists to design the change, but no matching "
                "capability is registered."
            ),
            query_tokens=tuple(sorted(tokens)),
        )

    return DevelopmentGapAssessment(
        kind=DevelopmentGapKind.MISSING_KNOWLEDGE,
        evidence=evidence,
        rationale=(
            "No matching capability and no validated knowledge; bounded "
            "research is required before design."
        ),
        query_tokens=tuple(sorted(tokens)),
    )
