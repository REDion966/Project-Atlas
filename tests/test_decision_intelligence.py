"""
Phase 14.2 — DecisionIntelligenceEngine Tests.

Tests for ``atlas/evolution/decision_intelligence.py``.
All tests use hand-crafted inputs and lightweight mock queries.

No infrastructure, no storage, no AI.
"""

from dataclasses import dataclass

import pytest

from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.evolution.decision_models import PlanningContext
from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    RecurringOutcomePattern,
    StrategyKnowledge,
)
from atlas.evolution.knowledge.query import EvolutionKnowledgeQuery


# ---------------------------------------------------------------------------
# Lightweight fake query
# ---------------------------------------------------------------------------


class FakeEvolutionKnowledgeQuery:
    """In-memory stand-in for EvolutionKnowledgeQuery."""

    def __init__(self) -> None:
        self._patterns: list[RecurringOutcomePattern] = []
        self._strategies: list[StrategyKnowledge] = []
        self._capabilities: list[CapabilityEvolution] = []
        self._bottlenecks: list[BottleneckProfile] = []

    def add_pattern(self, pattern: RecurringOutcomePattern) -> None:
        self._patterns.append(pattern)

    def add_strategy(self, strategy: StrategyKnowledge) -> None:
        self._strategies.append(strategy)

    def add_capability(self, capability: CapabilityEvolution) -> None:
        self._capabilities.append(capability)

    def add_bottleneck(self, bottleneck: BottleneckProfile) -> None:
        self._bottlenecks.append(bottleneck)

    # EvolutionKnowledgeQuery interface

    def get_patterns_by_area(
        self,
        area: str,
        n: int = 20,
    ) -> list[RecurringOutcomePattern]:
        filtered = [p for p in self._patterns if p.area == area]
        filtered.sort(key=lambda p: (p.confidence, p.occurrence_count), reverse=True)
        return filtered[:n] if n > 0 else filtered

    def get_bottlenecks(
        self,
        min_recurrences: int = 3,
        n: int = 20,
    ) -> list[BottleneckProfile]:
        filtered = [
            b for b in self._bottlenecks
            if b.recurrence_count >= min_recurrences
        ]
        filtered.sort(key=lambda b: b.recurrence_count, reverse=True)
        return filtered[:n] if n > 0 else filtered

    def get_bottlenecks_by_area(
        self,
        area: str,
        n: int = 20,
    ) -> list[BottleneckProfile]:
        filtered = [b for b in self._bottlenecks if b.area == area]
        return filtered[:n] if n > 0 else filtered

    def get_effective_strategies(
        self,
        min_effectiveness: float = 0.7,
        n: int = 20,
    ) -> list[StrategyKnowledge]:
        filtered = [
            s for s in self._strategies
            if s.effectiveness >= min_effectiveness
        ]
        return filtered[:n] if n > 0 else filtered

    def get_ineffective_strategies(
        self,
        max_effectiveness: float = 0.4,
        n: int = 20,
    ) -> list[StrategyKnowledge]:
        filtered = [
            s for s in self._strategies
            if s.effectiveness <= max_effectiveness
        ]
        filtered.sort(key=lambda s: s.effectiveness)
        return filtered[:n] if n > 0 else filtered

    def get_capabilities(
        self,
        n: int = 20,
    ) -> list[CapabilityEvolution]:
        return self._capabilities[:n] if n > 0 else list(self._capabilities)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_weakness(area: str = "runtime") -> object:
    """Create a minimal weakness-like object."""
    return type("Weakness", (), {"area": area})()


def make_pattern(
    area: str = "runtime",
    outcome: str = "success",
    occurrence_count: int = 10,
    success_count: int = 0,
    failure_count: int = 0,
    confidence: float = 0.8,
) -> RecurringOutcomePattern:
    """Create a RecurringOutcomePattern."""
    if outcome == "success":
        success_count = success_count or occurrence_count
    elif outcome == "failure":
        failure_count = failure_count or occurrence_count
    return RecurringOutcomePattern(
        pattern_id=f"PAT-{area}-{outcome}",
        area=area,
        outcome=outcome,
        occurrence_count=occurrence_count,
        success_count=success_count,
        failure_count=failure_count,
        confidence=confidence,
    )


def make_strategy(
    key: str = "refactor",
    area: str = "runtime",
    effectiveness: float = 0.5,
    confidence: float = 0.5,
    occurrence_count: int = 5,
) -> StrategyKnowledge:
    """Create a StrategyKnowledge tied to an area via metadata."""
    return StrategyKnowledge(
        strategy_key=key,
        strategy_name=key.replace("_", " ").title(),
        effectiveness=effectiveness,
        confidence=confidence,
        occurrence_count=occurrence_count,
        metadata={"area": area},
    )


def make_capability(
    name: str = "memory_retrieval",
    assessments: list[float] | None = None,
) -> CapabilityEvolution:
    """Create a CapabilityEvolution."""
    assessments = assessments or [0.5]
    return CapabilityEvolution(
        capability_name=name,
        assessments=assessments,
        observed_count=len(assessments),
    )


def make_bottleneck(
    area: str = "runtime",
    recurrence_count: int = 10,
) -> BottleneckProfile:
    """Create a BottleneckProfile."""
    return BottleneckProfile(
        bottleneck_id=f"BOT-{area}",
        area=area,
        description="A recurring bottleneck.",
        recurrence_count=recurrence_count,
    )


@dataclass(frozen=True)
class FakeCandidate:
    """Minimal candidate for ranking tests."""

    candidate_id: str
    area: str
    priority_score: float


# ---------------------------------------------------------------------------
# Empty / graceful degradation tests
# ---------------------------------------------------------------------------


class TestGracefulDegradation:

    def test_no_query_returns_neutral_context(self):
        """Missing knowledge query yields a neutral PlanningContext."""
        engine = DecisionIntelligenceEngine(knowledge_query=None)

        context = engine.get_planning_context()

        assert context.area_adjustments == {}
        assert context.bottleneck_alerts == []
        assert context.strategy_suggestions == {}
        assert context.capability_signals == {}
        assert context.overall_confidence == 0.0

    def test_empty_query_returns_neutral_context(self):
        """Empty knowledge repository yields a neutral PlanningContext."""
        query = FakeEvolutionKnowledgeQuery()
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context()

        assert context.area_adjustments == {}
        assert context.bottleneck_alerts == []
        assert context.strategy_suggestions == {}
        assert context.capability_signals == {}
        assert context.overall_confidence == 0.0

    def test_ranking_with_neutral_context_preserves_order(self):
        """Ranking with a neutral context sorts by base priority score."""
        engine = DecisionIntelligenceEngine(knowledge_query=None)
        candidates = [
            FakeCandidate("c1", "runtime", 0.5),
            FakeCandidate("c2", "memory", 0.9),
            FakeCandidate("c3", "reasoning", 0.3),
        ]

        ranked = engine.rank_candidates(candidates)

        assert [c.candidate_id for c in ranked] == ["c2", "c1", "c3"]

    def test_suggest_strategies_with_no_query_returns_empty(self):
        """Strategy suggestions are empty when no query is available."""
        engine = DecisionIntelligenceEngine(knowledge_query=None)

        suggestions = engine.suggest_strategies("runtime")

        assert suggestions == []

    def test_suggest_strategies_with_empty_context_returns_empty(self):
        """Strategy suggestions are empty when the area has none."""
        query = FakeEvolutionKnowledgeQuery()
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        suggestions = engine.suggest_strategies("runtime")

        assert suggestions == []


# ---------------------------------------------------------------------------
# Historical pattern tests
# ---------------------------------------------------------------------------


class TestHistoricalPatterns:

    def test_success_pattern_produces_prefer_adjustment(self):
        """A success pattern produces a 'prefer' area adjustment."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_pattern(make_pattern(outcome="success", occurrence_count=10))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])

        adjustment = context.area_adjustments["runtime"]
        assert adjustment.recommendation == "prefer"
        assert adjustment.adjustment_factor > 1.0

    def test_failure_pattern_produces_avoid_adjustment(self):
        """A failure pattern produces an 'avoid' area adjustment."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_pattern(make_pattern(outcome="failure", occurrence_count=10))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])

        adjustment = context.area_adjustments["runtime"]
        assert adjustment.recommendation == "avoid"
        assert adjustment.adjustment_factor < 1.0

    def test_multiple_areas_are_adjusted(self):
        """Patterns for multiple areas produce separate adjustments."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_pattern(make_pattern(area="runtime", outcome="success"))
        query.add_pattern(make_pattern(area="memory", outcome="failure"))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(
            weaknesses=[make_weakness("runtime"), make_weakness("memory")],
        )

        assert "runtime" in context.area_adjustments
        assert "memory" in context.area_adjustments
        assert context.area_adjustments["runtime"].adjustment_factor > 1.0
        assert context.area_adjustments["memory"].adjustment_factor < 1.0


# ---------------------------------------------------------------------------
# Bottleneck tests
# ---------------------------------------------------------------------------


class TestBottleneckAlerts:

    def test_bottleneck_alert_in_context(self):
        """A recurring bottleneck appears as an alert in the context."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_bottleneck(make_bottleneck(area="runtime", recurrence_count=10))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])

        assert len(context.bottleneck_alerts) == 1
        alert = context.bottleneck_alerts[0]
        assert alert.area == "runtime"
        assert alert.severity_boost == pytest.approx(0.3, abs=0.001)

    def test_bottleneck_alert_only_for_relevant_area(self):
        """Bottlenecks for other areas are not included."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_bottleneck(make_bottleneck(area="memory", recurrence_count=10))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])

        assert context.bottleneck_alerts == []


# ---------------------------------------------------------------------------
# Strategy suggestion tests
# ---------------------------------------------------------------------------


class TestStrategySuggestions:

    def test_prefer_strategy_appears_in_context(self):
        """An effective strategy is suggested as 'prefer'."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_strategy(
            make_strategy("add_tests", effectiveness=0.85, confidence=0.5),
        )
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])

        suggestions = context.strategy_suggestions["runtime"]
        assert len(suggestions) == 1
        assert suggestions[0].recommendation == "prefer"

    def test_suggest_strategies_orders_by_effectiveness(self):
        """suggest_strategies returns prefer strategies above neutral ones."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_strategy(make_strategy("a", effectiveness=0.3))
        query.add_strategy(make_strategy("b", effectiveness=0.9))
        query.add_strategy(make_strategy("c", effectiveness=0.6))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        suggestions = engine.suggest_strategies("runtime")

        assert suggestions[0].strategy_key == "b"
        assert suggestions[0].recommendation == "prefer"
        assert all(s.recommendation in ("prefer", "neutral", "avoid") for s in suggestions)

    def test_suggest_strategies_uses_context_cache(self):
        """suggest_strategies can read from a supplied PlanningContext."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_strategy(make_strategy("cached", effectiveness=0.8))
        engine = DecisionIntelligenceEngine(knowledge_query=query)
        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])

        suggestions = engine.suggest_strategies("runtime", context=context)

        assert len(suggestions) == 1
        assert suggestions[0].strategy_key == "cached"


# ---------------------------------------------------------------------------
# Capability signal tests
# ---------------------------------------------------------------------------


class TestCapabilitySignals:

    def test_improving_capability_signals_defer(self):
        """A strong improving capability produces a 'defer' signal."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_capability(make_capability(assessments=[0.4, 0.6, 0.8]))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context()

        signal = context.capability_signals["memory_retrieval"]
        assert signal.signal == "defer"

    def test_declining_capability_signals_intervene(self):
        """A declining capability produces an 'intervene' signal."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_capability(make_capability(assessments=[0.8, 0.6, 0.4]))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context()

        signal = context.capability_signals["memory_retrieval"]
        assert signal.signal == "intervene"


# ---------------------------------------------------------------------------
# Candidate ranking tests
# ---------------------------------------------------------------------------


class TestCandidateRanking:

    def test_success_area_boosts_candidate(self):
        """Candidates in successful areas rank higher after adjustment."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_pattern(make_pattern(area="runtime", outcome="success"))
        query.add_pattern(make_pattern(area="memory", outcome="failure"))
        engine = DecisionIntelligenceEngine(knowledge_query=query)
        context = engine.get_planning_context(
            weaknesses=[make_weakness("runtime"), make_weakness("memory")],
        )
        candidates = [
            FakeCandidate("runtime_candidate", "runtime", 0.6),
            FakeCandidate("memory_candidate", "memory", 0.6),
        ]

        ranked = engine.rank_candidates(candidates, context=context)

        assert ranked[0].area == "runtime"
        assert ranked[1].area == "memory"

    def test_bottleneck_boost_elevates_candidate(self):
        """Candidates matching a bottleneck receive a boost."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_bottleneck(make_bottleneck(area="runtime", recurrence_count=10))
        engine = DecisionIntelligenceEngine(knowledge_query=query)
        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])
        candidates = [
            FakeCandidate("runtime", "runtime", 0.5),
            FakeCandidate("memory", "memory", 0.5),
        ]

        ranked = engine.rank_candidates(candidates, context=context)

        assert ranked[0].area == "runtime"

    def test_declining_capability_boosts_intervention(self):
        """Candidates in declining capability areas rank higher."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_capability(make_capability(assessments=[0.8, 0.6, 0.4]))
        engine = DecisionIntelligenceEngine(knowledge_query=query)
        context = engine.get_planning_context()
        candidates = [
            FakeCandidate("memory", "memory_retrieval", 0.5),
            FakeCandidate("other", "other", 0.5),
        ]

        ranked = engine.rank_candidates(candidates, context=context)

        assert ranked[0].area == "memory_retrieval"


# ---------------------------------------------------------------------------
# Determinism and idempotency
# ---------------------------------------------------------------------------


class TestDeterminism:

    def test_context_is_deterministic(self):
        """Identical inputs always produce identical contexts."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_pattern(make_pattern(outcome="success"))
        query.add_bottleneck(make_bottleneck(recurrence_count=10))
        query.add_strategy(make_strategy(effectiveness=0.8))
        query.add_capability(make_capability(assessments=[0.4, 0.6, 0.8]))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])
        results = [
            engine.get_planning_context(weaknesses=[make_weakness("runtime")])
            for _ in range(50)
        ]

        assert all(
            r.area_adjustments == context.area_adjustments
            and r.bottleneck_alerts == context.bottleneck_alerts
            and r.strategy_suggestions == context.strategy_suggestions
            and r.capability_signals == context.capability_signals
            for r in results
        )

    def test_ranking_is_idempotent(self):
        """Ranking the same candidates twice yields the same order."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_pattern(make_pattern(area="runtime", outcome="success"))
        engine = DecisionIntelligenceEngine(knowledge_query=query)
        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])
        candidates = [
            FakeCandidate("c1", "runtime", 0.5),
            FakeCandidate("c2", "memory", 0.6),
        ]

        first = engine.rank_candidates(candidates, context=context)
        second = engine.rank_candidates(candidates, context=context)

        assert [c.candidate_id for c in first] == [c.candidate_id for c in second]

    def test_suggest_strategies_is_idempotent(self):
        """Suggesting strategies twice yields the same result."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_strategy(make_strategy(effectiveness=0.8))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        first = engine.suggest_strategies("runtime")
        second = engine.suggest_strategies("runtime")

        assert first == second


# ---------------------------------------------------------------------------
# Overall confidence
# ---------------------------------------------------------------------------


class TestOverallConfidence:

    def test_overall_confidence_with_evidence(self):
        """Overall confidence is positive when historical evidence exists."""
        query = FakeEvolutionKnowledgeQuery()
        query.add_pattern(make_pattern(outcome="success", confidence=0.8))
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context(weaknesses=[make_weakness("runtime")])

        assert context.overall_confidence > 0.0

    def test_overall_confidence_with_no_evidence(self):
        """Overall confidence is zero when no evidence exists."""
        query = FakeEvolutionKnowledgeQuery()
        engine = DecisionIntelligenceEngine(knowledge_query=query)

        context = engine.get_planning_context()

        assert context.overall_confidence == 0.0
