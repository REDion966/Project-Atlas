"""
Atlas Reasoning Engine
"""

from __future__ import annotations

from atlas.intelligence.reasoning_context import ReasoningContext
from atlas.intelligence.reasoning_result import ReasoningResult
from atlas.intelligence.reasoning_strategy import ReasoningStrategy


class ReasoningEngine:
    """
    Produces reasoning before planning.
    """

    def reason(
        self,
        context: ReasoningContext,
        strategy: ReasoningStrategy = ReasoningStrategy.DIRECT,
    ) -> ReasoningResult:

        conclusion = (
            f"Goal '{context.goal}' "
            f"evaluated using "
            f"{strategy.value} reasoning."
        )

        return ReasoningResult(
            success=True,
            conclusion=conclusion,
            confidence=1.0,
        )