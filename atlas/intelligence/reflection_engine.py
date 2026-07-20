"""
Atlas Reflection Engine
"""

from __future__ import annotations

from atlas.intelligence.decision_result import DecisionResult
from atlas.intelligence.reflection_result import ReflectionResult


class ReflectionEngine:
    """
    Evaluates previous decisions.
    """

    def reflect(
        self,
        decision: DecisionResult,
    ) -> ReflectionResult:

        return ReflectionResult(
            successful=True,
            feedback=(
                f"Decision '{decision.action}' completed successfully."
            ),
        )