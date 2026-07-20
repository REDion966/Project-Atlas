"""
Atlas Decision Engine
"""

from __future__ import annotations

from atlas.intelligence.reasoning_result import ReasoningResult
from atlas.intelligence.decision_result import DecisionResult


class DecisionEngine:
    """
    Converts reasoning into actions.
    """

    def decide(
        self,
        reasoning: ReasoningResult,
    ) -> DecisionResult:

        return DecisionResult(
            action="continue",
            confidence=reasoning.confidence,
        )