"""Atlas Evolution — Runtime Observation Collection (Post-Core F1).

Transforms already-available pipeline evidence (the ``CognitionState`` and
``PipelineMetrics`` of a RuntimeCoordinator run) into the EXISTING
``SelfObservationEngine`` observation types, so the evolution scheduler
receives a multi-category observation picture instead of runtime metrics
alone.

Design constraints (post-core guided self-improvement, F1):
  - Reuses the existing observation taxonomy, producers, and bounded store.
    No new observation system, no new category, no persistence.
  - Deterministic: categories are produced in a fixed order and equivalent
    evidence always yields equivalent observations.
  - Fail-soft per category: a producer failure degrades only that category
    (recorded in the returned skip list) and never raises into the pipeline.

The helper is the smallest possible adapter between
``RuntimeCoordinator._stage_evolution_observation`` and the existing
``SelfObservationEngine``; it is pure logic (no infrastructure imports).
"""

from __future__ import annotations

from typing import Any

from atlas.evolution.self_observation import SelfObservationEngine

_SOURCE = "runtime_coordinator"


def collect_runtime_observations(
    engine: SelfObservationEngine,
    state: Any,
    metrics: Any,
    elapsed_ms: float,
) -> tuple[list[Any], list[str]]:
    """Produce observations from the runtime evidence available this run.

    Args:
        engine: The ``SelfObservationEngine`` (producers + bounded store).
        state: The pipeline ``CognitionState`` for the current run.
        metrics: The pipeline ``PipelineMetrics`` for the current run, or
            ``None`` when unavailable.
        elapsed_ms: Elapsed pipeline time in milliseconds.

    Returns:
        A tuple of ``(observations, skipped_categories)``. Observations are
        produced in the fixed order: runtime_metrics, health, reasoning,
        tool, memory. A category that cannot be produced (no evidence or a
        producer failure) is recorded in ``skipped_categories``; a failing
        producer never raises.
    """
    observations: list[Any] = []
    skipped: list[str] = []

    # 1. Runtime metrics — existing behavior preserved.
    try:
        obs = engine.observe_runtime_metrics(
            avg_response_time_ms=round(elapsed_ms, 2),
            request_count=1,
            error_count=_error_count(metrics),
            source=_SOURCE,
        )
        observations.append(obs)
    except Exception:
        skipped.append("runtime_metrics")

    # 2. Health — derived from pipeline stage outcomes.
    try:
        status, message = _health_evidence(metrics)
        obs = engine.observe_system_health(
            component="runtime_coordinator",
            status=status,
            message=message,
            source=_SOURCE,
        )
        observations.append(obs)
    except Exception:
        skipped.append("health")

    # 3. Reasoning — derived from the planning-dispatch outcomes.
    try:
        evidence = _reasoning_evidence(state)
        if evidence is not None:
            success_rate, total_outcomes, avg_capabilities_used = evidence
            obs = engine.observe_reasoning_quality(
                success_rate=success_rate,
                total_outcomes=total_outcomes,
                avg_capabilities_used=avg_capabilities_used,
                source=_SOURCE,
            )
            observations.append(obs)
        else:
            skipped.append("reasoning")
    except Exception:
        skipped.append("reasoning")

    # 4. Tool — derived from the TOOL_EXECUTION stage result.
    try:
        evidence = _tool_evidence(state)
        if evidence is not None:
            tool_name, success, duration_ms = evidence
            obs = engine.observe_tool_usage(
                tool_name=tool_name,
                invocation_count=1,
                success_count=1 if success else 0,
                avg_duration_ms=duration_ms,
                source=_SOURCE,
            )
            observations.append(obs)
        else:
            skipped.append("tool")
    except Exception:
        skipped.append("tool")

    # 5. Memory — derived from the MEMORY_RETRIEVAL stage results.
    try:
        evidence = _memory_evidence(state)
        if evidence is not None:
            total_retrieved, retrieval_rate, avg_relevance = evidence
            obs = engine.observe_memory_quality(
                total_memories=total_retrieved,
                avg_relevance_score=avg_relevance,
                retrieval_success_rate=retrieval_rate,
                source=_SOURCE,
            )
            observations.append(obs)
        else:
            skipped.append("memory")
    except Exception:
        skipped.append("memory")

    return observations, skipped


# ---------------------------------------------------------------------------
# Evidence adapters (deterministic, read-only)
# ---------------------------------------------------------------------------


def _error_count(metrics: Any) -> int:
    """Return the number of failed stages from pipeline metrics."""
    if metrics is None:
        return 0
    return int(getattr(metrics, "failed_count", 0) or 0)


def _health_evidence(metrics: Any) -> tuple[str, str]:
    """Return ``(status, message)`` from pipeline stage outcomes."""
    error_count = _error_count(metrics)
    if error_count > 0:
        return "degraded", f"{error_count} stage failure(s) in this pipeline run"
    return "healthy", "all pipeline stages successful"


def _reasoning_evidence(state: Any) -> tuple[float, int, float] | None:
    """Return ``(success_rate, total_outcomes, avg_capabilities_used)``.

    Derived from the planning-dispatch results recorded on the pipeline
    state. Returns ``None`` when no capability was dispatched (no outcome
    evidence this run).
    """
    reasoning = getattr(state, "reasoning_result", None) or {}
    results = reasoning.get("results") or []
    if not results:
        return None
    capabilities = reasoning.get("capabilities") or []
    successes = sum(1 for result in results if result.get("success"))
    success_rate = successes / len(results)
    avg_capabilities_used = round(len(capabilities) / len(results), 4)
    return (success_rate, len(results), avg_capabilities_used)


def _tool_evidence(state: Any) -> tuple[str, bool, float] | None:
    """Return ``(tool_name, success, avg_duration_ms)``.

    Derived from the TOOL_EXECUTION stage result. Returns ``None`` when no
    tool ran this run.
    """
    tool = getattr(state, "tool_result", None)
    if tool is None:
        return None
    tool_name = tool.get("tool_name") or "unknown"
    success = bool(tool.get("success", False))
    duration_ms = float(tool.get("execution_time_ms", 0.0) or 0.0)
    return (tool_name, success, duration_ms)


def _memory_evidence(state: Any) -> tuple[int, float, float] | None:
    """Return ``(total_retrieved, retrieval_success_rate, avg_relevance)``.

    Derived from the MEMORY_RETRIEVAL stage results. Only retrieved
    (search-selected) memories are counted, so retrieval success and
    relevance proxies are ``1.0`` when any memory was retrieved. An empty
    retrieval yields no evidence (``None``) and the category is skipped
    rather than fabricating a failure.
    """
    memories = getattr(state, "memories", None)
    if not memories:
        return None
    return (len(memories), 1.0, 1.0)
