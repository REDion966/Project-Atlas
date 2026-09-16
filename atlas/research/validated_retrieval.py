"""Atlas Research — Validated Knowledge Retrieval (C6.1).

A deterministic, read-only retrieval surface over Atlas's EXISTING persisted
research knowledge:

  * ``research_claims``       (``KnowledgeClaim``)
  * ``research_verifications`` (``ClaimVerification``)
  * ``research_citations``    (``CitationRecord``, attached to claims on load)

Contract (authoritative: ``C6_1_CONTRACT_RESOLUTION.md``):

* Only claims whose **latest** verification (by ``(verified_at,
  verification_id)``) has status ``VerificationStatus.SUPPORTED`` are returned.
* Both confidence values are exposed separately and never merged:
  ``claim_confidence`` = ``KnowledgeClaim.confidence``;
  ``verification_score`` = ``ClaimVerification.score``.
* Provenance is preserved verbatim from ``CitationRecord``; nothing is
  fabricated.
* Deterministic matching reuses ``norm_alpha`` and ``significant_tokens``:
  a query matches a claim when ``norm_alpha(query)`` is contained in
  ``norm_alpha(statement)`` OR ``significant_tokens(query)`` is a subset of
  ``significant_tokens(statement)``. No embeddings / semantic / model matching.
* Stable ordering by ``claim_id``; identical store state → identical output.
* Read-only; the store is gated by ``is_available()``; unavailable/error reads
  FAIL CLOSED and never fall back to unvalidated in-memory knowledge.

No AI, no network, no mutation, no new persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from atlas.research._text import significant_tokens
from atlas.research._verification import norm_alpha
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    VerificationStatus,
)

#: The single validation status eligible for validated retrieval.
_SUPPORTED = VerificationStatus.SUPPORTED


class ValidatedKnowledgeStatus(str, Enum):
    """Outcome of a validated-knowledge retrieval request."""

    OK = "ok"
    EMPTY = "empty"  # valid, non-error: no validated claim matched
    STORE_UNAVAILABLE = "store_unavailable"  # fail closed
    STORE_ERROR = "store_error"  # fail closed


def _citation_to_json(citation: CitationRecord) -> dict[str, Any]:
    """JSON-safe projection of a CitationRecord (provenance preserved)."""
    retrieved_at = getattr(citation, "retrieved_at", None)
    return {
        "record_id": citation.record_id,
        "source_uri": citation.source_uri,
        "source_title": citation.source_title,
        "source_kind": citation.source_kind.name,
        "section": citation.section,
        "page_or_line": citation.page_or_line,
        "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
        "metadata": dict(citation.metadata),
    }


@dataclass(frozen=True, slots=True)
class ValidatedKnowledgeItem:
    """One validated (SUPPORTED) knowledge claim with provenance."""

    claim_id: str
    statement: str
    validation_status: str
    claim_confidence: float
    verification_score: float
    citations: tuple[CitationRecord, ...] = ()
    extracted_at: datetime | None = None
    verified_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection (timestamps as ISO strings)."""
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "validation_status": self.validation_status,
            "claim_confidence": self.claim_confidence,
            "verification_score": self.verification_score,
            "citations": [_citation_to_json(c) for c in self.citations],
            "extracted_at": (
                self.extracted_at.isoformat() if self.extracted_at else None
            ),
            "verified_at": (
                self.verified_at.isoformat() if self.verified_at else None
            ),
        }


@dataclass(frozen=True, slots=True)
class ValidatedKnowledgeResult:
    """Immutable retrieval result (read-only)."""

    status: ValidatedKnowledgeStatus
    query: str
    items: tuple[ValidatedKnowledgeItem, ...] = ()
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "query": self.query,
            "count": len(self.items),
            "message": self.message,
            "items": [i.to_dict() for i in self.items],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Validated Knowledge Retrieval",
            "",
            f"**Query:** {self.query or '(none)'}",
            f"**Status:** {self.status.value}",
            f"**Validated claims:** {len(self.items)}",
            "**Modification performed:** NONE",
        ]
        if self.message:
            lines.append("")
            lines.append(self.message)
        for item in self.items:
            lines.append("")
            lines.append(f"## {item.claim_id}")
            lines.append(f"- **Statement:** {item.statement}")
            lines.append(f"- **Validation status:** {item.validation_status}")
            lines.append(f"- **Claim confidence:** {item.claim_confidence}")
            lines.append(f"- **Verification score:** {item.verification_score}")
            if item.citations:
                lines.append("- **Citations:**")
                for citation in item.citations:
                    label = citation.source_title or citation.source_uri or citation.record_id
                    lines.append(
                        f"    - {label} ({citation.source_kind.name.lower()})"
                    )
        return "\n".join(lines)


def select_latest_verifications(
    verifications: list[ClaimVerification],
) -> dict[str, ClaimVerification]:
    """Select the latest verification per claim (append-only log rule).

    Latest is the maximum by ``(verified_at, verification_id)`` — deterministic.
    """
    latest: dict[str, ClaimVerification] = {}
    for verification in verifications:
        current = latest.get(verification.claim_id)
        if current is None or (
            verification.verified_at,
            verification.verification_id,
        ) > (current.verified_at, current.verification_id):
            latest[verification.claim_id] = verification
    return latest


def _matches(statement: str, query_norm: str, query_tokens: set[str]) -> bool:
    """Deterministic match (norm_alpha containment OR token containment)."""
    statement_norm = norm_alpha(statement)
    if query_norm and query_norm in statement_norm:
        return True
    if query_tokens and query_tokens <= significant_tokens(statement):
        return True
    return False


class ValidatedKnowledgeRetriever:
    """Read-only validated-knowledge retriever over a research storage adapter.

    The storage is duck-typed: any object exposing ``is_available()``,
    ``load_claims()``, and ``load_verifications()`` (e.g.
    ``ResearchSQLiteStorage``). It is never mutated.
    """

    def __init__(self, storage: Any | None) -> None:
        self._storage = storage

    def retrieve(self, query: str) -> ValidatedKnowledgeResult:
        """Return validated (SUPPORTED) claims matching ``query``."""
        if self._storage is None:
            return ValidatedKnowledgeResult(
                status=ValidatedKnowledgeStatus.STORE_UNAVAILABLE,
                query=query or "",
                message=(
                    "Research knowledge store is unavailable; no validated "
                    "knowledge was retrieved."
                ),
            )

        is_available = getattr(self._storage, "is_available", None)
        if not callable(is_available) or not is_available():
            return ValidatedKnowledgeResult(
                status=ValidatedKnowledgeStatus.STORE_UNAVAILABLE,
                query=query or "",
                message=(
                    "Research knowledge store is unavailable; no validated "
                    "knowledge was retrieved."
                ),
            )

        if not isinstance(query, str) or not query.strip():
            return ValidatedKnowledgeResult(
                status=ValidatedKnowledgeStatus.EMPTY,
                query=query or "",
                message="No query was provided; nothing to retrieve.",
            )

        try:
            claims: list[KnowledgeClaim] = list(self._storage.load_claims())
            verifications: list[ClaimVerification] = list(
                self._storage.load_verifications()
            )
        except Exception as exc:  # fail closed on any storage error
            return ValidatedKnowledgeResult(
                status=ValidatedKnowledgeStatus.STORE_ERROR,
                query=query,
                message=(
                    f"Research knowledge store could not be read ({type(exc).__name__}); "
                    "no validated knowledge was retrieved."
                ),
            )

        query_norm = norm_alpha(query)
        query_tokens = significant_tokens(query)
        latest = select_latest_verifications(verifications)

        items: list[ValidatedKnowledgeItem] = []
        for claim in claims:
            if not _matches(claim.statement, query_norm, query_tokens):
                continue
            verification = latest.get(claim.claim_id)
            if verification is None or verification.status is not _SUPPORTED:
                continue
            items.append(
                ValidatedKnowledgeItem(
                    claim_id=claim.claim_id,
                    statement=claim.statement,
                    validation_status=_SUPPORTED.name,
                    claim_confidence=claim.confidence,
                    verification_score=verification.score,
                    citations=tuple(claim.citations),
                    extracted_at=claim.extracted_at,
                    verified_at=verification.verified_at,
                )
            )

        items.sort(key=lambda item: item.claim_id)
        if not items:
            return ValidatedKnowledgeResult(
                status=ValidatedKnowledgeStatus.EMPTY,
                query=query,
                message=(
                    "No validated (SUPPORTED) knowledge matched the query. "
                    "An empty result is not an error."
                ),
            )
        return ValidatedKnowledgeResult(
            status=ValidatedKnowledgeStatus.OK,
            query=query,
            items=tuple(items),
            message=(
                f"{len(items)} validated (SUPPORTED) claim(s) matched the query."
            ),
        )
