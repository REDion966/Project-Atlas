"""
Atlas Improvement Planner

Consumes observations, identifies weaknesses, prioritizes improvement
opportunities, and produces structured improvement plans.
Never modifies anything.

Phase 7.0 — Self-Evolution Foundation.
Phase 12.4 — Added evolution feedback integration. Planner can optionally
receive EvolutionInsight objects to adjust planning based on past outcomes.
Post-Core F2 — Weakness detectors aggregate the relevant metric across the
bounded per-category observation window (mean) instead of only the newest
observation. Single-observation behavior is preserved (mean == value).
"""

from collections import Counter
from datetime import datetime
from typing import Any

from atlas.evolution.decision_models import PlanningContext
from atlas.evolution.models import (
    EvolutionInsight,
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

    Phase 12.4 — When optional insights are provided, historical evolution
    outcomes influence weakness severity and plan prioritisation.
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
        insights: list[EvolutionInsight] | None = None,
        planning_context: PlanningContext | None = None,
    ) -> list[Weakness]:
        """
        Analyze observations and produce a list of detected weaknesses.

        When past evolution insights are provided, weakness severity is
        adjusted based on historical outcomes:
          - Similar areas with successful past outcomes → higher confidence
          - Similar areas with failed past outcomes → cautious treatment

        When a PlanningContext is provided, area adjustments from
        consolidated evolution knowledge are used in preference to crude
        keyword matching.

        Args:
            observations: A list of Observation instances to analyze.
            insights: Optional list of EvolutionInsight instances from
                past evolution outcome analysis.
            planning_context: Optional PlanningContext with consolidated
                historical evidence.

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

        # Phase 12.4 / 14.3: Adjust weaknesses based on historical evidence.
        if planning_context is not None:
            weaknesses = self._apply_evolution_feedback(
                weaknesses,
                insights or [],
                planning_context,
            )
        elif insights:
            weaknesses = self._apply_evolution_feedback(weaknesses, insights)

        return weaknesses

    # ------------------------------------------------------------------
    # Evolution feedback integration (Phase 12.4+)
    # ------------------------------------------------------------------

    def _apply_evolution_feedback(
        self,
        weaknesses: list[Weakness],
        insights: list[EvolutionInsight],
        planning_context: PlanningContext | None = None,
    ) -> list[Weakness]:
        """
        Adjust weakness severity based on historical evolution outcomes.

        Rules:
          - Insights with outcome="success" and effectiveness >= 0.75 in a
            matching area → boost priority one level.
          - Insights with outcome="failure" and regression_risk >= 0.5 in a
            matching area → reduce priority one level.
          - Insights with confidence < 0.3 → ignored (low confidence).
          - No match → unchanged.

        When a PlanningContext is provided, area adjustments from
        consolidated knowledge are used first; insights are only used as
        a fallback when no area adjustment is available.

        Args:
            weaknesses: Detected weaknesses to adjust.
            insights: Historical evolution insights.
            planning_context: Optional PlanningContext with consolidated
                historical evidence.

        Returns:
            Adjusted list of Weakness instances.
        """
        if not weaknesses:
            return weaknesses

        if planning_context is None and not insights:
            return weaknesses

        # Build a map of area → list of relevant insights (fallback)
        area_feedback: dict[str, list[EvolutionInsight]] = {}
        if insights:
            for insight in insights:
                if insight.confidence < 0.3:
                    continue

                area = self._insight_to_area(insight)
                if area is None:
                    continue

                area_feedback.setdefault(area, []).append(insight)

        # Adjust each weakness
        adjusted: list[Weakness] = []
        for weakness in weaknesses:
            adjustment = None
            if planning_context is not None:
                adjustment = planning_context.area_adjustments.get(weakness.area)

            if adjustment is not None and adjustment.occurrence_count > 0:
                weakness = self._adjust_weakness_from_context(
                    weakness,
                    adjustment,
                )
            else:
                matching_insights = area_feedback.get(weakness.area, [])
                if matching_insights:
                    weakness = self._adjust_weakness(weakness, matching_insights)
            adjusted.append(weakness)

        return adjusted

    @staticmethod
    def _adjust_weakness_from_context(
        weakness: Weakness,
        adjustment,
    ) -> Weakness:
        """Adjust a weakness using a consolidated AreaAdjustment."""
        recommendation = adjustment.recommendation
        if recommendation == "prefer":
            new_severity = _boost_priority(weakness.severity)
            if new_severity != weakness.severity:
                return Weakness(
                    area=weakness.area,
                    description=(
                        f"{weakness.description} "
                        f"[Evolution feedback: historical success rate "
                        f"{adjustment.historical_success_rate:.0%} across "
                        f"{adjustment.occurrence_count} occurrences]"
                    ),
                    severity=new_severity,
                    supporting_observations=weakness.supporting_observations,
                    detected_at=weakness.detected_at,
                )
        elif recommendation == "avoid":
            new_severity = _reduce_priority(weakness.severity)
            if new_severity != weakness.severity:
                return Weakness(
                    area=weakness.area,
                    description=(
                        f"{weakness.description} "
                        f"[Evolution feedback: historical failures across "
                        f"{adjustment.occurrence_count} occurrences; "
                        f"proceed with caution]"
                    ),
                    severity=new_severity,
                    supporting_observations=weakness.supporting_observations,
                    detected_at=weakness.detected_at,
                )

        return weakness

    @staticmethod
    def _insight_to_area(insight: EvolutionInsight) -> str | None:
        """
        Map an evolution insight to a weakness area.

        Uses keyword matching against proposal title/summary.
        Returns one of: "runtime", "reasoning", "tools", "memory",
        "system_health", or None.
        """
        text = f"{insight.proposal_title} {insight.proposal_summary}".lower()

        # Area keyword mapping
        area_keywords = {
            "runtime": ["runtime", "performance", "response", "latency"],
            "reasoning": ["reasoning", "capability", "analysis"],
            "tools": ["tool", "executor", "selector"],
            "memory": ["memory", "retrieval", "ranking", "context"],
            "system_health": ["health", "stability", "component", "reliability"],
        }

        for area, keywords in area_keywords.items():
            if any(kw in text for kw in keywords):
                return area

        return None

    @staticmethod
    def _adjust_weakness(
        weakness: Weakness,
        matching_insights: list[EvolutionInsight],
    ) -> Weakness:
        """
        Adjust a single weakness based on matching evolution insights.

        Majority vote among matching insights determines direction:
        - More successes than failures → boost
        - More failures than successes → reduce
        """
        successes = sum(
            1 for ins in matching_insights
            if ins.outcome == "success" and ins.effectiveness_score >= 0.75
        )
        failures = sum(
            1 for ins in matching_insights
            if ins.outcome == "failure" and ins.regression_risk >= 0.5
        )

        if successes > failures:
            # Boost: increase severity one level if possible
            new_severity = _boost_priority(weakness.severity)
            if new_severity != weakness.severity:
                return Weakness(
                    area=weakness.area,
                    description=(
                        f"{weakness.description} "
                        f"[Evolution feedback: similar past improvements "
                        f"succeeded with {successes} successful outcomes]"
                    ),
                    severity=new_severity,
                    supporting_observations=weakness.supporting_observations,
                    detected_at=weakness.detected_at,
                )

        elif failures > successes:
            # Reduce: decrease severity one level if possible
            new_severity = _reduce_priority(weakness.severity)
            if new_severity != weakness.severity:
                return Weakness(
                    area=weakness.area,
                    description=(
                        f"{weakness.description} "
                        f"[Evolution feedback: similar past improvements "
                        f"failed with {failures} failed outcomes]"
                    ),
                    severity=new_severity,
                    supporting_observations=weakness.supporting_observations,
                    detected_at=weakness.detected_at,
                )

        return weakness

    # ------------------------------------------------------------------
    # Observation aggregation helper (Post-Core F2)
    # ------------------------------------------------------------------

    @staticmethod
    def _mean_value(
        observations: list[Observation],
        key: str,
        default: float,
    ) -> float:
        """
        Return the arithmetic mean of a metric across the observation window.

        Post-Core F2: weakness detectors aggregate the relevant metric over
        the bounded per-category window supplied by the scheduler rather than
        only the newest observation. A single observation yields
        ``mean == value``, so single-observation behavior is preserved
        exactly. Deterministic: ordinary arithmetic over the exact
        observations already passed in.
        """
        numeric = [
            value
            for obs in observations
            for value in (obs.value.get(key), )
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if not numeric:
            return default
        return sum(numeric) / len(numeric)

    # ------------------------------------------------------------------
    # Weakness detection methods
    # ------------------------------------------------------------------

    def _detect_runtime_weakness(
        self,
        observations: list[Observation],
    ) -> Weakness | None:
        """
        Detect runtime performance weaknesses.

        Post-Core F2: aggregates avg_response_time_ms and error_rate_percent
        across the runtime window (mean) instead of only the newest
        observation.
        """
        runtime_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.RUNTIME_METRICS
        ]
        if not runtime_obs:
            return None

        latest = runtime_obs[-1]
        obs_id = f"{latest.timestamp.isoformat()}:{latest.metric_name}"

        avg_time = self._mean_value(
            runtime_obs, "avg_response_time_ms", 0.0
        )
        error_rate = self._mean_value(
            runtime_obs, "error_rate_percent", 0.0
        )

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

        Post-Core F2: aggregates success_rate across the reasoning window
        (mean) instead of only the newest observation.
        """
        reasoning_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.REASONING_QUALITY
        ]
        if not reasoning_obs:
            return None

        latest = reasoning_obs[-1]
        obs_id = f"{latest.timestamp.isoformat()}:{latest.metric_name}"

        success_rate = self._mean_value(
            reasoning_obs, "success_rate", 1.0
        )

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

        Post-Core F2: aggregates avg_relevance_score and
        retrieval_success_rate across the memory window (mean) instead of
        only the newest observation.
        """
        memory_obs = [
            obs for obs in observations
            if obs.category == ObservationCategory.MEMORY_QUALITY
        ]
        if not memory_obs:
            return None

        latest = memory_obs[-1]
        obs_id = f"{latest.timestamp.isoformat()}:{latest.metric_name}"

        avg_relevance = self._mean_value(
            memory_obs, "avg_relevance_score", 1.0
        )
        retrieval_rate = self._mean_value(
            memory_obs, "retrieval_success_rate", 1.0
        )

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
        insights: list[EvolutionInsight] | None = None,
        planning_context: PlanningContext | None = None,
        research_evidence: dict | None = None,
    ) -> ImprovementPlan | None:
        """
        Create a single improvement plan from a list of weaknesses.

        When past evolution insights are provided, the plan description
        and expected benefit may reference historical outcomes.

        When a PlanningContext is provided, bottleneck alerts and strategy
        suggestions enrich the plan description and benefit estimate.

        Stage F: when bounded research evidence is provided it is attached
        verbatim as ``plan.metadata["research"]`` — advisory only, never
        affecting plan structure or authority.

        If no weaknesses are provided, returns None.

        Args:
            weaknesses: A list of Weakness instances to address.
            insights: Optional list of EvolutionInsight instances for
                enriched planning context.
            planning_context: Optional PlanningContext with consolidated
                historical evidence.
            research_evidence: Optional bounded JSON-safe research-evidence
                summary (see ``atlas.research.evidence_summary``).

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

        # Enrich with evolution feedback if available
        feedback_note = ""
        if insights:
            feedback_note = self._build_feedback_note(primary.area, insights)

        # Phase 14.3: enrich with bottleneck alerts when available
        bottleneck_note = ""
        if planning_context is not None:
            bottleneck_note = self._build_bottleneck_note(
                primary.area,
                planning_context,
            )

        description = (
            f"Address {len(sorted_weaknesses)} identified weakness(es) "
            f"in {', '.join(target_components)}. "
            f"Primary issue: {primary.description}"
        )
        if feedback_note:
            description += f" {feedback_note}"
        if bottleneck_note:
            description += f" {bottleneck_note}"

        expected_benefit = self._estimate_benefit(
            primary,
            insights=insights,
            planning_context=planning_context,
        )

        return ImprovementPlan(
            plan_id=self._next_plan_id(),
            title=f"Improve {area_name}",
            description=description,
            priority=primary.severity,
            weaknesses=sorted_weaknesses,
            expected_benefit=expected_benefit,
            complexity_estimate=self._estimate_complexity(sorted_weaknesses),
            target_components=target_components,
            metadata=(
                {"research": dict(research_evidence)}
                if research_evidence
                else {}
            ),
        )

    def create_all_plans(
        self,
        weaknesses: list[Weakness],
        insights: list[EvolutionInsight] | None = None,
        planning_context: PlanningContext | None = None,
        research_evidence: dict | None = None,
    ) -> list[ImprovementPlan]:
        """
        Create improvement plans for each distinct area with weaknesses.

        Args:
            weaknesses: A list of Weakness instances.
            insights: Optional list of EvolutionInsight instances.
            planning_context: Optional PlanningContext with consolidated
                historical evidence.

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
            plan = self.create_improvement_plan(
                area_weaknesses,
                insights=insights,
                planning_context=planning_context,
                research_evidence=research_evidence,
            )
            if plan is not None:
                plans.append(plan)

        plans.sort(key=lambda p: p.priority.value)
        return plans

    # ------------------------------------------------------------------
    # Feedback enrichment helpers (Phase 12.4+)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_feedback_note(
        area: str,
        insights: list[EvolutionInsight],
    ) -> str:
        """Build a short feedback note from historical insights for an area."""
        relevant = [
            ins for ins in insights
            if ImprovementPlanner._insight_to_area(ins) == area
        ]
        if not relevant:
            return ""

        successes = sum(1 for ins in relevant if ins.outcome == "success")
        failures = sum(1 for ins in relevant if ins.outcome == "failure")
        total = len(relevant)

        if successes > failures:
            return (
                f"Evolution history: {successes}/{total} similar improvements "
                f"succeeded."
            )
        elif failures > successes:
            return (
                f"Evolution history: {failures}/{total} similar improvements "
                f"had challenges. Proceed with caution."
            )
        return ""

    def _estimate_benefit(
        self,
        weakness: Weakness,
        insights: list[EvolutionInsight] | None = None,
        planning_context: PlanningContext | None = None,
    ) -> str:
        """Estimate the expected benefit of addressing a weakness.

        When insights are available, use measured outcomes from past
        improvements in the same area to provide data-driven estimates.

        When a PlanningContext is available, preferred strategies for the
        area are mentioned without overriding deterministic logic.
        """
        # Default estimates by area
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

        base = estimates.get(weakness.area, "Improved system behavior.")

        # Enrich with measured outcomes from past insights
        if insights:
            area_insights = [
                ins for ins in insights
                if ImprovementPlanner._insight_to_area(ins) == weakness.area
            ]
            if area_insights:
                avg_effectiveness = (
                    sum(ins.effectiveness_score for ins in area_insights)
                    / len(area_insights)
                )
                if avg_effectiveness >= 0.7:
                    base += (
                        f" Past similar improvements averaged "
                        f"{avg_effectiveness:.0%} effectiveness."
                    )

        # Phase 14.3: enrich with preferred strategies from context
        if planning_context is not None:
            suggestions = planning_context.strategy_suggestions.get(weakness.area, [])
            preferred = [
                s for s in suggestions if s.recommendation == "prefer"
            ]
            if preferred:
                names = ", ".join(s.strategy_name or s.strategy_key for s in preferred[:3])
                base += f" Preferred strategies: {names}."

        return base

    @staticmethod
    def _build_bottleneck_note(
        area: str,
        planning_context: PlanningContext,
    ) -> str:
        """Build a note about recurring bottlenecks for an area."""
        for alert in planning_context.bottleneck_alerts:
            if alert.area == area:
                return (
                    f"Recurring bottleneck detected "
                    f"({alert.recurrence_count} historical occurrences)."
                )
        return ""

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


# ---------------------------------------------------------------------------
# Module-level helpers for priority adjustment
# ---------------------------------------------------------------------------


def _boost_priority(priority: ImprovementPriority) -> ImprovementPriority:
    """Increase severity one level."""
    mapping = {
        ImprovementPriority.LOW: ImprovementPriority.MEDIUM,
        ImprovementPriority.MEDIUM: ImprovementPriority.HIGH,
        ImprovementPriority.HIGH: ImprovementPriority.CRITICAL,
        ImprovementPriority.CRITICAL: ImprovementPriority.CRITICAL,
    }
    return mapping.get(priority, priority)


def _reduce_priority(priority: ImprovementPriority) -> ImprovementPriority:
    """Decrease severity one level."""
    mapping = {
        ImprovementPriority.CRITICAL: ImprovementPriority.HIGH,
        ImprovementPriority.HIGH: ImprovementPriority.MEDIUM,
        ImprovementPriority.MEDIUM: ImprovementPriority.LOW,
        ImprovementPriority.LOW: ImprovementPriority.LOW,
    }
    return mapping.get(priority, priority)
