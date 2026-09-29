"""Atlas — Source Evaluation & Provenance (Step 17).

A bounded, deterministic, model-free layer that turns a Step 16
``ResearchOutcome`` (plus the EXISTING stored research artifacts) into an
explicit provenance chain: **research → source → evidence → claim**.

It is NOT a second persistence system and NOT a competing claim model: the
sources, claims, citations and verifications are the EXISTING ones
(``CitationRecord`` / ``KnowledgeClaim`` / ``ClaimVerification`` /
``ResearchReport``) read from the EXISTING storage, and the standing of a claim
is the EXISTING verifier's own verdict (``metadata["outcome"]`` /
``VerificationStatus``). This module only REPRESENTS and EVALUATES what Atlas
already recorded.

Design guarantees:

* **Evidence only.** Every evaluated property is something Atlas actually
  possesses: the authorization outcome of the acquisition policy, whether the
  source was used/loaded, whether its identity (URI/title) is known, whether any
  acquired claim cites it, and the existing verification verdict. Source
  credibility is never invented from domain names, popularity or any other
  heuristic, and reachability alone is never treated as truth.
* **Metadata is not evidence.** A citation (``ProvenanceEvidence``) records WHERE
  content came from; the acquired claim (``ProvenanceClaim``) is the evidence.
  A source that was used but cited by no claim is reported as evidence-less
  rather than assumed useful.
* **Retrieved ≠ established.** ``verified`` requires the EXISTING verifier to
  have corroborated the claim from two or more independent sources; a single
  supporting source is ``supported``; a claim with no supporting evidence is
  ``unverified`` (merely retrieved); conflicting evidence is ``contested`` and
  is surfaced, never silently trusted.
* **Deterministic and model-free.** Pure logic over recorded data: no AI, no
  network, no clock, no randomness, no writes, no authority.
* **Bounded and immutable.** Every field is length-capped and every collection
  is capped; all representation objects are frozen.

The result retains claim ids/statements/confidences, verification status/score,
citation identity (URI/title/kind/section) and the per-source evaluation, so a
later, separately authorized knowledge-representation step can reason over it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Bounds applied so a malformed source cannot produce unbounded output.
_MAX_TEXT_CHARS: int = 400
_MAX_STATEMENT_CHARS: int = 400
_MAX_SOURCES: int = 12
_MAX_EVIDENCE: int = 40
_MAX_CLAIMS: int = 40
_MAX_FINDINGS: int = 8
_MAX_NOTE_CHARS: int = 300

#: The EXISTING verifier verdicts (``ClaimOutcome`` names in verification
#: metadata) and their deterministic claim standing.
_VERDICT_VERIFIED = "VERIFIED"
_VERDICT_PLAUSIBLE = "PLAUSIBLE"
_VERDICT_CONTESTED = "CONTESTED"
_VERDICT_UNKNOWN = "UNKNOWN"


class SourceAuthorization(str, Enum):
    """The authorization outcome Atlas actually recorded for a source."""

    AUTHORIZED = "authorized"
    DENIED = "denied"
    UNKNOWN = "unknown"


class ClaimStanding(str, Enum):
    """How far the EXISTING verification supports an acquired claim."""

    VERIFIED = "verified"  # corroborated by 2+ independent supporting sources
    SUPPORTED = "supported"  # exactly one supporting source
    CONTESTED = "contested"  # contradicting evidence exists
    UNVERIFIED = "unverified"  # retrieved, but no supporting evidence
    UNKNOWN = "unknown"  # no verification was recorded


@dataclass(frozen=True, slots=True)
class ProvenanceSource:
    """Evaluated provenance of one source (immutable).

    Its properties are evidence, never judgement: ``authorization`` is the
    acquisition policy's outcome, ``accessed`` says the source was actually
    used, ``identity_known`` says a URI or title identifies it, and
    ``evidence_present`` says at least one acquired claim cites it.
    """

    source_uri: str
    title: str = ""
    kind: str = ""
    authorization: str = SourceAuthorization.UNKNOWN.value
    accessed: bool = False
    identity_known: bool = False
    evidence_present: bool = False
    claim_count: int = 0
    supporting_claims: int = 0
    contradicted_claims: int = 0
    findings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "title": self.title,
            "kind": self.kind,
            "authorization": self.authorization,
            "accessed": self.accessed,
            "identity_known": self.identity_known,
            "evidence_present": self.evidence_present,
            "claim_count": self.claim_count,
            "supporting_claims": self.supporting_claims,
            "contradicted_claims": self.contradicted_claims,
            "findings": list(self.findings),
        }


@dataclass(frozen=True, slots=True)
class ProvenanceEvidence:
    """One citation record: WHERE evidence was found (metadata, not evidence).

    Kept distinct from the claim so a consumer can never mistake a source
    reference for established knowledge.
    """

    evidence_id: str
    source_uri: str = ""
    source_title: str = ""
    source_kind: str = ""
    section: str = ""
    page_or_line: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_uri": self.source_uri,
            "source_title": self.source_title,
            "source_kind": self.source_kind,
            "section": self.section,
            "page_or_line": self.page_or_line,
        }


@dataclass(frozen=True, slots=True)
class ProvenanceClaim:
    """One acquired claim plus everything Atlas can evidence about it."""

    claim_id: str
    statement: str
    confidence: float = 0.0
    verification_status: str = ""
    verification_score: float = 0.0
    verification_outcome: str = ""
    standing: str = ClaimStanding.UNKNOWN.value
    source_uris: tuple[str, ...] = ()
    supporting_sources: tuple[str, ...] = ()
    contradicting_sources: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        """True only when the EXISTING verifier corroborated it (2+ sources)."""
        return self.standing == ClaimStanding.VERIFIED.value

    @property
    def merely_retrieved(self) -> bool:
        """True when the claim was obtained but no supporting evidence exists."""
        return self.standing in (
            ClaimStanding.UNVERIFIED.value,
            ClaimStanding.UNKNOWN.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "verification_score": self.verification_score,
            "verification_outcome": self.verification_outcome,
            "standing": self.standing,
            "source_uris": list(self.source_uris),
            "supporting_sources": list(self.supporting_sources),
            "contradicting_sources": list(self.contradicting_sources),
            "evidence_ids": list(self.evidence_ids),
            "findings": list(self.findings),
            "verified": self.verified,
            "merely_retrieved": self.merely_retrieved,
        }


@dataclass(frozen=True, slots=True)
class ResearchProvenance:
    """The bounded provenance chain for one research result (immutable)."""

    objective: str
    query: str = ""
    acquisition_id: str = ""
    report_ids: tuple[str, ...] = ()
    sources: tuple[ProvenanceSource, ...] = ()
    evidence: tuple[ProvenanceEvidence, ...] = ()
    claims: tuple[ProvenanceClaim, ...] = ()
    denied_sources: tuple[str, ...] = ()
    stored_reports: int = 0
    findings: tuple[str, ...] = ()

    # -- derived, evidence-based views (never invented) ---------------------

    def _claim_ids(self, standing: str) -> tuple[str, ...]:
        return tuple(c.claim_id for c in self.claims if c.standing == standing)

    @property
    def established_claim_ids(self) -> tuple[str, ...]:
        """Claims the EXISTING verifier corroborated (2+ supporting sources)."""
        return self._claim_ids(ClaimStanding.VERIFIED.value)

    @property
    def supported_claim_ids(self) -> tuple[str, ...]:
        """Claims supported by exactly one source (retrieved and supported)."""
        return self._claim_ids(ClaimStanding.SUPPORTED.value)

    @property
    def contested_claim_ids(self) -> tuple[str, ...]:
        """Claims with conflicting evidence (surfaced, never trusted away)."""
        return self._claim_ids(ClaimStanding.CONTESTED.value)

    @property
    def unverified_claim_ids(self) -> tuple[str, ...]:
        """Claims retrieved without supporting evidence."""
        return self._claim_ids(ClaimStanding.UNVERIFIED.value) + self._claim_ids(
            ClaimStanding.UNKNOWN.value
        )

    @property
    def has_conflicts(self) -> bool:
        """True when material conflicting evidence was recorded."""
        return bool(self.contested_claim_ids) or any(
            source.contradicted_claims for source in self.sources
        )

    @property
    def has_insufficient_provenance(self) -> bool:
        """True when the provenance cannot fully support what was retrieved."""
        if not self.claims and self.stored_reports == 0:
            return True
        if self.unverified_claim_ids:
            return True
        if any(
            source.evidence_present is False
            and source.authorization != SourceAuthorization.DENIED.value
            for source in self.sources
        ):
            return True
        return any("no citation" in finding for c in self.claims for finding in c.findings)

    @property
    def retained_for_learning(self) -> bool:
        """True when claim-level provenance was retained for a later step."""
        return bool(self.claims) and all(
            claim.claim_id and claim.statement for claim in self.claims
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "query": self.query,
            "acquisition_id": self.acquisition_id,
            "report_ids": list(self.report_ids),
            "sources": [s.to_dict() for s in self.sources],
            "evidence": [e.to_dict() for e in self.evidence],
            "claims": [c.to_dict() for c in self.claims],
            "denied_sources": list(self.denied_sources),
            "stored_reports": self.stored_reports,
            "findings": list(self.findings),
            "established_claim_ids": list(self.established_claim_ids),
            "supported_claim_ids": list(self.supported_claim_ids),
            "contested_claim_ids": list(self.contested_claim_ids),
            "unverified_claim_ids": list(self.unverified_claim_ids),
            "has_conflicts": self.has_conflicts,
            "has_insufficient_provenance": self.has_insufficient_provenance,
            "retained_for_learning": self.retained_for_learning,
        }


# ---------------------------------------------------------------------------
# Bounded extraction helpers
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


def _name(value: Any) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return _clean(value, limit=64)


def _strings(values: Any, limit: int, width: int = 200) -> tuple[str, ...]:
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[str] = []
    for item in items:
        text = _clean(item, width)
        if text and text not in out:
            out.append(text)
    return tuple(out[:limit])


def _int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


def _standing(verification: Any) -> str:
    """Derive the claim standing from the EXISTING verification (never guess)."""
    if verification is None:
        return ClaimStanding.UNKNOWN.value
    metadata = getattr(verification, "metadata", None) or {}
    outcome = str(metadata.get("outcome", "") or "").strip().upper()
    if outcome == _VERDICT_VERIFIED:
        return ClaimStanding.VERIFIED.value
    if outcome == _VERDICT_PLAUSIBLE:
        return ClaimStanding.SUPPORTED.value
    if outcome == _VERDICT_CONTESTED:
        return ClaimStanding.CONTESTED.value
    if outcome == _VERDICT_UNKNOWN:
        return ClaimStanding.UNVERIFIED.value
    # Fall back to the stored status only (no verdict available).
    status = _name(getattr(verification, "status", ""))
    if status == "SUPPORTED":
        return ClaimStanding.SUPPORTED.value
    if status == "CONTRADICTED":
        return ClaimStanding.CONTESTED.value
    if status == "UNVERIFIED":
        return ClaimStanding.UNVERIFIED.value
    return ClaimStanding.UNKNOWN.value


def _claims_and_evidence(
    reports: Any,
) -> tuple[
    list[ProvenanceClaim],
    list[ProvenanceEvidence],
    dict[str, dict[str, Any]],
    dict[str, dict[str, str]],
]:
    """Read claim/citation/verification provenance from EXISTING reports."""
    try:
        from atlas.research.validated_retrieval import select_latest_verifications
    except Exception:  # pragma: no cover - defensive
        select_latest_verifications = None

    raw_claims: list[Any] = []
    raw_verifications: list[Any] = []
    for report in reports or ():
        try:
            raw_claims.extend(list(getattr(report, "claims", ()) or ()))
        except TypeError:
            continue
        try:
            raw_verifications.extend(list(getattr(report, "verifications", ()) or ()))
        except TypeError:
            continue

    latest: dict[str, Any] = {}
    if select_latest_verifications is not None and raw_verifications:
        try:
            latest = select_latest_verifications(raw_verifications) or {}
        except Exception:
            latest = {}
    if not latest:
        for verification in raw_verifications:
            claim_id = _clean(getattr(verification, "claim_id", ""), 120)
            if claim_id:
                latest.setdefault(claim_id, verification)

    claims: list[ProvenanceClaim] = []
    evidence: list[ProvenanceEvidence] = []
    seen_evidence: set[str] = set()
    citation_meta: dict[str, dict[str, str]] = {}
    for raw in raw_claims[:_MAX_CLAIMS]:
        claim_id = _clean(getattr(raw, "claim_id", ""), 120)
        if not claim_id:
            continue
        citations = list(getattr(raw, "citations", ()) or ())
        source_uris: list[str] = []
        evidence_ids: list[str] = []
        for citation in citations:
            record_id = _clean(getattr(citation, "record_id", ""), 200)
            uri = _clean(getattr(citation, "source_uri", ""), 200)
            if uri and uri not in source_uris:
                source_uris.append(uri)
            if record_id and record_id not in evidence_ids:
                evidence_ids.append(record_id)
            citation_title = _clean(getattr(citation, "source_title", ""), 200)
            citation_kind = _name(getattr(citation, "source_kind", ""))
            if uri and (citation_title or citation_kind):
                slot = citation_meta.setdefault(uri, {"title": "", "kind": ""})
                slot["title"] = slot["title"] or citation_title
                slot["kind"] = slot["kind"] or citation_kind
            if record_id and record_id not in seen_evidence:
                seen_evidence.add(record_id)
                evidence.append(
                    ProvenanceEvidence(
                        evidence_id=record_id,
                        source_uri=uri,
                        source_title=citation_title,
                        source_kind=citation_kind,
                        section=_clean(getattr(citation, "section", ""), 120),
                        page_or_line=_clean(getattr(citation, "page_or_line", ""), 120),
                    )
                )
        verification = latest.get(claim_id)
        metadata = getattr(verification, "metadata", None) or {}
        findings: list[str] = []
        if not citations:
            findings.append(
                "no citation recorded for this claim (the provenance link is missing)"
            )
        standing = _standing(verification)
        if standing in (
            ClaimStanding.UNVERIFIED.value,
            ClaimStanding.UNKNOWN.value,
        ):
            findings.append(
                "retrieved without supporting evidence (not established knowledge)"
            )
        if standing == ClaimStanding.CONTESTED.value:
            findings.append("conflicting evidence was recorded for this claim")
        claims.append(
            ProvenanceClaim(
                claim_id=claim_id,
                statement=_clean(
                    getattr(raw, "statement", ""), _MAX_STATEMENT_CHARS
                ),
                confidence=_float(getattr(raw, "confidence", 0.0)),
                verification_status=_name(getattr(verification, "status", "")),
                verification_score=_float(getattr(verification, "score", 0.0)),
                verification_outcome=_clean(metadata.get("outcome", ""), 32).upper(),
                standing=standing,
                source_uris=tuple(source_uris[:_MAX_SOURCES]),
                supporting_sources=_strings(metadata.get("supporting"), _MAX_SOURCES),
                contradicting_sources=_strings(
                    metadata.get("contradicting"), _MAX_SOURCES
                ),
                evidence_ids=tuple(evidence_ids[:_MAX_EVIDENCE]),
                findings=tuple(findings[:_MAX_FINDINGS]),
            )
        )

    # Per-source tallies derived from the claims themselves (deterministic).
    tallies: dict[str, dict[str, Any]] = {}
    for claim in claims:
        for uri in claim.source_uris:
            entry = tallies.setdefault(
                uri, {"claims": 0, "supporting": 0, "contradicted": 0}
            )
            entry["claims"] += 1
        for uri in claim.source_uris:
            if claim.standing in (
                ClaimStanding.VERIFIED.value,
                ClaimStanding.SUPPORTED.value,
            ):
                tallies[uri]["supporting"] += 1
            elif claim.standing == ClaimStanding.CONTESTED.value:
                tallies[uri]["contradicted"] += 1
    return claims, evidence[:_MAX_EVIDENCE], tallies, citation_meta


def _sources(
    used_sources: tuple[str, ...],
    denied_sources: tuple[str, ...],
    evidence_by_source: dict[str, Any],
    tallies: dict[str, dict[str, Any]],
    citation_meta: dict[str, dict[str, str]],
) -> tuple[ProvenanceSource, ...]:
    """Deterministically evaluate each source from recorded evidence only."""
    order: list[str] = []
    meta: dict[str, dict[str, Any]] = {}
    denied = set(denied_sources)

    def _slot(uri: str) -> dict[str, Any]:
        if uri not in meta:
            meta[uri] = {"title": "", "kind": ""}
            order.append(uri)
        return meta[uri]

    for uri in used_sources:
        _slot(uri)
    for uri in denied_sources:
        _slot(uri)
    for uri, item in evidence_by_source.items():
        slot = _slot(uri)
        slot["title"] = _clean(getattr(item, "source_title", ""), 200)
        slot["kind"] = _name(getattr(item, "source_kind", ""))
    for uri, recorded in citation_meta.items():
        slot = _slot(uri)
        slot["title"] = slot["title"] or _clean(recorded.get("title", ""), 200)
        slot["kind"] = slot["kind"] or _clean(recorded.get("kind", ""), 64)
    for uri in tallies:
        _slot(uri)

    out: list[ProvenanceSource] = []
    for uri in order[:_MAX_SOURCES]:
        slot = meta[uri]
        facts = evidence_by_source.get(uri)
        tally = tallies.get(uri) or {"claims": 0, "supporting": 0, "contradicted": 0}
        is_denied = uri in denied
        accessed = (uri in used_sources) or uri in tallies
        claim_count = _int(getattr(facts, "total_claims", 0)) or tally["claims"]
        supporting = _int(getattr(facts, "supporting_claims", 0)) or tally["supporting"]
        contradicted = (
            _int(getattr(facts, "contradicted_claims", 0)) or tally["contradicted"]
        )
        evidence_present = claim_count > 0
        title = slot["title"]
        kind = slot["kind"]
        findings: list[str] = []
        if is_denied:
            findings.append(
                "denied by the acquisition authorization policy; nothing was "
                "fetched from it"
            )
        elif not accessed:
            findings.append("not used by this research result")
        if accessed and not evidence_present:
            findings.append(
                "used but no acquired claim cites it (no evidence recorded)"
            )
        if not (uri or title):
            findings.append("source identity is unknown (no URI or title recorded)")
        if contradicted:
            findings.append(
                f"{contradicted} claim(s) citing it carry conflicting evidence"
            )
        out.append(
            ProvenanceSource(
                source_uri=uri,
                title=title,
                kind=kind,
                authorization=(
                    SourceAuthorization.DENIED.value
                    if is_denied
                    else (
                        SourceAuthorization.AUTHORIZED.value
                        if accessed
                        else SourceAuthorization.UNKNOWN.value
                    )
                ),
                accessed=accessed,
                identity_known=bool(uri or title),
                evidence_present=evidence_present,
                claim_count=claim_count,
                supporting_claims=supporting,
                contradicted_claims=contradicted,
                findings=tuple(findings[:_MAX_FINDINGS]),
            )
        )
    return tuple(out)


def build_research_provenance(
    *,
    objective: str,
    query: str = "",
    acquisition_id: str = "",
    report_ids: Any = (),
    used_sources: Any = (),
    denied_sources: Any = (),
    source_evidence: Any = (),
    reports: Any = (),
) -> ResearchProvenance:
    """Build the bounded provenance chain from recorded research artifacts.

    Pure and deterministic. ``reports`` are the EXISTING stored
    ``ResearchReport`` objects (or any object exposing ``claims`` /
    ``verifications``); nothing is written and nothing is invented.
    """
    used = _strings(used_sources, _MAX_SOURCES)
    denied = _strings(denied_sources, _MAX_SOURCES)
    report_id_list = _strings(report_ids, _MAX_SOURCES)
    report_list = list(reports or ())

    evidence_by_source: dict[str, Any] = {}
    for item in source_evidence or ():
        uri = _clean(getattr(item, "source_uri", ""), 200)
        if uri and uri not in evidence_by_source:
            evidence_by_source[uri] = item

    claims, evidence, tallies, citation_meta = _claims_and_evidence(report_list)
    sources = _sources(used, denied, evidence_by_source, tallies, citation_meta)

    findings: list[str] = []
    if not report_list:
        findings.append(
            "no stored research report was available; provenance is limited to "
            "the aggregate research result (claim-level provenance is missing)"
        )
    if denied:
        findings.append(
            f"{len(denied)} source(s) were denied by the authorization policy and "
            "contributed no evidence"
        )
    contested = [c for c in claims if c.standing == ClaimStanding.CONTESTED.value]
    if contested:
        findings.append(
            f"{len(contested)} claim(s) carry conflicting evidence and are not "
            "treated as trusted knowledge"
        )
    unverified = [
        c
        for c in claims
        if c.standing in (ClaimStanding.UNVERIFIED.value, ClaimStanding.UNKNOWN.value)
    ]
    if unverified:
        findings.append(
            f"{len(unverified)} claim(s) were retrieved without supporting evidence"
        )
    verified = [c for c in claims if c.standing == ClaimStanding.VERIFIED.value]
    if claims and not verified:
        findings.append(
            "no claim reached multi-source corroboration (verified); the evidence "
            "is single-source at best"
        )

    return ResearchProvenance(
        objective=_clean(objective),
        query=_clean(query, 200),
        acquisition_id=_clean(acquisition_id, 120),
        report_ids=report_id_list,
        sources=sources,
        evidence=tuple(evidence)[:_MAX_EVIDENCE],
        claims=tuple(claims)[:_MAX_CLAIMS],
        denied_sources=denied,
        stored_reports=len(report_list),
        findings=tuple(findings[:_MAX_FINDINGS]),
    )


def provenance_from_outcome(
    outcome: Any, *, reports: Any = ()
) -> ResearchProvenance:
    """Build provenance for a Step 16 ``ResearchOutcome`` (never raises)."""
    if outcome is None:
        return build_research_provenance(objective="")
    return build_research_provenance(
        objective=_clean(getattr(outcome, "objective", "")),
        query=_clean(getattr(outcome, "query", ""), 200),
        acquisition_id=_clean(getattr(outcome, "acquisition_id", ""), 120),
        report_ids=getattr(outcome, "report_ids", ()) or (),
        used_sources=getattr(outcome, "sources", ()) or (),
        denied_sources=getattr(outcome, "denied_sources", ()) or (),
        source_evidence=getattr(outcome, "source_evidence", ()) or (),
        reports=reports,
    )


__all__ = [
    "ClaimStanding",
    "ProvenanceClaim",
    "ProvenanceEvidence",
    "ProvenanceSource",
    "ResearchProvenance",
    "SourceAuthorization",
    "build_research_provenance",
    "provenance_from_outcome",
]
