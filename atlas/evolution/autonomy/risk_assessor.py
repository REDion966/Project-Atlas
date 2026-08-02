"""
Atlas Evolution Autonomy — Risk Assessor — Phase 16.2

Deterministic risk scoring for ``EvolutionRequest``.

Gate 3 of the governance pipeline (see ``PHASE_16_ARCHITECTURE.md`` §7).
The assessor consumes a request plus optional contextual signals
(``PlanningContext`` and goal-layer metadata) and produces an immutable
``RiskAssessment``. It contains no infrastructure, no AI, and no gateway
access.

Risk is a deterministic function of:
  - target scope blast radius
  - operation kind (e.g. remove/deprecate is riskier than add)
  - presence/absence of a rollback plan signal
  - historical context (PlanningContext area adjustments / bottlenecks)
  - goal-layer signals when the request was transcribed from a goal

The score is bounded to [0.0, 1.0] and maps to one of the four
``RiskLevel`` values. The weights and thresholds are module-level constants
so they can be reviewed in a single place.

Pure logic. No infrastructure. No AI. No gateway access.
"""

from dataclasses import dataclass, field
from typing import Any

from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    RiskAssessment,
    RiskLevel,
)
from atlas.evolution.decision_models import PlanningContext
from atlas.evolution.governance.models import ScopeType
from atlas.goals.models import ImprovementGoal


# ---------------------------------------------------------------------------
# Tuning constants (reviewed per architecture; deterministic and explicit)
# ---------------------------------------------------------------------------


# Base blast radius per scope. Higher means more system surface affected.
_SCOPE_BASE_WEIGHT: dict[ScopeType, float] = {
    ScopeType.CONFIG: 0.30,
    ScopeType.MEMORY: 0.15,
    ScopeType.KNOWLEDGE: 0.15,
    ScopeType.CAPABILITY: 0.35,
}

# Operation-kind risk modifier. Added to the score for dangerous operations.
_OPERATION_MODIFIERS: dict[str, float] = {
    "add": 0.00,
    "update": 0.05,
    "remove": 0.20,
    "register": 0.05,
    "enhance": 0.10,
    "deprecate": 0.15,
}

# Risk thresholds mapping continuous score to RiskLevel.
_LOW_THRESHOLD = 0.30
_MEDIUM_THRESHOLD = 0.55
_HIGH_THRESHOLD = 0.80

# Historical context multipliers.
_CONTEXT_HISTORY_WEIGHT = 0.15
_CONTEXT_RECOMMENDATION_RISK: dict[str, float] = {
    "prefer": -0.10,
    "neutral": 0.00,
    "caution": 0.10,
    "avoid": 0.20,
}

# Bottleneck alert presence adds a small deterministic boost.
_BOTTLENECK_BOOST = 0.05

# Missing rollback plan (when one would be expected) adds risk.
_MISSING_ROLLBACK_PENALTY = 0.10


# ---------------------------------------------------------------------------
# Public assessor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionRiskAssessor:
    """Deterministic gate 3 risk assessor for ``EvolutionRequest``.

    Accepts optional contextual inputs via dependency injection:
      - planning_context: historical evolution evidence from the Phase 13.6
        knowledge pipeline (read-only).
      - goal: the Phase 15 ImprovementGoal when the request was transcribed
        from a goal (read-only).

    All scoring is deterministic: the same request + context always yields
    the same RiskAssessment.
    """

    planning_context: PlanningContext | None = None
    goal: ImprovementGoal | None = None

    def assess(self, request: EvolutionRequest) -> RiskAssessment:
        """Return a deterministic RiskAssessment for ``request``.

        Args:
            request: The EvolutionRequest to assess.

        Returns:
            A RiskAssessment with risk_level, score, factors, and the
            requires_user_approval / requires_rollback flags.
        """
        factors: dict[str, float] = {}

        # 1. Scope blast radius
        scope = request.target_scope
        scope_weight = _SCOPE_BASE_WEIGHT.get(scope, 0.25)
        factors["scope_weight"] = round(scope_weight, 3)

        # 2. Operation kind modifier
        operation = _extract_operation(request)
        operation_modifier = _OPERATION_MODIFIERS.get(operation, 0.10)
        factors["operation_modifier"] = round(operation_modifier, 3)

        # 3. Rollback readiness
        rollback_ready = request.rollback is not None
        rollback_modifier = 0.0 if rollback_ready else _MISSING_ROLLBACK_PENALTY
        factors["rollback_modifier"] = round(rollback_modifier, 3)

        # 4. Historical context signals (PlanningContext)
        context_modifier = _context_modifier(self.planning_context, request)
        factors["context_modifier"] = round(context_modifier, 3)

        # 5. Goal-layer signals
        goal_modifier = _goal_modifier(self.goal)
        factors["goal_modifier"] = round(goal_modifier, 3)

        # Compose score
        score = (
            scope_weight
            + operation_modifier
            + rollback_modifier
            + context_modifier
            + goal_modifier
        )
        score = max(0.0, min(1.0, score))
        factors["raw_score"] = round(score, 3)

        risk_level = _risk_level_for_score(score)
        requires_user_approval = risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        requires_rollback = risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}

        summary = (
            f"Risk assessment for {scope.name}: score={score:.3f}, "
            f"level={risk_level.name}. "
            f"Scope weight={scope_weight:.3f}, operation={operation}, "
            f"rollback_ready={rollback_ready}."
        )

        return RiskAssessment(
            risk_level=risk_level,
            score=round(score, 3),
            factors=factors,
            requires_user_approval=requires_user_approval,
            requires_rollback=requires_rollback,
            summary=summary,
        )


# ---------------------------------------------------------------------------
# Internal scoring helpers
# ---------------------------------------------------------------------------


def _extract_operation(request: EvolutionRequest) -> str:
    """Extract a normalised operation string from the request payload.

    The payload's operation field is preferred. CAPABILITY requests use
    ``upgrade_kind``. Defaults to 'update' when no operation is present.
    """
    payload = request.change_payload
    scope = request.target_scope

    if scope == ScopeType.CAPABILITY:
        upgrade_kind = payload.get("upgrade_kind")
        if isinstance(upgrade_kind, str):
            return upgrade_kind.lower()

    operation = payload.get("operation")
    if isinstance(operation, str):
        return operation.lower()

    # No recognised operation -> conservative default
    return "update"


def _context_modifier(
    context: PlanningContext | None,
    request: EvolutionRequest,
) -> float:
    """Compute the deterministic modifier from a PlanningContext.

    Reads the area-adjustment recommendation for the request's canonical
    area and any bottleneck alerts. No side effects.
    """
    if context is None:
        return 0.0

    area = _area_for_scope(request.target_scope)
    modifier = 0.0

    adjustment = context.area_adjustments.get(area)
    if adjustment is not None:
        recommendation = adjustment.recommendation.lower()
        modifier += _CONTEXT_RECOMMENDATION_RISK.get(recommendation, 0.0)
        # Historical success rate below 0.5 adds a small caution penalty.
        if adjustment.historical_success_rate < 0.5:
            modifier += 0.05

    if context.bottleneck_alerts:
        # Only count alerts relevant to the request's area.
        for alert in context.bottleneck_alerts:
            if alert.area.lower() == area.lower():
                modifier += _BOTTLENECK_BOOST
                break

    return round(modifier * _CONTEXT_HISTORY_WEIGHT, 3)


def _goal_modifier(goal: ImprovementGoal | None) -> float:
    """Compute the deterministic modifier from goal-layer signals.

    Uses goal priority and evidence count as weak signals. Higher priority
    goals and goals with strong evidence slightly increase the perceived
    risk because their failure has more planning weight.
    """
    if goal is None:
        return 0.0

    modifier = 0.0

    # Priority signal: CRITICAL adds more risk than LOW.
    priority_value = getattr(goal.priority, "value", 3)
    if isinstance(priority_value, int):
        # priority_value is 1..5 where 1 is CRITICAL and 5 is DEFERRED.
        modifier += (priority_value / 10.0)

    # Evidence signal: goals with substantial evidence carry more weight.
    if goal.evidence_count > 5:
        modifier += 0.03

    # Confidence signal: low-confidence goals are slightly riskier.
    if goal.confidence < 0.5:
        modifier += 0.02

    return round(modifier, 3)


def _risk_level_for_score(score: float) -> RiskLevel:
    """Map a continuous score in [0.0, 1.0] to a RiskLevel."""
    if score < _LOW_THRESHOLD:
        return RiskLevel.LOW
    if score < _MEDIUM_THRESHOLD:
        return RiskLevel.MEDIUM
    if score < _HIGH_THRESHOLD:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def _area_for_scope(scope: ScopeType) -> str:
    """Canonical evolution area for a scope (matches adapter mapping)."""
    if scope == ScopeType.CONFIG:
        return "config"
    if scope == ScopeType.MEMORY:
        return "memory"
    if scope == ScopeType.KNOWLEDGE:
        return "knowledge"
    if scope == ScopeType.CAPABILITY:
        return "capability"
    return "governance:unknown"
