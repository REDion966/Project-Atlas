"""
Atlas Cognition Decision

Represents the result of Atlas thinking.
"""


class CognitionDecision:
    """Decision produced by cognition engine."""

    def __init__(
        self,
        action: str,
        reasoning: str = "",
        data=None,
    ):
        self.action = action
        self.reasoning = reasoning
        self.data = data or {}

    def __repr__(self):
        return (
            f"CognitionDecision("
            f"action='{self.action}', "
            f"reasoning='{self.reasoning}')"
        )