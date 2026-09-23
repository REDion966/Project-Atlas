"""Atlas Evolution — Self-Directed Capability Discovery (Phase 10.1–10.8).

A bounded, deterministic, model-independent DISCOVERY layer. It inspects the
capability landscape, normalizes signals already held elsewhere in Atlas into
structured evidence, detects candidate capability gaps/opportunities, classifies
them, assesses relevance/uncertainty, decides whether research is needed, and
hands a validated candidate to the EXISTING gap/development/acquisition path —
then STOPS at the governance boundary.

It is explicitly NOT a self-evolution engine:

* read-only / advisory: it never develops, approves, promotes, activates,
  installs, executes, or mutates production;
* it adds no planner, research system, registry, memory, or governance system —
  it reuses ``CapabilityModel``, ``SelfDevelopmentInventory``,
  ``assess_development_gap``, the Phase-8 acquisition strategy layer, and the
  existing ``ResearchQuery`` model;
* it fabricates nothing: no evidence -> no actionable candidate;
* one bounded invocation, never a loop.

Heuristics are transparent and deterministic (lexical token overlap, explicit
thresholds). They are NOT semantic understanding.

Pure logic: stdlib only. No AI, no network, no storage, no kernel, no execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from atlas.evolution.capability_acquisition import (
    AcquisitionNeed,
    AcquisitionStrategy,
    determine_acquisition_strategy,
)
from atlas.evolution.development_gap import (
    DevelopmentGapAssessment,
    assess_development_gap,
)
from atlas.research._text import significant_tokens

#: Minimum distinct evidence references for a candidate to be actionable.
MIN_ACTIONABLE_EVIDENCE: int = 1
#: Recurrence threshold for a repeated-failure/limitation signal.
REPEAT_THRESHOLD: int = 2
#: Capability self-assessment below which a capability is treated as degraded.
WEAK_CAPABILITY_SCORE: float = 0.5


def _bounded(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _tokens(text: Any) -> set[str]:
    return significant_tokens(text if isinstance(text, str) else "")


def _matches(subject: str, names: Iterable[str]) -> bool:
    """Deterministic token-overlap match of a subject against capability names."""
    subject_tokens = {
        t for t in _tokens(subject) if len(t) >= 3
    } | {t for t in _tokens(subject.replace(".", " ").replace("_", " "))}
    if not subject_tokens:
        return False
    for name in names or ():
        if not isinstance(name, str) or not name:
            continue
        name_tokens = _tokens(
            name.replace(".", " ").replace("_", " ").replace("-", " ")
        )
        if name_tokens and name_tokens <= subject_tokens:
            return True
    return False


# ---------------------------------------------------------------------------
# 10.2 — Signals
# ---------------------------------------------------------------------------


class DiscoverySignalKind(str, Enum):
    """What a discovery signal indicates (never an assumption)."""

    OBSERVED_FAILURE = "observed_failure"
    UNMET_REQUIREMENT = "unmet_requirement"
    UNAVAILABLE_CAPABILITY = "unavailable_capability"
    DEGRADED_CAPABILITY = "degraded_capability"
    MISSING_KNOWLEDGE = "missing_knowledge"
    REPEATED_LIMITATION = "repeated_limitation"
    EMERGING_OPPORTUNITY = "emerging_opportunity"
    UNCERTAINTY = "uncertainty"


class DiscoverySourceKind(str, Enum):
    """Authoritative Atlas source a signal came from (provenance)."""

    CAPABILITY_MODEL = "capability_model"
    SELF_DEVELOPMENT_INVENTORY = "self_development_inventory"
    SELF_MODEL = "self_model"
    EXPERIENCE = "experience"
    DEVELOPMENT_GAP = "development_gap"
    RESEARCH = "research"
    HUMAN_GOAL = "human_goal"


@dataclass(frozen=True, slots=True)
class DiscoverySignal:
    """One normalized capability signal with provenance."""

    kind: DiscoverySignalKind
    subject: str
    source: DiscoverySourceKind
    evidence: tuple[str, ...] = ()
    occurrences: int = 1
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "subject": self.subject,
            "source": self.source.value,
            "evidence": list(self.evidence),
            "occurrences": self.occurrences,
            "detail": self.detail,
        }


def _entry_availability(entry: Any) -> str:
    return getattr(getattr(entry, "availability", None), "value", "")


def signals_from_capability_model(model: Any) -> tuple[DiscoverySignal, ...]:
    """Signals from a ``CapabilityModel`` (unavailable/degraded/external dep)."""
    signals: list[DiscoverySignal] = []
    for entry in getattr(model, "entries", ()) or ():
        name = _bounded(getattr(entry, "name", ""), 200)
        if not name:
            continue
        availability = _entry_availability(entry)
        dependency = getattr(getattr(entry, "dependency", None), "value", "")
        refs = tuple(
            _bounded(getattr(s, "reference", ""), 200)
            for s in getattr(entry, "sources", ()) or ()
        )
        if availability == "unavailable":
            signals.append(
                DiscoverySignal(
                    DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
                    name,
                    DiscoverySourceKind.CAPABILITY_MODEL,
                    evidence=tuple(r for r in refs if r),
                    detail="capability is registered but unavailable",
                )
            )
        elif availability == "degraded":
            signals.append(
                DiscoverySignal(
                    DiscoverySignalKind.DEGRADED_CAPABILITY,
                    name,
                    DiscoverySourceKind.CAPABILITY_MODEL,
                    evidence=tuple(r for r in refs if r),
                    detail="capability is degraded",
                )
            )
        elif dependency == "external_model_dependent":
            signals.append(
                DiscoverySignal(
                    DiscoverySignalKind.EMERGING_OPPORTUNITY,
                    name,
                    DiscoverySourceKind.CAPABILITY_MODEL,
                    evidence=tuple(r for r in refs if r),
                    detail="capability depends on an optional external model",
                )
            )
    return tuple(signals)


def signals_from_inventory(inventory: Any) -> tuple[DiscoverySignal, ...]:
    """Signals from a ``SelfDevelopmentInventory`` (missing required stages)."""
    return tuple(
        DiscoverySignal(
            DiscoverySignalKind.MISSING_KNOWLEDGE,
            str(key),
            DiscoverySourceKind.SELF_DEVELOPMENT_INVENTORY,
            evidence=(f"inventory:{key}",),
            detail="a required development capability is missing",
        )
        for key in getattr(inventory, "missing_required", lambda: ())()
    )


def signals_from_self_model(snapshot: Any) -> tuple[DiscoverySignal, ...]:
    """Signals from a self-model snapshot (weak capabilities, challenges)."""
    signals: list[DiscoverySignal] = []
    assessments = getattr(snapshot, "capability_assessments", None) or {}
    for capability, score in assessments.items():
        if isinstance(score, (int, float)) and score < WEAK_CAPABILITY_SCORE:
            signals.append(
                DiscoverySignal(
                    DiscoverySignalKind.DEGRADED_CAPABILITY,
                    _bounded(capability, 200),
                    DiscoverySourceKind.SELF_MODEL,
                    evidence=(f"self_model:{_bounded(capability, 120)}",),
                    detail=f"capability self-assessment {score}",
                )
            )
    for challenge in getattr(snapshot, "persistent_challenges", ()) or ():
        signals.append(
            DiscoverySignal(
                DiscoverySignalKind.REPEATED_LIMITATION,
                _bounded(challenge, 200),
                DiscoverySourceKind.SELF_MODEL,
                evidence=(f"self_model:challenge:{_bounded(challenge, 120)}",),
                detail="persistent challenge reported by the self-model",
            )
        )
    return tuple(signals)


def signals_from_experiences(experiences: Iterable[Any]) -> tuple[DiscoverySignal, ...]:
    """Signals from experience history (repeated capability failures)."""
    failures: dict[str, int] = {}
    for experience in experiences or ():
        outcome = getattr(experience, "outcome", None)
        name = getattr(outcome, "name", str(outcome))
        if name not in ("FAILURE", "PARTIAL"):
            continue
        for capability in getattr(experience, "reasoning_capabilities", ()) or ():
            key = _bounded(capability, 200)
            if key:
                failures[key] = failures.get(key, 0) + 1

    signals: list[DiscoverySignal] = []
    for subject in sorted(failures):
        count = failures[subject]
        if count < REPEAT_THRESHOLD:
            continue
        signals.append(
            DiscoverySignal(
                DiscoverySignalKind.OBSERVED_FAILURE,
                subject,
                DiscoverySourceKind.EXPERIENCE,
                evidence=(f"experience:{subject}:failures={count}",),
                occurrences=count,
                detail=f"{count} failing/partial outcomes involving this capability",
            )
        )
    return tuple(signals)


def signals_from_human_goal(goal: str) -> tuple[DiscoverySignal, ...]:
    """A single explicit human/goal signal (never inferred from vague text)."""
    text = _bounded(goal, 300)
    if not text or not _tokens(text):
        return ()
    return (
        DiscoverySignal(
            DiscoverySignalKind.UNMET_REQUIREMENT,
            text,
            DiscoverySourceKind.HUMAN_GOAL,
            evidence=(f"goal:{text}",),
            detail="explicit human goal",
        ),
    )


# ---------------------------------------------------------------------------
# 10.3 / 10.4 — Candidates
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CapabilityDiscoveryCandidate:
    """One deterministic capability-gap/opportunity candidate."""

    candidate_id: str
    kind: DiscoverySignalKind
    subject: str
    sources: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    occurrences: int = 1
    affected_area: str = ""
    already_supported: bool = False
    limitations: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind.value,
            "subject": self.subject,
            "sources": list(self.sources),
            "evidence": list(self.evidence),
            "occurrences": self.occurrences,
            "affected_area": self.affected_area,
            "already_supported": self.already_supported,
            "limitations": list(self.limitations),
            "assumptions": list(self.assumptions),
            "unresolved_questions": list(self.unresolved_questions),
        }


def detect_candidates(
    signals: Iterable[DiscoverySignal],
    *,
    capability_names: Iterable[str] = (),
) -> tuple[CapabilityDiscoveryCandidate, ...]:
    """Detect deterministic candidates from signals (dedup, ordered).

    A subject matching an already-registered capability is marked
    ``already_supported`` and is never presented as missing. A subject with no
    evidence is never emitted. Lexical token overlap is the only matching
    heuristic (explicitly not semantic understanding).
    """
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for signal in signals or ():
        if not isinstance(signal, DiscoverySignal):
            continue
        subject = signal.subject.strip()
        if not subject or not signal.evidence:
            continue  # no evidence -> no candidate
        key = (signal.kind.value, subject)
        acc = grouped.setdefault(
            key, {"sources": set(), "evidence": set(), "occurrences": 0}
        )
        acc["sources"].add(signal.source.value)
        acc["evidence"].update(signal.evidence)
        acc["occurrences"] += max(1, int(signal.occurrences))

    candidates: list[CapabilityDiscoveryCandidate] = []
    for (kind_value, subject), acc in grouped.items():
        kind = DiscoverySignalKind(kind_value)
        supported = _matches(subject, capability_names)
        limitations: list[str] = []
        if kind is DiscoverySignalKind.UNCERTAINTY:
            limitations.append("signal is explicitly uncertain")
        if supported:
            limitations.append("subject matches an already-registered capability")
        candidates.append(
            CapabilityDiscoveryCandidate(
                candidate_id=f"disc:{kind_value}:{_stable(subject)}",
                kind=kind,
                subject=_bounded(subject, 200),
                sources=tuple(sorted(acc["sources"])),
                evidence=tuple(sorted(acc["evidence"])),
                occurrences=int(acc["occurrences"]),
                affected_area=subject.split()[0] if subject.split() else subject,
                already_supported=supported,
                limitations=tuple(limitations),
            )
        )
    candidates.sort(key=lambda c: (c.kind.value, c.subject))
    return tuple(candidates)


def _stable(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 10.5 / 10.6 — Assessment + research trigger
# ---------------------------------------------------------------------------


class DiscoveryVerdict(str, Enum):
    """Discovery assessment outcome (advisory; never authorization)."""

    ACTIONABLE_GAP = "actionable_gap"
    REQUIRES_RESEARCH = "requires_research"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNCERTAIN_OPPORTUNITY = "uncertain_opportunity"
    ALREADY_SUPPORTED = "already_supported"
    DUPLICATE = "duplicate"
    BLOCKED_DEPENDENCY = "blocked_dependency"
    GOVERNANCE_BLOCKED = "governance_blocked"


@dataclass(frozen=True, slots=True)
class DiscoveryAssessment:
    """Deterministic, evidence-bounded assessment of one candidate."""

    candidate_id: str
    subject: str
    verdict: DiscoveryVerdict
    rationale: str
    evidence: tuple[str, ...] = ()
    research_question: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def actionable(self) -> bool:
        return self.verdict is DiscoveryVerdict.ACTIONABLE_GAP

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "subject": self.subject,
            "verdict": self.verdict.value,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "research_question": self.research_question,
            "limitations": list(self.limitations),
        }


def assess_candidate(
    candidate: CapabilityDiscoveryCandidate,
    *,
    capability_names: Iterable[str] = (),
    knowledge_retriever: Any | None = None,
    dependency_blocked: bool = False,
    seen_subjects: Iterable[str] = (),
) -> DiscoveryAssessment:
    """Assess relevance/uncertainty of one candidate (deterministic precedence)."""
    if not isinstance(candidate, CapabilityDiscoveryCandidate):
        return DiscoveryAssessment(
            candidate_id="", subject="", verdict=DiscoveryVerdict.INSUFFICIENT_EVIDENCE,
            rationale="malformed candidate (fail closed)",
        )

    if candidate.already_supported or _matches(candidate.subject, capability_names):
        return DiscoveryAssessment(
            candidate_id=candidate.candidate_id,
            subject=candidate.subject,
            verdict=DiscoveryVerdict.ALREADY_SUPPORTED,
            rationale="the subject already matches a registered capability",
            evidence=candidate.evidence,
        )
    if _matches(candidate.subject, seen_subjects):
        return DiscoveryAssessment(
            candidate_id=candidate.candidate_id,
            subject=candidate.subject,
            verdict=DiscoveryVerdict.DUPLICATE,
            rationale="the same subject was already discovered in this cycle",
            evidence=candidate.evidence,
        )
    if dependency_blocked:
        return DiscoveryAssessment(
            candidate_id=candidate.candidate_id,
            subject=candidate.subject,
            verdict=DiscoveryVerdict.BLOCKED_DEPENDENCY,
            rationale="a required dependency is unavailable; candidate is blocked",
            evidence=candidate.evidence,
        )
    if len(candidate.evidence) < MIN_ACTIONABLE_EVIDENCE:
        return DiscoveryAssessment(
            candidate_id=candidate.candidate_id,
            subject=candidate.subject,
            verdict=DiscoveryVerdict.INSUFFICIENT_EVIDENCE,
            rationale="no evidence supports this candidate",
            evidence=candidate.evidence,
        )
    if candidate.kind is DiscoverySignalKind.UNCERTAINTY:
        return DiscoveryAssessment(
            candidate_id=candidate.candidate_id,
            subject=candidate.subject,
            verdict=DiscoveryVerdict.INSUFFICIENT_EVIDENCE,
            rationale="the underlying signal is explicitly uncertain",
            evidence=candidate.evidence,
        )

    # Evidence-dependent precedence: absent knowledge -> research required.
    knowledge_question = _research_question(candidate.subject)
    if candidate.kind in (
        DiscoverySignalKind.MISSING_KNOWLEDGE,
        DiscoverySignalKind.EMERGING_OPPORTUNITY,
    ):
        research_needed = True
    else:
        research_needed = False

    if research_needed and not _has_knowledge(knowledge_retriever, knowledge_question):
        return DiscoveryAssessment(
            candidate_id=candidate.candidate_id,
            subject=candidate.subject,
            verdict=DiscoveryVerdict.REQUIRES_RESEARCH,
            rationale="evidence is insufficient; bounded research is required first",
            evidence=candidate.evidence,
            research_question=knowledge_question,
        )

    if candidate.occurrences >= REPEAT_THRESHOLD or candidate.kind in (
        DiscoverySignalKind.OBSERVED_FAILURE,
        DiscoverySignalKind.UNMET_REQUIREMENT,
        DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        DiscoverySignalKind.MISSING_KNOWLEDGE,
    ):
        return DiscoveryAssessment(
            candidate_id=candidate.candidate_id,
            subject=candidate.subject,
            verdict=DiscoveryVerdict.ACTIONABLE_GAP,
            rationale="evidence-backed capability gap with no matching capability",
            evidence=candidate.evidence,
        )

    return DiscoveryAssessment(
        candidate_id=candidate.candidate_id,
        subject=candidate.subject,
        verdict=DiscoveryVerdict.UNCERTAIN_OPPORTUNITY,
        rationale="plausible but not yet evidence-backed; remains uncertain",
        evidence=candidate.evidence,
    )


def _research_question(subject: str) -> str:
    return f"what capabilities or mechanisms are required to {subject}".strip()


def _has_knowledge(knowledge_retriever: Any | None, query: str) -> bool:
    """Best-effort validated-knowledge presence (never fabricated)."""
    if knowledge_retriever is None or not callable(
        getattr(knowledge_retriever, "retrieve", None)
    ):
        return False
    try:
        result = knowledge_retriever.retrieve(query)
    except Exception:
        return False
    items = getattr(result, "items", None)
    if items is None and isinstance(result, (list, tuple)):
        items = result
    try:
        return len(list(items or ())) > 0
    except TypeError:
        return False


# ---------------------------------------------------------------------------
# 10.7 — Hand-off to the existing governed path (advisory only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiscoveryHandoff:
    """Advisory hand-off of an actionable candidate to the existing path."""

    candidate_id: str
    subject: str
    gap_kind: str
    acquisition_mechanism: str
    acquirable: bool
    rationale: str = ""
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "subject": self.subject,
            "gap_kind": self.gap_kind,
            "acquisition_mechanism": self.acquisition_mechanism,
            "acquirable": self.acquirable,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
        }


def handoff_to_development(
    candidate: CapabilityDiscoveryCandidate,
    *,
    capability_names: Iterable[str] = (),
    knowledge_retriever: Any | None = None,
) -> DiscoveryHandoff | None:
    """Connect an actionable candidate to the existing gap/acquisition path.

    Uses the EXISTING ``assess_development_gap`` and Phase-8 acquisition
    strategy layer. Produces an ADVISORY hand-off only — it grants no
    authority, prepares nothing, and never executes.
    """
    if candidate is None or not isinstance(candidate, CapabilityDiscoveryCandidate):
        return None

    gap: DevelopmentGapAssessment = assess_development_gap(
        candidate.subject,
        capability_names=capability_names,
        knowledge_retriever=knowledge_retriever,
    )
    strategy: AcquisitionStrategy = determine_acquisition_strategy(
        AcquisitionNeed(
            request=candidate.subject,
            target_capability=candidate.subject,
            knowledge_available=gap.kind.value in ("already_supported", "missing_capability"),
            authorized=True,
        ),
        capability_names=capability_names,
    )
    return DiscoveryHandoff(
        candidate_id=candidate.candidate_id,
        subject=candidate.subject,
        gap_kind=gap.kind.value,
        acquisition_mechanism=strategy.mechanism.value,
        acquirable=strategy.acquirable,
        rationale=gap.rationale,
        evidence=candidate.evidence,
    )


# ---------------------------------------------------------------------------
# 10.1 / 10.8 — Landscape + bounded single discovery cycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CapabilityLandscape:
    """Deterministic view of what Atlas currently can/cannot do."""

    known_capabilities: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    degraded: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    external_dependent: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "known_capabilities": list(self.known_capabilities),
            "unavailable": list(self.unavailable),
            "degraded": list(self.degraded),
            "unknown": list(self.unknown),
            "external_dependent": list(self.external_dependent),
        }


def inspect_landscape(capability_model: Any = None) -> CapabilityLandscape:
    """Inspect the existing capability landscape (read-only)."""
    known: list[str] = []
    unavailable: list[str] = []
    degraded: list[str] = []
    unknown: list[str] = []
    external: list[str] = []
    for entry in getattr(capability_model, "entries", ()) or ():
        name = _bounded(getattr(entry, "name", ""), 200)
        if not name:
            continue
        known.append(name)
        availability = getattr(getattr(entry, "availability", None), "value", "")
        dependency = getattr(getattr(entry, "dependency", None), "value", "")
        if availability == "unavailable":
            unavailable.append(name)
        elif availability == "degraded":
            degraded.append(name)
        elif availability == "unknown":
            unknown.append(name)
        if dependency == "external_model_dependent":
            external.append(name)
    return CapabilityLandscape(
        known_capabilities=tuple(sorted(set(known))),
        unavailable=tuple(sorted(set(unavailable))),
        degraded=tuple(sorted(set(degraded))),
        unknown=tuple(sorted(set(unknown))),
        external_dependent=tuple(sorted(set(external))),
    )


@dataclass(frozen=True, slots=True)
class DiscoveryCycleResult:
    """Bounded result of ONE discovery invocation (advisory only)."""

    landscape: CapabilityLandscape
    signals: tuple[DiscoverySignal, ...] = ()
    candidates: tuple[CapabilityDiscoveryCandidate, ...] = ()
    assessments: tuple[DiscoveryAssessment, ...] = ()
    handoffs: tuple[DiscoveryHandoff, ...] = ()

    @property
    def actionable(self) -> tuple[DiscoveryAssessment, ...]:
        return tuple(a for a in self.assessments if a.actionable)

    def research_requests(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    a.research_question
                    for a in self.assessments
                    if a.verdict is DiscoveryVerdict.REQUIRES_RESEARCH
                    and a.research_question
                }
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "landscape": self.landscape.to_dict(),
            "signals": [s.to_dict() for s in self.signals],
            "candidates": [c.to_dict() for c in self.candidates],
            "assessments": [a.to_dict() for a in self.assessments],
            "handoffs": [h.to_dict() for h in self.handoffs],
            "research_requests": list(self.research_requests()),
        }


def run_discovery_cycle(
    *,
    capability_model: Any = None,
    inventory: Any = None,
    self_model_snapshot: Any = None,
    experiences: Iterable[Any] = (),
    human_goal: str = "",
    extra_signals: Iterable[DiscoverySignal] = (),
    capability_names: Iterable[str] = (),
    knowledge_retriever: Any | None = None,
    dependency_blocked_subjects: Iterable[str] = (),
    max_candidates: int = 20,
) -> DiscoveryCycleResult:
    """Run ONE bounded, deterministic, model-independent discovery invocation.

    Read-only and advisory: it inspects, normalizes signals, detects and
    assesses candidates, and produces an ADVISORY hand-off for actionable ones.
    It never develops, approves, promotes, activates, or mutates anything, and
    it never loops.
    """
    landscape = inspect_landscape(capability_model)

    signals: list[DiscoverySignal] = []
    signals.extend(signals_from_capability_model(capability_model))
    signals.extend(signals_from_inventory(inventory))
    signals.extend(signals_from_self_model(self_model_snapshot))
    signals.extend(signals_from_experiences(experiences))
    signals.extend(signals_from_human_goal(human_goal))
    signals.extend(
        s for s in (extra_signals or ()) if isinstance(s, DiscoverySignal)
    )

    bloom = _dedupe_signals(signals)[: max(1, int(max_candidates))]
    candidates = detect_candidates(bloom, capability_names=capability_names)

    assessments: list[DiscoveryAssessment] = []
    handoffs: list[DiscoveryHandoff] = []
    seen: list[str] = []
    blocked = tuple(dependency_blocked_subjects or ())
    for candidate in candidates:
        assessment = assess_candidate(
            candidate,
            capability_names=capability_names,
            knowledge_retriever=knowledge_retriever,
            dependency_blocked=_matches(candidate.subject, blocked),
            seen_subjects=seen,
        )
        assessments.append(assessment)
        if assessment.verdict is DiscoveryVerdict.ACTIONABLE_GAP:
            handoff = handoff_to_development(
                candidate,
                capability_names=capability_names,
                knowledge_retriever=knowledge_retriever,
            )
            if handoff is not None:
                handoffs.append(handoff)
            seen.append(candidate.subject)

    return DiscoveryCycleResult(
        landscape=landscape,
        signals=tuple(bloom),
        candidates=candidates,
        assessments=tuple(assessments),
        handoffs=tuple(handoffs),
    )


def _dedupe_signals(signals: Iterable[DiscoverySignal]) -> list[DiscoverySignal]:
    """Deterministically de-duplicate signals by (kind, subject, source)."""
    seen: dict[tuple[str, str, str], DiscoverySignal] = {}
    for signal in signals or ():
        if not isinstance(signal, DiscoverySignal):
            continue
        if not signal.subject.strip() or not signal.evidence:
            continue  # no evidence -> not a signal
        key = (signal.kind.value, signal.subject, signal.source.value)
        existing = seen.get(key)
        if existing is None:
            seen[key] = signal
        else:
            merged = DiscoverySignal(
                kind=existing.kind,
                subject=existing.subject,
                source=existing.source,
                evidence=tuple(sorted(set(existing.evidence) | set(signal.evidence))),
                occurrences=existing.occurrences + signal.occurrences,
                detail=existing.detail,
            )
            seen[key] = merged
    return [seen[k] for k in sorted(seen)]
