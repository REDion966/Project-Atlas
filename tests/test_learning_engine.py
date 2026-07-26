"""
Phase 7.3 — Learning Engine: Tests.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from atlas.learning_engine.models import (
    LearningCategory, InsightImportance, LearningInsight,
    StrategyPerformance, FailurePattern, ImprovementRecommendation,
)
from atlas.learning_engine.strategy_analyzer import StrategyAnalyzer
from atlas.learning_engine.insight_consolidator import InsightConsolidator
from atlas.learning_engine.learning_memory import LearningMemory
from atlas.learning_engine.learning_engine import LearningEngine


# ===================================================================
# Model Tests
# ===================================================================

class TestLearningInsight:
    def test_create_minimal(self):
        i = LearningInsight(insight_id="LRN-001", category=LearningCategory.REASONING_STRATEGY, title="Test", description="Desc")
        assert i.insight_id == "LRN-001"
        assert i.importance == InsightImportance.MEDIUM

class TestStrategyPerformance:
    def test_success_rate(self):
        s = StrategyPerformance(strategy_id="S1", strategy_name="test", total_uses=10, success_count=7, failure_count=3)
        assert s.success_rate == 0.7
        assert s.is_effective is True
    def test_success_rate_zero_uses(self):
        s = StrategyPerformance(strategy_id="S2", strategy_name="test2")
        assert s.success_rate == 0.0
        assert s.is_effective is False

class TestFailurePattern:
    def test_create(self):
        f = FailurePattern(pattern_id="F1", description="fail")
        assert f.failure_count == 1

class TestImprovementRecommendation:
    def test_create(self):
        r = ImprovementRecommendation(recommendation_id="R1", title="Fix", description="Fix it")
        assert r.actionable is True


# ===================================================================
# StrategyAnalyzer Tests
# ===================================================================

class TestStrategyAnalyzer:
    def test_analyze_strategy_new(self):
        analyzer = StrategyAnalyzer()
        data = {"success": True, "has_reasoning": True, "has_planning": True, "has_tool_result": True}
        perf = analyzer.analyze_strategy(data)
        assert perf.strategy_name == "full_pipeline"
        assert perf.total_uses == 1
        assert perf.success_count == 1

    def test_analyze_strategy_existing(self):
        analyzer = StrategyAnalyzer()
        existing = StrategyPerformance(strategy_id="S1", strategy_name="reasoning_only", total_uses=5, success_count=3, failure_count=2)
        data = {"success": True, "has_reasoning": True, "has_planning": False, "has_tool_result": False}
        updated = analyzer.analyze_strategy(data, existing)
        assert updated.total_uses == 6
        assert updated.success_count == 4

    def test_analyze_strategy_failure(self):
        analyzer = StrategyAnalyzer()
        data = {"success": False, "has_reasoning": False, "has_planning": False, "has_tool_result": False}
        perf = analyzer.analyze_strategy(data)
        assert perf.strategy_name == "direct_response"
        assert perf.failure_count == 1

    def test_analyze_failures_no_failure(self):
        analyzer = StrategyAnalyzer()
        data = {"success": True, "has_reasoning": True}
        patterns = analyzer.analyze_failures(data)
        assert patterns == []

    def test_analyze_failures_detects(self):
        analyzer = StrategyAnalyzer()
        data = {"success": False, "has_reasoning": False, "has_planning": False}
        patterns = analyzer.analyze_failures(data)
        assert len(patterns) >= 1

    def test_analyze_failures_updates_existing(self):
        analyzer = StrategyAnalyzer()
        existing = [FailurePattern(pattern_id="F1", description="Pipeline completed without reasoning stage", failure_count=2)]
        data = {"success": False, "has_reasoning": False, "has_planning": False}
        patterns = analyzer.analyze_failures(data, existing)
        assert len(patterns) == 1
        assert patterns[0].failure_count == 3

    def test_score_effectiveness(self):
        analyzer = StrategyAnalyzer()
        performances = [
            StrategyPerformance(strategy_id="S1", strategy_name="full", total_uses=10, success_count=9, failure_count=1),
            StrategyPerformance(strategy_id="S2", strategy_name="basic", total_uses=10, success_count=2, failure_count=8),
        ]
        scored = analyzer.score_strategy_effectiveness(performances)
        assert len(scored) == 2
        assert scored[0]["success_rate"] >= scored[1]["success_rate"]

    def test_generate_strategy_insights(self):
        analyzer = StrategyAnalyzer()
        performances = [
            StrategyPerformance(strategy_id="S1", strategy_name="full_pipeline", total_uses=10, success_count=9, failure_count=1),
        ]
        insights = analyzer.generate_strategy_insights(performances)
        assert len(insights) >= 1

    def test_generate_failure_insights(self):
        analyzer = StrategyAnalyzer()
        patterns = [FailurePattern(pattern_id="F1", description="Repeated failure", failure_count=5, common_cause="Missing dep")]
        insights = analyzer.generate_failure_insights(patterns)
        assert len(insights) >= 1


# ===================================================================
# InsightConsolidator Tests
# ===================================================================

class TestInsightConsolidator:
    def test_consolidate_new(self):
        c = InsightConsolidator()
        new = [LearningInsight(insight_id="L1", category=LearningCategory.REASONING_STRATEGY, title="Test", description="D")]
        result = c.consolidate(new, [])
        assert len(result) == 1

    def test_consolidate_duplicate(self):
        c = InsightConsolidator()
        existing = [LearningInsight(insight_id="L1", category=LearningCategory.REASONING_STRATEGY, title="Test", description="D", confidence=0.5, observation_count=1)]
        new = [LearningInsight(insight_id="L2", category=LearningCategory.REASONING_STRATEGY, title="Test", description="D", confidence=0.7, observation_count=2)]
        result = c.consolidate(new, existing)
        # Should have merged — only 1 insight
        assert len(result) == 1
        assert result[0].observation_count >= 3
        assert result[0].confidence > 0.5

    def test_remove_weak(self):
        c = InsightConsolidator()
        weak = LearningInsight(insight_id="L1", category=LearningCategory.OPTIMIZATION, title="Weak", description="D", importance=InsightImportance.LOW, confidence=0.2)
        strong = LearningInsight(insight_id="L2", category=LearningCategory.REASONING_STRATEGY, title="Strong", description="D", importance=InsightImportance.HIGH, confidence=0.9)
        result = c.consolidate([weak, strong], [])
        assert len(result) == 1
        assert result[0].insight_id == "L2"

    def test_calculate_strength(self):
        c = InsightConsolidator()
        i = LearningInsight(insight_id="L1", category=LearningCategory.REASONING_STRATEGY, title="T", description="D", importance=InsightImportance.CRITICAL, confidence=1.0, observation_count=100)
        strength = c.calculate_strength(i)
        assert 0.0 <= strength <= 1.0
        assert strength > 0.8

    def test_invalid_max(self):
        with pytest.raises(ValueError):
            InsightConsolidator(max_insights=0)


# ===================================================================
# LearningMemory Tests
# ===================================================================

class TestLearningMemory:
    def test_store_and_get_insights(self):
        mem = LearningMemory()
        i = LearningInsight(insight_id="L1", category=LearningCategory.REASONING_STRATEGY, title="T", description="D")
        mem.store_insights([i])
        assert mem.insight_count == 1
        assert len(mem.get_insights(10)) == 1

    def test_store_and_get_strategies(self):
        mem = LearningMemory()
        s = StrategyPerformance(strategy_id="S1", strategy_name="test")
        mem.store_strategy(s)
        assert mem.strategy_count == 1
        assert mem.get_strategy("S1") is not None
        assert mem.get_strategy_by_name("test") is not None

    def test_store_and_get_failures(self):
        mem = LearningMemory()
        f = FailurePattern(pattern_id="F1", description="fail")
        mem.store_failures([f])
        assert mem.failure_count == 1

    def test_store_recommendation(self):
        mem = LearningMemory()
        r = ImprovementRecommendation(recommendation_id="R1", title="Fix", description="Fix")
        mem.store_recommendation(r)
        assert mem.recommendation_count == 1

    def test_invalid_limits(self):
        with pytest.raises(ValueError):
            LearningMemory(max_insights=0)

    def test_clear(self):
        mem = LearningMemory()
        mem.store_insights([LearningInsight(insight_id="L1", category=LearningCategory.REASONING_STRATEGY, title="T", description="D")])
        assert mem.insight_count == 1
        mem.clear()
        assert mem.insight_count == 0

    def test_summary(self):
        mem = LearningMemory()
        s = mem.summary()
        assert "insight_count" in s


# ===================================================================
# LearningEngine Tests
# ===================================================================

class TestLearningEngine:
    def test_learn_from_successful_pipeline(self):
        engine = LearningEngine()
        data = {
            "success": True,
            "has_reasoning": True,
            "has_planning": True,
            "has_tool_result": False,
            "understanding_insights_count": 3,
            "user_input": "test query",
        }
        insights = engine.learn_from_pipeline(data)
        assert len(insights) >= 1
        assert engine.memory.insight_count > 0

    def test_learn_from_failed_pipeline(self):
        engine = LearningEngine()
        data = {
            "success": False,
            "has_reasoning": False,
            "has_planning": False,
            "has_tool_result": False,
        }
        insights = engine.learn_from_pipeline(data)
        assert engine.memory.strategy_count > 0

    def test_learning_summary(self):
        engine = LearningEngine()
        data = {"success": True, "has_reasoning": True, "has_planning": True, "has_tool_result": True}
        engine.learn_from_pipeline(data)
        summary = engine.get_learning_summary()
        assert summary["pipelines_processed"] >= 1
        assert "memory" in summary
        assert "top_insights" in summary

    def test_multiple_pipelines_accumulate(self):
        engine = LearningEngine()
        for _ in range(5):
            engine.learn_from_pipeline({"success": True, "has_reasoning": True, "has_planning": True, "has_tool_result": False})
        assert engine.memory.strategy_count >= 1
        # After 5 runs, a strategy should have total_uses=5
        strategies = engine.memory.get_all_strategies()
        full = [s for s in strategies if s.strategy_name == "reasoning_with_planning"]
        if full:
            assert full[0].total_uses == 5

    def test_recommendations_generated(self):
        engine = LearningEngine()
        for _ in range(3):
            engine.learn_from_pipeline({"success": True, "has_reasoning": True, "has_planning": True, "has_tool_result": True, "understanding_insights_count": 5})
        assert engine.memory.recommendation_count > 0