"""Atlas Post-Core F2 — Knowledge Freshness Assessor.

Deterministic freshness/provenance assessment over existing knowledge
artifacts. Consumes F1 ``EnvironmentChange`` records (through stable
duck-typed accessors) and existing-knowledge provenance metadata.

The assessor NEVER:
  * performs research / web / source / model calls
  * modifies a KnowledgeEntry / Claim / Source / Memory store
  * imports or invokes governance/authorization subsystems
  * triggers adaptation

It only produces bounded assessment + candidate output for a future governed
(F3/F4) adaptation engine.

Determinism contract: identical (knowledge metadata, F1 changes, policy, now)
always produce identical assessments.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from atlas.evolution.freshness.models import (
    FreshnessReason,
    FreshnessStatus,
    KnowledgeFreshnessAssessment,
    KnowledgeRef,
    RecommendedAction,
    StaleKnowledgeCandidate,
    coerce_utc,
    utc_now,
)
from atlas.evolution.freshness.policy import FreshnessPolicy


def _coerce_dt(value: Any) -> datetime | None:
    """Normalize a value into a UTC-aware datetime (or None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return coerce_utc(value)
    if isinstance(value, str):
        try:
            return coerce_utc(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


DEFAULT_POLICY = FreshnessPolicy(
    max_source_age=timedelta(days=180),
    max_verification_age=timedelta(days=90),
    min_confidence=0.5,
)


class KnowledgeFreshnessAssessor:
    """Assess knowledge freshness against a deterministic policy.

    Args:
        policy: The ``FreshnessPolicy`` to apply (injectable for tests).
        now: Optional clock callable returning a UTC ``datetime``; defaults to
            ``utc_now``. Injectable for deterministic tests.
    """

    def __init__(
        self,
        policy: FreshnessPolicy | None = None,
        now: Any | None = None,
    ) -> None:
        self._policy = policy if policy is not None else DEFAULT_POLICY
        self._now = now or utc_now

    @property
    def policy(self) -> FreshnessPolicy:
        """The applied policy (read-only)."""
        return self._policy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        reference: KnowledgeRef,
        changes: Iterable[Any] | None = None,
        now: datetime | None = None,
    ) -> KnowledgeFreshnessAssessment:
        """Assess a single knowledge artifact.

        Args:
            reference: Normalized knowledge projection.
            changes: Optional iterable of F1 ``EnvironmentChange`` objects
                (or duck-typed objects exposing ``entity`` / ``change_type``).
            now: Optional UTC timestamp; defaults to the injected clock.

        The underlying reference is never mutated.
        """
        assessed_at = _coerce_dt(now) or self._now()
        reasons: list[FreshnessReason] = []
        status = FreshnessStatus.FRESH

        # 1. Missing provenance is never fresh.
        has_provenance = bool(reference.source_uris or reference.retrieved_at)
        if not has_provenance:
            return self._build(
                reference,
                assessed_at,
                status=self._policy.missing_provenance_status,
                reasons=[FreshnessReason.MISSING_PROVENANCE],
                rationale="no-provenance",
            )

        # 2. Source age.
        if reference.retrieved_at is None:
            reasons.append(FreshnessReason.MISSING_PROVENANCE)
            status = _severer(status, self._policy.missing_provenance_status)
        elif (assessed_at - reference.retrieved_at) > self._policy.max_source_age:
            reasons.append(FreshnessReason.SOURCE_AGE)
            status = FreshnessStatus.STALE

        # 3. Verification age (only when verification metadata exists).
        if reference.verified_at is None:
            if reference.verification_id:  # named but timestampless
                reasons.append(FreshnessReason.VERIFICATION_AGE)
                status = FreshnessStatus.STALE
        elif (assessed_at - reference.verified_at) > self._policy.max_verification_age:
            reasons.append(FreshnessReason.VERIFICATION_AGE)
            status = FreshnessStatus.STALE

        # 4. Confidence.
        if reference.confidence is not None:
            if reference.confidence < self._policy.min_confidence:
                reasons.append(FreshnessReason.LOW_CONFIDENCE)
                status = _severer(status, self._policy.low_confidence_status)

        # 5. Relevant F1 environment changes.
        triggering_id = ""
        triggering_key = ""
        for change in changes or ():
            if self._is_relevant(change, reference):
                reasons.append(FreshnessReason.ENVIRONMENT_CHANGE)
                status = _severer(
                    status, self._policy.environment_invalidated_status
                )
                triggering_key = self._change_entity_key(change)
                change_id = self._change_id(change)
                if change_id:
                    triggering_id = change_id

        rationale = self._rationale(status, reasons)
        return self._build(
            reference,
            assessed_at,
            status=status,
            reasons=reasons,
            rationale=rationale,
            triggering_id=triggering_id,
            triggering_key=triggering_key,
        )

    def assess_many(
        self,
        references: Iterable[KnowledgeRef],
        changes: Iterable[Any] | None = None,
        now: datetime | None = None,
    ) -> list[KnowledgeFreshnessAssessment]:
        """Assess many references; deterministic order by knowledge_id."""
        return sorted(
            (self.assess(r, changes=changes, now=now) for r in references),
            key=lambda a: a.knowledge_id,
        )

    def find_stale_candidates(
        self,
        references: Iterable[KnowledgeRef],
        changes: Iterable[Any] | None = None,
        now: datetime | None = None,
    ) -> list[StaleKnowledgeCandidate]:
        """Return STALE/UNCERTAIN knowledge as bounded candidates.

        Deterministic ordering: highest priority first, then knowledge_id.
        """
        candidates: list[StaleKnowledgeCandidate] = []
        for assessment in self.assess_many(references, changes=changes, now=now):
            if assessment.status is FreshnessStatus.FRESH:
                continue
            candidates.append(self._to_candidate(assessment))
        return sorted(
            candidates,
            key=lambda c: (-c.priority, c.knowledge_id),
        )

    # ------------------------------------------------------------------
    # Relevance (deterministic only; never semantic / LLM)
    # ------------------------------------------------------------------

    @classmethod
    def _is_relevant(cls, change: Any, reference: KnowledgeRef) -> bool:
        """True when an F1 change deterministically relates to a reference.

        A change is relevant when ANY of the following holds:
          * the change entity key is in the reference's affected_entity_keys
          * the change entity key equals the reference entity_key
          * the change domain is in the reference's affected_domains
        If relevance cannot be established deterministically it is NOT
        relevant (never invents a relationship).
        """
        change_key = cls._change_entity_key(change)
        change_domain = cls._change_domain(change)
        if not change_key and not change_domain:
            return False  # unclassifiable change
        if change_key:
            if change_key in reference.affected_entity_keys:
                return True
            if reference.entity_key and change_key == reference.entity_key:
                return True
        if change_domain:
            if change_domain in reference.affected_domains:
                return True
        return False

    @staticmethod
    def _change_id(change: Any) -> str:
        direct = getattr(change, "change_id", "") or ""
        if direct:
            return str(direct)
        # Deterministic fallback: subject key + observed timestamp.
        key = KnowledgeFreshnessAssessor._change_entity_key(change)
        observed = getattr(change, "observed_at", None)
        if key and observed is not None:
            stamp = _coerce_dt(observed)
            if stamp is not None:
                return f"{key}@{stamp.isoformat()}"
        return ""

    @staticmethod
    def _change_entity_key(change: Any) -> str:
        entity = getattr(change, "entity", None)
        if entity is None:
            return ""
        key = getattr(entity, "key", "") or ""
        if key:
            return str(key)
        domain = getattr(entity, "domain", None)
        eid = getattr(entity, "entity_id", "")
        if domain is not None and eid:
            return f"{_enum_name(domain)}:{eid}"
        return ""

    @staticmethod
    def _change_domain(change: Any) -> str:
        entity = getattr(change, "entity", None)
        if entity is None:
            return ""
        domain = getattr(entity, "domain", None)
        return _enum_name(domain) if domain is not None else ""

    # ------------------------------------------------------------------
    # Candidate / rationale construction
    # ------------------------------------------------------------------

    def _to_candidate(
        self, assessment: KnowledgeFreshnessAssessment
    ) -> StaleKnowledgeCandidate:
        return StaleKnowledgeCandidate(
            knowledge_id=assessment.knowledge_id,
            priority=self._priority(assessment),
            recommended_action=self._action(assessment),
            reasons=assessment.reasons,
            provenance_refs=tuple(u for u in assessment.source_uris if u)[:20],
            triggering_environment_change_id=(
                assessment.triggering_environment_change_id
            ),
            triggering_environment_entity_key=(
                assessment.triggering_environment_entity_key
            ),
            rationale=assessment.rationale,
        )

    @staticmethod
    def _priority(assessment: KnowledgeFreshnessAssessment) -> float:
        """Deterministic severity in [0.0, 1.0]."""
        reasons = set(assessment.reasons)
        base = 0.0
        if assessment.status is FreshnessStatus.STALE:
            base = 0.7
        elif assessment.status is FreshnessStatus.UNCERTAIN:
            base = 0.4
        if FreshnessReason.ENVIRONMENT_CHANGE in reasons:
            base += 0.3
        if FreshnessReason.SOURCE_CHANGED in reasons:
            base += 0.3
        if FreshnessReason.LOW_CONFIDENCE in reasons:
            base -= 0.05
        return round(min(1.0, max(0.0, base)), 2)

    @staticmethod
    def _action(assessment: KnowledgeFreshnessAssessment) -> RecommendedAction:
        reasons = set(assessment.reasons)
        if (
            FreshnessReason.ENVIRONMENT_CHANGE in reasons
            or FreshnessReason.SOURCE_CHANGED in reasons
            or FreshnessReason.SOURCE_AGE in reasons
        ):
            return RecommendedAction.RESEARCH
        if FreshnessReason.VERIFICATION_AGE in reasons:
            return RecommendedAction.VERIFY
        if assessment.status is FreshnessStatus.UNCERTAIN:
            return RecommendedAction.REVIEW
        if assessment.status is FreshnessStatus.STALE:
            return RecommendedAction.REVIEW
        return RecommendedAction.NONE

    @staticmethod
    def _rationale(status: FreshnessStatus, reasons: list[FreshnessReason]) -> str:
        """Stable keyword rationale (never free-form AI text)."""
        if not reasons:
            return "fresh"
        return ",".join(r.name.lower() for r in reasons)

    @staticmethod
    def _build(
        reference: KnowledgeRef,
        assessed_at: datetime,
        status: FreshnessStatus,
        reasons: list[FreshnessReason],
        rationale: str,
        triggering_id: str = "",
        triggering_key: str = "",
    ) -> KnowledgeFreshnessAssessment:
        return KnowledgeFreshnessAssessment(
            knowledge_id=reference.knowledge_id,
            status=status,
            assessed_at=assessed_at,
            retrieved_at=reference.retrieved_at,
            verified_at=reference.verified_at,
            confidence=reference.confidence,
            triggering_environment_change_id=triggering_id,
            triggering_environment_entity_key=triggering_key,
            reasons=tuple(reasons),
            source_uris=tuple(reference.source_uris),
            claim_id=reference.claim_id,
            verification_id=reference.verification_id,
            rationale=rationale,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _severer(a: FreshnessStatus, b: FreshnessStatus) -> FreshnessStatus:
    """Return the more severe status (STALE > UNCERTAIN > FRESH)."""
    order = {
        FreshnessStatus.FRESH: 0,
        FreshnessStatus.UNASSESSED: 1,
        FreshnessStatus.UNCERTAIN: 2,
        FreshnessStatus.STALE: 3,
    }
    return a if order[a] >= order[b] else b


def _enum_name(value: Any) -> str:
    """Return the ``name`` of an enum-like value, or its string form."""
    name = getattr(value, "name", None)
    return str(name) if name is not None else str(value)