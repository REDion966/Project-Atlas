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

    def __init__(
        self,
        memory_service=None,
        knowledge_manager=None,
    ) -> None:

        self.intelligence = IntelligenceManager()

        self.learning = LearningManager()

        self.feedback = KnowledgeFeedback()

        self.memory_service = memory_service

        self.knowledge_manager = knowledge_manager


    def process(
        self,
        goal: str,
    ) -> ThinkingCycle:

        thinking = self.intelligence.process(
            goal
        )

        learning = self.learning.learn(
            thinking.reflection
        )

        self.feedback.remember(
            learning.knowledge
        )

        if self.knowledge_manager:

            self.knowledge_manager.remember(
                title=goal,
                content=learning.knowledge,
                source="cognitive_loop",
            )


        return ThinkingCycle(
            goal=goal,
            conclusion=thinking.conclusion,
            action=thinking.action,
            lesson=learning.knowledge,
        )