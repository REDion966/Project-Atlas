"""
Atlas Cognitive Loop
"""

from __future__ import annotations

from atlas.intelligence.intelligence_manager import IntelligenceManager
from atlas.learning.learning_manager import LearningManager
from atlas.learning.knowledge_feedback import KnowledgeFeedback
from atlas.intelligence.thinking_cycle import ThinkingCycle


class CognitiveLoop:
    """
    Connects thinking and learning into one lifecycle.
    """

    def __init__(self):

        self.intelligence = IntelligenceManager()

        self.learning = LearningManager()

        self.feedback = KnowledgeFeedback()

    def process(
        self,
        goal: str,
    ) -> ThinkingCycle:

        thinking = self.intelligence.process(goal)

        learning = self.learning.learn(
            thinking.reflection
        )

        self.feedback.remember(
            learning.knowledge
        )

        return ThinkingCycle(
            goal=goal,
            conclusion=thinking.conclusion,
            action=thinking.action,
            lesson=learning.knowledge,
        )