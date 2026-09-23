"""Atlas Evolution — Phase 13: Continuous Evolution Continuity.

A deterministic, READ-ONLY projection that lets a **later, separately invoked**
bounded evolution cycle understand what previous cycles did — and refuse to
blindly repeat what already failed.

The problem this closes (Phase 13 investigation):

* Phase 10 discovers capability gaps.
* Phase 11 runs ONE bounded governed evolution cycle and records its outcome
  (``evolution_outcome`` + ``self_evolution_development`` + ``promotion_review``
  records) into the EXISTING durable ``EvolutionMemory``.
* Nothing then read those outcomes to decide what a *future* invocation should
  do — so the same subject could be attempted again and again even after a
  deterministic, non-retryable termination.

This module adds exactly one thing: a projection from persisted outcome
evidence to a per-subject *opportunity state* with retry eligibility, plus a
gate that filters Phase-10 candidates against it.

It deliberately adds NO new store, scheduler, daemon, loop, or authority:

* it reads the EXISTING ``EvolutionMemory`` (durable across processes via the
  existing storage adapter) and never writes to it;
* it never approves, authorizes, promotes, activates, or executes anything;
* it never calls a model, never uses the network, and never spawns a process;
* it starts no cycle: a future cycle remains an explicit external invocation;
* it produces no opaque score — states and reasons are explicit and explainable;
* it reuses the EXISTING ``ImprovementStatus`` lifecycle vocabulary by mapping
  to it rather than defining a competing lifecycle.

Pure logic. Stdlib + existing Atlas domain models only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from atlas.evolution.models import ImprovementStatus

#: Default bounded evidence window (records examined, newest first).
DEFAULT_MAX_RECORDS: int = 200

#: Event type Phase 11 writes for every completed evolution cycle.
OUTCOME_EVENT_TYPE: str = "evolution_outcome"

#: Event type Phase 11 writes for verified sandbox development.
DEVELOPMENT_EVENT_TYPE: str = "self_evolution_development"


class EvolutionOpportunityState(str, Enum):
    """What a future invocation must do about one subject.

    Only ``READY`` may be attempted by a new bounded cycle. Every other state
    is a deterministic, evidence-backed reason NOT to attempt it.

    ``IN_PROGRESS`` is reserved for an active invocation and is never derived
    from history.
    """

    READY = "ready"                       # no blocking history: may be attempted
    EVIDENCE_REQUIRED = "evidence_required"  # retryable ONLY with new evidence
    DEFERRED = "deferred"                 # awaits a human governance decision
    BLOCKED = "blocked"                   # an external condition blocks progress
    REJECTED = "rejected"                 # deterministically rejected: final
    COMPLETED = "completed"               # already activated: do not repeat
    IN_PROGRESS = "in_progress"           # reserved (never history-derived)


#: Terminal state -> opportunity state. Deterministic and total: any terminal
#: absent from this map is handled fail-closed (see ``_classify``).
_STATE_BY_TERMINAL: dict[str, EvolutionOpportunityState] = {
    # Success: the capability was activated. Never repeat.
    "activated": EvolutionOpportunityState.COMPLETED,
    # Awaiting (or requiring) a human governance decision.
    "stopped_at_approval": EvolutionOpportunityState.DEFERRED,
    "pending_promotion_review": EvolutionOpportunityState.DEFERRED,
    "promotion_not_ready": EvolutionOpportunityState.DEFERRED,
    # Blocked by authority or by an inconsistent/unsafe state.
    "promotion_not_authorized": EvolutionOpportunityState.BLOCKED,
    "invalid_lifecycle_state": EvolutionOpportunityState.BLOCKED,
    "self_model_inconsistent": EvolutionOpportunityState.BLOCKED,
    "ineligible": EvolutionOpportunityState.BLOCKED,
    # Deterministic, final rejections (a different subject/evidence is needed).
    "rejected_candidate": EvolutionOpportunityState.REJECTED,
    "promotion_failed": EvolutionOpportunityState.REJECTED,
    # Retryable, but only with NEW or CORRECTED evidence.
    "sandbox_failed": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "verification_failed": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "preparation_failed": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "invalid_objective": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "research_required": EvolutionOpportunityState.EVIDENCE_REQUIRED,
}

#: States a future invocation may attempt.
_ATTEMPTABLE: frozenset[EvolutionOpportunityState] = frozenset(
    {EvolutionOpportunityState.READY}
)

#: Deterministic ordering precedence (most blocking first).
_STATE_ORDER: tuple[EvolutionOpportunityState, ...] = (
    EvolutionOpportunityState.BLOCKED,
    EvolutionOpportunityState.REJECTED,
    EvolutionOpportunityState.COMPLETED,
    EvolutionOpportunityState.DEFERRED,
    EvolutionOpportunityState.EVIDENCE_REQUIRED,
    EvolutionOpportunityState.READY,
    EvolutionOpportunityState.IN_PROGRESS,
)

#: Existing lifecycle vocabulary each continuity state feeds into.
_IMPROVEMENT_STATUS_BY_STATE: dict[EvolutionOpportunityState, ImprovementStatus] = {
    EvolutionOpportunityState.READY: ImprovementStatus.IDENTIFIED,
    EvolutionOpportunityState.EVIDENCE_REQUIRED: ImprovementStatus.PLANNED,
    EvolutionOpportunityState.DEFERRED: ImprovementStatus.DEFERRED,
    EvolutionOpportunityState.BLOCKED: ImprovementStatus.DEFERRED,
    EvolutionOpportunityState.REJECTED: ImprovementStatus.REJECTED,
    EvolutionOpportunityState.COMPLETED: ImprovementStatus.COMPLETED,
    EvolutionOpportunityState.IN_PROGRESS: ImprovementStatus.PROPOSED,
}


def _text(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _metadata(record: Any) -> dict[str, Any]:
    metadata = getattr(record, "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _record_id(record: Any) -> str:
    return _text(getattr(record, "record_id", ""), 200)


@dataclass(frozen=True, slots=True)
class EvolutionOpportunity:
    """Deterministic continuation state for ONE evolution subject."""

    subject: str
    state: EvolutionOpportunityState
    attempts: int = 0
    last_terminal: str = ""
    last_outcome_kind: str = ""
    last_cycle_id: str = ""
    last_record_id: str = ""
    rationale: str = ""
    retry_eligible: bool = False
    requires_new_evidence: bool = False
    evidence_ids: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()

    @property
    def attemptable(self) -> bool:
        """True when a future invocation MAY attempt this subject again."""
        return self.state in _ATTEMPTABLE

    def to_improvement_status(self) -> ImprovementStatus:
        """Map onto the EXISTING lifecycle vocabulary (no competing lifecycle)."""
        return _IMPROVEMENT_STATUS_BY_STATE[self.state]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "state": self.state.value,
            "attemptable": self.attemptable,
            "attempts": self.attempts,
            "last_terminal": self.last_terminal,
            "last_outcome_kind": self.last_outcome_kind,
            "last_cycle_id": self.last_cycle_id,
            "rationale": self.rationale,
            "retry_eligible": self.retry_eligible,
            "requires_new_evidence": self.requires_new_evidence,
            "evidence_ids": list(self.evidence_ids),
            "record_ids": list(self.record_ids),
            "improvement_status": self.to_improvement_status().name,
        }


def _classify(terminal: str) -> tuple[EvolutionOpportunityState, bool, bool, str]:
    """Return ``(state, retry_eligible, requires_new_evidence, rationale)``.

    Fail-closed: an unrecognised or missing terminal is DEFERRED (never READY),
    with an explicit rationale, so unknown history can never be re-attempted
    automatically.
    """
    key = _text(terminal, 80).lower()
    if not key:
        return (
            EvolutionOpportunityState.DEFERRED,
            False,
            False,
            "no terminal state recorded (fail closed)",
        )
    state = _STATE_BY_TERMINAL.get(key)
    if state is None:
        return (
            EvolutionOpportunityState.DEFERRED,
            False,
            False,
            f"unrecognised terminal state {key!r} (fail closed)",
        )
    if state is EvolutionOpportunityState.COMPLETED:
        return (state, False, False, "capability already activated; do not repeat")
    if state is EvolutionOpportunityState.REJECTED:
        return (
            state,
            False,
            False,
            "deterministic rejection; a different subject/evidence is required",
        )
    if state is EvolutionOpportunityState.BLOCKED:
        return (
            state,
            False,
            False,
            "blocked by an external condition; requires resolution, not a retry",
        )
    if state is EvolutionOpportunityState.DEFERRED:
        return (
            state,
            False,
            False,
            "awaits an explicit human governance decision",
        )
    return (
        state,
        True,
        True,
        "retryable, but only with new or corrected evidence",
    )


def project_opportunities(
    memory: Any,
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> tuple[EvolutionOpportunity, ...]:
    """Project persisted evolution outcomes into per-subject opportunity states.

    Read-only. Reads ``evolution_outcome`` records from the passed
    ``EvolutionMemory``-like store (duck-typed ``get_records_by_type``), takes
    the most recent outcome per subject, and classifies it deterministically.

    Args:
        memory: An ``EvolutionMemory``-like store. ``None`` yields no
            opportunities (no fabricated history).
        max_records: Bounded evidence window.

    Returns:
        A deterministically ordered tuple of opportunities. Subjects with no
        attributable outcome record are omitted (never invented).
    """
    if memory is None:
        return ()
    loader = getattr(memory, "get_records_by_type", None)
    if not callable(loader):
        return ()
    try:
        records = list(loader(OUTCOME_EVENT_TYPE, max_records) or ())
    except Exception:
        return ()

    latest: dict[str, Any] = {}
    attempts: dict[str, int] = {}
    seen_records: set[str] = set()
    for record in records:
        metadata = _metadata(record)
        subject = _text(metadata.get("subject", ""), 200)
        if not subject:
            continue  # no attribution -> never invent one
        record_id = _record_id(record)
        if record_id:
            if record_id in seen_records:
                continue  # replayed/duplicated durable record -> count once
            seen_records.add(record_id)
        attempts[subject] = attempts.get(subject, 0) + 1
        if subject not in latest:  # newest-first ordering
            latest[subject] = record

    opportunities: list[EvolutionOpportunity] = []
    for subject, record in latest.items():
        metadata = _metadata(record)
        terminal = _text(metadata.get("terminal", ""), 80)
        state, retryable, needs_evidence, rationale = _classify(terminal)
        evidence: list[str] = []
        for ref in tuple(getattr(record, "related_ids", ()) or ()):
            text = _text(ref, 200)
            if text and text not in evidence:
                evidence.append(text)
        opportunities.append(
            EvolutionOpportunity(
                subject=subject,
                state=state,
                attempts=int(attempts.get(subject, 0)),
                last_terminal=terminal,
                last_outcome_kind=_text(metadata.get("outcome_kind", ""), 80),
                last_cycle_id=_text(metadata.get("cycle_id", ""), 200),
                last_record_id=_record_id(record),
                rationale=rationale,
                retry_eligible=retryable,
                requires_new_evidence=needs_evidence,
                evidence_ids=tuple(evidence),
                record_ids=(_record_id(record),),
            )
        )

    opportunities.sort(
        key=lambda o: (_STATE_ORDER.index(o.state), o.subject)
    )
    return tuple(opportunities)


@dataclass(frozen=True, slots=True)
class EvolutionContinuation:
    """What a NEW explicitly invoked cycle can see about prior evolution."""

    opportunities: tuple[EvolutionOpportunity, ...] = ()
    source_errors: tuple[tuple[str, str], ...] = ()

    def for_subject(self, subject: str) -> EvolutionOpportunity | None:
        wanted = _text(subject, 200)
        for opportunity in self.opportunities:
            if opportunity.subject == wanted:
                return opportunity
        return None

    def may_attempt(self, subject: str) -> tuple[bool, str]:
        """Return ``(allowed, reason)`` for attempting ``subject`` again.

        A subject with NO prior outcome is attemptable (fresh evidence is
        supplied by discovery). A subject with a blocking history is refused
        with the recorded rationale.
        """
        opportunity = self.for_subject(subject)
        if opportunity is None:
            return (True, "no prior evolution outcome recorded for this subject")
        if opportunity.attemptable:
            return (True, opportunity.rationale)
        return (False, opportunity.rationale)

    def by_state(
        self, state: EvolutionOpportunityState
    ) -> tuple[EvolutionOpportunity, ...]:
        return tuple(o for o in self.opportunities if o.state is state)

    @property
    def attemptable(self) -> tuple[EvolutionOpportunity, ...]:
        return self.by_state(EvolutionOpportunityState.READY)

    @property
    def completed(self) -> tuple[EvolutionOpportunity, ...]:
        return self.by_state(EvolutionOpportunityState.COMPLETED)

    @property
    def blocked(self) -> tuple[EvolutionOpportunity, ...]:
        return self.by_state(EvolutionOpportunityState.BLOCKED)

    def next_opportunity(self) -> EvolutionOpportunity | None:
        """Return the first attemptable opportunity, or ``None``.

        Deterministic (facets ordered by state precedence then subject); never
        a score-based ranking.
        """
        candidates = self.attemptable
        return candidates[0] if candidates else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunities": [o.to_dict() for o in self.opportunities],
            "attemptable": [o.subject for o in self.attemptable],
            "completed": [o.subject for o in self.completed],
            "blocked": [o.subject for o in self.blocked],
            "source_errors": [list(e) for e in self.source_errors],
            "next_opportunity": (
                self.next_opportunity().subject
                if self.next_opportunity() is not None
                else None
            ),
        }


def continuation_view(
    memory: Any,
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> EvolutionContinuation:
    """Build the bounded continuation view for a future explicit invocation."""
    return EvolutionContinuation(
        opportunities=project_opportunities(memory, max_records=max_records)
    )


@dataclass(frozen=True, slots=True)
class CandidateGate:
    """Advisory filter result over Phase-10 candidates (never authorization)."""

    admitted: tuple[Any, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()

    @property
    def admitted_ids(self) -> tuple[str, ...]:
        return tuple(
            _text(getattr(c, "candidate_id", ""), 200) for c in self.admitted
        )

    @property
    def excluded_subjects(self) -> tuple[str, ...]:
        return tuple(subject for subject, _ in self.excluded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": list(self.admitted_ids),
            "excluded": [list(item) for item in self.excluded],
        }


def gate_candidates(
    candidates: Iterable[Any],
    continuation: EvolutionContinuation,
    *,
    capability_names: Iterable[str] = (),
) -> CandidateGate:
    """Filter discovery candidates against recorded evolution history.

    A candidate whose subject has a blocking prior outcome is EXCLUDED with the
    recorded reason, so a new cycle cannot blindly repeat a known failure. The
    gate is advisory: it never authorizes anything, and it never fabricates a
    candidate. Candidates matching an existing capability are excluded too.
    """
    admitted: list[Any] = []
    excluded: list[tuple[str, str]] = []
    names = tuple(capability_names or ())
    for candidate in candidates or ():
        subject = _text(getattr(candidate, "subject", ""), 200)
        if not subject:
            excluded.append(("", "candidate has no subject (fail closed)"))
            continue
        allowed, reason = continuation.may_attempt(subject)
        if not allowed:
            excluded.append((subject, reason))
            continue
        if names and _matches_any(subject, names):
            excluded.append((subject, "already provided by a registered capability"))
            continue
        admitted.append(candidate)
    return CandidateGate(admitted=tuple(admitted), excluded=tuple(excluded))


def _matches_any(subject: str, names: Iterable[str]) -> bool:
    """Deterministic token-overlap match against known capability names."""
    from atlas.research._text import significant_tokens

    subject_tokens = significant_tokens(subject) | significant_tokens(
        subject.replace(".", " ").replace("_", " ")
    )
    if not subject_tokens:
        return False
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        name_tokens = significant_tokens(
            name.replace(".", " ").replace("_", " ").replace("-", " ")
        )
        if name_tokens and name_tokens <= subject_tokens:
            return True
    return False


@dataclass(frozen=True, slots=True)
class EvolutionHistoryFact:
    """One durable, attributable fact about a subject's evolution history."""

    cycle_id: str
    event_type: str
    terminal: str
    outcome_kind: str
    record_id: str
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "event_type": self.event_type,
            "terminal": self.terminal,
            "outcome_kind": self.outcome_kind,
            "record_id": self.record_id,
            "evidence_ids": list(self.evidence_ids),
        }


def subject_history(
    memory: Any,
    subject: str,
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> tuple[EvolutionHistoryFact, ...]:
    """Return the durable evolution history for ONE subject (oldest first).

    Answers, from persisted evidence only: which cycles touched this subject,
    what each terminated as, what outcome was learned, and what evidence is
    attached. Read-only; never rewrites or infers a missing fact.
    """
    if memory is None:
        return ()
    loader = getattr(memory, "get_records", None)
    if not callable(loader):
        return ()
    wanted = _text(subject, 200)
    if not wanted:
        return ()
    try:
        records = list(loader(max_records) or ())
    except Exception:
        return ()

    facts: list[EvolutionHistoryFact] = []
    for record in reversed(records):  # oldest -> newest
        metadata = _metadata(record)
        if _text(metadata.get("subject", ""), 200) != wanted:
            continue
        evidence: list[str] = []
        for ref in tuple(getattr(record, "related_ids", ()) or ()):
            text = _text(ref, 200)
            if text and text not in evidence:
                evidence.append(text)
        facts.append(
            EvolutionHistoryFact(
                cycle_id=_text(metadata.get("cycle_id", ""), 200),
                event_type=_text(getattr(record, "event_type", ""), 80),
                terminal=_text(metadata.get("terminal", ""), 80),
                outcome_kind=_text(metadata.get("outcome_kind", ""), 80),
                record_id=_record_id(record),
                evidence_ids=tuple(evidence),
            )
        )
    return tuple(facts)


@dataclass(frozen=True, slots=True)
class MultiCyclePlan:
    """Bounded description of what an explicitly invoked continuation may do."""

    cycles_requested: int
    subjects: tuple[str, ...] = ()
    note: str = "explicit invocations only; never self-chaining"

    def __post_init__(self) -> None:
        if self.cycles_requested < 0:
            raise ValueError("cycles_requested must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycles_requested": self.cycles_requested,
            "subjects": list(self.subjects),
            "note": self.note,
        }


#: Hard bound on how many explicit invocations a single driver call may
#: orchestrate. This is a *caller* bound, not a scheduler: nothing here starts
#: a cycle by itself.
MAX_EXPLICIT_CYCLES: int = 5


def bounded_multi_cycle_plan(
    continuation: EvolutionContinuation,
    cycles: int,
    *,
    policy: Any | None = None,
) -> MultiCyclePlan:
    """Describe a FINITE sequence of explicitly invoked cycles.

    Reuses ``OperationPolicy``'s bounded vocabulary when supplied (its
    ``max_budget_cycles`` caps the sequence); otherwise caps at
    :data:`MAX_EXPLICIT_CYCLES`. Returns a plan only — it never invokes a cycle.
    """
    hard_cap = MAX_EXPLICIT_CYCLES
    if policy is not None:
        cap = getattr(policy, "max_budget_cycles", None)
        if isinstance(cap, int) and cap > 0:
            hard_cap = min(hard_cap, cap)
    requested = max(0, min(int(cycles), hard_cap))
    subjects = tuple(o.subject for o in continuation.attemptable)[:requested]
    return MultiCyclePlan(cycles_requested=requested, subjects=subjects)
