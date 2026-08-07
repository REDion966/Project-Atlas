"""Track D — MetaReasoningEngine tests (Batch 2).

Covers strategy effectiveness evaluation, historical reasoning analysis,
strategy recommendation, reasoning-quality metrics, adaptive (deterministic)
strategy selection, read-only provider discipline, and edge cases.
"""

from atlas.advanced_reasoning.meta import MetaReasoningEngine, ReasoningHistoryProvider
from atlas.advanced_reasoning.models import ReasoningStrategy
from tests._advanced_reasoning_fakes import FakeHistoryProvider


def _trace(strategy: str = "DECOMPOSE", status: str = "COMPLETED") -> object:
    """Build a trace-like record for meta-reasoning aggregation."""
    return FakeHistoryProvider.build_trace(
        trace_id=f"t-{strategy}-{status}",
        strategy_name=strategy,
        status_name=status,
        step_count=2,
    )


class TestEvaluateStrategy:
    def test_all_successful_scores_max_success_rate(self):
        engine = MetaReasoningEngine()
        score = engine.evaluate_strategy(
            ReasoningStrategy.DECOMPOSE,
            window=(_trace(), _trace()),
        )
        assert score.total_count == 2
        assert score.success_count == 2
        assert score.success_rate == 1.0

    def test_empty_window_zeroed(self):
        engine = MetaReasoningEngine()
        score = engine.evaluate_strategy(ReasoningStrategy.DECOMPOSE, window=())
        assert score.total_count == 0
        assert score.success_rate == 0.0
        assert score.score == 0.0

    def test_failure_count_tracked(self):
        engine = MetaReasoningEngine()
        score = engine.evaluate_strategy(
            ReasoningStrategy.DECOMPOSE,
            window=(_trace(status="COMPLETED"), _trace(status="FAILED")),
        )
        assert score.success_count == 1
        assert score.failure_count == 1
        assert score.success_rate == 0.5

    def test_avg_steps_calculated(self):
        engine = MetaReasoningEngine()
        score = engine.evaluate_strategy(
            ReasoningStrategy.DECOMPOSE,
            window=(_trace(), _trace()),
        )
        assert score.avg_steps == 2.0


class TestRecommend:
    def test_best_strategy_selected(self):
        engine = MetaReasoningEngine()
        winner = engine.evaluate_strategy(
            ReasoningStrategy.CAUSAL, window=(_trace(strategy="CAUSAL"), _trace(strategy="CAUSAL"))
        )
        loser = engine.evaluate_strategy(
            ReasoningStrategy.DECOMPOSE, window=(_trace(status="FAILED"),)
        )
        best, reason = engine.recommend((loser, winner))
        assert best is not None
        assert best.strategy == ReasoningStrategy.CAUSAL
        assert "CAUSAL" in reason

    def test_empty_scores(self):
        engine = MetaReasoningEngine()
        best, reason = engine.recommend(())
        assert best is None
        assert "No strategy evidence" in reason

    def test_tie_breaks_by_declaration_order(self):
        engine = MetaReasoningEngine()
        decompose = engine.evaluate_strategy(
            ReasoningStrategy.DECOMPOSE, window=(_trace(),)
        )
        causal = engine.evaluate_strategy(
            ReasoningStrategy.CAUSAL, window=(_trace(strategy="CAUSAL"),)
        )
        best, _ = engine.recommend((causal, decompose))
        assert best is not None
        assert best.strategy == ReasoningStrategy.DECOMPOSE


class TestAssess:
    def test_assess_with_provider_history(self):
        provider = FakeHistoryProvider(
            records=[_trace(), _trace(status="FAILED"), _trace(strategy="CAUSAL")]
        )
        engine = MetaReasoningEngine(history_provider=provider)
        assessment = engine.assess()
        assert assessment.metadata["window_size"] == 3
        assert assessment.metadata["history_count"] == 3

    def test_assess_with_explicit_traces_no_provider(self):
        engine = MetaReasoningEngine()
        assessment = engine.assess(traces=(_trace(), _trace()))
        assert assessment.strategy_scores[0].total_count == 2

    def test_assess_empty_uses_default_strategy(self):
        engine = MetaReasoningEngine()
        assessment = engine.assess()
        assert assessment.recommended_strategy == ReasoningStrategy.DECOMPOSE
        assert assessment.strategy_scores == ()

    def test_assessment_id_override(self):
        provider = FakeHistoryProvider(records=[_trace()])
        engine = MetaReasoningEngine(history_provider=provider)
        assessment = engine.assess(assessment_id="custom")
        assert assessment.assessment_id == "custom"

    def test_provider_read_only(self):
        provider = FakeHistoryProvider(records=[_trace(), _trace()])
        engine = MetaReasoningEngine(history_provider=provider)
        engine.assess()
        # Only reads: recent(), count() — the provider surface is unchanged.
        assert len(provider.records) == 2
        assert provider.recent_calls == [100]


class TestQualityMetrics:
    def test_empty_metrics(self):
        engine = MetaReasoningEngine()
        metrics = engine.quality_metrics()
        assert metrics["sample_size"] == 0
        assert metrics["success_rate"] == 0.0

    def test_strategy_distribution(self):
        provider = FakeHistoryProvider(
            records=[
                _trace(strategy="CAUSAL"),
                _trace(strategy="CAUSAL"),
                _trace(strategy="DECOMPOSE", status="FAILED"),
            ]
        )
        engine = MetaReasoningEngine(history_provider=provider)
        metrics = engine.quality_metrics()
        assert metrics["sample_size"] == 3
        assert metrics["strategy_distribution"] == {"CAUSAL": 2, "DECOMPOSE": 1}
        assert metrics["success_rate"] == round(2 / 3, 4)


class TestProviderFailSoft:
    def test_invalid_provider_returns_empty(self):
        class WrongShape:
            def nope(self) -> list:
                return []

        engine = MetaReasoningEngine(history_provider=WrongShape())  # type: ignore[arg-type]
        assert engine._sample() == ()

    def test_provider_never_raises(self):
        class BoomProvider:
            def recent(self, n: int = 10):
                raise RuntimeError("boom")

            def count(self) -> int:
                raise RuntimeError("boom")

            def summary(self) -> dict:
                raise RuntimeError("boom")

        engine = MetaReasoningEngine(history_provider=BoomProvider())  # type: ignore[arg-type]
        assessment = engine.assess()
        assert assessment.recommended_strategy == ReasoningStrategy.DECOMPOSE


class TestProtocol:
    def test_protocol_runtime_checkable(self):
        provider = FakeHistoryProvider(records=[])
        assert isinstance(provider, ReasoningHistoryProvider)
