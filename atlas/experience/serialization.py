"""
Atlas Experience Serialization — Phase 9.1

Pure logic conversion between domain models and JSON-safe dictionaries.
This module is the only place that knows both the model shapes and the
storage representation; it is intentionally separate from both models.py
and the SQLite adapter.

No infrastructure imports. No database imports.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    SelfModelSnapshot,
    StructuredExperience,
    TrackedGoal,
    TrendAnalysis,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    """Convert a datetime to an ISO 8601 string with timezone-naive fallback."""
    return dt.isoformat()


def _parse_iso(value: Any) -> datetime:
    """Parse an ISO 8601 string into a datetime."""
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.now()
    # fromisoformat handles the format produced by datetime.isoformat()
    return datetime.fromisoformat(str(value))


def _as_enum_name(value: Any, enum_cls: type[Enum]) -> Enum:
    """Return the enum member whose name matches the string value."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls[value] if value is not None else list(enum_cls)[0]
    except (KeyError, TypeError):
        # Unknown enum value — use the first member as a safe default.
        return list(enum_cls)[0]


def _as_list(value: Any) -> list[Any]:
    """Ensure a value is a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


# ----------------------------------------------------------------------
# StructuredExperience
# ----------------------------------------------------------------------

def experience_to_dict(experience: StructuredExperience) -> dict[str, Any]:
    """Convert a StructuredExperience to a JSON-safe dictionary."""
    return {
        "experience_id": experience.experience_id,
        "timestamp": _iso(experience.timestamp),
        "duration_ms": experience.duration_ms,
        "pipeline_path": list(experience.pipeline_path),
        "outcome": experience.outcome.name,
        "user_input": experience.user_input,
        "conversation_history_length": experience.conversation_history_length,
        "understanding_insights_count": experience.understanding_insights_count,
        "concepts_extracted": list(experience.concepts_extracted),
        "world_model_entities": experience.world_model_entities,
        "world_model_relations": experience.world_model_relations,
        "reasoning_goal": experience.reasoning_goal,
        "reasoning_capabilities": list(experience.reasoning_capabilities),
        "reasoning_success_count": experience.reasoning_success_count,
        "reasoning_total_count": experience.reasoning_total_count,
        "planning_goal": experience.planning_goal,
        "planning_step_count": experience.planning_step_count,
        "planning_validation_errors": experience.planning_validation_errors,
        "tool_name": experience.tool_name,
        "tool_success": experience.tool_success,
        "learning_insights_count": experience.learning_insights_count,
        "reflection_suggestions_count": experience.reflection_suggestions_count,
        "goal_recommendations_count": experience.goal_recommendations_count,
        "identity_version": experience.identity_version,
        "identity_belief_count": experience.identity_belief_count,
        "identity_capability_count": experience.identity_capability_count,
    }


def dict_to_experience(data: dict[str, Any]) -> StructuredExperience:
    """Convert a dictionary back to a StructuredExperience."""
    safe = dict(data)  # copy to avoid mutating caller

    # Only copy keys that the model actually accepts; drop extras for forward
    # compatibility.
    model_fields = {
        "experience_id",
        "timestamp",
        "duration_ms",
        "pipeline_path",
        "outcome",
        "user_input",
        "conversation_history_length",
        "understanding_insights_count",
        "concepts_extracted",
        "world_model_entities",
        "world_model_relations",
        "reasoning_goal",
        "reasoning_capabilities",
        "reasoning_success_count",
        "reasoning_total_count",
        "planning_goal",
        "planning_step_count",
        "planning_validation_errors",
        "tool_name",
        "tool_success",
        "learning_insights_count",
        "reflection_suggestions_count",
        "goal_recommendations_count",
        "identity_version",
        "identity_belief_count",
        "identity_capability_count",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["timestamp"] = _parse_iso(filtered.get("timestamp"))
    filtered["outcome"] = _as_enum_name(filtered.get("outcome"), ExperienceOutcome)
    filtered["pipeline_path"] = _as_list(filtered.get("pipeline_path"))
    filtered["concepts_extracted"] = _as_list(filtered.get("concepts_extracted"))
    filtered["reasoning_capabilities"] = _as_list(filtered.get("reasoning_capabilities"))

    return StructuredExperience(**filtered)


# ----------------------------------------------------------------------
# TrendAnalysis
# ----------------------------------------------------------------------

def analysis_to_dict(analysis: TrendAnalysis) -> dict[str, Any]:
    """Convert a TrendAnalysis to a JSON-safe dictionary."""
    return {
        "analysis_id": analysis.analysis_id,
        "timestamp": _iso(analysis.timestamp),
        "window_size": analysis.window_size,
        "overall_success_rate": analysis.overall_success_rate,
        "success_rate_trend": analysis.success_rate_trend,
        "avg_understanding_insights": analysis.avg_understanding_insights,
        "understanding_trend": analysis.understanding_trend,
        "avg_reasoning_success": analysis.avg_reasoning_success,
        "reasoning_trend": analysis.reasoning_trend,
        "avg_planning_errors": analysis.avg_planning_errors,
        "planning_trend": analysis.planning_trend,
        "tool_success_rate": analysis.tool_success_rate,
        "tool_trend": analysis.tool_trend,
        "learning_insight_rate": analysis.learning_insight_rate,
        "learning_trend": analysis.learning_trend,
        "identity_stability": analysis.identity_stability,
        "capability_trends": dict(analysis.capability_trends),
    }


def dict_to_analysis(data: dict[str, Any]) -> TrendAnalysis:
    """Convert a dictionary back to a TrendAnalysis."""
    safe = dict(data)
    model_fields = {
        "analysis_id",
        "timestamp",
        "window_size",
        "overall_success_rate",
        "success_rate_trend",
        "avg_understanding_insights",
        "understanding_trend",
        "avg_reasoning_success",
        "reasoning_trend",
        "avg_planning_errors",
        "planning_trend",
        "tool_success_rate",
        "tool_trend",
        "learning_insight_rate",
        "learning_trend",
        "identity_stability",
        "capability_trends",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["timestamp"] = _parse_iso(filtered.get("timestamp"))
    filtered["capability_trends"] = dict(filtered.get("capability_trends") or {})

    return TrendAnalysis(**filtered)


# ----------------------------------------------------------------------
# TrackedGoal
# ----------------------------------------------------------------------

def goal_to_dict(goal: TrackedGoal) -> dict[str, Any]:
    """Convert a TrackedGoal to a JSON-safe dictionary."""
    return {
        "goal_id": goal.goal_id,
        "recommendation_id": goal.recommendation_id,
        "goal_title": goal.goal_title,
        "proposed_at": _iso(goal.proposed_at),
        "outcome": goal.outcome.name,
        "outcome_reason": goal.outcome_reason,
        "related_experience_ids": list(goal.related_experience_ids),
        "last_evaluated": _iso(goal.last_evaluated),
    }


def dict_to_goal(data: dict[str, Any]) -> TrackedGoal:
    """Convert a dictionary back to a TrackedGoal."""
    safe = dict(data)
    model_fields = {
        "goal_id",
        "recommendation_id",
        "goal_title",
        "proposed_at",
        "outcome",
        "outcome_reason",
        "related_experience_ids",
        "last_evaluated",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["proposed_at"] = _parse_iso(filtered.get("proposed_at"))
    filtered["last_evaluated"] = _parse_iso(filtered.get("last_evaluated"))
    filtered["outcome"] = _as_enum_name(filtered.get("outcome"), GoalOutcome)
    filtered["related_experience_ids"] = _as_list(filtered.get("related_experience_ids"))

    return TrackedGoal(**filtered)


# ----------------------------------------------------------------------
# SelfModelSnapshot
# ----------------------------------------------------------------------

def snapshot_to_dict(snapshot: SelfModelSnapshot) -> dict[str, Any]:
    """Convert a SelfModelSnapshot to a JSON-safe dictionary."""
    return {
        "snapshot_id": snapshot.snapshot_id,
        "timestamp": _iso(snapshot.timestamp),
        "total_experiences": snapshot.total_experiences,
        "overall_success_rate": snapshot.overall_success_rate,
        "capability_assessments": dict(snapshot.capability_assessments),
        "belief_evidence": dict(snapshot.belief_evidence),
        "trend_summary": snapshot.trend_summary,
        "identity_version": snapshot.identity_version,
        "last_trend_analysis": _iso(snapshot.last_trend_analysis),
        "recent_improvement_evidence": list(snapshot.recent_improvement_evidence),
        "persistent_challenges": list(snapshot.persistent_challenges),
    }


def dict_to_snapshot(data: dict[str, Any]) -> SelfModelSnapshot:
    """Convert a dictionary back to a SelfModelSnapshot."""
    safe = dict(data)
    model_fields = {
        "snapshot_id",
        "timestamp",
        "total_experiences",
        "overall_success_rate",
        "capability_assessments",
        "belief_evidence",
        "trend_summary",
        "identity_version",
        "last_trend_analysis",
        "recent_improvement_evidence",
        "persistent_challenges",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["timestamp"] = _parse_iso(filtered.get("timestamp"))
    filtered["last_trend_analysis"] = _parse_iso(filtered.get("last_trend_analysis"))
    filtered["capability_assessments"] = dict(filtered.get("capability_assessments") or {})
    filtered["belief_evidence"] = dict(filtered.get("belief_evidence") or {})
    filtered["recent_improvement_evidence"] = _as_list(
        filtered.get("recent_improvement_evidence")
    )
    filtered["persistent_challenges"] = _as_list(filtered.get("persistent_challenges"))

    return SelfModelSnapshot(**filtered)
