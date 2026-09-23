"""Atlas Research — Deterministic Technology Analysis (Phase 7.4–7.6).

A bounded, deterministic, model-independent layer that turns VALIDATED research
knowledge about a technology into structured analysis, criteria-driven
comparison, and a contextual suitability/feasibility assessment — and an
evidence-based research conclusion.

It deliberately keeps three things SEPARATE, and never collapses them:

* **FACT / verified claim** — a ``TechnologyFact`` whose ``state`` is
  ``VERIFIED`` (derived only from already-validated knowledge).
* **ANALYSIS / inference** — ``CriterionFinding`` / comparison results derived
  deterministically from facts; each cites the evidence it rests on.
* **CONCLUSION / assessment** — ``SuitabilityAssessment`` / ``ResearchConclusion``
  whose strength is bounded by the evidence actually available.

Source of truth: the existing Phase-3 validated-knowledge surface
(``ValidatedKnowledgeItem`` / ``ValidatedKnowledgeResult``). This module never
gathers information, never verifies claims, never persists anything, and never
authorizes any action. It adds NO second evidence, knowledge, or provenance
store — it projects and reasons over existing validated knowledge.

Absence of evidence is reported as ``UNKNOWN`` / ``INSUFFICIENT_EVIDENCE``,
never as a fact. Unsourced statements cannot become facts.

Pure logic: stdlib only. No AI, no network, no storage, no kernel, no execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

#: Bound applied to any retained free text so a malformed source cannot produce
#: unbounded output.
_MAX_TEXT_CHARS: int = 400
#: Bound on retained evidence references per entry.
_MAX_EVIDENCE_REFS: int = 20

_TOKEN_RE = re.compile(r"[a-z0-9]+")
#: Tokens too generic to evidence a criterion (kept deliberately small).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "are", "was", "has",
        "have", "its", "into", "not", "but", "can", "will", "would", "should",
        "may", "might", "than", "then", "when", "which", "who", "how", "what",
        "a", "an", "of", "in", "on", "to", "is", "be", "as", "or", "by", "at",
    }
)


class VerificationState(str, Enum):
    """Verification state of a technology fact (never guessed)."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class SuitabilityVerdict(str, Enum):
    """Contextual suitability of a technology for a specific requirement."""

    SUITABLE = "suitable"
    PARTIALLY_SUITABLE = "partially_suitable"
    NOT_SUITABLE = "not_suitable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ConclusionStrength(str, Enum):
    """Overall strength of an evidence-based research conclusion."""

    SUPPORTED = "supported"
    PARTIAL = "partial"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class TechnologyFact:
    """A single structured statement about a technology.

    ``state`` distinguishes a verified (sourced) fact from an unverified or
    contradicted one. ``evidence`` carries the provenance references.
    """

    statement: str
    state: VerificationState
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "state": self.state.value,
            "confidence": round(self.confidence, 4),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class TechnologyProfile:
    """Structured, factual profile of one technology (facts only)."""

    name: str
    facts: tuple[TechnologyFact, ...] = ()

    @property
    def verified_facts(self) -> tuple[TechnologyFact, ...]:
        return tuple(f for f in self.facts if f.state is VerificationState.VERIFIED)

    @property
    def unverified_facts(self) -> tuple[TechnologyFact, ...]:
        return tuple(f for f in self.facts if f.state is VerificationState.UNVERIFIED)

    @property
    def contradicted_facts(self) -> tuple[TechnologyFact, ...]:
        return tuple(
            f for f in self.facts if f.state is VerificationState.CONTRADICTED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "facts": [f.to_dict() for f in self.facts],
            "verified_count": len(self.verified_facts),
            "unverified_count": len(self.unverified_facts),
            "contradicted_count": len(self.contradicted_facts),
        }


@dataclass(frozen=True, slots=True)
class EvaluationCriterion:
    """An explicit criterion used for comparison/suitability."""

    name: str
    required: bool = True
    keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("criterion name must be a non-empty string")
        if not self.keywords:
            # Derive deterministic keywords from the name when none are given.
            object.__setattr__(
                self, "keywords", _keywords(self.name)
            )


@dataclass(frozen=True, slots=True)
class CriterionFinding:
    """ANALYSIS: how one technology fares against one criterion.

    ``satisfied`` is ``True`` (a verified fact supports it), ``False`` (a
    verified/contradicted fact refutes it), or ``None`` (no evidence).
    """

    criterion: str
    satisfied: bool | None
    evidence: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "satisfied": self.satisfied,
            "evidence": list(self.evidence),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class TechnologyComparison:
    """ANALYSIS: criteria-driven comparison of multiple technologies."""

    alternatives: tuple[str, ...]
    criteria: tuple[str, ...]
    findings: tuple[tuple[str, tuple[CriterionFinding, ...]], ...] = ()
    unmet_requirements: tuple[tuple[str, str], ...] = ()
    uncertainties: tuple[tuple[str, str], ...] = ()

    def findings_for(self, technology: str) -> tuple[CriterionFinding, ...]:
        for name, findings in self.findings:
            if name == technology:
                return findings
        return ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "alternatives": list(self.alternatives),
            "criteria": list(self.criteria),
            "findings": [
                {"technology": name, "findings": [f.to_dict() for f in fs]}
                for name, fs in self.findings
            ],
            "unmet_requirements": [list(x) for x in self.unmet_requirements],
            "uncertainties": [list(x) for x in self.uncertainties],
        }


@dataclass(frozen=True, slots=True)
class SuitabilityAssessment:
    """CONCLUSION: contextual suitability of a technology for a requirement."""

    requirement: str
    technology: str
    verdict: SuitabilityVerdict
    satisfied: tuple[str, ...] = ()
    unmet: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "technology": self.technology,
            "verdict": self.verdict.value,
            "satisfied": list(self.satisfied),
            "unmet": list(self.unmet),
            "unknown": list(self.unknown),
            "evidence": list(self.evidence),
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class ResearchConclusion:
    """CONCLUSION: an evidence-based conclusion whose strength is bounded."""

    question: str
    summary: str
    strength: ConclusionStrength
    supporting_evidence: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "summary": self.summary,
            "strength": self.strength.value,
            "supporting_evidence": list(self.supporting_evidence),
            "contradictions": list(self.contradictions),
            "uncertainties": list(self.uncertainties),
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    text = value if isinstance(value, str) else ""
    return " ".join(text.split())[:limit]


def _keywords(text: str) -> tuple[str, ...]:
    return tuple(sorted({t for t in _TOKEN_RE.findall(text.lower())}))


def _citation_ref(citation: Any) -> str:
    """Stable provenance reference for one citation (never fabricated)."""
    for attr in ("source_uri", "record_id"):
        value = getattr(citation, attr, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    title = getattr(citation, "source_title", "")
    return title.strip() if isinstance(title, str) else ""


def _evidence_refs(items: Iterable[Any]) -> tuple[str, ...]:
    refs: set[str] = set()
    for citation in items or ():
        ref = _citation_ref(citation)
        if ref:
            refs.add(ref)
    return tuple(sorted(refs))[:_MAX_EVIDENCE_REFS]


def _state_for(validation_status: Any) -> VerificationState:
    status = validation_status if isinstance(validation_status, str) else ""
    normalized = status.strip().upper()
    if normalized == "SUPPORTED":
        return VerificationState.VERIFIED
    if normalized == "CONTRADICTED":
        return VerificationState.CONTRADICTED
    if normalized in ("UNVERIFIED", "AMBIGUOUS"):
        return VerificationState.UNVERIFIED
    return VerificationState.UNKNOWN


def _confidence(item: Any) -> float:
    for attr in ("verification_score", "claim_confidence"):
        value = getattr(item, attr, None)
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
    return 0.0


# ---------------------------------------------------------------------------
# Fact construction (from existing validated knowledge only)
# ---------------------------------------------------------------------------


def fact_from_validated_item(item: Any) -> TechnologyFact | None:
    """Build a :class:`TechnologyFact` from one validated-knowledge item.

    The item is duck-typed on the existing ``ValidatedKnowledgeItem`` surface
    (``statement`` / ``validation_status`` / ``verification_score`` /
    ``citations``). A blank statement yields ``None`` (nothing to report).
    """
    statement = _bounded(getattr(item, "statement", ""))
    if not statement:
        return None
    return TechnologyFact(
        statement=statement,
        state=_state_for(getattr(item, "validation_status", "")),
        confidence=_confidence(item),
        evidence=_evidence_refs(getattr(item, "citations", ()) or ()),
    )


def profile_from_validated_items(name: str, items: Iterable[Any]) -> TechnologyProfile:
    """Build a factual technology profile from validated-knowledge items.

    Facts derived from unsupported/raw items are retained but marked
    ``UNVERIFIED`` — they never become facts. Deterministic ordering.
    """
    facts: list[TechnologyFact] = []
    for item in items or ():
        fact = fact_from_validated_item(item)
        if fact is not None:
            facts.append(fact)
    facts.sort(key=lambda f: (f.statement, f.state.value))
    return TechnologyProfile(name=_bounded(name, limit=200), facts=tuple(facts))


# ---------------------------------------------------------------------------
# Analysis: criterion evaluation and comparison
# ---------------------------------------------------------------------------


def _matches(statement_tokens: set[str], keywords: tuple[str, ...]) -> bool:
    return bool(statement_tokens & set(keywords))


def evaluate_criterion(
    profile: TechnologyProfile, criterion: EvaluationCriterion
) -> CriterionFinding:
    """Evaluate ONE criterion against ONE profile (deterministic, evidence-bound).

    A contradicted fact that matches the criterion is decisive evidence
    AGAINST it. Otherwise a verified matching fact satisfies it. With no
    matching evidence the result is ``None`` (unknown), never a guess.
    """
    refuted: list[str] = []
    supported: list[str] = []
    for fact in profile.facts:
        tokens = set(_TOKEN_RE.findall(fact.statement.lower()))
        if not _matches(tokens, criterion.keywords):
            continue
        if fact.state is VerificationState.CONTRADICTED:
            refuted.extend(fact.evidence)
        elif fact.state is VerificationState.VERIFIED:
            supported.extend(fact.evidence)

    if refuted:
        return CriterionFinding(
            criterion=criterion.name,
            satisfied=False,
            evidence=tuple(sorted(set(refuted)))[:_MAX_EVIDENCE_REFS],
            notes="a verified/contradicted fact argues against this criterion",
        )
    if supported:
        return CriterionFinding(
            criterion=criterion.name,
            satisfied=True,
            evidence=tuple(sorted(set(supported)))[:_MAX_EVIDENCE_REFS],
        )
    return CriterionFinding(
        criterion=criterion.name,
        satisfied=None,
        notes="no verified evidence for this criterion",
    )


def compare_technologies(
    profiles: Iterable[TechnologyProfile],
    criteria: Iterable[EvaluationCriterion],
) -> TechnologyComparison:
    """Compare technologies against explicit criteria (no opaque overall score)."""
    profile_list = list(profiles or ())
    criteria_list = list(criteria or ())
    names = tuple(sorted(p.name for p in profile_list))
    criteria_names = tuple(c.name for c in criteria_list)

    findings: list[tuple[str, tuple[CriterionFinding, ...]]] = []
    unmet: set[tuple[str, str]] = set()
    uncertainties: set[tuple[str, str]] = set()
    for profile in sorted(profile_list, key=lambda p: p.name):
        per = tuple(evaluate_criterion(profile, c) for c in criteria_list)
        findings.append((profile.name, per))
        for criterion, finding in zip(criteria_list, per):
            if finding.satisfied is False and criterion.required:
                unmet.add((profile.name, criterion.name))
            if finding.satisfied is None and criterion.required:
                uncertainties.add((profile.name, criterion.name))

    return TechnologyComparison(
        alternatives=names,
        criteria=criteria_names,
        findings=tuple(findings),
        unmet_requirements=tuple(sorted(unmet)),
        uncertainties=tuple(sorted(uncertainties)),
    )


# ---------------------------------------------------------------------------
# Conclusion: suitability and evidence-based research conclusion
# ---------------------------------------------------------------------------


def assess_suitability(
    requirement: str,
    profile: TechnologyProfile,
    criteria: Iterable[EvaluationCriterion],
) -> SuitabilityAssessment:
    """Assess contextual suitability of ONE technology against a requirement.

    Deterministic precedence (never stronger than the evidence):

    * any unmet REQUIRED criterion -> NOT_SUITABLE
    * no evidence at all for any required criterion -> INSUFFICIENT_EVIDENCE
    * some required criteria unknown -> PARTIALLY_SUITABLE
    * every required criterion satisfied -> SUITABLE
    """
    criteria_list = list(criteria or ())
    findings = [evaluate_criterion(profile, c) for c in criteria_list]

    satisfied = tuple(
        f.criterion for f in findings if f.satisfied is True
    )
    unmet = tuple(f.criterion for f in findings if f.satisfied is False)
    unknown = tuple(f.criterion for f in findings if f.satisfied is None)
    evidence = tuple(
        sorted({ref for f in findings for ref in f.evidence})[:_MAX_EVIDENCE_REFS]
    )

    if unmet:
        verdict = SuitabilityVerdict.NOT_SUITABLE
        rationale = "at least one required criterion is not satisfied by evidence"
    elif not satisfied and unknown:
        verdict = SuitabilityVerdict.INSUFFICIENT_EVIDENCE
        rationale = "no evidence supports the required criteria"
    elif unknown:
        verdict = SuitabilityVerdict.PARTIALLY_SUITABLE
        rationale = "some required criteria lack supporting evidence"
    elif satisfied:
        verdict = SuitabilityVerdict.SUITABLE
        rationale = "every required criterion is supported by verified evidence"
    else:
        verdict = SuitabilityVerdict.INSUFFICIENT_EVIDENCE
        rationale = "no criteria were provided"

    return SuitabilityAssessment(
        requirement=_bounded(requirement, limit=200),
        technology=profile.name,
        verdict=verdict,
        satisfied=satisfied,
        unmet=unmet,
        unknown=unknown,
        evidence=evidence,
        rationale=rationale,
    )


def build_research_conclusion(
    question: str,
    profiles: Iterable[TechnologyProfile],
    *,
    assumptions: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> ResearchConclusion:
    """Produce an evidence-based conclusion whose strength is bounded.

    Strength rules (deterministic):

    * any contradicted fact -> CONTRADICTED
    * verified facts AND no unverified facts -> SUPPORTED
    * verified facts AND some unverified facts -> PARTIAL
    * no verified facts -> INSUFFICIENT
    """
    profile_list = list(profiles or ())
    verified: list[str] = []
    unverified: list[str] = []
    contradicted: list[str] = []
    evidence: set[str] = set()

    for profile in profile_list:
        for fact in profile.facts:
            if fact.state is VerificationState.VERIFIED:
                verified.append(fact.statement)
                evidence.update(fact.evidence)
            elif fact.state is VerificationState.CONTRADICTED:
                contradicted.append(fact.statement)
                evidence.update(fact.evidence)
            else:
                unverified.append(fact.statement)

    if contradicted:
        strength = ConclusionStrength.CONTRADICTED
    elif verified and not unverified:
        strength = ConclusionStrength.SUPPORTED
    elif verified:
        strength = ConclusionStrength.PARTIAL
    else:
        strength = ConclusionStrength.INSUFFICIENT

    verified_sorted = tuple(sorted(set(verified)))
    summary = (
        f"{len(verified_sorted)} verified fact(s) across "
        f"{len(profile_list)} technology profile(s); "
        f"{len(contradicted)} contradicted; {len(set(unverified))} unverified."
    )

    return ResearchConclusion(
        question=_bounded(question),
        summary=summary,
        strength=strength,
        supporting_evidence=tuple(sorted(evidence))[:_MAX_EVIDENCE_REFS],
        contradictions=tuple(sorted(set(contradicted))),
        uncertainties=tuple(sorted(set(unverified))),
        assumptions=tuple(_bounded(a, 200) for a in (assumptions or ())),
        limitations=tuple(_bounded(l, 200) for l in (limitations or ())),
    )


def conclusion_from_suitability(
    requirement: str,
    assessments: Iterable[SuitabilityAssessment],
) -> SuitabilityVerdict:
    """Aggregate several suitability assessments into ONE honest verdict.

    Deterministic: any NOT_SUITABLE -> NOT_SUITABLE; else any SUITABLE ->
    SUITABLE; else any PARTIALLY_SUITABLE -> PARTIALLY_SUITABLE; else
    INSUFFICIENT_EVIDENCE.
    """
    verdicts = [a.verdict for a in assessments or ()]
    if not verdicts:
        return SuitabilityVerdict.INSUFFICIENT_EVIDENCE
    if SuitabilityVerdict.NOT_SUITABLE in verdicts:
        return SuitabilityVerdict.NOT_SUITABLE
    if SuitabilityVerdict.SUITABLE in verdicts:
        return SuitabilityVerdict.SUITABLE
    if SuitabilityVerdict.PARTIALLY_SUITABLE in verdicts:
        return SuitabilityVerdict.PARTIALLY_SUITABLE
    return SuitabilityVerdict.INSUFFICIENT_EVIDENCE
