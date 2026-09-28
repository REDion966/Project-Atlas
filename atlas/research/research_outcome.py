"""Atlas — Autonomous Research (Step 16).

A bounded, deterministic, model-free orchestration that acts on an ACTIONABLE
knowledge need (Step 15 ``KnowledgeNeed``) by researching through the EXISTING
authorized acquisition machinery, and returns ONE structured research result.

It is NOT a second acquisition system: the research request is executed by the
EXISTING governed D2 boundary (``atlas.research.external_acquisition``), which
owns the deny-by-default web host policy and the SSRF/bound guards, and the
actual pipeline is the EXISTING F8 ``InformationAcquisitionService`` /
``ConcreteResearchCoordinator``. This module only decides WHETHER to research,
formulates a bounded request, and REPORTS what the existing machinery returned.

Design guarantees:

* **Deterministic orchestration.** The decision to research, the request, and
  the outcome mapping are pure functions of the knowledge need plus the
  acquisition result: no AI, no randomness, no clock, no storage.
* **Model-independent authority.** No external model is consulted, and no model
  decides whether research is valid. The only authority is the EXISTING
  authorization boundary (the host policy) and the OWNER.
* **Deny-by-default preserved.** No source is enabled here and no network access
  is unlocked: an unlisted host is denied by the existing policy, and a request
  with no authorized candidate reaches nothing. Research that succeeded is NOT
  persisted, promoted or turned into knowledge by this step — the existing
  governed ingest path remains the only persistence boundary.
* **No false knowledge claims.** ``researched`` requires validated claims to
  actually have been established; an authorized source that yields nothing is
  reported as ``insufficient``, and a denied/failed attempt never claims
  knowledge.
* **Fail-closed.** A missing boundary, a raising acquirer, or an unrecognised
  result maps to ``failed``/``unknown`` — never to a knowledge claim.
* **Bounded.** Every field is length-capped and every collection is capped.

Outcome statuses (closed set):

* ``not_needed`` — the need is not a genuine knowledge need (or existing
  validated knowledge already covers it); no research was performed.
* ``researched`` — an authorized source produced validated claims.
* ``no_authorized_source`` — deny-by-default: no authorized source was
  available, so nothing was fetched.
* ``insufficient`` — an authorized source was reached but established no
  validated claim.
* ``failed`` — the research path was unavailable or failed closed.
* ``unknown`` — no grounded knowledge need was supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

#: Bounds applied so a malformed source cannot produce unbounded output.
_MAX_TEXT_CHARS: int = 400
_MAX_FINDINGS_CHARS: int = 2000
_MAX_URLS: int = 8
_MAX_SOURCES: int = 8
_MAX_EVIDENCE_ITEMS: int = 8
_MAX_FAILURES: int = 5
_MAX_REASON_CHARS: int = 400

#: The EXISTING D2 acquisition statuses (``ExternalAcquisitionStatus``).
_ACQ_EXISTING = "existing_knowledge"
_ACQ_ACQUIRED = "acquired"
_ACQ_NO_AUTHORIZED_SOURCE = "no_authorized_source"
_ACQ_FAILED = "failed"

#: Capability states (Steps 12-13) that mean the research path cannot act.
_UNAVAILABLE_STATES: frozenset[str] = frozenset({"unavailable", "blocked"})

#: Statuses the EXISTING F8 ``AcquisitionResult`` may report after research ran.
_RAN_STATUSES: frozenset[str] = frozenset({"ok", "partial"})


class ResearchStatus(str, Enum):
    """Outcome of a bounded research attempt (closed set)."""

    NOT_NEEDED = "not_needed"
    RESEARCHED = "researched"
    NO_AUTHORIZED_SOURCE = "no_authorized_source"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ResearchMechanism(str, Enum):
    """Which EXISTING mechanism produced (or would produce) the evidence."""

    NONE = "none"
    EXISTING_VALIDATED_KNOWLEDGE = "existing_validated_knowledge"
    GOVERNED_EXTERNAL_ACQUISITION = "governed_external_acquisition"


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    """The bounded research request formulated from a knowledge need."""

    objective: str
    query: str = ""
    need_kind: str = ""
    need_status: str = ""
    freshness_required: bool = False
    candidate_urls: tuple[str, ...] = ()
    authorized_urls: tuple[str, ...] = ()
    denied_urls: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "query": self.query,
            "need_kind": self.need_kind,
            "need_status": self.need_status,
            "freshness_required": self.freshness_required,
            "candidate_urls": list(self.candidate_urls),
            "authorized_urls": list(self.authorized_urls),
            "denied_urls": list(self.denied_urls),
        }


@dataclass(frozen=True, slots=True)
class ResearchSourceEvidence:
    """Per-source evidence preserved for the later provenance step."""

    source_uri: str
    total_claims: int = 0
    supporting_claims: int = 0
    contradicted_claims: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "total_claims": self.total_claims,
            "supporting_claims": self.supporting_claims,
            "contradicted_claims": self.contradicted_claims,
        }


@dataclass(frozen=True, slots=True)
class ResearchOutcome:
    """A bounded, structured research result (immutable).

    Source identity and raw evidence are preserved (``sources``,
    ``source_evidence``, ``report_ids``, bounded ``findings``) so a later,
    separately authorized provenance step can reason over them. This object
    establishes nothing by itself: ``established`` is true only when research
    actually produced validated claims.
    """

    status: ResearchStatus
    objective: str
    query: str = ""
    need_kind: str = ""
    need_status: str = ""
    actionable: bool = False
    mechanism: str = ResearchMechanism.NONE.value
    reason: str = ""
    request: Optional[ResearchRequest] = None
    acquisition_id: str = ""
    decision: str = ""
    findings: str = ""
    sources: tuple[str, ...] = ()
    denied_sources: tuple[str, ...] = ()
    source_evidence: tuple[ResearchSourceEvidence, ...] = ()
    claim_count: int = 0
    verification_count: int = 0
    verification_statuses: tuple[str, ...] = ()
    report_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    failures: tuple[tuple[str, str], ...] = ()
    evidence: tuple[str, ...] = ()

    @property
    def established(self) -> bool:
        """True only when research actually established validated knowledge."""
        return self.status is ResearchStatus.RESEARCHED and self.claim_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "objective": self.objective,
            "query": self.query,
            "need_kind": self.need_kind,
            "need_status": self.need_status,
            "actionable": self.actionable,
            "mechanism": self.mechanism,
            "reason": self.reason,
            "request": self.request.to_dict() if self.request is not None else None,
            "acquisition_id": self.acquisition_id,
            "decision": self.decision,
            "findings": self.findings,
            "sources": list(self.sources),
            "denied_sources": list(self.denied_sources),
            "source_evidence": [item.to_dict() for item in self.source_evidence],
            "claim_count": self.claim_count,
            "verification_count": self.verification_count,
            "verification_statuses": list(self.verification_statuses),
            "report_ids": list(self.report_ids),
            "confidence": self.confidence,
            "failures": [list(item) for item in self.failures],
            "evidence": list(self.evidence),
            "established": self.established,
        }


# ---------------------------------------------------------------------------
# Bounded extraction helpers
# ---------------------------------------------------------------------------


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return _clean(raw, 64).lower()


def _strings(values: Any, limit: int) -> tuple[str, ...]:
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[str] = []
    for item in items:
        text = _clean(item, 200)
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


def _source_evidence(acquisition: Any) -> tuple[ResearchSourceEvidence, ...]:
    items = getattr(acquisition, "source_evidence", ()) or ()
    out: list[ResearchSourceEvidence] = []
    try:
        for item in items:
            uri = _clean(getattr(item, "source_uri", ""), 200)
            if not uri:
                continue
            out.append(
                ResearchSourceEvidence(
                    source_uri=uri,
                    total_claims=_int(getattr(item, "total_claims", 0)),
                    supporting_claims=_int(getattr(item, "supporting_claims", 0)),
                    contradicted_claims=_int(getattr(item, "contradicted_claims", 0)),
                )
            )
    except Exception:  # fail-soft: evidence extraction never raises
        return ()
    return tuple(out[:_MAX_SOURCES])


def _failures(acquisition: Any) -> tuple[tuple[str, str], ...]:
    items = getattr(acquisition, "failures", ()) or ()
    out: list[tuple[str, str]] = []
    try:
        for item in items:
            pair = tuple(item)
            if len(pair) != 2:
                continue
            out.append((_clean(pair[0], 64), _clean(pair[1], 200)))
    except Exception:
        return ()
    return tuple(out[:_MAX_FAILURES])


def _request_for(
    need: Any, candidate_urls: tuple[str, ...]
) -> ResearchRequest:
    objective = _clean(getattr(need, "objective", ""))
    query = _clean(getattr(need, "query", ""), 200) or objective
    return ResearchRequest(
        objective=objective,
        query=query,
        need_kind=_value(getattr(need, "kind", "")),
        need_status=_value(getattr(need, "status", "")),
        freshness_required=bool(getattr(need, "freshness_required", False)),
        candidate_urls=tuple(candidate_urls[:_MAX_URLS]),
    )


def _outcome(
    status: ResearchStatus,
    need: Any,
    *,
    request: Optional[ResearchRequest],
    actionable: bool,
    mechanism: ResearchMechanism,
    reason: str,
    evidence: tuple[str, ...] = (),
    **fields: Any,
) -> ResearchOutcome:
    objective = _clean(getattr(need, "objective", ""))
    query = _clean(getattr(need, "query", ""), 200) or objective
    return ResearchOutcome(
        status=status,
        objective=objective,
        query=query,
        need_kind=_value(getattr(need, "kind", "")),
        need_status=_value(getattr(need, "status", "")),
        actionable=bool(actionable),
        mechanism=mechanism.value,
        reason=_clean(reason, _MAX_REASON_CHARS),
        request=request,
        acquisition_id=_clean(fields.get("acquisition_id", ""), 120),
        decision=_clean(fields.get("decision", ""), 32),
        findings=_clean(fields.get("findings", ""), _MAX_FINDINGS_CHARS),
        sources=_strings(fields.get("sources"), _MAX_SOURCES),
        denied_sources=_strings(fields.get("denied_sources"), _MAX_URLS),
        source_evidence=tuple(fields.get("source_evidence", ()) or ())[:_MAX_SOURCES],
        claim_count=_int(fields.get("claim_count", 0)),
        verification_count=_int(fields.get("verification_count", 0)),
        verification_statuses=_strings(
            fields.get("verification_statuses"), _MAX_SOURCES
        ),
        report_ids=_strings(fields.get("report_ids"), _MAX_SOURCES),
        confidence=_float(fields.get("confidence", 0.0)),
        failures=tuple(fields.get("failures", ()) or ())[:_MAX_FAILURES],
        evidence=tuple(evidence)[:_MAX_EVIDENCE_ITEMS],
    )


def map_acquisition_result(
    need: Any,
    acquisition_result: Any,
    *,
    request: Optional[ResearchRequest] = None,
    actionable: bool = True,
) -> ResearchOutcome:
    """Map an EXISTING ``ExternalAcquisitionResult`` to a research outcome.

    Deterministic, pure and fail-closed: an unrecognised result never becomes a
    knowledge claim. ``researched`` is reported ONLY when validated claims were
    actually established.
    """
    status = _value(getattr(acquisition_result, "status", ""))
    message = _clean(getattr(acquisition_result, "message", ""))
    denied = _strings(getattr(acquisition_result, "denied_sources", ()), _MAX_URLS)
    authorized = _strings(getattr(acquisition_result, "authorized_sources", ()), _MAX_URLS)
    base_evidence: list[str] = []
    if status:
        base_evidence.append(f"acquisition:{status}")
    if authorized:
        base_evidence.append("authorized:1")
    if denied:
        base_evidence.append("denied:1")

    if request is not None and (authorized or denied):
        request = ResearchRequest(
            objective=request.objective,
            query=request.query,
            need_kind=request.need_kind,
            need_status=request.need_status,
            freshness_required=request.freshness_required,
            candidate_urls=request.candidate_urls,
            authorized_urls=authorized,
            denied_urls=denied,
        )

    # 1. Existing validated knowledge already covers the request: no research.
    if status == _ACQ_EXISTING:
        return _outcome(
            ResearchStatus.NOT_NEEDED,
            need,
            request=request,
            actionable=actionable,
            mechanism=ResearchMechanism.EXISTING_VALIDATED_KNOWLEDGE,
            reason=(
                "Existing validated knowledge already covers the request; no "
                "research was performed."
            ),
            evidence=tuple(base_evidence),
            denied_sources=denied,
        )

    # 2. Deny-by-default: nothing was authorized, so nothing was fetched.
    if status == _ACQ_NO_AUTHORIZED_SOURCE:
        return _outcome(
            ResearchStatus.NO_AUTHORIZED_SOURCE,
            need,
            request=request,
            actionable=actionable,
            mechanism=ResearchMechanism.NONE,
            reason=(
                message
                or "No authorized source is available (deny-by-default); "
                "nothing was fetched."
            ),
            evidence=tuple(base_evidence),
            denied_sources=denied,
        )

    # 3. The acquisition path reported a failure. The EXISTING boundary attaches
    #    the inner acquisition result when the source WAS reached and simply
    #    produced nothing usable, so "reached but insufficient" is distinguished
    #    from "the path itself failed".
    if status == _ACQ_FAILED:
        reached = getattr(acquisition_result, "acquisition", None)
        if reached is not None:
            return _outcome(
                ResearchStatus.INSUFFICIENT,
                need,
                request=request,
                actionable=actionable,
                mechanism=ResearchMechanism.GOVERNED_EXTERNAL_ACQUISITION,
                reason=(
                    "The authorized source was reached but established no usable "
                    "evidence (no knowledge is claimed)."
                ),
                evidence=tuple(base_evidence + ["established:0"]),
                acquisition_id=_clean(getattr(reached, "acquisition_id", ""), 120),
                decision=_clean(getattr(reached, "decision", ""), 32),
                findings=_clean(getattr(reached, "findings", ""), _MAX_FINDINGS_CHARS),
                sources=_strings(getattr(reached, "sources", ()), _MAX_SOURCES),
                report_ids=_strings(getattr(reached, "report_ids", ()), _MAX_SOURCES),
                claim_count=_int(getattr(reached, "claim_count", 0)),
                failures=_failures(reached),
                source_evidence=_source_evidence(reached),
                denied_sources=denied,
            )
        return _outcome(
            ResearchStatus.FAILED,
            need,
            request=request,
            actionable=actionable,
            mechanism=ResearchMechanism.NONE,
            reason=message or "The authorized research path failed (fail-closed).",
            evidence=tuple(base_evidence),
            denied_sources=denied,
        )

    # 4. Research ran through the authorized path: report only what it produced.
    if status == _ACQ_ACQUIRED:
        acquisition = getattr(acquisition_result, "acquisition", None)
        claim_count = _int(getattr(acquisition, "claim_count", 0))
        sources = _strings(getattr(acquisition, "sources", ()), _MAX_SOURCES)
        ran = _value(getattr(acquisition, "status", "")) in _RAN_STATUSES
        common = dict(
            acquisition_id=_clean(getattr(acquisition, "acquisition_id", ""), 120),
            decision=_clean(getattr(acquisition, "decision", ""), 32),
            findings=_clean(getattr(acquisition, "findings", ""), _MAX_FINDINGS_CHARS),
            sources=sources,
            report_ids=_strings(getattr(acquisition, "report_ids", ()), _MAX_SOURCES),
            confidence=_float(getattr(acquisition, "confidence", 0.0)),
            source_evidence=_source_evidence(acquisition),
            failures=_failures(acquisition),
            denied_sources=denied,
        )
        if ran and claim_count > 0:
            return _outcome(
                ResearchStatus.RESEARCHED,
                need,
                request=request,
                actionable=actionable,
                mechanism=ResearchMechanism.GOVERNED_EXTERNAL_ACQUISITION,
                reason=(
                    f"Authorized research established {claim_count} validated "
                    "claim(s)."
                ),
                evidence=tuple(base_evidence + ["established:1"]),
                verification_count=_int(getattr(acquisition, "verification_count", 0)),
                verification_statuses=_strings(
                    getattr(acquisition, "verification_statuses", ()), _MAX_SOURCES
                ),
                claim_count=claim_count,
                **common,
            )
        return _outcome(
            ResearchStatus.INSUFFICIENT,
            need,
            request=request,
            actionable=actionable,
            mechanism=ResearchMechanism.GOVERNED_EXTERNAL_ACQUISITION,
            reason=(
                "The authorized source was reached but established no validated "
                "claim (no knowledge is claimed)."
            ),
            evidence=tuple(base_evidence + ["established:0"]),
            claim_count=claim_count,
            **common,
        )

    # 5. Unrecognised result: fail closed rather than assume success.
    return _outcome(
        ResearchStatus.UNKNOWN,
        need,
        request=request,
        actionable=actionable,
        mechanism=ResearchMechanism.NONE,
        reason=(
            "The research path returned an unrecognised outcome, so no knowledge "
            "is claimed (fail-closed)."
        ),
        evidence=tuple(base_evidence),
        denied_sources=denied,
    )


class ResearchOrchestrator:
    """Deterministically act on a knowledge need through existing machinery.

    ``external_acquirer`` is the EXISTING governed D2 boundary (it owns the
    deny-by-default host policy); ``capability_state_provider`` optionally
    supplies the EXISTING Step-13 state of ``research`` so an unavailable
    mechanism fails closed instead of attempting anything.
    """

    def __init__(
        self,
        *,
        external_acquirer: Any | None = None,
        capability_state_provider: Any | None = None,
    ) -> None:
        self._acquirer = external_acquirer
        self._capability_state_provider = capability_state_provider

    def research(
        self, need: Any, *, candidate_urls: Any = ()
    ) -> ResearchOutcome:
        """Research an actionable knowledge need; never raises, never guesses."""
        if need is None:
            return _outcome(
                ResearchStatus.UNKNOWN,
                need,
                request=None,
                actionable=False,
                mechanism=ResearchMechanism.NONE,
                reason="No grounded knowledge need was supplied.",
            )

        urls = _strings(candidate_urls, _MAX_URLS)
        request = _request_for(need, urls)

        # 1. Only a genuine knowledge need is researched.
        if not bool(getattr(need, "is_need", False)):
            return _outcome(
                ResearchStatus.NOT_NEEDED,
                need,
                request=request,
                actionable=False,
                mechanism=ResearchMechanism.NONE,
                reason=(
                    "The detected need is not a genuine knowledge need "
                    f"(kind: {_value(getattr(need, 'kind', '')) or 'unknown'}); "
                    "no research was performed."
                ),
            )

        # 2. The research mechanism itself must be usable (Steps 12-13).
        state = self._capability_state()
        if state in _UNAVAILABLE_STATES:
            return _outcome(
                ResearchStatus.FAILED,
                need,
                request=request,
                actionable=False,
                mechanism=ResearchMechanism.NONE,
                reason=(
                    f"The research capability is {state}, so no research was "
                    "attempted (fail-closed)."
                ),
                evidence=(f"capability:research={state}",),
            )

        actionable = True
        if self._acquirer is None:
            return _outcome(
                ResearchStatus.FAILED,
                need,
                request=request,
                actionable=False,
                mechanism=ResearchMechanism.NONE,
                reason=(
                    "No authorized acquisition boundary is wired, so no research "
                    "was attempted (fail-closed)."
                ),
            )

        # 3. Execute through the EXISTING governed acquisition boundary. The
        #    policy check happens inside it, before any I/O.
        try:
            result = self._acquirer.acquire(
                _clean(getattr(need, "objective", "")),
                candidate_urls=urls,
                knowledge_query=_clean(getattr(need, "query", ""), 200),
            )
        except Exception as exc:  # fail-closed: a raising path claims nothing
            return _outcome(
                ResearchStatus.FAILED,
                need,
                request=request,
                actionable=actionable,
                mechanism=ResearchMechanism.NONE,
                reason=f"Research failed closed ({type(exc).__name__}).",
                evidence=("acquisition:exception",),
            )
        return map_acquisition_result(
            need, result, request=request, actionable=actionable
        )

    def _capability_state(self) -> str:
        provider = self._capability_state_provider
        if provider is None:
            return ""
        try:
            return _value(provider())
        except Exception:  # fail-soft: an unknown state is not a failure
            return ""


def research_orchestrator(
    *,
    external_acquirer: Any | None = None,
    capability_state_provider: Any | None = None,
) -> ResearchOrchestrator:
    """Convenience constructor for :class:`ResearchOrchestrator`."""
    return ResearchOrchestrator(
        external_acquirer=external_acquirer,
        capability_state_provider=capability_state_provider,
    )


__all__ = [
    "ResearchMechanism",
    "ResearchOrchestrator",
    "ResearchOutcome",
    "ResearchRequest",
    "ResearchSourceEvidence",
    "ResearchStatus",
    "map_acquisition_result",
    "research_orchestrator",
]
