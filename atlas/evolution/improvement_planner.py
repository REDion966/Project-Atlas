"""
Atlas Improvement Planner

Consumes observations, identifies weaknesses, prioritizes improvement
opportunities, and produces structured improvement plans.
Never modifies anything.

Phase 7.0 — Self-Evolution Foundation.
"""

from collections import Counter
from datetime import datetime
from typing import Any

from atlas.evolution.models import (
    ImprovementPlan,
    ImprovementPriority,
    Observation,
    ObservationCategory,
    Weakness,
)


class ImprovementPlanner:
    """
    Analyzes observations to identify weaknesses and produce improvement plans.

    This is a pure logic component with no infrastructure dependencies.
    It receives observations as input and returns plans as output.
    It never modifies the system or calls external services.
    """

    def __init__(self) -> None:
        self._plan_counter = 0

    def _next_plan_id(self) -> str:
        """Generate a unique plan identifier."""
        self._plan_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"IMP-{timestamp}-{self._plan_counter:04d}"

    # ------------------------------------------------------------------
    # Weakness detection
    # ------------------------------------------------------------------

    def detect_weaknesses(
        self,
        observations: list[Observation],
    ) -> list[Weakness]:
        """
        Analyze observations and produce a list of detected weaknesses.

        Args:
            observations: A list of Observation instances to analyze.

        Returns:
            A list of Weakness instances. Returns an empty list when no
            weaknesses are detected.
        """
        if not observations:
            return []

        weaknesses: list[Weakness] = []

        runtime_weakness = self._detect_runtime_weakness(observations)
        if runtime_weakness is not None:
            weaknesses.append(runtime_weakness)

        reasoning_weakness = self._detect_reasoning_weakness(observations)
        if reasoning_weakness is not None:
            weaknesses.append(reasoning_weakness)

        tool_weakness = self._detect_tool_weakness(observations)
        if tool_weakness is not None:
            weaknesses.append(tool_weakness)

        memory_weakness = self._detect_memory_weakness(observations)
        if memory_weakness is not None:
            weaknesses.append(memory_weakness)

        health_weakness = self._detect_health_weakness(observations)
        if health_weakness is not None:
            weaknesses.append(health_weakness)

        return weaknesses

    def _detect_runtime_weakness(
        self,
        observations: list[Observation],
    ) -> Weakness | None:
        """
        Detect runtime performance weaknesses.

        Flags if:
        - Average response time exceeds 5000ms.
        - Error rate exceeds 10%.
        """
        runtime_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.RUNTIME_METRICS
        ]
        if not runtime_obs:
            return None

        latest = runtime_obs[-1]
        value = latest.value
        obs_id = f"{latest.timestamp.isoformat()}:{latest.metric_name}"

        avg_time = value.get("avg_response_time_ms", 0)
        error_rate = value.get("error_rate_percent", 0)

        issues: list[str] = []
        if avg_time > 5000:
            issues.append(
                f"Average response time is {avg_time:.0f}ms (threshold: 5000ms)."
            )
        if error_rate > 10:
            issues.append(
                f"Error rate is {error_rate:.1f}% (threshold: 10%)."
            )

        if not issues:
            return None

        severity = (
            ImprovementPriority.CRITICAL
            if error_rate > 20 or avg_time > 10000
            else ImprovementPriority.HIGH
        )

        return Weakness(
            area="runtime",
            description=" ".join(issues),
            severity=severity,
            supporting_observations=[obs_id],
        )

    def _detect_reasoning_weakness(
        self,
        observations: list[Observation],
    ) -> Weakness | None:
        """
        Detect reasoning quality weaknesses.

        Flags if:
        - Success rate is below 70%.
        """
        reasoning_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.REASONING_QUALITY
        ]
        if not reasoning_obs:
            return None

        latest = reasoning_obs[-1]
        value = latest.value
        obs_id = f"{latest.timestamp.isoformat()}:{latest.metric_name}"

        success_rate = value.get("success_rate", 1.0)

        if success_rate >= 0.7:
            return None

        return Weakness(
            area="reasoning",
            description=(
                f"Reasoning success rate is {success_rate:.1%}, "
                f"which is below the 70% threshold."
            ),
            severity=(
                ImprovementPriority.CRITICAL
                if success_rate < 0.4
                else ImprovementPriority.HIGH
            ),
            supporting_observations=[obs_id],
        )

    def _detect_tool_weakness(
        self,
        observations: list[Observation],
    ) -> Weakness | None:
        """
        Detect tool usage weaknesses.

        Flags tools with success rate below 60%.
        """
        tool_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.TOOL_USAGE
        ]
        if not tool_obs:
            return None

        failing_tools: list[str] = []
        for obs in tool_obs:
            value = obs.value
            success_rate = value.get("success_rate_percent", 100)
            if success_rate < 60:
                tool_name = value.get("tool_name", "unknown")
                failing_tools.append(
                    f"Tool '{tool_name}' has {success_rate:.0f}% success rate."
                )

        if not failing_tools:
            return None

        obs_ids = [
            f"{obs.timestamp.isoformat()}:{obs.metric_name}"
            for obs in tool_obs
        ]

        return Weakness(
            area="tools",
            description=" ".join(failing_tools),
            severity=ImprovementPriority.MEDIUM,
            supporting_observations=obs_ids,
        )

    def _detect_memory_weakness(
        self,
        observations: list[Observation],
    ) -> Weakness | None:
        """
        Detect memory quality weaknesses.

        Flags if:
        - Average relevance score is below 0.5.
        - Retrieval success rate is below 80%.
        """
        memory_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.MEMORY_QUALITY
        ]
        if not memory_obs:
            return None

        latest = memory_obs[-1]
        value = latest.value
        obs_id = f"{latest.timestamp.isoformat()}:{latest.metric_name}"

        avg_relevance = value.get("avg_relevance_score", 1.0)
        retrieval_rate = value.get("retrieval_success_rate", 1.0)

        issues: list[str] = []
        if avg_relevance < 0.5:
            issues.append(
                f"Average memory relevance is {avg_relevance:.2f} "
                f"(threshold: 0.5)."
            )
        if retrieval_rate < 0.8:
            issues.append(
                f"Memory retrieval success rate is {retrieval_rate:.1%} "
                f"(threshold: 80%)."
            )

        if not issues:
            return None

        return Weakness(
            area="memory",
            description=" ".join(issues),
            severity=ImprovementPriority.MEDIUM,
            supporting_observations=[obs_id],
        )

    def _detect_health_weakness(
        self,
        observations: list[Observation],
    ) -> Weakness | None:
        """
        Detect system health weaknesses.

        Flags components with status other than "healthy".
        """
        health_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.SYSTEM_HEALTH
        ]
        if not health_obs:
            return None

        unhealthy: list[str] = []
        for obs in health_obs:
            value = obs.value
            status = value.get("status", "unknown")
            if status != "healthy":
                component = value.get("component", "unknown")
                message = value.get("message", "")
                unhealthy.append(
                    f"Component '{component}' is '{status}': {message}"
                )

        if not unhealthy:
            return None

        obs_ids = [
            f"{obs.timestamp.isoformat()}:{obs.metric_name}"
            for obs in health_obs
        ]

        return Weakness(
            area="system_health",
            description=" ".join(unhealthy),
            severity=ImprovementPriority.HIGH,
            supporting_observations=obs_ids,
        )

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    def create_improvement_plan(
        self,
        weaknesses: list[Weakness],
    ) -> ImprovementPlan | None:
        """
        Create a single improvement plan from a list of weaknesses.

        If no weaknesses are provided, returns None.

        Args:
            weaknesses: A list of Weakness instances to address.

        Returns:
            An ImprovementPlan targeting the most critical weaknesses,
            or None if no weaknesses are provided.
        """
        if not weaknesses:
            return None

        sorted_weaknesses = sorted(
            weaknesses,
            key=lambda w: (
                w.severity.value,
                len(w.supporting_observations),
            ),
            reverse=True,
        )

        primary = sorted_weaknesses[0]

        area_labels = {
            "runtime": "Runtime Performance",
            "reasoning": "Reasoning Quality",
            "tools": "Tool Reliability",
            "memory": "Memory System",
            "system_health": "System Health",
        }

        area_name = area_labels.get(primary.area, primary.area.capitalize())

        target_components = list(dict.fromkeys(
            w.area for w in sorted_weaknesses
        ))

        return ImprovementPlan(
            plan_id=self._next_plan_id(),
            title=f"Improve {area_name}",
            description=(
                f"Address {len(sorted_weaknesses)} identified weakness(es) "
                f"in {', '.join(target_components)}. "
                f"Primary issue: {primary.description}"
            ),
            priority=primary.severity,
            weaknesses=sorted_weaknesses,
            expected_benefit=self._estimate_benefit(primary),
            complexity_estimate=self._estimate_complexity(sorted_weaknesses),
            target_components=target_components,
        )

    def create_all_plans(
        self,
        weaknesses: list[Weakness],
    ) -> list[ImprovementPlan]:
        """
        Create improvement plans for each distinct area with weaknesses.

        Args:
            weaknesses: A list of Weakness instances.

        Returns:
            A list of ImprovementPlan instances, one per affected area.
        """
        if not weaknesses:
            return []

        by_area: dict[str, list[Weakness]] = {}
        for w in weaknesses:
            if w.area not in by_area:
                by_area[w.area] = []
            by_area[w.area].append(w)

        plans: list[ImprovementPlan] = []
        for area, area_weaknesses in by_area.items():
            plan = self.create_improvement_plan(area_weaknesses)
            if plan is not None:
                plans.append(plan)

        plans.sort(key=lambda p: p.priority.value)
        return plans

    def _estimate_benefit(
        self,
        weakness: Weakness,
    ) -> str:
        """Estimate the expected benefit of addressing a weakness."""
        estimates = {
            "runtime": (
                "Improved response times and reduced error rates "
                "leading to more reliable system behavior."
            ),
            "reasoning": (
                "Higher reasoning success rates and more reliable "
                "capability execution."
            ),
            "tools": (
                "More reliable tool execution and reduced failure rates."
            ),
            "memory": (
                "Better memory retrieval quality and more relevant "
                "context assembly."
            ),
            "system_health": (
                "Improved system stability and reduced component failures."
            ),
        }
        return estimates.get(weakness.area, "Improved system behavior.")

    def _estimate_complexity(
        self,
        weaknesses: list[Weakness],
    ) -> str:
        """Estimate implementation complexity based on weaknesses."""
        high_severity = sum(
            1 for w in weaknesses
            if w.severity in (
                ImprovementPriority.CRITICAL,
                ImprovementPriority.HIGH,
            )
        )

        if high_severity >= 3:
            return "high"
        elif high_severity >= 1:
            return "medium"
        return "low"