"""
Atlas TrendAnalyzer — Phase 9.0

Analyzes windows of StructuredExperience records and produces
directional trend assessments (improving / stable / declining).

Pure logic. No AI. No infrastructure.
"""

from datetime import datetime
from typing import Any

from atlas.experience.models import StructuredExperience, TrendAnalysis


class TrendAnalyzer:
    """
    Calculates directional trends over a window of experiences.

    Uses simple statistical thresholds. A trend is classified as:
      - improving: metric increased by at least threshold over the window
      - declining: metric decreased by at least threshold over the window
      - stable:  neither improving nor declining
    """

    DEFAULT_THRESHOLD = 0.10
    MIN_WINDOW_SIZE = 2

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        if not 0.0 < threshold < 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        self._threshold = threshold
        self._analysis_counter = 0

    def analyze(
        self,
        experiences: list[StructuredExperience],
    ) -> TrendAnalysis:
        """
        Analyze a window of experiences and produce a TrendAnalysis.

        Args:
            experiences: Ordered list of experiences (oldest first).

        Returns:
            A TrendAnalysis with directional classifications.
        """
        self._analysis_counter += 1
        analysis_id = f"TRND-{self._analysis_counter:06d}"
        timestamp = datetime.now()
        window_size = len(experiences)

        if window_size < self.MIN_WINDOW_SIZE:
            return TrendAnalysis(
                analysis_id=analysis_id,
                timestamp=timestamp,
                window_size=window_size,
            )

        # Split window in half: first half vs second half
        mid = window_size // 2
        first_half = experiences[:mid]
        second_half = experiences[mid:]

        overall_success_rate = self._success_rate(experiences)
        success_rate_trend = self._compare_halves(
            self._success_rate(first_half),
            self._success_rate(second_half),
        )

        avg_understanding_insights = self._avg(
            [e.understanding_insights_count for e in experiences]
        )
        understanding_trend = self._compare_halves(
            self._avg([e.understanding_insights_count for e in first_half]),
            self._avg([e.understanding_insights_count for e in second_half]),
        )

        avg_reasoning_success = self._avg(
            [self._safe_ratio(e.reasoning_success_count, e.reasoning_total_count)
             for e in experiences if e.reasoning_total_count > 0]
        ) or 0.0
        reasoning_trend = self._compare_halves(
            self._avg([self._safe_ratio(e.reasoning_success_count, e.reasoning_total_count)
                       for e in first_half if e.reasoning_total_count > 0]) or 0.0,
            self._avg([self._safe_ratio(e.reasoning_success_count, e.reasoning_total_count)
                       for e in second_half if e.reasoning_total_count > 0]) or 0.0,
        )

        avg_planning_errors = self._avg(
            [e.planning_validation_errors for e in experiences]
        )
        # For errors, lower is better, so trend direction is inverted
        raw_planning_trend = self._compare_halves(
            self._avg([e.planning_validation_errors for e in first_half]),
            self._avg([e.planning_validation_errors for e in second_half]),
        )
        planning_trend = self._invert_trend(raw_planning_trend)

        tool_success_rate = self._tool_success_rate(experiences)
        tool_trend = self._compare_halves(
            self._tool_success_rate(first_half),
            self._tool_success_rate(second_half),
        )

        learning_insight_rate = self._avg(
            [e.learning_insights_count for e in experiences]
        )
        learning_trend = self._compare_halves(
            self._avg([e.learning_insights_count for e in first_half]),
            self._avg([e.learning_insights_count for e in second_half]),
        )

        identity_stability = self._calculate_identity_stability(experiences)
        capability_trends = self._calculate_capability_trends(experiences)

        return TrendAnalysis(
            analysis_id=analysis_id,
            timestamp=timestamp,
            window_size=window_size,
            overall_success_rate=round(overall_success_rate, 4),
            success_rate_trend=success_rate_trend,
            avg_understanding_insights=round(avg_understanding_insights, 4),
            understanding_trend=understanding_trend,
            avg_reasoning_success=round(avg_reasoning_success, 4),
            reasoning_trend=reasoning_trend,
            avg_planning_errors=round(avg_planning_errors, 4),
            planning_trend=planning_trend,
            tool_success_rate=round(tool_success_rate, 4),
            tool_trend=tool_trend,
            learning_insight_rate=round(learning_insight_rate, 4),
            learning_trend=learning_trend,
            identity_stability=round(identity_stability, 4),
            capability_trends=capability_trends,
        )

    # ------------------------------------------------------------------
    # Calculation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _success_rate(experiences: list[StructuredExperience]) -> float:
        if not experiences:
            return 0.0
        successes = sum(
            1 for e in experiences
            if e.outcome.name == "SUCCESS"
        )
        return successes / len(experiences)

    @staticmethod
    def _tool_success_rate(experiences: list[StructuredExperience]) -> float:
        tool_runs = [e for e in experiences if e.tool_name]
        if not tool_runs:
            return 0.0
        successes = sum(1 for e in tool_runs if e.tool_success)
        return successes / len(tool_runs)

    @staticmethod
    def _safe_ratio(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return numerator / denominator

    @staticmethod
    def _avg(values: list[float | int]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _compare_halves(self, first: float, second: float) -> str:
        diff = second - first
        if diff >= self._threshold:
            return "improving"
        if diff <= -self._threshold:
            return "declining"
        return "stable"

    @staticmethod
    def _invert_trend(trend: str) -> str:
        if trend == "improving":
            return "declining"
        if trend == "declining":
            return "improving"
        return "stable"

    @staticmethod
    def _calculate_identity_stability(experiences: list[StructuredExperience]) -> float:
        if len(experiences) < 2:
            return 1.0
        versions = [e.identity_version for e in experiences]
        unique_versions = len(set(versions))
        return max(0.0, 1.0 - (unique_versions - 1) / max(1, len(versions) - 1))

    @staticmethod
    def _calculate_capability_trends(
        experiences: list[StructuredExperience],
    ) -> dict[str, str]:
        """
        Calculate per-capability success trends from observed capabilities.
        Returns {capability_name: 'improving'|'stable'|'declining'}.
        """
        if len(experiences) < 2:
            return {}

        mid = len(experiences) // 2
        first_half = experiences[:mid]
        second_half = experiences[mid:]

        capability_stats: dict[str, dict[str, Any]] = {}

        def accumulate(target: list[StructuredExperience], label: str) -> None:
            for exp in target:
                success = exp.outcome.name == "SUCCESS"
                for cap in exp.reasoning_capabilities:
                    if not cap:
                        continue
                    if cap not in capability_stats:
                        capability_stats[cap] = {"first_total": 0, "first_success": 0,
                                                 "second_total": 0, "second_success": 0}
                    capability_stats[cap][f"{label}_total"] += 1
                    if success:
                        capability_stats[cap][f"{label}_success"] += 1

        accumulate(first_half, "first")
        accumulate(second_half, "second")

        trends: dict[str, str] = {}
        for cap, stats in capability_stats.items():
            first_rate = stats["first_success"] / max(1, stats["first_total"])
            second_rate = stats["second_success"] / max(1, stats["second_total"])
            diff = second_rate - first_rate
            if diff >= 0.20:
                trends[cap] = "improving"
            elif diff <= -0.20:
                trends[cap] = "declining"
            else:
                trends[cap] = "stable"

        return trends
