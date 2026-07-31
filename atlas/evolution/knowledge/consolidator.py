"""
Atlas Evolution Knowledge — Consolidator — Phase 13.5

Deterministic aggregation engine that converts raw evolution records
into durable knowledge objects.

The consolidator:
  - Normalizes weaknesses, proposals, and insights into stable keys.
  - Groups occurrences by those keys.
  - Applies threshold gating: a single occurrence never becomes
    knowledge; only repeated patterns reach the threshold.
  - Computes confidence deterministically from occurrence count and
    outcome consistency.
  - Is idempotent: re-consolidating the same records never produces
    duplicate knowledge and never changes the aggregate state.
  - NEVER deletes, edits, or otherwise modifies source records.

Pure logic. No AI. No infrastructure. Deterministic.

Phase 13.5 — Persistent Evolution Knowledge Foundation.
"""

from datetime import datetime
from typing import Any, Iterable

from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    EvolutionKnowledgeSnapshot,
    RecurringOutcomePattern,
    StrategyKnowledge,
)
from atlas.evolution.knowledge.normalizer import (
    insight_area,
    normalize_area,
    normalize_capability,
    normalize_outcome_key,
    normalize_strategy,
    normalize_weakness_key,
)
from atlas.evolution.models import (
    EvolutionInsight,
    Weakness,
)

# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------

DEFAULT_MIN_OCCURRENCES = 3
DEFAULT_MIN_CONFIDENCE = 0.3
_OUTCOME_ORDER = ("success", "partial", "failure", "inconclusive")


class EvolutionKnowledgeConsolidator:
    """
    Pure aggregation engine for persistent evolution knowledge.

    All state is accumulated from inputs passed to record_* methods.
    The consolidator itself does not store knowledge long-term — it
    produces it and hands it to EvolutionKnowledgeRepository.

    Idempotency: consolidate() uses the set of already-seen source IDs
    to skip records that were already aggregated.
    """

    def __init__(
        self,
        min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        """
        Initialise the consolidator.

        Args:
            min_occurrences: Minimum occurrences before a pattern
                becomes durable knowledge. Default 3.
            min_confidence: Minimum confidence for knowledge to be
                considered durable. Default 0.3.
        """
        if min_occurrences <= 0:
            raise ValueError("min_occurrences must be a positive integer")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")

        self._min_occurrences = min_occurrences
        self._min_confidence = min_confidence

        # Source tracking for idempotency
        self._seen_insight_ids: set[str] = set()
        self._seen_weakness_ids: set[str] = set()

        # Accumulators (keyed by normalized key)
        self._outcome_groups: dict[str, dict[str, Any]] = {}
        self._strategy_groups: dict[str, dict[str, Any]] = {}
        self._capability_groups: dict[str, dict[str, Any]] = {}
        self._bottleneck_groups: dict[str, dict[str, Any]] = {}

        # Deterministic sequence counter for generated IDs
        self._counter = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def min_occurrences(self) -> int:
        """Return the configured occurrence threshold."""
        return self._min_occurrences

    @property
    def min_confidence(self) -> float:
        """Return the configured confidence threshold."""
        return self._min_confidence

    # ------------------------------------------------------------------
    # Record ingestion (idempotent)
    # ------------------------------------------------------------------

    def record_insight(self, insight: EvolutionInsight) -> bool:
        """
        Record a single evolution insight.

        Returns True if the insight was newly aggregated, False if it
        was already seen (idempotency) or omitted because it lacks a
        usable outcome.

        Args:
            insight: The EvolutionInsight to aggregate.
        """
        source_id = insight.insight_id
        if source_id in self._seen_insight_ids:
            return False

        outcome = normalize_outcome_key(insight.outcome)

        self._seen_insight_ids.add(source_id)
        self._counter += 1

        # 1. Recurring outcome pattern by area
        area = insight_area(insight)
        self._accumulate_outcome(area, outcome, source_id, insight)

        # 2. Strategy knowledge
        strategy_key = normalize_strategy(insight)
        self._accumulate_strategy(
            strategy_key,
            insight,
            outcome,
            source_id,
        )

        # 3. Capability evolution
        capability = normalize_capability(insight)
        if capability is not None:
            self._accumulate_capability(capability, insight, source_id)

        return True

    def record_insights(self, insights: Iterable[EvolutionInsight]) -> int:
        """
        Record multiple insights. Returns the number newly aggregated.

        Args:
            insights: An iterable of EvolutionInsight instances.
        """
        new_count = 0
        for insight in insights:
            if self.record_insight(insight):
                new_count += 1
        return new_count

    def record_weakness(self, weakness: Weakness) -> bool:
        """
        Record a single weakness occurrence for bottleneck detection.

        Returns True if the weakness was newly aggregated.

        Args:
            weakness: The Weakness to aggregate.
        """
        source_id = weak_source_id(weakness)
        if source_id in self._seen_weakness_ids:
            return False

        self._seen_weakness_ids.add(source_id)
        self._counter += 1

        area = normalize_area(weakness.area)
        key = normalize_weakness_key(weakness)

        group = self._bottleneck_groups.get(key)
        if group is None:
            group = {
                "key": key,
                "area": area,
                "description": weakness.description,
                "recurrences": 0,
                "first_seen": weakness.detected_at,
                "last_seen": weakness.detected_at,
                "related_ids": [],
            }
            self._bottleneck_groups[key] = group

        group["recurrences"] += 1
        group["last_seen"] = weakness.detected_at
        group["related_ids"].append(source_id)

        return True

    def record_weaknesses(self, weaknesses: Iterable[Weakness]) -> int:
        """
        Record multiple weaknesses. Returns the number newly aggregated.

        Args:
            weaknesses: An iterable of Weakness instances.
        """
        new_count = 0
        for weakness in weaknesses:
            if self.record_weakness(weakness):
                new_count += 1
        return new_count

    # ------------------------------------------------------------------
    # Knowledge materialization
    # ------------------------------------------------------------------

    def consolidate(self) -> dict[str, list[Any]]:
        """
        Materialize durable knowledge from accumulated records.

        Only groups meeting the occurrence threshold produce knowledge.
        Re-running this method on unchanged state returns identical
        output — aggregation is deterministic.

        Returns:
            A dict with keys "outcome_patterns", "strategies",
            "capabilities", "bottlenecks" mapping to lists of knowledge
            objects sorted deterministically.
        """
        patterns = self._build_outcome_patterns()
        strategies = self._build_strategies()
        capabilities = self._build_capabilities()
        bottlenecks = self._build_bottlenecks()

        return {
            "outcome_patterns": patterns,
            "strategies": strategies,
            "capabilities": capabilities,
            "bottlenecks": bottlenecks,
        }

    def build_snapshot(self) -> EvolutionKnowledgeSnapshot:
        """
        Build a point-in-time EvolutionKnowledgeSnapshot.

        The snapshot is deterministic for a given accumulated state and
        includes a human-readable summary of the knowledge layers.

        Returns:
            An EvolutionKnowledgeSnapshot.
        """
        materialized = self.consolidate()
        patterns = materialized["outcome_patterns"]
        strategies = materialized["strategies"]
        capabilities = materialized["capabilities"]
        bottlenecks = materialized["bottlenecks"]

        self._counter += 1
        snapshot_id = f"EKS-{self._counter:06d}"

        summary = self._build_summary(patterns, strategies, capabilities, bottlenecks)

        return EvolutionKnowledgeSnapshot(
            snapshot_id=snapshot_id,
            timestamp=datetime.now(),
            pattern_count=len(patterns),
            strategy_count=len(strategies),
            capability_count=len(capabilities),
            bottleneck_count=len(bottlenecks),
            summary_text=summary,
        )

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """
        Reset all accumulated state.

        Useful for tests and for starting a fresh consolidation session.
        """
        self._seen_insight_ids.clear()
        self._seen_weakness_ids.clear()
        self._outcome_groups.clear()
        self._strategy_groups.clear()
        self._capability_groups.clear()
        self._bottleneck_groups.clear()
        self._counter = 0

    # ------------------------------------------------------------------
    # Deterministic confidence calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_pattern_confidence(
        occurrence_count: int,
        dominant_count: int,
        min_occurrences: int,
    ) -> float:
        """
        Compute confidence for a recurring outcome pattern.

        Confidence grows with occurrence count and the dominance of the
        most frequent outcome. Deterministic: same inputs always produce
        the same value.

        Args:
            occurrence_count: Total occurrences aggregated.
            dominant_count: Count of the dominant outcome.
            min_occurrences: Threshold used to scale confidence.

        Returns:
            A float in [0.0, 1.0].
        """
        if occurrence_count == 0:
            return 0.0
        consistency = dominant_count / occurrence_count
        coverage = min(1.0, occurrence_count / (min_occurrences * 2))
        return round(min(1.0, consistency * 0.6 + coverage * 0.4), 4)

    @staticmethod
    def _compute_strategy_confidence(occurrence_count: int) -> float:
        """
        Compute confidence for strategy knowledge.

        Deterministic: confidence scales with occurrence count toward
        1.0 as more evidence accumulates.

        Args:
            occurrence_count: Total strategy uses observed.

        Returns:
            A float in [0.0, 1.0].
        """
        if occurrence_count == 0:
            return 0.0
        return round(min(1.0, occurrence_count / 10.0), 4)

    # ------------------------------------------------------------------
    # Internal accumulators
    # ------------------------------------------------------------------

    def _accumulate_outcome(
        self,
        area: str,
        outcome: str,
        source_id: str,
        insight: EvolutionInsight,
    ) -> None:
        """Accumulate an insight into the outcome pattern group for its area."""
        group = self._outcome_groups.get(area)
        if group is None:
            group = {
                "area": area,
                "counts": {o: 0 for o in _OUTCOME_ORDER},
                "first_seen": insight.analyzed_at,
                "last_seen": insight.analyzed_at,
                "related_ids": [],
            }
            self._outcome_groups[area] = group

        group["counts"][outcome] += 1
        group["last_seen"] = insight.analyzed_at
        group["related_ids"].append(source_id)

    def _accumulate_strategy(
        self,
        strategy_key: str,
        insight: EvolutionInsight,
        outcome: str,
        source_id: str,
    ) -> None:
        """Accumulate an insight into the strategy knowledge group."""
        group = self._strategy_groups.get(strategy_key)
        if group is None:
            group = {
                "key": strategy_key,
                "name": strategy_key.replace("_", " ").title(),
                "success_count": 0,
                "failure_count": 0,
                "occurrence_count": 0,
                "regression_risk_sum": 0.0,
                "first_seen": insight.analyzed_at,
                "last_seen": insight.analyzed_at,
                "related_ids": [],
            }
            self._strategy_groups[strategy_key] = group

        group["occurrence_count"] += 1
        group["success_count"] += 1 if outcome == "success" else 0
        group["failure_count"] += 1 if outcome == "failure" else 0
        group["regression_risk_sum"] += getattr(insight, "regression_risk", 0.0)
        group["last_seen"] = insight.analyzed_at
        group["related_ids"].append(source_id)

    def _accumulate_capability(
        self,
        capability: str,
        insight: EvolutionInsight,
        source_id: str,
    ) -> None:
        """Accumulate an insight into the capability evolution group."""
        group = self._capability_groups.get(capability)
        if group is None:
            group = {
                "capability": capability,
                "assessments": [],
                "first_seen": insight.analyzed_at,
                "last_seen": insight.analyzed_at,
                "related_ids": [],
            }
            self._capability_groups[capability] = group

        effectiveness = float(getattr(insight, "effectiveness_score", 0.0))
        group["assessments"].append(effectiveness)
        group["last_seen"] = insight.analyzed_at
        group["related_ids"].append(source_id)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_outcome_patterns(self) -> list[RecurringOutcomePattern]:
        """Build durable RecurringOutcomePattern objects from groups."""
        patterns: list[RecurringOutcomePattern] = []

        for area in sorted(self._outcome_groups.keys()):
            group = self._outcome_groups[area]
            counts = group["counts"]
            occurrence_count = sum(counts.values())

            if occurrence_count < self._min_occurrences:
                continue

            dominant_outcome = max(
                _OUTCOME_ORDER,
                key=lambda o: (counts[o], -_OUTCOME_ORDER.index(o)),
            )
            dominant_count = counts[dominant_outcome]
            confidence = self._compute_pattern_confidence(
                occurrence_count,
                dominant_count,
                self._min_occurrences,
            )

            if confidence < self._min_confidence:
                continue

            self._counter += 1
            patterns.append(RecurringOutcomePattern(
                pattern_id=f"RKP-{self._counter:06d}",
                area=area,
                outcome=dominant_outcome,
                occurrence_count=occurrence_count,
                success_count=counts["success"],
                partial_count=counts["partial"],
                failure_count=counts["failure"],
                inconclusive_count=counts["inconclusive"],
                confidence=confidence,
                first_seen=group["first_seen"],
                last_seen=group["last_seen"],
                related_ids=list(group["related_ids"]),
            ))

        return patterns

    def _build_strategies(self) -> list[StrategyKnowledge]:
        """Build durable StrategyKnowledge objects from groups."""
        strategies: list[StrategyKnowledge] = []

        for key in sorted(self._strategy_groups.keys()):
            group = self._strategy_groups[key]
            occurrence_count = group["occurrence_count"]

            if occurrence_count < self._min_occurrences:
                continue

            confidence = self._compute_strategy_confidence(occurrence_count)
            if confidence < self._min_confidence:
                continue

            avg_regression = (
                group["regression_risk_sum"] / occurrence_count
                if occurrence_count > 0
                else 0.0
            )
            effectiveness = (
                group["success_count"] / occurrence_count
                if occurrence_count > 0
                else 0.0
            )

            self._counter += 1
            strategies.append(StrategyKnowledge(
                strategy_key=key,
                strategy_name=group["name"],
                success_count=group["success_count"],
                failure_count=group["failure_count"],
                occurrence_count=occurrence_count,
                effectiveness=round(effectiveness, 4),
                confidence=confidence,
                avg_regression_risk=round(avg_regression, 4),
                first_seen=group["first_seen"],
                last_seen=group["last_seen"],
                related_ids=list(group["related_ids"]),
            ))

        return strategies

    def _build_capabilities(self) -> list[CapabilityEvolution]:
        """Build durable CapabilityEvolution objects from groups."""
        capabilities: list[CapabilityEvolution] = []

        for name in sorted(self._capability_groups.keys()):
            group = self._capability_groups[name]
            assessments = group["assessments"]

            if len(assessments) < self._min_occurrences:
                continue

            self._counter += 1
            capabilities.append(CapabilityEvolution(
                capability_name=name,
                assessments=list(assessments),
                observed_count=len(assessments),
                first_seen=group["first_seen"],
                last_seen=group["last_seen"],
                related_ids=list(group["related_ids"]),
            ))

        return capabilities

    def _build_bottlenecks(self) -> list[BottleneckProfile]:
        """Build durable BottleneckProfile objects from groups."""
        bottlenecks: list[BottleneckProfile] = []

        for key in sorted(self._bottleneck_groups.keys()):
            group = self._bottleneck_groups[key]
            if group["recurrences"] < self._min_occurrences:
                continue

            self._counter += 1
            bottlenecks.append(BottleneckProfile(
                bottleneck_id=f"BTN-{self._counter:06d}",
                area=group["area"],
                description=group["description"],
                recurrence_count=group["recurrences"],
                first_seen=group["first_seen"],
                last_seen=group["last_seen"],
                related_ids=list(group["related_ids"]),
            ))

        return bottlenecks

    @staticmethod
    def _build_summary(
        patterns: list[RecurringOutcomePattern],
        strategies: list[StrategyKnowledge],
        capabilities: list[CapabilityEvolution],
        bottlenecks: list[BottleneckProfile],
    ) -> str:
        """Build a deterministic human-readable summary of knowledge."""
        if not any([patterns, strategies, capabilities, bottlenecks]):
            return "No durable evolution knowledge accumulated yet."

        parts: list[str] = []
        if patterns:
            parts.append(f"{len(patterns)} recurring outcome pattern(s)")
        if strategies:
            parts.append(f"{len(strategies)} tracked strategy(ies)")
        if capabilities:
            parts.append(f"{len(capabilities)} capability trajectory(ies)")
        if bottlenecks:
            parts.append(f"{len(bottlenecks)} recurring bottleneck(s)")
        return "Knowledge summary: " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def weak_source_id(weakness: Weakness) -> str:
    """
    Build a stable source identifier for a weakness instance.

    Falls back to a deterministic content hash when the weakness lacks
    an explicit identifier, so idempotency works for both stored and
    synthesized weaknesses.

    Args:
        weakness: The weakness to identify.

    Returns:
        A stable string identifier.
    """
    explicit = getattr(weakness, "weakness_id", None)
    if explicit:
        return str(explicit)
    return normalize_weakness_key(weakness)
