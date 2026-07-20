"""
Atlas Intelligence Manager
"""

from __future__ import annotations

from atlas.intelligence.thinking_pipeline import ThinkingPipeline
from atlas.intelligence.thinking_result import ThinkingResult


class IntelligenceManager:
    """
    Central intelligence entry point.
    """

    def __init__(self):

        self.pipeline = ThinkingPipeline()

    def process(
        self,
        goal: str,
    ) -> ThinkingResult:

        return self.pipeline.think(goal)