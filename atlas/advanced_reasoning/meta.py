"""Atlas Advanced Reasoning — MetaReasoningEngine (Track D, Batch 2).

Evaluates the effectiveness of reasoning strategies over collected trace /
outcome history, recommends the best strategy, and reports reasoning-quality
metrics. Consumes ONLY an injected read-only history provider duck-typed to
the ``recent(n)`` / ``count()`` / ``summary()`` surface shared by the existing
``ReasoningRecorder`` and the Track D ``ReasoningTraceRecorder``.

The engine NEVER mutates the provider: it only calls read methods and
performs pure aggregation over locally copied samples.

Pure logic. No storage. No kernel. No atlas.reasoning imports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from atlas.advanced_reasoning.catalog import (
    META_ASSESSMENT_ID_PREFIX,
    REASONER_VERSION,
)
from atlas.advanced_reasoning.models import (
    MetaAssessment,
    ReasoningConfig,
    ReasoningStrategy,
    StrategyScore,
)

#: Weight of success rate in the aggregate effectiveness score.
_SUCCESS_WEIGHT: float = 0.6
#: Weight of the verification pass rate in the aggregate score.
_VERIFICATION_WEIGHT: float = 0.2
#: Weight of the step-efficiency term in the aggregate score.
_EFFICIENCY_WEIGHT: float = 0.2

#: Read methods every injected history provider must expose.
_HISTORY_METHODS: tuple[str, ...] = ("recent", "count", "summary")


@runtime_checkable
class ReasoningHistoryProvider(Protocol):
    """Read-only reasoning-history surface.

    Duck-typed: satisfied by the existing ReasoningRecorder (atlas.reasoning
    outcomes) and by the Track D ReasoningTraceRecorder. Implementors expose
    ``recent(n)``, ``count()`` and ``summary()`` and never mutate on read.
    """

    def recent(self, n: int = 10) -> list[Any]:
        """Return the most recent n records, newest first."""
        ...

    def count(self) -> int:
        """Return the number of retained records."""
        ...

    def summary(self) -> dict[str, Any]:
        """Return an aggregate summary of retained records."""
        ...


class MetaReasoningEngine:
    """Deterministic meta-reasoning over an injected history provider.

    Args:
        history_provider: Injected read-only history source. When ``None``,
            assessments are produced from locally passed traces only.
        config: Optional reasoning configuration; a default is used when
            ``None`` is given.
    """

    def __init__(
        self,
        history_provider: ReasoningHistoryProvider | None = None,
        config: ReasoningConfig | None = None,
    ) -> None:
        self._history_provider = history_provider
        self._config = config or ReasoningConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_strategy(
        self,
        strategy: ReasoningStrategy,
        window: tuple[Any, ...] = (),
    ) -> StrategyScore:
        """Evaluate one strategy over the provided window (or provider history).

        Args:
            strategy: The strategy to score.
            window: Optional explicit records to score; when empty, the
                injected provider history is sampled.

        Returns:
            A StrategyScore with deterministic aggregate metrics. Fail-soft:
            no records or a failing provider yields a zeroed score.
        """
        records = window if window else self._sample()

        success_count = 0
        failure_count = 0
        for record in records:
            ok = self._record_success(record)
            if ok is True:
                success_count += 1
            elif ok is False:
                failure_count += 1

        total = len(records)
        success_rate = round(success_count / total, 4) if total else 0.0

        verifications = [
            self._verification_pass_rate(record)
            for record in records
        ]
        avg_verification = (
            round(sum(verifications) / len(verifications), 4)
            if verifications
            else 0.0
        )

        steps = [self._record_step_count(record) for record in records]
        avg_steps = round(sum(steps) / len(steps), 4) if steps else 0.0

        max_budget = float(max(1, self._config.max_steps))
        efficiency = max(0.0, 1.0 - (avg_steps / max_budget)) if total else 0.0
        score = round(
            _SUCCESS_WEIGHT * success_rate
            + _VERIFICATION_WEIGHT * avg_verification
            + _EFFICIENCY_WEIGHT * efficiency,
            4,
        )

        return StrategyScore(
            strategy=strategy,
            success_count=success_count,
            failure_count=failure_count,
            total_count=total,
            success_rate=success_rate,
            avg_verification_pass_rate=avg_verification,
            avg_steps=avg_steps,
            score=score,
            metadata={"source": "meta_reasoning"},
        )

    def recommend(
        self,
        scores: tuple[StrategyScore, ...],
    ) -> tuple[StrategyScore | None, str]:
        """Recommend the best strategy from precomputed scores.

        Ties are resolved by enum declaration order (stable). Returns the
        best score (or None) and a deterministic reason sentence.
        """
        if not scores:
            return None, "No strategy evidence available."
        best = max(
            scores,
            key=lambda s: (s.score, s.success_rate, -s.strategy.value),
        )
        candidates = sorted(
            scores,
            key=lambda s: (s.score, s.success_rate, -s.strategy.value),
            reverse=True,
        )
        reason = (
            f"Strategy {best.strategy.name} has the highest effectiveness "
            f"score ({best.score:.2f}) over {best.total_count} record(s)."
        )
        if len(candidates) > 1 and candidates[1].score == best.score:
            reason = (
                f"Strategy {best.strategy.name} ties the top score "
                f"({best.score:.2f}) and is preferred by declaration order."
            )
        return best, reason

    def assess(
        self,
        traces: tuple[Any, ...] = (),
        window_size: int | None = None,
        assessment_id: str | None = None,
    ) -> MetaAssessment:
        """Produce a full meta-reasoning assessment.

        Scores every strategy over the union of the supplied ``traces`` and
        (when available) the injected provider history, then recommends one.

        Returns:
            A MetaAssessment. Never raises: empty history yields a zeroed
            assessment with the default strategy recommendation.
        """
        window = self._sample(window_size) + tuple(traces)
        scores = tuple(
            self.evaluate_strategy(strategy, window)
            for strategy in ReasoningStrategy
        )
        recommended, reason = self.recommend(scores)

        return MetaAssessment(
            assessment_id=assessment_id or self._default_assessment_id(),
            strategy_scores=tuple(s for s in scores if s.total_count > 0),
            recommended_strategy=(
                recommended.strategy
                if recommended is not None
                else ReasoningStrategy.DECOMPOSE
            ),
            recommendation_reason=reason,
            assessed_at=datetime.now(),
            metadata={
                "reasoner_version": REASONER_VERSION,
                "window_size": len(window),
                "history_count": self._safe_provider_count(),
            },
        )

    def quality_metrics(
        self,
        window: tuple[Any, ...] = (),
    ) -> dict[str, Any]:
        """Deterministic reasoning-quality metrics over a sample window."""
        records = window if window else self._sample()
        if not records:
            return {
                "sample_size": 0,
                "success_rate": 0.0,
                "avg_steps": 0.0,
                "avg_verification_pass_rate": 0.0,
                "strategy_distribution": {},
            }
        success_count = sum(1 for r in records if self._record_success(r) is True)
        total = len(records)
        steps = [self._record_step_count(r) for r in records]
        verifications = [self._verification_pass_rate(r) for r in records]

        distribution: dict[str, int] = {}
        for record in records:
            key = self._record_strategy(record).name
            distribution[key] = distribution.get(key, 0) + 1

        return {
            "sample_size": total,
            "success_rate": round(success_count / total, 4),
            "avg_steps": round(sum(steps) / total, 4),
            "avg_verification_pass_rate": round(
                sum(verifications) / total, 4
            ),
            "strategy_distribution": distribution,
        }

    # ------------------------------------------------------------------
    # Reading the injected provider (read-only)
    # ------------------------------------------------------------------

    def _sample(self, window_size: int | None = None) -> tuple[Any, ...]:
        """Sample the injected provider without mutating it (fail-soft)."""
        provider = self._history_provider
        if provider is None:
            return ()
        size = max(1, window_size or self._config.meta_window_size)
        try:
            if not all(hasattr(provider, method) for method in _HISTORY_METHODS):
                return ()
            samples = provider.recent(size)
            return tuple(samples)
        except Exception:
            return ()

    def _safe_provider_count(self) -> int:
        """Read the provider count defensively (fail-soft)."""
        provider = self._history_provider
        if provider is None or not hasattr(provider, "count"):
            return 0
        try:
            return int(provider.count())
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Record introspection (duck-typed)
    # ------------------------------------------------------------------

    @staticmethod
    def _record_success(record: Any) -> bool | None:
        """Best-effort success value; None when indeterminate."""
        if hasattr(record, "success"):
            try:
                return bool(record.success)
            except Exception:
                return None
        if hasattr(record, "status"):
            try:
                return getattr(record, "status").name == "COMPLETED"
            except Exception:
                return None
        return None

    @staticmethod
    def _verification_pass_rate(record: Any) -> float:
        """Best-effort verification pass rate; 0.0 when unavailable."""
        if hasattr(record, "metadata"):
            try:
                meta = record.metadata
                if isinstance(meta, dict):
                    verdict = meta.get("verification_verdict")
                    if verdict == "PASSED":
                        return 1.0
                    if verdict == "FAILED":
                        return 0.0
            except Exception:
                return 0.0
        return 0.0

    @staticmethod
    def _record_step_count(record: Any) -> int:
        """Best-effort step count; 1 when a trace-like record has steps."""
        if hasattr(record, "steps"):
            try:
                return max(0, len(record.steps))
            except Exception:
                return 0
        return 0

    @staticmethod
    def _record_strategy(record: Any) -> ReasoningStrategy:
        """Best-effort strategy label; DECOMPOSE is the fallback."""
        if hasattr(record, "strategy"):
            try:
                strategy = record.strategy
                if isinstance(strategy, ReasoningStrategy):
                    return strategy
                if isinstance(strategy, str):
                    return ReasoningStrategy[strategy.upper()]
            except Exception:
                pass
        return ReasoningStrategy.DECOMPOSE

    @staticmethod
    def _default_assessment_id() -> str:
        """Timestamped assessment id."""
        return f"{META_ASSESSMENT_ID_PREFIX}:{datetime.now().isoformat()}"
