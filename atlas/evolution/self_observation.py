"""
Atlas Self-Observation Engine

Observes Atlas runtime metrics, reasoning quality, tool usage, memory quality,
and system health. Produces structured observations only — no modification.

Phase 7.0 — Self-Evolution Foundation.
"""

from collections import deque
from datetime import datetime
from typing import Any

from atlas.evolution.models import (
    Observation,
    ObservationCategory,
)


class SelfObservationEngine:
    """
    Observes Atlas runtime behavior and produces structured observations.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge, or
    interact with the EventBus. It receives data through method parameters
    and returns structured Observation instances.

    The engine maintains a bounded history of recent observations for
    trend analysis and pattern detection.
    """

    def __init__(self, max_observations: int = 1000) -> None:
        """
        Initialise the observation engine.

        Args:
            max_observations: Maximum number of observations to retain
                in memory. Older observations are discarded.
        """
        if max_observations <= 0:
            raise ValueError("max_observations must be a positive integer")

        self._max_observations = max_observations
        self._observations: deque[Observation] = deque(maxlen=max_observations)

    # ------------------------------------------------------------------
    # Observation recording
    # ------------------------------------------------------------------

    def record_observation(self, observation: Observation) -> None:
        """
        Record a single observation.

        Args:
            observation: The Observation to record.
        """
        self._observations.append(observation)

    def observe_runtime_metrics(
        self,
        avg_response_time_ms: float,
        request_count: int,
        error_count: int,
        source: str = "runtime_monitor",
    ) -> Observation:
        """
        Observe runtime performance metrics.

        Args:
            avg_response_time_ms: Average response time in milliseconds.
            request_count: Total number of requests in the period.
            error_count: Total number of errors in the period.
            source: Identifier for the observation source.

        Returns:
            An Observation with category RUNTIME_METRICS.
        """
        error_rate = (error_count / request_count * 100) if request_count > 0 else 0.0

        observation = Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="runtime_summary",
            value={
                "avg_response_time_ms": avg_response_time_ms,
                "request_count": request_count,
                "error_count": error_count,
                "error_rate_percent": round(error_rate, 2),
            },
            unit="composite",
            description=(
                f"Runtime metrics: {request_count} requests, "
                f"{error_count} errors ({error_rate:.1f}%), "
                f"avg {avg_response_time_ms:.0f}ms response time."
            ),
            source=source,
        )
        self._observations.append(observation)
        return observation

    def observe_reasoning_quality(
        self,
        success_rate: float,
        total_outcomes: int,
        avg_capabilities_used: float,
        source: str = "reasoning_monitor",
    ) -> Observation:
        """
        Observe reasoning pipeline quality metrics.

        Args:
            success_rate: Fraction of successful outcomes (0.0 to 1.0).
            total_outcomes: Total number of reasoning outcomes analyzed.
            avg_capabilities_used: Average number of capabilities used
                per outcome.
            source: Identifier for the observation source.

        Returns:
            An Observation with category REASONING_QUALITY.
        """
        observation = Observation(
            category=ObservationCategory.REASONING_QUALITY,
            metric_name="reasoning_quality",
            value={
                "success_rate": round(success_rate, 4),
                "total_outcomes": total_outcomes,
                "avg_capabilities_used": round(avg_capabilities_used, 2),
            },
            unit="composite",
            description=(
                f"Reasoning quality: {success_rate:.1%} success rate "
                f"across {total_outcomes} outcomes, "
                f"avg {avg_capabilities_used:.1f} capabilities per outcome."
            ),
            source=source,
        )
        self._observations.append(observation)
        return observation

    def observe_tool_usage(
        self,
        tool_name: str,
        invocation_count: int,
        success_count: int,
        avg_duration_ms: float,
        source: str = "tool_monitor",
    ) -> Observation:
        """
        Observe tool usage metrics for a specific tool.

        Args:
            tool_name: Name of the tool being observed.
            invocation_count: Total invocations of this tool.
            success_count: Successful invocations of this tool.
            avg_duration_ms: Average execution duration in milliseconds.
            source: Identifier for the observation source.

        Returns:
            An Observation with category TOOL_USAGE.
        """
        success_rate = (
            (success_count / invocation_count * 100)
            if invocation_count > 0
            else 0.0
        )

        observation = Observation(
            category=ObservationCategory.TOOL_USAGE,
            metric_name=f"tool_usage:{tool_name}",
            value={
                "tool_name": tool_name,
                "invocation_count": invocation_count,
                "success_count": success_count,
                "success_rate_percent": round(success_rate, 2),
                "avg_duration_ms": round(avg_duration_ms, 2),
            },
            unit="composite",
            description=(
                f"Tool '{tool_name}': {invocation_count} invocations, "
                f"{success_rate:.0f}% success, "
                f"avg {avg_duration_ms:.0f}ms duration."
            ),
            source=source,
        )
        self._observations.append(observation)
        return observation

    def observe_memory_quality(
        self,
        total_memories: int,
        avg_relevance_score: float,
        retrieval_success_rate: float,
        source: str = "memory_monitor",
    ) -> Observation:
        """
        Observe memory system quality metrics.

        Args:
            total_memories: Total number of stored memories.
            avg_relevance_score: Average relevance score of retrieved
                memories (0.0 to 1.0).
            retrieval_success_rate: Fraction of successful retrievals
                (0.0 to 1.0).
            source: Identifier for the observation source.

        Returns:
            An Observation with category MEMORY_QUALITY.
        """
        observation = Observation(
            category=ObservationCategory.MEMORY_QUALITY,
            metric_name="memory_quality",
            value={
                "total_memories": total_memories,
                "avg_relevance_score": round(avg_relevance_score, 4),
                "retrieval_success_rate": round(retrieval_success_rate, 4),
            },
            unit="composite",
            description=(
                f"Memory quality: {total_memories} memories, "
                f"{avg_relevance_score:.2f} avg relevance, "
                f"{retrieval_success_rate:.1%} retrieval success."
            ),
            source=source,
        )
        self._observations.append(observation)
        return observation

    def observe_system_health(
        self,
        component: str,
        status: str,
        message: str,
        source: str = "health_monitor",
    ) -> Observation:
        """
        Observe system health status for a component.

        Args:
            component: Name of the component being observed.
            status: Health status string (e.g. "healthy", "degraded",
                "unhealthy").
            message: Human-readable status message.
            source: Identifier for the observation source.

        Returns:
            An Observation with category SYSTEM_HEALTH.
        """
        observation = Observation(
            category=ObservationCategory.SYSTEM_HEALTH,
            metric_name=f"health:{component}",
            value={
                "component": component,
                "status": status,
                "message": message,
            },
            unit="status",
            description=f"Component '{component}' health: {status}. {message}",
            source=source,
        )
        self._observations.append(observation)
        return observation

    # ------------------------------------------------------------------
    # Observation retrieval
    # ------------------------------------------------------------------

    @property
    def observation_count(self) -> int:
        """Return the number of stored observations."""
        return len(self._observations)

    def recent_observations(self, n: int = 10) -> list[Observation]:
        """
        Return the most recent n observations, newest first.

        Args:
            n: Number of observations to return.

        Returns:
            A list of up to n Observation instances.
        """
        if n <= 0:
            return []

        return list(reversed(self._observations))[:n]

    def observations_by_category(
        self,
        category: ObservationCategory,
        n: int = 50,
    ) -> list[Observation]:
        """
        Return the most recent n observations of a given category.

        Args:
            category: The ObservationCategory to filter by.
            n: Maximum number of observations to return.

        Returns:
            A list of up to n Observation instances matching the category.
        """
        filtered = [
            obs for obs in reversed(self._observations)
            if obs.category == category
        ]
        return filtered[:n]

    def latest_observation(
        self,
        metric_name: str,
    ) -> Observation | None:
        """
        Return the most recent observation for a specific metric.

        Args:
            metric_name: The metric name to search for.

        Returns:
            The latest Observation for that metric, or None if not found.
        """
        for obs in reversed(self._observations):
            if obs.metric_name == metric_name:
                return obs
        return None

    def clear(self) -> None:
        """Remove all stored observations."""
        self._observations.clear()