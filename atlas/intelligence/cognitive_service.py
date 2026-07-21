"""
Atlas Cognitive Service

Public interface for Atlas cognitive operations.
"""

from __future__ import annotations

from atlas.intelligence.cognitive_loop import CognitiveLoop
from atlas.intelligence.thinking_cycle import ThinkingCycle


class CognitiveService:
    """
    Provides a stable API for Atlas cognition.
    """

    def __init__(
        self,
        cognitive_loop: CognitiveLoop,
    ) -> None:

        self._loop = cognitive_loop


    def process(
        self,
        goal: str,
    ) -> ThinkingCycle:
        """
        Process a cognitive goal.
        """

        return self._loop.process(
            goal
        )