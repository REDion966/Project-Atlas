"""Atlas Evolution — Capability/Knowledge Gap Adjudicator (Phase 5.2).

Deterministically decides, for a development request, whether Atlas already
supports it, whether a capability is genuinely missing, or whether knowledge is
missing (research is required). It reuses existing self-knowledge surfaces
(the capability model / capability registry names) and the Phase-3 validated
knowledge retriever; it fabricates nothing and fails closed to ``UNCLEAR`` on
malformed input.

Lexical overlap with a registered capability name is NECESSARY but NOT
SUFFICIENT evidence of functional equivalence. A capability is reported
``ALREADY_SUPPORTED`` only when the overlap accounts for a substantial share of
the request's own words; an incidental shared word inside a longer request
(for example "conversation" in "export the conversation history as markdown")
is not read as "Atlas already does this".

The knowledge half of the decision asks whether validated knowledge is held about
the request's SUBJECT rather than whether the request as a whole restates a
claim: the strict whole-request retrieval is tried first (unchanged), and when it
finds nothing a bounded, deterministic fallback probe establishes subject-known
evidence from validated claims. It can only ever report that a subject IS known —
it never manufactures a capability gap or a matched capability.

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

#: Minimum overlap evidence for capability matching. A capability name counts as
#: a match only when the tokens it shares with the request account for at least
#: ``MIN_OVERLAP_NUMERATOR / MIN_OVERLAP_DENOMINATOR`` of the request's own
#: significant tokens. Token overlap is necessary but not sufficient proof of
#: functional equivalence: a single incidental shared word inside a longer
#: request is not evidence that Atlas already does what was asked.
MIN_OVERLAP_NUMERATOR: int = 1
MIN_OVERLAP_DENOMINATOR: int = 3

#: Maximum number of bounded fallback subject probes performed when the strict
#: whole-request retrieval finds nothing. Boundedness: the probe count never
#: depends on the request's length.
MAX_SUBJECT_PROBES: int = 3

#: Minimum number of normalized significant tokens a validated claim must share
#: with the request before the request's SUBJECT counts as known from validated
#: knowledge. Deliberately conservative: three genuinely shared words are real
#: evidence of a shared subject, whereas two can be incidental ("format",
#: "reports"), so this keeps an unknown entity from being read as a known one.
MIN_SUBJECT_SHARED_TOKENS: int = 3


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


def _is_equivalence_evidence(overlap: set[str], request_token_count: int) -> bool:
    """Whether a capability-name ``overlap`` is strong enough evidence.

    Deterministic and bounded: the shared tokens must account for at least
    ``MIN_OVERLAP_NUMERATOR / MIN_OVERLAP_DENOMINATOR`` of the request's
    significant tokens. This keeps genuine matches ("memory search" against
    ``memory_search``) while refusing to read one incidental shared word inside
    a longer request as functional equivalence.
    """
    if not overlap:
        return False
    return (
        len(overlap) * MIN_OVERLAP_DENOMINATOR
        >= request_token_count * MIN_OVERLAP_NUMERATOR
    )


def _probe_tokens(request: str, limit: int = MAX_SUBJECT_PROBES) -> tuple[str, ...]:
    """The bounded, deterministic fallback probe tokens for ``request``.

    Longest first, then alphabetical — so equal-length tokens always probe in the
    same order — and de-duplicated. Never more than ``limit`` tokens, so the cost
    of the fallback never depends on how long the request is.
    """
    tokens = significant_tokens(request)
    ordered = sorted(tokens, key=lambda token: (-len(token), token))
    return tuple(ordered[: max(0, limit)])


def _subject_tokens(text: Any) -> set[str]:
    """Significant tokens of ``text`` under the EXISTING identifier convention.

    Mirrors ``_capability_tokens``: dotted/underscored identifiers are split into
    words before tokenizing, so ``audit_log`` and ``audit log`` agree instead of
    counting as one token. No new tokenizer or entity system is introduced.
    """
    if not isinstance(text, str) or not text:
        return set()
    return significant_tokens(text.replace(".", " ").replace("_", " "))


def _retrieved_items(result: Any) -> list[Any]:
    """The retrieved items of a retriever result (duck-typed, never raises)."""
    items = getattr(result, "items", None)
    if items is None and isinstance(result, (list, tuple)):
        items = result
    try:
        return list(items or ())
    except TypeError:
        return []


def _knowledge_present(knowledge_retriever: Any, query: str) -> tuple[bool, str]:
    """Best-effort: is validated knowledge held about the SUBJECT of ``query``?

    The EXISTING strict retrieval is tried first and is unchanged: a request that
    matched a claim before still matches it, with the same evidence string. Only
    when that finds nothing is a bounded fallback probe performed, because the
    strict rule requires EVERY query token to appear in a claim — the right rule
    for "which claims ANSWER this query", but one a natural sentence almost never
    satisfies even when its subject is well known.

    The fallback reuses the EXISTING retriever (contract unchanged), the EXISTING
    tokenizer and the EXISTING identifier normalization, and it can only ever
    report that a subject is KNOWN. It never invents knowledge, never manufactures
    a capability (capability absence is established before this is consulted) and
    never fabricates a matched capability.

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
    matches = _retrieved_items(result)
    status = getattr(getattr(result, "status", None), "value", "")
    if matches:
        return (True, f"validated knowledge matches={len(matches)} status={status}")

    # --- bounded subject probe (strict whole-request retrieval was empty) ------
    request_tokens = _subject_tokens(query)
    probes = _probe_tokens(query)
    for token in probes:
        try:
            probe_result = knowledge_retriever.retrieve(token)
        except Exception:  # a failed probe is simply not evidence
            continue
        claims = _retrieved_items(probe_result)
        for claim in claims:
            shared = request_tokens & _subject_tokens(getattr(claim, "statement", ""))
            if len(shared) >= MIN_SUBJECT_SHARED_TOKENS:
                return (
                    True,
                    f"subject probe={token!r} shared_tokens={sorted(shared)} "
                    f"matches={len(claims)} status={status}",
                )
    return (
        False,
        f"validated knowledge matches=0 status={status} probes={list(probes)}",
    )


def assess_development_gap(
    request: Any,
    *,
    capability_names: Iterable[str] = (),
    knowledge_retriever: Any | None = None,
) -> DevelopmentGapAssessment:
    """Classify ``request`` against Atlas's own capabilities/knowledge.

    Rules (deterministic, fail-closed):

    * blank/malformed request or no significant tokens -> ``UNCLEAR``
    * the request's tokens substantially overlap a registered capability name
      (the overlap covers at least a third of the request's own words) ->
      ``ALREADY_SUPPORTED``
    * otherwise, if validated knowledge exists for the request's SUBJECT ->
      ``MISSING_CAPABILITY`` (we know enough to build it, but lack the capability)
    * otherwise -> ``MISSING_KNOWLEDGE`` (research is required first)

    Overlap alone is never treated as functional equivalence: an incidental
    shared token inside a longer request leaves the gap ``MISSING_*`` so a
    legitimate capability request can still reach the governed development path.

    The knowledge half of that decision asks about the request's SUBJECT: the
    EXISTING strict whole-request retrieval is tried first, and only when it
    finds nothing is a bounded fallback probe (at most
    ``MAX_SUBJECT_PROBES`` tokens, deterministic order) used, which treats the
    subject as known only when a validated claim shares at least
    ``MIN_SUBJECT_SHARED_TOKENS`` tokens with the request. A natural sentence
    otherwise loses a subject Atlas demonstrably holds validated knowledge about,
    because the strict retrieval rule requires every query token to be present.
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

    request_token_count = len(tokens)
    matched: list[str] = []
    for raw_name in capability_names or ():
        if not isinstance(raw_name, str) or not raw_name:
            continue
        overlap = tokens & _capability_tokens(raw_name)
        if _is_equivalence_evidence(overlap, request_token_count):
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
