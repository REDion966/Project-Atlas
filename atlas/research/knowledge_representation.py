"""Atlas — Knowledge Representation & Learning (Step 18).

A bounded, deterministic, model-free representation of the JUSTIFIED knowledge
produced by the existing research/provenance pipeline (Steps 16-17), plus the
retention decision that separates it from what is merely retrieved.

It is NOT a second knowledge store and NOT a competing retrieval system: the
durable artifacts remain the EXISTING research storage
(``research_claims`` / ``research_verifications`` / ``research_citations`` /
``research_reports``), the standing remains the EXISTING verifier's verdict
(Step 17 ``ClaimStanding``), and retrieval remains the EXISTING
``ValidatedKnowledgeRetriever`` (now standing-aware). This module only
REPRESENTS the justified subset and DECIDES what may be retained as knowledge.

Retention rule (closed, deterministic, fail-closed — see :data:`RETENTION_RULE`):

* a claim is retained ONLY when the existing verification stands at
  ``verified`` (corroborated by 2+ independent sources) or ``supported``
  (exactly one supporting source), **and** it carries a provenance link (at
  least one evidence/citation record);
* ``contested`` (conflicting evidence), ``unverified`` (retrieved without
  supporting evidence) and ``unknown`` (no verification) claims are REFUSED,
  with the reason recorded — they are never promoted into established knowledge;
* duplicates are collapsed deterministically by ``claim_id`` (first occurrence
  wins in a stable order) and reported;
* with no claim-level provenance (no stored report / no claims) nothing is
  retained and the insufficiency is reported rather than hidden.

Guarantees: pure logic over recorded evidence (no AI, no network, no clock, no
randomness, no writes), immutable bounded objects, and no authority — retention
is a representation, never a promotion into the evolution lifecycle, and it
grants nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from atlas.research.provenance import (
    ClaimStanding,
    ProvenanceEvidence,
    ProvenanceSource,
    ResearchProvenance,
    provenance_from_outcome,
)

#: The retention rule, stated once so callers can report it verbatim.
RETENTION_RULE: str = (
    "A claim is retained as knowledge only when the existing verification "
    "stands at verified (2+ supporting sources) or supported (one supporting "
    "source) AND it carries a provenance link (at least one evidence record). "
    "Contested, unverified and unknown claims are refused, never promoted."
)

#: Bounds (a malformed source can never produce unbounded output).
_MAX_TEXT_CHARS: int = 400
_MAX_STATEMENT_CHARS: int = 400
_MAX_RECORDS: int = 40
_MAX_EVIDENCE: int = 40
_MAX_FINDINGS: int = 8
_MAX_REASON_CHARS: int = 300

#: The only standings that may be retained as knowledge.
_RETAINABLE: frozenset[str] = frozenset(
    {ClaimStanding.VERIFIED.value, ClaimStanding.SUPPORTED.value}
)

_REFUSAL_REASONS: dict[str, str] = {
    ClaimStanding.CONTESTED.value: (
        "conflicting evidence was recorded for this claim; contradictory "
        "information is never promoted into established knowledge"
    ),
    ClaimStanding.UNVERIFIED.value: (
        "the claim was retrieved without supporting evidence; it is not "
        "established knowledge"
    ),
    ClaimStanding.UNKNOWN.value: (
        "no verification was recorded for this claim; it is not established "
        "knowledge"
    ),
}


class KnowledgeStatus(str, Enum):
    """Outcome of a retained-knowledge retrieval (mirrors the C6.1 statuses)."""

    OK = "ok"
    EMPTY = "empty"
    STORE_UNAVAILABLE = "store_unavailable"
    STORE_ERROR = "store_error"


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    """One justified knowledge record (immutable).

    It carries the Step 17 provenance chain verbatim — the evaluated sources
    and the evidence (citation) records — so attribution survives retrieval.
    ``established`` is true only for multi-source corroboration; a
    single-source record is justified but not established.
    """

    record_id: str
    claim_id: str
    statement: str
    standing: str
    established: bool
    justified: bool = True
    confidence: float = 0.0
    verification_status: str = ""
    verification_score: float = 0.0
    verification_outcome: str = ""
    evidence: tuple[ProvenanceEvidence, ...] = ()
    sources: tuple[ProvenanceSource, ...] = ()
    supporting_sources: tuple[str, ...] = ()
    report_ids: tuple[str, ...] = ()
    acquisition_id: str = ""
    objective: str = ""
    query: str = ""
    findings: tuple[str, ...] = ()

    @property
    def source_uris(self) -> tuple[str, ...]:
        """Attribution: the source identity of every preserved evidence item."""
        return tuple(e.source_uri for e in self.evidence if e.source_uri)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "claim_id": self.claim_id,
            "statement": self.statement,
            "standing": self.standing,
            "established": self.established,
            "justified": self.justified,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "verification_score": self.verification_score,
            "verification_outcome": self.verification_outcome,
            "evidence": [e.to_dict() for e in self.evidence],
            "sources": [s.to_dict() for s in self.sources],
            "supporting_sources": list(self.supporting_sources),
            "report_ids": list(self.report_ids),
            "acquisition_id": self.acquisition_id,
            "objective": self.objective,
            "query": self.query,
            "findings": list(self.findings),
            "source_uris": list(self.source_uris),
        }


@dataclass(frozen=True, slots=True)
class RefusedKnowledge:
    """One claim that was NOT retained, and why (immutable)."""

    claim_id: str
    statement: str
    standing: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "standing": self.standing,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeRetention:
    """The bounded outcome of a retention decision (immutable)."""

    objective: str
    query: str = ""
    report_ids: tuple[str, ...] = ()
    acquisition_id: str = ""
    records: tuple[KnowledgeRecord, ...] = ()
    refused: tuple[RefusedKnowledge, ...] = ()
    duplicates: tuple[str, ...] = ()
    established_count: int = 0
    supported_count: int = 0
    contested_count: int = 0
    unverified_count: int = 0
    findings: tuple[str, ...] = ()

    @property
    def retained_count(self) -> int:
        return len(self.records)

    @property
    def refused_count(self) -> int:
        return len(self.refused)

    @property
    def has_insufficient_input(self) -> bool:
        """True when no claim-level provenance was available to retain from."""
        return not self.records and not self.refused

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "query": self.query,
            "report_ids": list(self.report_ids),
            "acquisition_id": self.acquisition_id,
            "records": [r.to_dict() for r in self.records],
            "refused": [r.to_dict() for r in self.refused],
            "duplicates": list(self.duplicates),
            "established_count": self.established_count,
            "supported_count": self.supported_count,
            "contested_count": self.contested_count,
            "unverified_count": self.unverified_count,
            "retained_count": self.retained_count,
            "refused_count": self.refused_count,
            "has_insufficient_input": self.has_insufficient_input,
            "findings": list(self.findings),
            "retention_rule": RETENTION_RULE,
        }


@dataclass(frozen=True, slots=True)
class RetainedKnowledge:
    """Deterministic retrieval of retained (justified) knowledge (immutable)."""

    status: KnowledgeStatus
    query: str
    records: tuple[KnowledgeRecord, ...] = ()
    message: str = ""

    @property
    def established(self) -> tuple[KnowledgeRecord, ...]:
        """Only the multi-source corroborated records."""
        return tuple(r for r in self.records if r.established)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "query": self.query,
            "records": [r.to_dict() for r in self.records],
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _value(value: Any, limit: int = 64) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return ""
    return _clean(raw, limit)


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


def _evidence_for(
    claim: Any, evidence: tuple[ProvenanceEvidence, ...]
) -> tuple[ProvenanceEvidence, ...]:
    """The preserved evidence items for ``claim``, in the claim's own order."""
    by_id = {item.evidence_id: item for item in evidence}
    out: list[ProvenanceEvidence] = []
    for evidence_id in getattr(claim, "evidence_ids", ()) or ():
        item = by_id.get(evidence_id)
        if item is not None and item not in out:
            out.append(item)
    return tuple(out[:_MAX_EVIDENCE])


def _sources_for(
    claim: Any, sources: tuple[ProvenanceSource, ...]
) -> tuple[ProvenanceSource, ...]:
    """The evaluated sources that support ``claim`` (attribution preserved)."""
    supporting = tuple(getattr(claim, "supporting_sources", ()) or ())
    wanted = supporting or tuple(getattr(claim, "source_uris", ()) or ())
    if not wanted:
        return ()
    by_uri = {source.source_uri: source for source in sources}
    out: list[ProvenanceSource] = []
    for uri in wanted:
        source = by_uri.get(uri)
        if source is not None:
            out.append(source)
    return tuple(out[:_MAX_EVIDENCE])


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def retain_knowledge(provenance: Any) -> KnowledgeRetention:
    """Decide which claims may be retained as knowledge (pure, fail-closed).

    Consumes a Step 17 ``ResearchProvenance`` and returns the justified records
    plus every refusal and its reason. Nothing is written, nothing is promoted
    and nothing is invented.
    """
    if provenance is None:
        return KnowledgeRetention(
            objective="",
            findings=("no research provenance was supplied; nothing was retained",),
        )

    objective = _clean(getattr(provenance, "objective", ""))
    query = _clean(getattr(provenance, "query", ""), 200)
    report_ids = tuple(getattr(provenance, "report_ids", ()) or ())
    acquisition_id = _clean(getattr(provenance, "acquisition_id", ""), 120)

    claims = tuple(getattr(provenance, "claims", ()) or ())
    evidence = tuple(getattr(provenance, "evidence", ()) or ())
    sources = tuple(getattr(provenance, "sources", ()) or ())

    records: list[KnowledgeRecord] = []
    refused: list[RefusedKnowledge] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    established = supported = contested = unverified = 0

    # Deterministic order regardless of how the provenance was assembled.
    for claim in sorted(claims, key=lambda c: _clean(getattr(c, "claim_id", ""), 120)):
        claim_id = _clean(getattr(claim, "claim_id", ""), 120)
        if not claim_id:
            continue
        statement = _clean(getattr(claim, "statement", ""), _MAX_STATEMENT_CHARS)
        standing = _value(getattr(claim, "standing", "")) or ClaimStanding.UNKNOWN.value
        if claim_id in seen:
            duplicates.append(claim_id)
            continue
        seen.add(claim_id)

        if standing == ClaimStanding.CONTESTED.value:
            contested += 1
        elif standing in (
            ClaimStanding.UNVERIFIED.value,
            ClaimStanding.UNKNOWN.value,
        ):
            unverified += 1
        elif standing == ClaimStanding.VERIFIED.value:
            established += 1
        elif standing == ClaimStanding.SUPPORTED.value:
            supported += 1

        if standing not in _RETAINABLE:
            refused.append(
                RefusedKnowledge(
                    claim_id=claim_id,
                    statement=statement,
                    standing=standing,
                    reason=_clean(
                        _REFUSAL_REASONS.get(
                            standing,
                            "the claim's standing does not satisfy the retention rule",
                        ),
                        _MAX_REASON_CHARS,
                    ),
                )
            )
            continue

        evidence_items = _evidence_for(claim, evidence)
        if not evidence_items:
            # Justified but without a provenance link: never retained silently.
            refused.append(
                RefusedKnowledge(
                    claim_id=claim_id,
                    statement=statement,
                    standing=standing,
                    reason=_clean(
                        "no provenance link was preserved for this claim (no "
                        "evidence record), so it is not retained as knowledge",
                        _MAX_REASON_CHARS,
                    ),
                )
            )
            continue

        findings: list[str] = []
        if standing == ClaimStanding.SUPPORTED.value:
            findings.append(
                "justified by a single source (supported, not multi-source "
                "established)"
            )
        records.append(
            KnowledgeRecord(
                record_id=f"knowledge:{claim_id}",
                claim_id=claim_id,
                statement=statement,
                standing=standing,
                established=standing == ClaimStanding.VERIFIED.value,
                confidence=_float(getattr(claim, "confidence", 0.0)),
                verification_status=_clean(
                    getattr(claim, "verification_status", ""), 32
                ),
                verification_score=_float(getattr(claim, "verification_score", 0.0)),
                verification_outcome=_clean(
                    getattr(claim, "verification_outcome", ""), 32
                ),
                evidence=evidence_items,
                sources=_sources_for(claim, sources),
                supporting_sources=tuple(
                    getattr(claim, "supporting_sources", ()) or ()
                )[:_MAX_EVIDENCE],
                report_ids=report_ids,
                acquisition_id=acquisition_id,
                objective=objective,
                query=query,
                findings=tuple(findings[:_MAX_FINDINGS]),
            )
        )
        if len(records) >= _MAX_RECORDS:
            break

    findings_list: list[str] = []
    if not claims:
        findings_list.append(
            "no claim-level provenance was available; nothing was retained"
        )
    if refused:
        findings_list.append(
            f"{len(refused)} claim(s) were refused (contested, unverified or "
            "without a provenance link) and are not retained as knowledge"
        )
    if duplicates:
        findings_list.append(
            f"{len(duplicates)} duplicate claim(s) were collapsed deterministically"
        )
    if records and not any(r.established for r in records):
        findings_list.append(
            "no retained record reached multi-source corroboration (established); "
            "the retained knowledge is single-source at best"
        )

    return KnowledgeRetention(
        objective=objective,
        query=query,
        report_ids=report_ids,
        acquisition_id=acquisition_id,
        records=tuple(records),
        refused=tuple(refused),
        duplicates=tuple(duplicates),
        established_count=established,
        supported_count=supported,
        contested_count=contested,
        unverified_count=unverified,
        findings=tuple(findings_list[:_MAX_FINDINGS]),
    )


def retention_from_outcome(outcome: Any, *, reports: Any = ()) -> KnowledgeRetention:
    """Retention decision for a Step 16 ``ResearchOutcome`` (never raises)."""
    return retain_knowledge(provenance_from_outcome(outcome, reports=reports))


# ---------------------------------------------------------------------------
# Deterministic retrieval of retained knowledge
# ---------------------------------------------------------------------------


class RetainedKnowledgeRetriever:
    """Deterministic, read-only retrieval of retained knowledge.

    Reads the EXISTING research storage through the EXISTING
    ``ValidatedKnowledgeRetriever`` (SUPPORTED-only, with provenance) and
    represents each match as a justified ``KnowledgeRecord`` carrying its
    Step 17 standing and attribution. It never writes, never acquires, never
    calls a model, and fails closed (``store_unavailable`` / ``store_error``)
    rather than falling back to unvalidated knowledge.
    """

    def __init__(self, storage: Any | None = None) -> None:
        self._storage = storage

    def retrieve(self, query: str) -> RetainedKnowledge:
        from atlas.research.validated_retrieval import (
            ValidatedKnowledgeRetriever,
            ValidatedKnowledgeStatus,
        )

        result = ValidatedKnowledgeRetriever(self._storage).retrieve(query)
        status = getattr(getattr(result, "status", None), "value", "") or ""
        message = _clean(getattr(result, "message", ""), _MAX_TEXT_CHARS)
        if status == ValidatedKnowledgeStatus.STORE_UNAVAILABLE.value:
            return RetainedKnowledge(
                status=KnowledgeStatus.STORE_UNAVAILABLE,
                query=_clean(query, 200),
                message=message,
            )
        if status == ValidatedKnowledgeStatus.STORE_ERROR.value:
            return RetainedKnowledge(
                status=KnowledgeStatus.STORE_ERROR,
                query=_clean(query, 200),
                message=message,
            )

        records: list[KnowledgeRecord] = []
        for item in getattr(result, "items", ()) or ():
            claim_id = _clean(getattr(item, "claim_id", ""), 120)
            if not claim_id:
                continue
            standing = _value(getattr(item, "standing", "")) or (
                ClaimStanding.SUPPORTED.value
            )
            citations = tuple(getattr(item, "citations", ()) or ())
            evidence = tuple(
                ProvenanceEvidence(
                    evidence_id=_clean(getattr(c, "record_id", ""), 200),
                    source_uri=_clean(getattr(c, "source_uri", ""), 200),
                    source_title=_clean(getattr(c, "source_title", ""), 200),
                    source_kind=_name_of(getattr(c, "source_kind", "")),
                    section=_clean(getattr(c, "section", ""), 120),
                    page_or_line=_clean(getattr(c, "page_or_line", ""), 120),
                )
                for c in citations
            )
            records.append(
                KnowledgeRecord(
                    record_id=f"knowledge:{claim_id}",
                    claim_id=claim_id,
                    statement=_clean(
                        getattr(item, "statement", ""), _MAX_STATEMENT_CHARS
                    ),
                    standing=standing,
                    established=standing == ClaimStanding.VERIFIED.value,
                    confidence=_float(getattr(item, "claim_confidence", 0.0)),
                    verification_status=_clean(
                        getattr(item, "validation_status", ""), 32
                    ),
                    verification_score=_float(
                        getattr(item, "verification_score", 0.0)
                    ),
                    evidence=evidence[:_MAX_EVIDENCE],
                )
            )

        records.sort(key=lambda r: r.claim_id)
        return RetainedKnowledge(
            status=KnowledgeStatus.OK if records else KnowledgeStatus.EMPTY,
            query=_clean(query, 200),
            records=tuple(records[:_MAX_RECORDS]),
            message=message,
        )


def _name_of(value: Any) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return _clean(value, 64)


__all__ = [
    "KnowledgeRecord",
    "KnowledgeRetention",
    "KnowledgeStatus",
    "RefusedKnowledge",
    "RetainedKnowledge",
    "RetainedKnowledgeRetriever",
    "RETENTION_RULE",
    "retain_knowledge",
    "retention_from_outcome",
]
