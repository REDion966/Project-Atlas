"""Atlas — Knowledge Refresh (Step 20).

A bounded, deterministic, model-free capability that identifies retained
knowledge whose EXISTING temporal/freshness evidence says it is stale or needs
revalidation, formulates a bounded refresh request from the knowledge's own
provenance, routes it through the EXISTING governed acquisition pipeline, and
decides — from the Step 17-18 evidence/standing rules — whether the refreshed
evidence may replace the retained knowledge.

It is NOT a second research or storage system and NOT a scheduler: the request is
built from the EXISTING provenance/source information, the authorization decision
is the EXISTING D2 host policy, the execution is the EXISTING F8 acquisition
pipeline, the refreshed evidence is read back through the EXISTING Step 17
provenance and Step 18 retention rules, and nothing is written, deleted,
replaced, promoted or scheduled here.

Refresh is never "overwrite because newer data was fetched":

* the ORIGINAL knowledge and its provenance are preserved — the store is never
  rewritten, and the outcome always reports the original record;
* replacement is ACCEPTED only when the refreshed evidence is JUSTIFIED under
  the Step 18 retention rule (standing ``verified``/``supported`` WITH a
  provenance link) AND its standing is at least as strong as the retained
  knowledge's;
* weaker, unjustified, absent, denied, insufficient or failed refresh attempts
  preserve the original and say so explicitly.

Statuses (closed set): ``not_required`` (fresh — no attempt), ``review_required``
(temporal standing unknown — a governed review, nothing fetched),
``refreshed`` (a stronger-or-equal justified replacement was accepted),
``preserved`` (evidence arrived but was weaker/unjustified — original kept),
``no_authorized_source`` (denied/unavailable source, nothing fetched),
``insufficient`` (the refresh ran but established nothing usable), ``failed``
(the refresh path failed closed) and ``unknown`` (nothing grounded to act on).

Guarantees: pure orchestration over recorded evidence with an injectable clock
(no AI, no network of its own, no clock of its own, no writes, no authority),
immutable bounded objects, deterministic ordering, and fail-closed behaviour
throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from atlas.research.knowledge_representation import (
    KnowledgeRecord,
    retain_knowledge,
)
from atlas.research.provenance import ClaimStanding, build_research_provenance
from atlas.research.temporal import (
    TemporalStatus,
    assess_record_temporal,
    knowledge_ref_for,
    record_source_uris,
)

#: Bounds (a malformed record or run can never produce unbounded output).
_MAX_REFRESHES: int = 3
_MAX_SOURCES: int = 8
_MAX_FINDINGS: int = 6
_MAX_REASON_CHARS: int = 300
_MAX_TEXT_CHARS: int = 300


def _web_schemes() -> frozenset[str]:
    """The EXISTING web scheme allowlist (never a new list)."""
    try:
        from atlas.research.source_catalog import WEB_SCHEMES

        return frozenset(WEB_SCHEMES)
    except Exception:  # pragma: no cover - defensive
        return frozenset({"http", "https"})


#: The EXISTING web scheme allowlist, used only to decide which recorded sources
#: the EXISTING web authorization policy has jurisdiction over.
_WEB_SCHEMES: frozenset[str] = _web_schemes()

#: Standing strength, used ONLY to refuse a weaker replacement.
_STANDING_RANK: dict[str, int] = {
    ClaimStanding.VERIFIED.value: 3,
    ClaimStanding.SUPPORTED.value: 2,
    ClaimStanding.CONTESTED.value: 1,
    ClaimStanding.UNVERIFIED.value: 0,
    ClaimStanding.UNKNOWN.value: 0,
}

#: The refresh rule, stated once so callers can report it verbatim.
REFRESH_RULE: str = (
    "Refresh re-acquires evidence through the existing governed acquisition "
    "pipeline and replaces retained knowledge ONLY when the refreshed evidence "
    "is justified (verified or supported WITH a provenance link) and at least as "
    "strong as the existing standing. Otherwise the original knowledge and its "
    "provenance are preserved."
)


class RefreshStatus(str, Enum):
    """Outcome of a bounded refresh attempt (closed set)."""

    NOT_REQUIRED = "not_required"
    REVIEW_REQUIRED = "review_required"
    REFRESHED = "refreshed"
    PRESERVED = "preserved"
    NO_AUTHORIZED_SOURCE = "no_authorized_source"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ReplacementDecision(str, Enum):
    """Whether refreshed evidence may stand in for the retained knowledge."""

    NONE = "none"
    ACCEPTED = "accepted"
    WEAKER_EVIDENCE = "weaker_evidence"
    UNJUSTIFIED = "unjustified"
    NO_CANDIDATE = "no_candidate"


@dataclass(frozen=True, slots=True)
class RefreshRequest:
    """The bounded refresh request derived from existing knowledge provenance."""

    record_id: str
    claim_id: str
    statement: str
    standing: str
    temporal_status: str
    required: bool
    action: str
    query: str
    sources: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "claim_id": self.claim_id,
            "statement": self.statement,
            "standing": self.standing,
            "temporal_status": self.temporal_status,
            "required": self.required,
            "action": self.action,
            "query": self.query,
            "sources": list(self.sources),
            "reasons": list(self.reasons),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    """The bounded outcome of one refresh attempt (immutable).

    ``original`` is the retained knowledge exactly as it was; ``replacement`` is
    populated ONLY when a justified, at-least-as-strong replacement was accepted.
    """

    status: RefreshStatus
    request: RefreshRequest
    decision: str = ReplacementDecision.NONE.value
    original: KnowledgeRecord | None = None
    replacement: KnowledgeRecord | None = None
    candidate_standing: str = ""
    fetch_sources: tuple[str, ...] = ()
    denied_sources: tuple[str, ...] = ()
    report_ids: tuple[str, ...] = ()
    claim_count: int = 0
    reason: str = ""
    findings: tuple[str, ...] = ()

    @property
    def replaced(self) -> bool:
        """True only when a validated, at-least-as-strong replacement was taken."""
        return self.status is RefreshStatus.REFRESHED and self.replacement is not None

    @property
    def original_preserved(self) -> bool:
        """True whenever the original knowledge remains the retained knowledge."""
        return self.status is not RefreshStatus.REFRESHED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "request": self.request.to_dict(),
            "decision": self.decision,
            "original": self.original.to_dict() if self.original is not None else None,
            "replacement": (
                self.replacement.to_dict() if self.replacement is not None else None
            ),
            "candidate_standing": self.candidate_standing,
            "fetch_sources": list(self.fetch_sources),
            "denied_sources": list(self.denied_sources),
            "report_ids": list(self.report_ids),
            "claim_count": self.claim_count,
            "reason": self.reason,
            "findings": list(self.findings),
            "replaced": self.replaced,
            "original_preserved": self.original_preserved,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeRefresh:
    """The bounded refresh pass over retained knowledge (immutable)."""

    query: str
    outcomes: tuple[RefreshOutcome, ...] = ()
    findings: tuple[str, ...] = ()

    def _count(self, status: RefreshStatus) -> int:
        return sum(1 for o in self.outcomes if o.status is status)

    @property
    def refreshed_count(self) -> int:
        return self._count(RefreshStatus.REFRESHED)

    @property
    def preserved_count(self) -> int:
        return self._count(RefreshStatus.PRESERVED) + self._count(
            RefreshStatus.INSUFFICIENT
        ) + self._count(RefreshStatus.FAILED) + self._count(
            RefreshStatus.NO_AUTHORIZED_SOURCE
        )

    @property
    def attempted(self) -> int:
        return sum(1 for o in self.outcomes if o.request.required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "refreshed_count": self.refreshed_count,
            "preserved_count": self.preserved_count,
            "attempted": self.attempted,
            "findings": list(self.findings),
            "refresh_rule": REFRESH_RULE,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _value(value: Any, limit: int = 48) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return ""
    return _clean(raw, limit)


def _action_name(value: Any) -> str:
    """The lowercased NAME of an action enum (``RecommendedAction`` uses ints)."""
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.strip().lower()
    return _clean(value, 32).lower()


def _rank(standing: Any) -> int:
    return _STANDING_RANK.get(_value(standing), 0)


def _scheme(spec: str) -> str:
    """The URI scheme of a source spec, or ``""`` when it has none."""
    text = spec.strip()
    if "://" not in text:
        return ""
    return text.split("://", 1)[0].strip().lower()


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


def build_refresh_request(
    record: Any,
    *,
    temporal: Any | None = None,
    assessor: Any | None = None,
    now: Any = None,
) -> RefreshRequest:
    """Derive a bounded refresh request from existing knowledge provenance.

    Uses the EXISTING freshness assessor (via the EXISTING ``KnowledgeRef``) to
    decide whether refresh/revalidation is appropriate, and the EXISTING recorded
    source identity as the re-acquisition list. Pure, deterministic, read-only
    and fail-closed: with no grounded freshness signal nothing is requested.
    """
    record_id = _clean(getattr(record, "record_id", ""), 120)
    claim_id = _clean(getattr(record, "claim_id", ""), 120)
    statement = _clean(getattr(record, "statement", ""), 200)
    standing = _value(getattr(record, "standing", ""))
    query = (
        _clean(getattr(record, "query", ""), 200)
        or _clean(getattr(record, "objective", ""), 200)
        or statement
    )
    sources = tuple(record_source_uris(record))[:_MAX_SOURCES]

    view = temporal
    if view is None:
        view = assess_record_temporal(record, assessor=assessor, now=now)
    temporal_status = _value(getattr(view, "status", ""))

    action = "none"
    reasons: tuple[str, ...] = tuple(getattr(view, "reasons", ()) or ())
    reference = knowledge_ref_for(record)
    if reference is not None:
        try:
            engine = assessor
            if engine is None:
                from atlas.evolution.freshness.assessor import (
                    KnowledgeFreshnessAssessor,
                )

                engine = KnowledgeFreshnessAssessor()
            candidates = engine.find_stale_candidates([reference], now=now)
        except Exception:  # fail-closed: no candidate, no request
            candidates = []
        if candidates:
            action = (
                _action_name(getattr(candidates[0], "recommended_action", "")) or action
            )
            # the EXISTING candidate's own provenance refs are authoritative
            refs = tuple(getattr(candidates[0], "provenance_refs", ()) or ())
            if refs:
                sources = refs[:_MAX_SOURCES]
            if not reasons:
                reasons = tuple(
                    getattr(r, "name", "") for r in (getattr(candidates[0], "reasons", ()) or ())
                )

    required = action in ("research", "verify") and temporal_status in (
        TemporalStatus.HISTORICAL.value,
    )
    reason = ""
    if action in ("research", "verify") and not required:
        reason = (
            "the temporal standing is not stale, so no refresh is requested"
        )
    elif not required:
        reason = "the EXISTING freshness evidence does not call for refresh"

    return RefreshRequest(
        record_id=record_id,
        claim_id=claim_id,
        statement=statement,
        standing=standing,
        temporal_status=temporal_status,
        required=required,
        action=action,
        query=query,
        sources=sources,
        reasons=reasons,
        reason=_clean(reason, _MAX_REASON_CHARS),
    )


def plan_refresh(
    records: Any,
    *,
    assessor: Any | None = None,
    now: Any = None,
) -> tuple[RefreshRequest, ...]:
    """Deterministic refresh requests for many records (ordered by claim id)."""
    ordered = sorted(
        (r for r in records or ()),
        key=lambda r: _clean(getattr(r, "claim_id", ""), 120),
    )
    return tuple(
        build_refresh_request(record, assessor=assessor, now=now)
        for record in ordered[:_MAX_REFRESHES]
    )


# ---------------------------------------------------------------------------
# Replacement comparison
# ---------------------------------------------------------------------------


def compare_replacement(
    original: Any, candidate: Any | None
) -> tuple[ReplacementDecision, str]:
    """Decide whether ``candidate`` may replace ``original`` (pure, fail-closed).

    Accepts ONLY a justified candidate (the Step 18 retention rule already
    filtered it, and its evidence must be present) whose standing is at least as
    strong as the original's. Everything else preserves the original.
    """
    if candidate is None:
        return (
            ReplacementDecision.NO_CANDIDATE,
            "no refreshed evidence was established, so the original is preserved",
        )
    original_standing = _value(getattr(original, "standing", ""))
    candidate_standing = _value(getattr(candidate, "standing", ""))
    if not bool(getattr(candidate, "justified", False)) or not tuple(
        getattr(candidate, "evidence", ()) or ()
    ):
        return (
            ReplacementDecision.UNJUSTIFIED,
            "the refreshed evidence is not justified under the Step 18 retention "
            "rule (no standing, no provenance link), so the original is preserved",
        )
    if _rank(candidate_standing) < _rank(original_standing):
        return (
            ReplacementDecision.WEAKER_EVIDENCE,
            f"the refreshed evidence is weaker ({candidate_standing or 'unknown'}) "
            f"than the retained knowledge ({original_standing or 'unknown'}), so "
            "the original is preserved",
        )
    return (
        ReplacementDecision.ACCEPTED,
        f"the refreshed evidence is justified and at least as strong "
        f"({candidate_standing or 'unknown'} vs {original_standing or 'unknown'})",
    )


def _best_candidate(records: Any) -> Any | None:
    """Strongest justified candidate; ties broken by claim id (deterministic)."""
    candidates = [r for r in records or ()]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (-_rank(getattr(r, "standing", "")), _clean(getattr(r, "claim_id", ""), 120)))
    return candidates[0]


# ---------------------------------------------------------------------------
# Refresh execution
# ---------------------------------------------------------------------------


class KnowledgeRefresher:
    """Route a refresh request through the EXISTING governed acquisition path.

    ``acquirer`` is the EXISTING D2 boundary and is used ONLY for its
    authorization decision (``authorize``, I/O-free, deny-by-default);
    ``acquisition`` is the EXISTING F8 pipeline that performs the bounded
    re-acquisition. The D2 acquirer's "existing validated knowledge already
    covers it" short-circuit is deliberately NOT used here: re-validating stale
    evidence is exactly the case it exists to short-circuit for question
    answering, so refresh authorizes through D2 and executes through F8, both
    EXISTING boundaries, and never fetches an unauthorized source.
    """

    def __init__(
        self,
        *,
        acquirer: Any | None = None,
        acquisition: Any | None = None,
        storage: Any | None = None,
        assessor: Any | None = None,
        capability_state_provider: Any | None = None,
        max_refreshes: int = _MAX_REFRESHES,
    ) -> None:
        self._acquirer = acquirer
        self._acquisition = acquisition
        self._storage = storage
        self._assessor = assessor
        self._capability_state_provider = capability_state_provider
        self._max_refreshes = max(1, int(max_refreshes))

    # -- planning ----------------------------------------------------------

    def plan(self, records: Any, *, now: Any = None) -> tuple[RefreshRequest, ...]:
        return plan_refresh(records, assessor=self._assessor, now=now)

    # -- execution ---------------------------------------------------------

    def refresh(
        self,
        record: Any,
        *,
        candidate_urls: Any = (),
        now: Any = None,
    ) -> RefreshOutcome:
        """Refresh one retained record; never raises and never guesses."""
        request = build_refresh_request(
            record, assessor=self._assessor, now=now
        )
        if not request.required:
            status = (
                RefreshStatus.REVIEW_REQUIRED
                if request.temporal_status
                in (TemporalStatus.UNDATED.value, TemporalStatus.UNKNOWN.value)
                else RefreshStatus.NOT_REQUIRED
            )
            reason = (
                "the temporal standing of this knowledge is unknown, so no refresh "
                "was attempted (a governed review is required)"
                if status is RefreshStatus.REVIEW_REQUIRED
                else "the retained knowledge is current relative to its "
                "acquisition; no refresh is required"
            )
            return self._outcome(
                status,
                request,
                record,
                reason=reason,
            )

        sources = tuple(candidate_urls or ()) or request.sources
        sources = tuple(
            dict.fromkeys(s for s in sources if isinstance(s, str) and s.strip())
        )[:_MAX_SOURCES]
        if not sources:
            return self._outcome(
                RefreshStatus.NO_AUTHORIZED_SOURCE,
                request,
                record,
                reason=(
                    "no source information was recorded for this knowledge, so "
                    "nothing could be re-acquired (deny-by-default)"
                ),
            )

        authorized, denied = self._authorize(sources)
        permitted, passed_through = self._split(authorized, denied, sources)
        if not permitted:
            return self._outcome(
                RefreshStatus.NO_AUTHORIZED_SOURCE,
                request,
                record,
                denied=denied,
                reason=(
                    "every recorded source was denied by the acquisition "
                    "authorization policy; nothing was fetched"
                ),
            )

        state = self._capability_state()
        if state in ("unavailable", "blocked"):
            return self._outcome(
                RefreshStatus.FAILED,
                request,
                record,
                denied=denied,
                reason=(
                    f"the research capability is {state}, so no refresh was "
                    "attempted (fail-closed)"
                ),
            )
        if self._acquisition is None:
            return self._outcome(
                RefreshStatus.FAILED,
                request,
                record,
                denied=denied,
                reason="no acquisition pipeline is wired (fail-closed)",
            )

        try:
            result = self._acquisition.acquire(
                question=request.query, sources=tuple(permitted)
            )
        except Exception as exc:  # fail-closed: the original is untouched
            return self._outcome(
                RefreshStatus.FAILED,
                request,
                record,
                fetch=tuple(permitted),
                denied=denied,
                reason=f"the refresh failed closed ({type(exc).__name__})",
            )

        report_ids = tuple(
            str(r) for r in (getattr(result, "report_ids", ()) or ()) if str(r)
        )
        claim_count = int(getattr(result, "claim_count", 0) or 0)
        findings: list[str] = []
        if passed_through:
            findings.append(
                f"{len(passed_through)} recorded source(s) are not web sources and "
                "were passed to the existing resolver unchanged"
            )

        # Read the refreshed evidence back through the EXISTING Step 17
        # provenance and Step 18 retention rules.
        candidates: tuple[Any, ...] = ()
        if report_ids:
            provenance = build_research_provenance(
                objective=request.query,
                query=request.query,
                report_ids=report_ids,
                used_sources=tuple(getattr(result, "sources", ()) or ()),
                source_evidence=tuple(getattr(result, "source_evidence", ()) or ()),
                reports=self._reports_for(report_ids),
            )
            candidates = tuple(retain_knowledge(provenance).records)

        candidate = _best_candidate(candidates)
        decision, decision_reason = compare_replacement(record, candidate)
        findings.append(decision_reason)

        if decision is ReplacementDecision.ACCEPTED:
            return self._outcome(
                RefreshStatus.REFRESHED,
                request,
                record,
                decision=decision,
                replacement=candidate,
                candidate_standing=_value(getattr(candidate, "standing", "")),
                fetch=tuple(permitted),
                denied=denied,
                report_ids=report_ids,
                claim_count=claim_count,
                reason=(
                    "an authorized refresh produced justified, at-least-as-strong "
                    "evidence, which replaces the retained knowledge"
                ),
                findings=findings,
            )

        status = (
            RefreshStatus.PRESERVED
            if candidates
            else RefreshStatus.INSUFFICIENT
        )
        reason = (
            "the refresh produced evidence that cannot replace the retained "
            "knowledge, so the original is preserved"
            if status is RefreshStatus.PRESERVED
            else "the refresh established no justified evidence, so the original "
            "is preserved"
        )
        return self._outcome(
            status,
            request,
            record,
            decision=decision,
            candidate_standing=_value(getattr(candidate, "standing", ""))
            if candidate is not None
            else "",
            fetch=tuple(permitted),
            denied=denied,
            report_ids=report_ids,
            claim_count=claim_count,
            reason=reason,
            findings=findings,
        )

    def refresh_all(
        self,
        records: Any,
        *,
        candidate_urls: Any = (),
        now: Any = None,
    ) -> KnowledgeRefresh:
        """Refresh up to ``max_refreshes`` retained records (bounded, ordered)."""
        ordered = sorted(
            (r for r in records or ()),
            key=lambda r: _clean(getattr(r, "claim_id", ""), 120),
        )[: self._max_refreshes]
        outcomes = tuple(
            self.refresh(record, candidate_urls=candidate_urls, now=now)
            for record in ordered
        )
        findings: list[str] = []
        if not outcomes:
            findings.append("no retained knowledge was available to refresh")
        else:
            refreshed = sum(1 for o in outcomes if o.status is RefreshStatus.REFRESHED)
            findings.append(
                f"{refreshed} of {len(outcomes)} retained record(s) were replaced; "
                "every original is preserved unless a justified replacement was "
                "accepted"
            )
        return KnowledgeRefresh(
            query=_clean(
                getattr(outcomes[0].request, "query", "") if outcomes else "", 200
            ),
            outcomes=outcomes,
            findings=tuple(findings[:_MAX_FINDINGS]),
        )

    # -- internals ---------------------------------------------------------

    def _capability_state(self) -> str:
        provider = self._capability_state_provider
        if provider is None:
            return ""
        try:
            return _value(provider())
        except Exception:  # fail-soft: an unknown state is not a failure
            return ""

    def _authorize(self, sources: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """The EXISTING D2 authorization decision over the WEB sources only."""
        web = tuple(s for s in sources if _scheme(s) in _WEB_SCHEMES)
        if not web:
            return (), ()
        acquirer = self._acquirer
        if acquirer is None:
            return (), web  # fail-closed: without the boundary nothing is web-authorized
        try:
            authorized, denied = acquirer.authorize(web)
        except Exception:  # fail-closed: deny
            return (), web
        return tuple(authorized), tuple(denied)

    @staticmethod
    def _split(
        authorized: tuple[str, ...],
        denied: tuple[str, ...],
        sources: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Permitted sources: the authorized web sources + the non-web specs."""
        permitted = list(authorized)
        passed_through: list[str] = []
        for spec in sources:
            if _scheme(spec) not in _WEB_SCHEMES:
                passed_through.append(spec)
        permitted.extend(passed_through)
        return tuple(permitted), tuple(passed_through)

    def _reports_for(self, report_ids: tuple[str, ...]) -> tuple[Any, ...]:
        """Load the EXISTING stored reports for ``report_ids`` (fail-soft)."""
        storage = self._storage
        if storage is None or not report_ids:
            return ()
        try:
            wanted = set(report_ids)
            return tuple(
                report
                for report in storage.load_reports()
                if str(getattr(report, "report_id", "")) in wanted
            )
        except Exception:  # fail-soft: no report, no candidate evidence
            return ()

    def _outcome(
        self,
        status: RefreshStatus,
        request: RefreshRequest,
        record: Any,
        *,
        decision: ReplacementDecision = ReplacementDecision.NONE,
        replacement: Any = None,
        candidate_standing: str = "",
        fetch: tuple[str, ...] = (),
        denied: tuple[str, ...] = (),
        report_ids: tuple[str, ...] = (),
        claim_count: int = 0,
        reason: str = "",
        findings: Any = (),
    ) -> RefreshOutcome:
        original = record if isinstance(record, KnowledgeRecord) else None
        return RefreshOutcome(
            status=status,
            request=request,
            decision=decision.value,
            original=original,
            replacement=replacement if isinstance(replacement, KnowledgeRecord) else None,
            candidate_standing=_clean(candidate_standing, 32),
            fetch_sources=tuple(fetch)[:_MAX_SOURCES],
            denied_sources=tuple(denied)[:_MAX_SOURCES],
            report_ids=tuple(report_ids)[:_MAX_SOURCES],
            claim_count=int(claim_count or 0),
            reason=_clean(reason, _MAX_REASON_CHARS),
            findings=tuple(_clean(f, _MAX_TEXT_CHARS) for f in findings)[:_MAX_FINDINGS],
        )


def knowledge_refresher(
    *,
    acquirer: Any | None = None,
    acquisition: Any | None = None,
    storage: Any | None = None,
    assessor: Any | None = None,
    capability_state_provider: Any | None = None,
) -> KnowledgeRefresher:
    """Convenience constructor for :class:`KnowledgeRefresher`."""
    return KnowledgeRefresher(
        acquirer=acquirer,
        acquisition=acquisition,
        storage=storage,
        assessor=assessor,
        capability_state_provider=capability_state_provider,
    )


__all__ = [
    "KnowledgeRefresh",
    "KnowledgeRefresher",
    "REFRESH_RULE",
    "RefreshOutcome",
    "RefreshRequest",
    "RefreshStatus",
    "ReplacementDecision",
    "build_refresh_request",
    "compare_replacement",
    "knowledge_refresher",
    "plan_refresh",
]
