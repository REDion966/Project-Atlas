"""
Atlas Reflection Engine

Pure logic component that analyzes recorded reasoning outcomes and produces
actionable suggestions. This is analysis only — no autonomous learning,
strategy modification, or AI provider calls.

Phase 6.7 — Reflection Foundation.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.reasoning.outcomes import ReasoningOutcome


@dataclass
class ReflectionSuggestion:
    """
    A single suggestion produced by analyzing reasoning outcomes.

    Attributes:
        pattern: The detected pattern category (e.g. "frequent_failures").
        description: Human-readable explanation of the finding.
        suggestion: Actionable suggestion based on the analysis.
        confidence: Confidence score between 0.0 and 1.0.
        target_area: The area the suggestion applies to
            (e.g. "capability_selection", "handler_choice").
        timestamp: When the suggestion was generated.
        affected_outcomes_count: How many outcomes contributed to this
            suggestion.
    """

    pattern: str
    description: str
    suggestion: str
    confidence: float
    target_area: str
    timestamp: datetime
    affected_outcomes_count: int = 0


class ReflectionEngine:
    """
    Analyzes reasoning outcomes to produce structured suggestions.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge, or
    interact with the EventBus.

    Initial analysis patterns:
        - Frequent failures: detects capabilities with high failure rates.
        - Repeated routing patterns: detects overused or underused routes.
        - Capability usage imbalance: detects uneven capability selection.
    """

    def analyze(
        self,
        outcomes: list[ReasoningOutcome],
    ) -> list[ReflectionSuggestion]:
        """
        Analyze a list of reasoning outcomes and produce suggestions.

        Args:
            outcomes: A list of ReasoningOutcome instances to analyze.
                May be empty.

        Returns:
            A list of ReflectionSuggestion instances. Returns an empty
            list when no outcomes are provided or no patterns are
            detected.
        """
        if not outcomes:
            return []

        suggestions: list[ReflectionSuggestion] = []

        failure_suggestion = self._detect_frequent_failures(outcomes)
        if failure_suggestion is not None:
            suggestions.append(failure_suggestion)

        routing_suggestion = self._detect_repeated_routing(outcomes)
        if routing_suggestion is not None:
            suggestions.append(routing_suggestion)

        imbalance_suggestion = self._detect_capability_imbalance(outcomes)
        if imbalance_suggestion is not None:
            suggestions.append(imbalance_suggestion)

        return suggestions

    def _detect_frequent_failures(
        self,
        outcomes: list[ReasoningOutcome],
    ) -> ReflectionSuggestion | None:
        """
        Detect capabilities with high failure rates.

        A capability is flagged if it has at least 3 recorded uses and
        a failure rate >= 50%.

        Returns:
            A ReflectionSuggestion if a frequent failure pattern is
            detected, or None otherwise.
        """
        capability_results: dict[str, list[bool]] = {}

        for outcome in outcomes:
            for result in outcome.results:
                cap_name = result.get("capability", "unknown")
                success = result.get("success", False)
                if cap_name not in capability_results:
                    capability_results[cap_name] = []
                capability_results[cap_name].append(success)

        failing_capabilities: list[tuple[str, float, int]] = []
        for cap_name, successes in capability_results.items():
            total = len(successes)
            if total < 3:
                continue
            failures = sum(1 for s in successes if not s)
            failure_rate = failures / total
            if failure_rate >= 0.5:
                failing_capabilities.append((cap_name, failure_rate, total))

        if not failing_capabilities:
            return None

        worst = max(failing_capabilities, key=lambda x: x[1])
        cap_name, failure_rate, total = worst
        affected = sum(
            1
            for outcome in outcomes
            for result in outcome.results
            if result.get("capability") == cap_name and not result.get("success", False)
        )

        return ReflectionSuggestion(
            pattern="frequent_failures",
            description=(
                f"Capability '{cap_name}' has a {failure_rate:.0%} failure rate "
                f"across {total} uses ({affected} failures)."
            ),
            suggestion=(
                f"Review handler for capability '{cap_name}'. "
                f"Consider updating the handler implementation or "
                f"adjusting routing criteria to reduce failures."
            ),
            confidence=min(failure_rate, 1.0),
            target_area="capability_selection",
            timestamp=datetime.now(),
            affected_outcomes_count=affected,
        )

    def _detect_repeated_routing(
        self,
        outcomes: list[ReasoningOutcome],
    ) -> ReflectionSuggestion | None:
        """
        Detect routing patterns that are overused or underused.

        A route is flagged if it appears in more than 80% of outcomes
        (overused) or in less than 10% of outcomes (underused), provided
        there are at least 5 outcomes to analyze.

        Returns:
            A ReflectionSuggestion if a repeated routing pattern is
            detected, or None otherwise.
        """
        if len(outcomes) < 5:
            return None

        route_counts: Counter[str] = Counter()
        for outcome in outcomes:
            seen_routes: set[str] = set()
            for route in outcome.routes:
                route_key = route.get("handler_name", route.get("capability", "unknown"))
                if route_key not in seen_routes:
                    route_counts[route_key] += 1
                    seen_routes.add(route_key)

        total_outcomes = len(outcomes)
        threshold_high = int(total_outcomes * 0.8)
        threshold_low = max(1, int(total_outcomes * 0.1))

        overused = [
            (route, count)
            for route, count in route_counts.items()
            if count >= threshold_high
        ]
        underused = [
            (route, count)
            for route, count in route_counts.items()
            if count <= threshold_low
        ]

        if not overused and not underused:
            return None

        if overused:
            route_name, count = max(overused, key=lambda x: x[1])
            usage_pct = count / total_outcomes
            return ReflectionSuggestion(
                pattern="repeated_routing",
                description=(
                    f"Route '{route_name}' is used in {count}/{total_outcomes} "
                    f"outcomes ({usage_pct:.0%}). This may indicate over-reliance "
                    f"on a single routing path."
                ),
                suggestion=(
                    f"Consider whether route '{route_name}' is being selected "
                    f"appropriately or if alternative routes should be explored "
                    f"for better outcome diversity."
                ),
                confidence=min(usage_pct, 1.0),
                target_area="handler_choice",
                timestamp=datetime.now(),
                affected_outcomes_count=count,
            )

        if underused:
            route_name, count = min(underused, key=lambda x: x[1])
            usage_pct = count / total_outcomes
            return ReflectionSuggestion(
                pattern="repeated_routing",
                description=(
                    f"Route '{route_name}' is used in only {count}/{total_outcomes} "
                    f"outcomes ({usage_pct:.0%}). This route may be underutilized."
                ),
                suggestion=(
                    f"Review whether route '{route_name}' should be considered "
                    f"more often, or if it can be deprecated."
                ),
                confidence=1.0 - min(usage_pct, 1.0),
                target_area="handler_choice",
                timestamp=datetime.now(),
                affected_outcomes_count=count,
            )

        return None

    def _detect_capability_imbalance(
        self,
        outcomes: list[ReasoningOutcome],
    ) -> ReflectionSuggestion | None:
        """
        Detect uneven capability usage across outcomes.

        A capability is flagged if it appears in more than 80% of
        outcomes (dominant) or in less than 10% of outcomes (rare),
        provided there are at least 5 outcomes to analyze.

        Returns:
            A ReflectionSuggestion if an imbalance is detected, or None
            otherwise.
        """
        if len(outcomes) < 5:
            return None

        capability_counts: Counter[str] = Counter()
        for outcome in outcomes:
            seen_caps: set[str] = set()
            for cap in outcome.capabilities:
                cap_name = cap.get("name", "unknown")
                if cap_name not in seen_caps:
                    capability_counts[cap_name] += 1
                    seen_caps.add(cap_name)

        total_outcomes = len(outcomes)
        threshold_high = int(total_outcomes * 0.8)
        threshold_low = max(1, int(total_outcomes * 0.1))

        dominant = [
            (cap, count)
            for cap, count in capability_counts.items()
            if count >= threshold_high
        ]
        rare = [
            (cap, count)
            for cap, count in capability_counts.items()
            if count <= threshold_low
        ]

        if not dominant and not rare:
            return None

        if dominant:
            cap_name, count = max(dominant, key=lambda x: x[1])
            usage_pct = count / total_outcomes
            return ReflectionSuggestion(
                pattern="capability_imbalance",
                description=(
                    f"Capability '{cap_name}' is selected in {count}/{total_outcomes} "
                    f"outcomes ({usage_pct:.0%}). This capability dominates the "
                    f"selection landscape."
                ),
                suggestion=(
                    f"Review whether capability '{cap_name}' is being selected "
                    f"correctly, or if the analyzer should consider alternative "
                    f"capabilities more frequently."
                ),
                confidence=min(usage_pct, 1.0),
                target_area="capability_selection",
                timestamp=datetime.now(),
                affected_outcomes_count=count,
            )

        if rare:
            cap_name, count = min(rare, key=lambda x: x[1])
            usage_pct = count / total_outcomes
            return ReflectionSuggestion(
                pattern="capability_imbalance",
                description=(
                    f"Capability '{cap_name}' is selected in only {count}/{total_outcomes} "
                    f"outcomes ({usage_pct:.0%}). This capability may be underutilized."
                ),
                suggestion=(
                    f"Review whether capability '{cap_name}' should be considered "
                    f"more often, or if it can be removed from the registry."
                ),
                confidence=1.0 - min(usage_pct, 1.0),
                target_area="capability_selection",
                timestamp=datetime.now(),
                affected_outcomes_count=count,
            )

        return None