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

        # 4b. Phase 20 Batch 4: Turn reflection suggestions into reusable
        #     learning evidence. Additive — pipelines without reflection
        #     suggestions are unaffected.
        reflection_insights = self._generate_reflection_insights(pipeline_data)
        new_insights.extend(reflection_insights)

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

    def _generate_reflection_insights(
        self,
        data: dict[str, Any],
    ) -> list[LearningInsight]:
        """Generate reusable learning insights from reflection suggestions.

        Phase 20 Batch 4 — closes the feedback path: reflection output
        becomes structured, reusable strategy/learning evidence in the
        existing LearningMemory representation.

        Suggestions are passed as serialized dictionaries (the learning
        engine does not depend on the reasoning layer). When the same
        suggestion pattern recurs, the InsightConsolidator merges it and
        strengthens confidence/observation count.

        Backward compatible: no suggestions → no insights.
        """
        suggestions = data.get("reflection_suggestions") or []
        insights: list[LearningInsight] = []

        for index, suggestion in enumerate(suggestions):
            pattern = str(suggestion.get("pattern", "") or "reflection")
            confidence = float(suggestion.get("confidence", 0.0))
            affected = int(suggestion.get("affected_outcomes_count", 0) or 0)
            description = str(suggestion.get("description", "") or "")
            suggestion_text = str(suggestion.get("suggestion", "") or "")
            target_area = str(suggestion.get("target_area", "") or "")

            title = f"Reflection: {pattern}"
            if description and suggestion_text:
                body = f"{description} {suggestion_text}"
            else:
                body = description or suggestion_text or pattern

            insights.append(LearningInsight(
                insight_id=f"LRN-REF-{self._pipeline_count:06d}-{index + 1:02d}",
                category=LearningCategory.OPTIMIZATION,
                title=title,
                description=body,
                importance=(
                    InsightImportance.HIGH
                    if confidence >= 0.7
                    else InsightImportance.MEDIUM
                ),
                confidence=max(0.0, min(confidence, 1.0)),
                observation_count=max(1, affected),
                applicable_areas=[target_area] if target_area else ["general"],
                metadata={"source": "reflection"},
            ))

            # Phase 20 Batch 4: record capability-keyed strategy
            # performance so the CapabilityAnalyzer can consume the
            # reflection evidence during later selection.
            self._record_capability_evidence(suggestion, pattern, confidence)

        return insights

    def _record_capability_evidence(
        self,
        suggestion: dict[str, Any],
        pattern: str,
        confidence: float,
    ) -> None:
        """Record capability-keyed strategy performance from a suggestion.

        Only failure suggestions carry enough signal to deprioritize a
        capability: the suggestion text names the capability and the
        confidence is its observed failure rate. The record is stored
        under the capability name so the CapabilityAnalyzer's
        ``get_strategy_by_name`` lookup finds it during later selection.

        Deterministic and bounded; no-op when the suggestion does not
        name a capability.
        """
        if pattern != "frequent_failures":
            return

        description = str(suggestion.get("description", "") or "")
        suggestion_text = str(suggestion.get("suggestion", "") or "")
        import re

        match = re.search(r"Capability '([^']+)'", description) or re.search(
            r"Capability '([^']+)'", suggestion_text
        )
        if match is None:
            return

        capability_name = match.group(1)
        affected = int(suggestion.get("affected_outcomes_count", 0) or 0)
        total = max(1, affected)

        # Reflection confidence for frequent_failures IS the failure rate.
        failure_rate = max(0.0, min(confidence, 1.0))
        failures = round(total * failure_rate)
        successes = total - failures

        existing = self._memory.get_strategy_by_name(capability_name)
        if existing is not None:
            existing.total_uses += total
            existing.success_count += successes
            existing.failure_count += failures
            existing.last_used = datetime.now()
            return

        self._memory.store_strategy(StrategyPerformance(
            strategy_id=f"STRAT-CAP-{capability_name}",
            strategy_name=capability_name,
            strategy_type="capability",
            total_uses=total,
            success_count=successes,
            failure_count=failures,
            avg_confidence=1.0 - failure_rate,
        ))

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
