"""Atlas Orchestration — Experience Capture (P2/B2.4).

Additive, deterministic bridge from a completed orchestration run
(TaskSpec + OrchestrationResult) into the existing
StructuredExperience contract. Reuses ExperienceRepository surface
without schema changes, migrations, or RuntimeCoordinator modifications.

The module is pure: no kernel, AI, storage, or evolution imports.
It never bypasses AuthorityService or SessionContext, never
fabricates success, and never executes arbitrary code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlas.experience.models import ExperienceOutcome, StructuredExperience


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _derive_outcome(result: Any) -> ExperienceOutcome:
    status = getattr(result, "status", None)
    value = getattr(status, "value", None) or str(status or "")
    value = value.lower() if isinstance(value, str) else ""
    if value == "completed":
        return ExperienceOutcome.SUCCESS
    if value == "partial":
        return ExperienceOutcome.PARTIAL
    if value in ("failed", "rejected"):
        return ExperienceOutcome.FAILURE
    if value in ("empty", "skipped"):
        return ExperienceOutcome.SKIPPED
    # Fallback: inspect step failure kinds.
    failure_kinds = getattr(result, "failure_kinds", None)
    if callable(failure_kinds):
        try:
            kinds = failure_kinds()
            if kinds:
                return ExperienceOutcome.FAILURE
        except Exception:
            pass
    return ExperienceOutcome.SKIPPED


def _pipeline_path_for(task_spec: Any | None, result: Any) -> list[str]:
    parts: list[str] = ["orchestration"]
    if task_spec is not None:
        task_type = getattr(getattr(task_spec, "task_type", None), "value", None)
        if isinstance(task_type, str) and task_type:
            parts.append(task_type)
        else:
            raw = str(getattr(task_spec, "task_type", "") or "").strip()
            if raw:
                parts.append(raw)
    status = getattr(result, "status", None)
    status_value = getattr(status, "value", None) or str(status or "")
    if status_value:
        parts.append(str(status_value).strip().lower())
    # Include first target for provenance (bounded).
    steps = getattr(result, "steps", ()) or ()
    if steps:
        first = steps[0]
        target = getattr(first, "target", "") or ""
        if isinstance(target, str) and target.strip():
            parts.append(target.strip()[:64])
    # Session attribution is encoded in existing pipeline_path so it
    # survives persistence without schema migration.
    session_id = getattr(result, "session_id", None)
    principal_id = getattr(result, "principal_id", None)
    authority = getattr(result, "authority", None)
    if isinstance(principal_id, str) and principal_id.strip():
        parts.append(f"principal:{principal_id.strip()[:64]}")
    if isinstance(authority, str) and authority.strip():
        parts.append(f"authority:{authority.strip()[:32]}")
    if isinstance(session_id, str) and session_id.strip():
        parts.append(f"session:{session_id.strip()[:64]}")
    return parts[:12]


def _concepts_for(task_spec: Any | None, principal_id: str | None, authority: str | None) -> list[str]:
    concepts: list[str] = []
    if task_spec is not None:
        context = getattr(task_spec, "context", None)
        if isinstance(context, dict):
            raw_concepts = context.get("concepts")
            if isinstance(raw_concepts, (list, tuple)):
                for item in list(raw_concepts)[:20]:
                    if isinstance(item, str) and item.strip():
                        concepts.append(item.strip()[:64])
    # Encode session attribution as concepts so per-user learning
    # can filter without a schema change.
    if isinstance(principal_id, str) and principal_id.strip():
        concepts.append(f"principal:{principal_id.strip()[:64]}")
    if isinstance(authority, str) and authority.strip():
        concepts.append(f"authority:{authority.strip()[:32]}")
    # Deduplicate preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped[:24]


def build_orchestration_experience(
    *,
    experience_id: str,
    user_input: str,
    task_spec: Any | None,
    result: Any,
    conversation_history_length: int = 0,
    timestamp: datetime | None = None,
    duration_ms: float | None = None,
) -> StructuredExperience | None:
    """Build a StructuredExperience from an orchestration run.

    Pure and deterministic. Never raises. Returns None only when
    inputs are missing in a fail-closed manner (no result).

    Args:
        experience_id: Bounded ID (e.g. "EXP-00000001").
        user_input: Original bounded user text (≤500 chars).
        task_spec: The TaskSpec that produced the run (may be None).
        result: The OrchestrationResult (required).
        conversation_history_length: Bounded history length.
        timestamp: Optional timestamp override (defaults to result.created_at or now).
        duration_ms: Optional duration override (defaults to result.elapsed_ms).
    """
    if result is None:
        return None
    try:
        outcome = _derive_outcome(result)
        ts = timestamp
        if ts is None:
            ts = getattr(result, "created_at", None)
            if not isinstance(ts, datetime):
                ts = _utc_now()
        dur = duration_ms
        if dur is None:
            dur = getattr(result, "elapsed_ms", 0.0)
            try:
                dur = float(dur)
            except Exception:
                dur = 0.0
        pipeline_path = _pipeline_path_for(task_spec, result)
        concepts = _concepts_for(
            task_spec,
            getattr(result, "principal_id", None),
            getattr(result, "authority", None),
        )
        history_len = max(0, min(int(conversation_history_length or 0), 10_000))

        # Derive reasoning/planning fields from the run.
        reasoning_goal = ""
        planning_goal = ""
        if task_spec is not None:
            reasoning_goal = _bounded_text(getattr(task_spec, "intent", ""), 500)
            # goal_string() is the canonical bounded goal.
            try:
                goal_fn = getattr(task_spec, "goal_string", None)
                if callable(goal_fn):
                    planning_goal = _bounded_text(goal_fn(), 500)
                else:
                    planning_goal = _bounded_text(getattr(task_spec, "goal", ""), 500)
            except Exception:
                planning_goal = _bounded_text(getattr(task_spec, "goal", ""), 500)

        steps = tuple(getattr(result, "steps", ()) or ())
        reasoning_caps = []
        for s in steps:
            target = getattr(s, "target", "") or ""
            if isinstance(target, str) and target.strip():
                reasoning_caps.append(target.strip()[:120])
        # Deduplicate caps.
        seen_caps: set[str] = set()
        dedup_caps: list[str] = []
        for c in reasoning_caps:
            if c not in seen_caps:
                seen_caps.add(c)
                dedup_caps.append(c)
        dedup_caps = dedup_caps[:8]

        completed = 0
        total = len(steps)
        try:
            completed = int(getattr(result, "completed_count", 0) or 0)
        except Exception:
            completed = sum(1 for s in steps if getattr(s, "state", None) and getattr(s.state, "value", "") == "completed")

        # Tool attribution: first TOOL or RESEARCH step.
        tool_name = ""
        tool_success = False
        for s in steps:
            kind = getattr(s, "kind", None)
            kind_val = getattr(kind, "value", None) or str(kind or "")
            if kind_val in ("tool", "research", "capability"):
                tool_name = getattr(s, "target", "") or ""
                tool_success = bool(getattr(s, "state", None) and getattr(s.state, "value", "") == "completed")
                break

        # Planning validation errors: count of failed steps.
        failed = 0
        try:
            failed = int(getattr(result, "failed_count", 0) or 0)
        except Exception:
            failed = sum(1 for s in steps if getattr(s, "state", None) and getattr(s.state, "value", "") == "failed")

        return StructuredExperience(
            experience_id=experience_id,
            timestamp=ts,
            duration_ms=float(dur),
            pipeline_path=pipeline_path,
            outcome=outcome,
            user_input=_bounded_text(user_input, 500),
            conversation_history_length=history_len,
            understanding_insights_count=0,
            concepts_extracted=concepts,
            world_model_entities=0,
            world_model_relations=0,
            reasoning_goal=reasoning_goal,
            reasoning_capabilities=dedup_caps,
            reasoning_success_count=max(0, min(completed, 10_000)),
            reasoning_total_count=max(0, min(total, 10_000)),
            planning_goal=planning_goal,
            planning_step_count=max(0, min(total, 10_000)),
            planning_validation_errors=max(0, min(failed, 10_000)),
            tool_name=_bounded_text(tool_name, 120),
            tool_success=bool(tool_success),
            learning_insights_count=0,
            reflection_suggestions_count=0,
            goal_recommendations_count=0,
            identity_version=0,
            identity_belief_count=0,
            identity_capability_count=0,
        )
    except Exception:
        return None
