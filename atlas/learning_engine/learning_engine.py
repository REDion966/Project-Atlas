"""
Atlas Learning Engine

Receives completed PipelineResult instances, analyzes successful and
failed executions, identifies reusable learning, and produces structured
LearningInsight objects. Never modifies Atlas directly.

Phase 7.3 — Learning Engine.
"""

from datetime import datetime
from typing import Any

from atlas.learning_engine.models import (
    FailurePattern,
    ImprovementRecommendation,
    InsightImportance,
    LearningCategory,
    LearningInsight,
    StrategyPerformance,
)
from atlas.learning_engine.strategy_analyzer import StrategyAnalyzer
from atlas.learning_engine.insight_consolidator import InsightConsolidator
from atlas.learning_engine.learning_memory import LearningMemory


class LearningEngine:
    """
    Orchestrates the learning pipeline.

    Receives pipeline execution data, analyzes it through the StrategyAnalyzer,
    consolidates insights, and stores results in LearningMemory.

    This is a pure logic component with no infrastructure dependencies.
    It never modifies Atlas directly — it only produces structured learning.
    """

    def __init__(
        self,
        memory: LearningMemory | None = None,
        analyzer: StrategyAnalyzer | None = None,
        consolidator: InsightConsolidator | None = None,
    ) -> None:
        self._memory = memory or LearningMemory()
        self._analyzer = analyzer or StrategyAnalyzer()
        self._consolidator = consolidator or InsightConsolidator()
        self._pipeline_count = 0

    @property
    def memory(self) -> LearningMemory:
        return self._memory

    # ------------------------------------------------------------------
    # Core learning pipeline
    # ------------------------------------------------------------------

    def learn_from_pipeline(
        self,
        pipeline_data: dict[str, Any],
    ) -> list[LearningInsight]:
        """
        Process a completed pipeline execution and produce learning.

        Args:
            pipeline_data: The intermediate_data dict from a PipelineResult.

        Returns:
            A list of new LearningInsight instances generated.
        """
        self._pipeline_count += 1

        new_insights: list[LearningInsight] = []

        # 1. Analyze strategy performance
        strategy = self._analyze_and_store_strategy(pipeline_data)

        # 2. Analyze failures
        failures = self._analyze_and_store_failures(pipeline_data)

        # 3. Generate strategy insights
        all_strategies = self._memory.get_all_strategies()
        strategy_insights = self._analyzer.generate_strategy_insights(all_strategies)
        new_insights.extend(strategy_insights)

        # 4. Generate failure insights
        all_failures = self._memory.get_failures(50)
        failure_insights = self._analyzer.generate_failure_insights(all_failures)
        new_insights.extend(failure_insights)

        # 5. Generate understanding insight if applicable
        if pipeline_data.get("understanding_insights_count", 0) > 0:
            understanding_insight = self._generate_understanding_insight(pipeline_data)
            new_insights.append(understanding_insight)

        # 6. Consolidate with existing insights
        existing = self._memory.get_insights(500)
        consolidated = self._consolidator.consolidate(new_insights, existing)

        # 7. Store consolidated insights
        self._memory.store_insights(consolidated)

        # 8. Generate recommendations
        recommendations = self._generate_recommendations(consolidated)
        for rec in recommendations:
            self._memory.store_recommendation(rec)

        return new_insights

    def _analyze_and_store_strategy(
        self,
        pipeline_data: dict[str, Any],
    ) -> StrategyPerformance:
        """Analyze strategy and store/update in memory."""
        strategy_name = self._classify_strategy(pipeline_data)
        existing = self._memory.get_strategy_by_name(strategy_name)

        strategy = self._analyzer.analyze_strategy(pipeline_data, existing)
        self._memory.store_strategy(strategy)
        return strategy

    def _analyze_and_store_failures(
        self,
        pipeline_data: dict[str, Any],
    ) -> list[FailurePattern]:
        """Analyze failures and store in memory."""
        existing = self._memory.get_failures(100)
        patterns = self._analyzer.analyze_failures(pipeline_data, existing)
        self._memory.store_failures(patterns)
        return patterns

    def _classify_strategy(
        self,
        data: dict[str, Any],
    ) -> str:
        """Classify the execution strategy."""
        has_reasoning = data.get("has_reasoning", False)
        has_planning = data.get("has_planning", False)
        has_tool = data.get("has_tool_result", False)

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

    def _generate_understanding_insight(
        self,
        data: dict[str, Any],
    ) -> LearningInsight:
        """Generate an insight about understanding usage."""
        count = data.get("understanding_insights_count", 0)
        return LearningInsight(
            insight_id=f"LRN-UND-{self._pipeline_count:06d}",
            category=LearningCategory.UNDERSTANDING_STRATEGY,
            title="Understanding engine produced insights",
            description=(
                f"The understanding engine generated {count} insight(s) "
                f"during pipeline execution. Understanding is being "
                f"actively used in the cognitive pipeline."
            ),
            importance=InsightImportance.MEDIUM,
            confidence=0.6,
            observation_count=1,
            applicable_areas=["understanding"],
        )

    def _generate_recommendations(
        self,
        insights: list[LearningInsight],
    ) -> list[ImprovementRecommendation]:
        """Generate improvement recommendations from insights."""
        recs: list[ImprovementRecommendation] = []

        high_insights = [
            i for i in insights
            if i.importance in (InsightImportance.CRITICAL, InsightImportance.HIGH)
            and i.confidence >= 0.6
        ]

        if high_insights:
            for insight in high_insights[:3]:
                recs.append(ImprovementRecommendation(
                    recommendation_id=f"REC-{len(recs) + 1:04d}",
                    title=f"Act on: {insight.title}",
                    description=insight.description,
                    source_insight_ids=[insight.insight_id],
                    expected_benefit="Improved pipeline effectiveness",
                    target_area=insight.applicable_areas[0] if insight.applicable_areas else "general",
                    priority=insight.importance,
                ))

        return recs

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_learning_summary(self) -> dict[str, Any]:
        """Return a summary of all accumulated learning."""
        return {
            "pipelines_processed": self._pipeline_count,
            "memory": self._memory.summary(),
            "top_insights": [
                {
                    "id": i.insight_id,
                    "title": i.title,
                    "importance": i.importance.name,
                    "confidence": i.confidence,
                    "strength": self._consolidator.calculate_strength(i),
                }
                for i in self._memory.get_insights(10)
            ],
            "strategy_performance": [
                {
                    "name": s.strategy_name,
                    "success_rate": s.success_rate,
                    "total_uses": s.total_uses,
                    "is_effective": s.is_effective,
                }
                for s in self._memory.get_all_strategies()
            ],
        }