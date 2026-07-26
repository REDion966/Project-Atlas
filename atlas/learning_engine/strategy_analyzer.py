"""
Atlas Strategy Analyzer

Discovers which reasoning strategies perform better, compares planning
outcomes, detects repeated failures, and scores effectiveness over time.

Phase 7.3 — Learning Engine.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any

from atlas.learning_engine.models import (
    FailurePattern,
    InsightImportance,
    LearningCategory,
    LearningInsight,
    StrategyPerformance,
)


class StrategyAnalyzer:
    """
    Analyzes pipeline results to discover strategy effectiveness.

    This is a pure logic component with no infrastructure dependencies.
    It receives PipelineResult data and returns structured performance
    metrics and insights.
    """

    def __init__(self) -> None:
        self._strategy_counter = 0
        self._failure_counter = 0

    def _next_strategy_id(self) -> str:
        self._strategy_counter += 1
        return f"STRAT-{self._strategy_counter:06d}"

    def _next_failure_id(self) -> str:
        self._failure_counter += 1
        return f"FAIL-{self._failure_counter:06d}"

    # ------------------------------------------------------------------
    # Strategy tracking
    # ------------------------------------------------------------------

    def analyze_strategy(
        self,
        pipeline_data: dict[str, Any],
        existing: StrategyPerformance | None = None,
    ) -> StrategyPerformance:
        """
        Analyze a single pipeline execution and update strategy performance.

        Args:
            pipeline_data: Pipeline intermediate_data dict.
            existing: Existing StrategyPerformance to update, or None.

        Returns:
            Updated StrategyPerformance instance.
        """
        success = pipeline_data.get("success", False)
        has_reasoning = pipeline_data.get("has_reasoning", False)
        has_planning = pipeline_data.get("has_planning", False)
        has_tool = pipeline_data.get("has_tool_result", False)

        strategy_name = self._classify_strategy(has_reasoning, has_planning, has_tool)

        if existing is not None:
            existing.total_uses += 1
            if success:
                existing.success_count += 1
            else:
                existing.failure_count += 1
            existing.last_used = datetime.now()
            return existing

        return StrategyPerformance(
            strategy_id=self._next_strategy_id(),
            strategy_name=strategy_name,
            strategy_type=self._classify_type(strategy_name),
            total_uses=1,
            success_count=1 if success else 0,
            failure_count=0 if success else 1,
            avg_confidence=0.7 if success else 0.3,
        )

    def _classify_strategy(
        self,
        has_reasoning: bool,
        has_planning: bool,
        has_tool: bool,
    ) -> str:
        """Classify the execution strategy based on which stages ran."""
        if has_reasoning and has_planning and has_tool:
            return "full_pipeline"
        elif has_reasoning and has_planning:
            return "reasoning_with_planning"
        elif has_reasoning and has_tool:
            return "reasoning_with_tools"
        elif has_reasoning:
            return "reasoning_only"
        elif has_tool:
            return "tool_only"
        return "direct_response"

    def _classify_type(self, strategy_name: str) -> str:
        """Classify the strategy type."""
        if "reasoning" in strategy_name:
            return "reasoning"
        elif "tool" in strategy_name:
            return "tool"
        return "response"

    # ------------------------------------------------------------------
    # Failure analysis
    # ------------------------------------------------------------------

    def analyze_failures(
        self,
        pipeline_data: dict[str, Any],
        existing_patterns: list[FailurePattern] | None = None,
    ) -> list[FailurePattern]:
        """
        Analyze pipeline data for failure patterns.

        Args:
            pipeline_data: Pipeline intermediate_data dict.
            existing_patterns: Previously detected patterns.

        Returns:
            Updated list of FailurePattern instances.
        """
        existing = existing_patterns or []
        patterns = list(existing)

        success = pipeline_data.get("success", True)
        if success:
            return patterns

        # Detect failure from intermediate data
        failure_type = self._detect_failure_type(pipeline_data)

        # Update existing pattern or create new one
        found = False
        for pattern in patterns:
            if pattern.description == failure_type["description"]:
                pattern.failure_count += 1
                pattern.last_occurrence = datetime.now()
                pattern.confidence = min(pattern.confidence + 0.1, 1.0)
                found = True
                break

        if not found:
            patterns.append(FailurePattern(
                pattern_id=self._next_failure_id(),
                description=failure_type["description"],
                common_cause=failure_type.get("cause", ""),
                affected_stages=failure_type.get("stages", []),
                suggested_approach=failure_type.get("suggestion", ""),
            ))

        return patterns

    def _detect_failure_type(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Detect the type of failure from pipeline data."""
        if not data.get("has_reasoning"):
            return {
                "description": "Pipeline completed without reasoning stage",
                "cause": "Reasoning components may not be injected",
                "stages": ["reasoning"],
                "suggestion": "Ensure reasoning pipeline is configured",
            }
        if not data.get("has_planning"):
            return {
                "description": "Pipeline completed without planning stage",
                "cause": "Planning engine may not be injected",
                "stages": ["planning"],
                "suggestion": "Consider enabling planning engine",
            }
        return {
            "description": "Pipeline execution had one or more failed stages",
            "cause": "Unknown stage failure",
            "stages": ["general"],
            "suggestion": "Review pipeline stage results for errors",
        }

    # ------------------------------------------------------------------
    # Effectiveness scoring
    # ------------------------------------------------------------------

    def score_strategy_effectiveness(
        self,
        performances: list[StrategyPerformance],
    ) -> list[dict[str, Any]]:
        """
        Score all tracked strategies by effectiveness.

        Args:
            performances: List of StrategyPerformance instances.

        Returns:
            Sorted list of dicts with strategy name, success rate,
            and effectiveness score.
        """
        scored = []
        for perf in performances:
            if perf.total_uses == 0:
                continue
            scored.append({
                "strategy_name": perf.strategy_name,
                "strategy_type": perf.strategy_type,
                "total_uses": perf.total_uses,
                "success_rate": perf.success_rate,
                "is_effective": perf.is_effective,
                "avg_confidence": perf.avg_confidence,
            })

        scored.sort(key=lambda x: x["success_rate"], reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Insight generation
    # ------------------------------------------------------------------

    def generate_strategy_insights(
        self,
        performances: list[StrategyPerformance],
    ) -> list[LearningInsight]:
        """
        Generate learning insights from strategy performance data.

        Args:
            performances: List of StrategyPerformance instances.

        Returns:
            A list of LearningInsight instances.
        """
        insights: list[LearningInsight] = []

        effective = [p for p in performances if p.is_effective and p.total_uses >= 3]
        ineffective = [p for p in performances if not p.is_effective and p.total_uses >= 3]

        if effective:
            best = max(effective, key=lambda p: p.success_rate)
            insights.append(LearningInsight(
                insight_id=f"LRN-STRAT-{len(insights) + 1:04d}",
                category=LearningCategory.REASONING_STRATEGY,
                title=f"Effective strategy: {best.strategy_name}",
                description=(
                    f"Strategy '{best.strategy_name}' has {best.success_rate:.0%} "
                    f"success rate across {best.total_uses} uses. "
                    f"This is a reliably effective approach."
                ),
                importance=InsightImportance.HIGH,
                confidence=min(best.success_rate + 0.1, 1.0),
                observation_count=best.total_uses,
                applicable_areas=[best.strategy_type],
            ))

        if ineffective:
            worst = min(ineffective, key=lambda p: p.success_rate)
            insights.append(LearningInsight(
                insight_id=f"LRN-STRAT-{len(insights) + 1:04d}",
                category=LearningCategory.FAILURE_AVOIDANCE,
                title=f"Ineffective strategy: {worst.strategy_name}",
                description=(
                    f"Strategy '{worst.strategy_name}' has only "
                    f"{worst.success_rate:.0%} success rate "
                    f"across {worst.total_uses} uses. "
                    f"This strategy should be reviewed or avoided."
                ),
                importance=InsightImportance.MEDIUM,
                confidence=min(1.0 - worst.success_rate + 0.1, 1.0),
                observation_count=worst.total_uses,
                applicable_areas=[worst.strategy_type],
            ))

        return insights

    def generate_failure_insights(
        self,
        patterns: list[FailurePattern],
    ) -> list[LearningInsight]:
        """
        Generate learning insights from failure patterns.

        Args:
            patterns: List of FailurePattern instances.

        Returns:
            A list of LearningInsight instances.
        """
        insights: list[LearningInsight] = []

        for pattern in patterns:
            if pattern.failure_count < 2:
                continue

            insights.append(LearningInsight(
                insight_id=f"LRN-FAIL-{len(insights) + 1:04d}",
                category=LearningCategory.FAILURE_AVOIDANCE,
                title=f"Recurring failure: {pattern.description[:60]}",
                description=(
                    f"Failure pattern occurred {pattern.failure_count} times. "
                    f"Common cause: {pattern.common_cause}. "
                    f"Suggested approach: {pattern.suggested_approach}"
                ),
                importance=InsightImportance.HIGH if pattern.failure_count >= 5 else InsightImportance.MEDIUM,
                confidence=pattern.confidence,
                observation_count=pattern.failure_count,
                applicable_areas=pattern.affected_stages,
            ))

        return insights