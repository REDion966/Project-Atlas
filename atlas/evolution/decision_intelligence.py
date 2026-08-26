"""
Atlas Evolution — Decision Intelligence Engine — Phase 14.2

Adaptive planning layer that consumes consolidated evolution knowledge
(from ``EvolutionKnowledgeQuery``) and produces a ``PlanningContext`` for
downstream planning decisions.

The engine is strictly read-only. It never writes to repositories, calls
the knowledge pipeline, performs consolidation, or touches storage. All
dependencies are injected via the constructor.

Phase 14.2 introduces the engine only. Phase 14.3 will wire it into the
scheduler and planner.
"""

from typing import Any

from atlas.evolution.decision_models import (
    AreaAdjustment,
    BottleneckAlert,
    CapabilitySignal,
    PlanningContext,
    StrategySuggestion,
)
from atlas.evolution.decision_scorer import (
    compute_area_adjustment,
    compute_bottleneck_alert,
    compute_capability_signal,
    compute_strategy_recommendation,
)
from atlas.evolution.knowledge.models import StrategyKnowledge
from atlas.evolution.knowledge.query import EvolutionKnowledgeQuery


# ---------------------------------------------------------------------------
# Tunable defaults (constants, not runtime configuration)
# ---------------------------------------------------------------------------

_DEFAULT_RANKING_BOTTLENECK_WEIGHT = 0.3
_DEFAULT_RANKING_CAPABILITY_WEIGHT = 0.1


class DecisionIntelligenceEngine:
    """
    Read-only adaptive planning intelligence.

    Queries the consolidated evolution knowledge layer and produces a
    ``PlanningContext`` enriched with historical evidence. Downstream
    components (planner, priority engine, proposal generator) can use
    this context to make historically-informed decisions without
    importing the knowledge layer themselves.

    The engine degrades gracefully: if ``EvolutionKnowledgeQuery`` is
    None or empty, it returns a neutral ``PlanningContext``.

    All methods are deterministic and side-effect free.
    """

    def __init__(
        self,
        knowledge_query: EvolutionKnowledgeQuery | None = None,
        repository_map_provider: Any = None,
        evolution_context_provider: Any = None,
    ) -> None:
        """
        Initialise the engine with read-only context surfaces.

        Args:
            knowledge_query: The EvolutionKnowledgeQuery to read from.
                If None, all queries return empty/neutral results.
            repository_map_provider: Optional zero-argument callable
                returning an already-built ``RepositoryMap`` (or None).
                Stage A1: the engine only CONSUMES already-built maps via
                this provider — it never triggers repository scanning.
            evolution_context_provider: Optional zero-argument callable
                returning a bounded, JSON-safe dictionary of evolution
                history evidence (Stage D — expected shape::

                    {"history": {...}, "development": {...}}

                ). The dictionary is merged verbatim into the planning
                context metadata. Fail-soft: provider exceptions yield an
                empty section. Advisory only — never changes permissions.
        """
        self._query = knowledge_query
        self._repository_map_provider = repository_map_provider
        self._evolution_context_provider = evolution_context_provider

    # ------------------------------------------------------------------
    # Core context production
    # ------------------------------------------------------------------

    def get_planning_context(
        self,
        weaknesses: list[Any] | None = None,
    ) -> PlanningContext:
        """
        Build a PlanningContext from historical evolution knowledge.

        The context includes per-area adjustments, recurring bottleneck
        alerts, strategy suggestions, and capability signals. If the
        knowledge query is unavailable, all values are neutral/empty.

        Args:
            weaknesses: Optional list of Weakness-like objects whose
                ``area`` attribute identifies the evolution areas to
                enrich. If omitted, all known areas are considered.

        Returns:
            A populated ``PlanningContext``.
        """
        if self._query is None:
            metadata: dict[str, Any] = {}
            repository_meta = self._build_repository_metadata()
            if repository_meta:
                metadata["repository"] = repository_meta
            evolution_meta = self._build_evolution_context()
            if evolution_meta:
                metadata.update(evolution_meta)
            if metadata:
                return PlanningContext(metadata=metadata)
            return PlanningContext()

        areas = self._collect_areas(weaknesses)

        area_adjustments = self._build_area_adjustments(areas)
        bottleneck_alerts = self._build_bottleneck_alerts(areas)
        strategy_suggestions = self._build_strategy_suggestions(areas)
        capability_signals = self._build_capability_signals()

        overall_confidence = self._compute_overall_confidence(
            area_adjustments,
            bottleneck_alerts,
            capability_signals,
        )

        metadata: dict[str, Any] = {}
        repository_meta = self._build_repository_metadata()
        if repository_meta:
            metadata["repository"] = repository_meta

        evolution_meta = self._build_evolution_context()
        if evolution_meta:
            metadata.update(evolution_meta)

        return PlanningContext(
            area_adjustments=area_adjustments,
            bottleneck_alerts=bottleneck_alerts,
            strategy_suggestions=strategy_suggestions,
            capability_signals=capability_signals,
            overall_confidence=overall_confidence,
            metadata=metadata,
        )

    def _build_evolution_context(self) -> dict[str, Any]:
        """Consume the kernel-supplied evolution history snapshot, fail-soft."""
        if self._evolution_context_provider is None:
            return {}
        try:
            context = self._evolution_context_provider()
        except Exception:
            return {}
        if not isinstance(context, dict) or not context:
            return {}
        return context

    def _build_repository_metadata(self) -> dict[str, Any]:
        """Consume the already-built repository map, fail-soft.

        Returns an empty dict when no provider is wired, the provider
        returns None, or the provider raises — never triggers scanning.
        """
        if self._repository_map_provider is None:
            return {}
        try:
            repository_map = self._repository_map_provider()
        except Exception:
            return {}
        if repository_map is None:
            return {}

        from atlas.research.repository_map import RepositoryMap

        if not isinstance(repository_map, RepositoryMap):
            return {}
        return {
            "module_count": repository_map.module_count(),
            "edge_count": repository_map.edge_count(),
            "truncated": repository_map.truncated,
            "error_count": len(repository_map.errors),
            "architecture_summary": {
                "packages": repository_map.metadata.get("packages", 0),
                "files_scanned": repository_map.metadata.get("files_scanned", 0),
            },
        }

    # ------------------------------------------------------------------
    # Candidate ranking
    # ------------------------------------------------------------------

    def rank_candidates(
        self,
        candidates: list[Any],
        context: PlanningContext | None = None,
    ) -> list[Any]:
        """
        Rank candidates using deterministic historical evidence.

        Each candidate should have an ``area`` attribute (str) and a
        ``priority_score`` attribute (float). The returned list is
        ordered by adjusted score descending.

        Scoring:
          adjusted = priority_score × area_adjustment
                     + bottleneck_boost × weight
                     + capability_signal × weight

        Weights are small so that historical evidence nudges rather than
        overrides the base priority.

        Args:
            candidates: List of candidate objects to rank.
            context: Optional PlanningContext. If None, a neutral context
                is built internally.

        Returns:
            The candidates sorted by adjusted score descending.
        """
        if context is None:
            context = PlanningContext()

        scored: list[tuple[float, Any]] = []
        for candidate in candidates:
            score = self._score_candidate(candidate, context)
            scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in scored]

    # ------------------------------------------------------------------
    # Strategy suggestions
    # ------------------------------------------------------------------

    def suggest_strategies(
        self,
        area: str,
        context: PlanningContext | None = None,
    ) -> list[StrategySuggestion]:
        """
        Return ranked strategy suggestions for an area.

        If a PlanningContext is provided, its cached suggestions are
        used. Otherwise the knowledge query is consulted directly.

        Args:
            area: The canonical evolution area.
            context: Optional PlanningContext with cached suggestions.

        Returns:
            A list of StrategySuggestion objects, ordered by
            effectiveness descending. Empty if no strategies are known.
        """
        if context is not None and area in context.strategy_suggestions:
            suggestions = list(context.strategy_suggestions[area])
            suggestions.sort(key=lambda s: s.effectiveness, reverse=True)
            return suggestions

        if self._query is None:
            return []

        strategies = self._get_strategies_for_area(area)
        suggestions = [
            compute_strategy_recommendation(strategy)
            for strategy in strategies
        ]
        suggestions.sort(key=lambda s: s.effectiveness, reverse=True)
        return suggestions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_areas(self, weaknesses: list[Any] | None) -> set[str]:
        """Collect canonical areas from weaknesses, or all known areas."""
        if weaknesses:
            areas: set[str] = set()
            for weakness in weaknesses:
                area = getattr(weakness, "area", None)
                if isinstance(area, str) and area:
                    areas.add(area)
            if areas:
                return areas

        if self._query is None:
            return set()

        # Fall back to all areas mentioned in patterns and bottlenecks.
        areas = {p.area for p in self._query.get_patterns_by_area("", n=-1)}
        areas.update(b.area for b in self._query.get_bottlenecks(n=-1))
        return areas

    def _build_area_adjustments(
        self,
        areas: set[str],
    ) -> dict[str, AreaAdjustment]:
        """Build per-area adjustments from recurring outcome patterns."""
        adjustments: dict[str, AreaAdjustment] = {}
        if self._query is None:
            return adjustments

        for area in areas:
            patterns = self._query.get_patterns_by_area(area, n=1)
            pattern = patterns[0] if patterns else None
            adjustment = compute_area_adjustment(pattern)
            adjustments[area] = adjustment

        return adjustments

    def _build_bottleneck_alerts(
        self,
        areas: set[str],
    ) -> list[BottleneckAlert]:
        """Build bottleneck alerts for the given areas."""
        if self._query is None:
            return []

        alerts: list[BottleneckAlert] = []
        seen: set[str] = set()

        for area in areas:
            for bottleneck in self._query.get_bottlenecks_by_area(area, n=-1):
                if bottleneck.bottleneck_id in seen:
                    continue
                seen.add(bottleneck.bottleneck_id)
                alerts.append(compute_bottleneck_alert(bottleneck))

        alerts.sort(key=lambda alert: alert.severity_boost, reverse=True)
        return alerts

    def _build_strategy_suggestions(
        self,
        areas: set[str],
    ) -> dict[str, list[StrategySuggestion]]:
        """Build per-area strategy suggestions from strategy knowledge."""
        suggestions: dict[str, list[StrategySuggestion]] = {}
        if self._query is None:
            return suggestions

        for area in areas:
            area_strategies = self._get_strategies_for_area(area)
            area_suggestions = [
                compute_strategy_recommendation(strategy)
                for strategy in area_strategies
            ]
            if area_suggestions:
                area_suggestions.sort(
                    key=lambda suggestion: suggestion.effectiveness,
                    reverse=True,
                )
                suggestions[area] = area_suggestions

        return suggestions

    def _get_strategies_for_area(self, area: str) -> list[StrategyKnowledge]:
        """Return strategies whose metadata identifies them with an area."""
        if self._query is None:
            return []

        strategies: list[StrategyKnowledge] = []
        for strategy in self._query.get_effective_strategies(n=-1):
            if strategy.metadata.get("area") == area:
                strategies.append(strategy)
        for strategy in self._query.get_ineffective_strategies(n=-1):
            if strategy.metadata.get("area") == area:
                strategies.append(strategy)

        # Deduplicate by key while preserving order.
        seen: set[str] = set()
        unique: list[StrategyKnowledge] = []
        for strategy in strategies:
            if strategy.strategy_key not in seen:
                seen.add(strategy.strategy_key)
                unique.append(strategy)
        return unique

    def _build_capability_signals(self) -> dict[str, CapabilitySignal]:
        """Build capability signals from all known capability evolutions."""
        signals: dict[str, CapabilitySignal] = {}
        if self._query is None:
            return signals

        for capability in self._query.get_capabilities(n=-1):
            signals[capability.capability_name] = compute_capability_signal(
                capability,
            )

        return signals

    def _compute_overall_confidence(
        self,
        area_adjustments: dict[str, AreaAdjustment],
        bottleneck_alerts: list[BottleneckAlert],
        capability_signals: dict[str, CapabilitySignal],
    ) -> float:
        """Compute an aggregate confidence score for the context."""
        scores: list[float] = []

        for adjustment in area_adjustments.values():
            if adjustment.occurrence_count > 0:
                scores.append(adjustment.pattern_confidence)

        for alert in bottleneck_alerts:
            # Higher recurrence → higher confidence, capped at 1.0.
            scores.append(min(1.0, alert.recurrence_count / 10.0))

        for signal in capability_signals.values():
            if signal.latest_assessment > 0.0:
                scores.append(1.0)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    def _score_candidate(
        self,
        candidate: Any,
        context: PlanningContext,
    ) -> float:
        """Compute a historical-evidence-adjusted score for a candidate."""
        base_score = float(getattr(candidate, "priority_score", 0.0))
        area = getattr(candidate, "area", "")

        adjustment = context.area_adjustments.get(area)
        adjustment_factor = adjustment.adjustment_factor if adjustment else 1.0

        bottleneck_boost = 0.0
        for alert in context.bottleneck_alerts:
            if alert.area == area:
                bottleneck_boost = max(bottleneck_boost, alert.severity_boost)

        capability_signal = 0.0
        signal = context.capability_signals.get(area)
        if signal is not None:
            if signal.signal == "intervene":
                capability_signal = 0.1
            elif signal.signal == "defer":
                capability_signal = -0.1

        adjusted = (
            base_score * adjustment_factor
            + bottleneck_boost * _DEFAULT_RANKING_BOTTLENECK_WEIGHT
            + capability_signal * _DEFAULT_RANKING_CAPABILITY_WEIGHT
        )

        return float(adjusted)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def knowledge_query(self) -> EvolutionKnowledgeQuery | None:
        """Return the injected knowledge query, or None."""
        return self._query
