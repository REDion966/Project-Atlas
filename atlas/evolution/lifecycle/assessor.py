"""Atlas Post-Core F3 — Lifecycle Assessor.

Pure, deterministic capability/model/tool/skill lifecycle assessment layer.

The assessor consumes:
  * F1 ``EnvironmentChange`` records (duck-typed: ``entity`` / ``change_type``)
  * F2 ``KnowledgeFreshnessAssessment`` records (duck-typed: ``knowledge_id`` /
    ``status``)
  * existing lifecycle metadata exposed through ``LifecycleTarget``

It NEVER:
  * mutates a registry (register/unregister/activate/deprecate/remove)
  * modifies routing priorities or fallback chains
  * replaces providers or models
  * disables capabilities
  * executes code / performs research
  * approves proposals
  * invokes governance, authorization, or the SelfDevelopmentLoop

It only produces bounded, deterministically-ordered ``LifecycleAssessment``
records for a future governed adaptation engine.

Determinism contract: identical (targets, changes, freshness, now) always
produce identical assessments. Priority is always in [0.0, 1.0].
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from atlas.evolution.lifecycle.models import (
    LifecycleAction,
    LifecycleAssessment,
    LifecycleAssessmentResult,
    LifecycleReason,
    LifecycleTarget,
    LifecycleTargetKind,
    utc_now,
)


def _enum_name(value: Any) -> str:
    """Return the ``name`` of an enum-like value, or its string form."""
    name = getattr(value, "name", None)
    return str(name) if name is not None else str(value)


def _status_name(status: Any) -> str:
    """Normalize a status value (enum or string) to an upper-cased string."""
    if status is None:
        return ""
    return _enum_name(status).upper()


class CapabilityLifecycleAssessor:
    """Assess lifecycle targets against deterministic signals.

    Args:
        now: Optional clock callable returning a UTC ``datetime``; defaults to
            ``utc_now``. Injectable for deterministic tests.
    """

    def __init__(self, now: Any | None = None) -> None:
        self._now = now or utc_now

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        target: LifecycleTarget,
        changes: Iterable[Any] | None = None,
        freshness: Iterable[Any] | None = None,
        now: datetime | None = None,
    ) -> LifecycleAssessment:
        """Assess a single lifecycle target.

        The target and all inputs are never mutated.
        """
        assessed_at = now or self._now()
        reasons: list[LifecycleReason] = []
        evidence_change_ids: list[str] = []
        evidence_knowledge_ids: list[str] = []
        action = LifecycleAction.NONE
        priority = 0.0

        # 1. Explicit deprecation / unavailability (highest precedence).
        if _is_deprecated(target):
            reasons.append(LifecycleReason.EXPLICIT_DEPRECATION)
            if target.replacement:
                action = LifecycleAction.REPLACE
                reasons.append(LifecycleReason.REPLACEMENT_AVAILABLE)
                priority = 1.0
            else:
                action = LifecycleAction.DEPRECATE
                priority = 1.0
        elif _is_unavailable(target):
            reasons.append(LifecycleReason.UNAVAILABLE)
            if target.replacement:
                action = LifecycleAction.FALLBACK
                reasons.append(LifecycleReason.REPLACEMENT_AVAILABLE)
                priority = 1.0
            else:
                action = LifecycleAction.DEPRECATE
                priority = 0.9

        # 2. Relevant F1 environment changes.
        relevant_changes = [
            c for c in (changes or ()) if self._is_relevant(c, target)
        ]
        if relevant_changes:
            reasons.append(LifecycleReason.ENVIRONMENT_CHANGE)
            evidence_change_ids = [
                self._change_id(c) for c in relevant_changes
            ]
            if _changes_say_unavailable(relevant_changes):
                if action is LifecycleAction.NONE and target.replacement:
                    action = LifecycleAction.FALLBACK
                    reasons.append(LifecycleReason.REPLACEMENT_AVAILABLE)
                    priority = 0.95
                elif action is LifecycleAction.NONE:
                    action = LifecycleAction.REVIEW
                    priority = 0.9
                else:
                    priority = max(priority, 0.95)
            elif action is LifecycleAction.NONE:
                action = LifecycleAction.REVIEW
                priority = 0.8
            else:
                priority = max(priority, 0.8)

        # 3. F2 freshness signals on explicitly declared knowledge deps.
        relevant_freshness = [
            a for a in (freshness or ())
            if getattr(a, "knowledge_id", "") in target.knowledge_dependencies
        ]
        for assessment in relevant_freshness:
            status = _status_name(getattr(assessment, "status", ""))
            kid = getattr(assessment, "knowledge_id", "") or ""
            if status == "STALE":
                reasons.append(LifecycleReason.STALE_KNOWLEDGE)
                if kid and kid not in evidence_knowledge_ids:
                    evidence_knowledge_ids.append(kid)
                priority = max(priority, 0.6)
                if action is LifecycleAction.NONE:
                    action = LifecycleAction.REVIEW
            elif status == "UNCERTAIN":
                reasons.append(LifecycleReason.UNCERTAIN_KNOWLEDGE)
                if kid and kid not in evidence_knowledge_ids:
                    evidence_knowledge_ids.append(kid)
                priority = max(priority, 0.4)
                if action is LifecycleAction.NONE:
                    action = LifecycleAction.REVIEW

        # 4. No actionable evidence.
        if action is LifecycleAction.NONE:
            reasons.append(LifecycleReason.VALID)
            priority = 0.0

        return LifecycleAssessment(
            target_kind=target.target_kind,
            target_identifier=target.identifier,
            action=action,
            reasons=tuple(_dedup(reasons)),
            priority=_clamp(priority),
            evidence_change_ids=tuple(_dedup(evidence_change_ids)),
            evidence_knowledge_ids=tuple(_dedup(evidence_knowledge_ids)),
            assessed_at=assessed_at,
            rationale=",".join(r.name.lower() for r in _dedup(reasons)),
        )

    def assess_many(
        self,
        targets: Iterable[LifecycleTarget],
        changes: Iterable[Any] | None = None,
        freshness: Iterable[Any] | None = None,
        now: datetime | None = None,
    ) -> LifecycleAssessmentResult:
        """Assess many targets; result is deterministically ordered."""
        assessments = tuple(
            self.assess(t, changes=changes, freshness=freshness, now=now)
            for t in targets
        )
        return LifecycleAssessmentResult(
            assessments=assessments,
            assessed_at=now or self._now(),
        )

    def find_actionable(
        self,
        targets: Iterable[LifecycleTarget],
        changes: Iterable[Any] | None = None,
        freshness: Iterable[Any] | None = None,
        now: datetime | None = None,
    ) -> "tuple[LifecycleAssessment, ...]":
        """Return only assessments whose action is not NONE."""
        return self.assess_many(
            targets, changes=changes, freshness=freshness, now=now
        ).actionable

    # ------------------------------------------------------------------
    # Deterministic relevance
    # ------------------------------------------------------------------

    @staticmethod
    def _is_relevant(change: Any, target: LifecycleTarget) -> bool:
        """True when an F1 change deterministically relates to a target.

        A change is relevant when ANY of the following holds:
          * the change entity key equals the target key
          * the change entity key is in the target's dependency_entity_keys
          * the change domain is in the target's affected_domains
        Relevance is never invented; unclassifiable changes are not relevant.
        """
        change_key = CapabilityLifecycleAssessor._change_entity_key(change)
        change_domain = CapabilityLifecycleAssessor._change_domain(change)
        if not change_key and not change_domain:
            return False
        if change_key:
            if change_key == target.key:
                return True
            if change_key in target.dependency_entity_keys:
                return True
        if change_domain:
            if change_domain in target.affected_domains:
                return True
        return False

    @staticmethod
    def _change_id(change: Any) -> str:
        direct = getattr(change, "change_id", "") or ""
        if direct:
            return str(direct)
        key = CapabilityLifecycleAssessor._change_entity_key(change)
        observed = getattr(change, "observed_at", None)
        if key and observed is not None:
            stamp = getattr(observed, "isoformat", None)
            if stamp is not None:
                return f"{key}@{stamp()}"
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


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _is_deprecated(target: LifecycleTarget) -> bool:
    if target.deprecated:
        return True
    return _status_name(target.status) == "DEPRECATED"


def _is_unavailable(target: LifecycleTarget) -> bool:
    if target.available is False:
        return True
    return _status_name(target.status) in ("UNAVAILABLE", "OFFLINE", "REMOVED")


def _changes_say_unavailable(changes: Iterable[Any]) -> bool:
    for change in changes:
        current = getattr(change, "current", None) or {}
        if isinstance(current, dict):
            if current.get("available") is False:
                return True
            status = str(current.get("status", "") or "").upper()
            if status in ("UNAVAILABLE", "OFFLINE", "REMOVED"):
                return True
        prev = getattr(change, "previous", None) or {}
        if isinstance(prev, dict) and prev.get("available") is True:
            current_map = getattr(change, "current", None) or {}
            if isinstance(current_map, dict) and current_map.get("available") is not True:
                return True
    return False


def _dedup(items: list[Any]) -> list[Any]:
    """Return items in order with duplicates removed."""
    out: list[Any] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _clamp(value: float) -> float:
    """Bound a priority to [0.0, 1.0] with two-decimal rounding."""
    return round(min(1.0, max(0.0, float(value))), 2)