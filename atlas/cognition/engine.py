"""
Atlas Cognition Engine

Core reasoning coordinator.
"""

from atlas.cognition.context import CognitionContext
from atlas.cognition.decision import CognitionDecision


class CognitionEngine:
    """Processes context and creates decisions."""

    def process(
        self,
        context: CognitionContext,
    ) -> CognitionDecision:
        """Analyze context."""

        if not context.user_input:
            return CognitionDecision(
                action="idle",
                reasoning="No input provided.",
            )

        return CognitionDecision(
            action="respond",
            reasoning="User input requires response.",
            data={
                "input": context.user_input,
            },
        )