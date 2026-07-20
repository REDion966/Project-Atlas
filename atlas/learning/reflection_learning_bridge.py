"""
Reflection → Learning Bridge
"""

from __future__ import annotations

from atlas.intelligence.reflection_result import ReflectionResult
from atlas.learning.learning_manager import LearningManager
from atlas.learning.learning_result import LearningResult


class ReflectionLearningBridge:
    """
    Converts reflections into learning.
    """

    def __init__(self):

        self.learning = LearningManager()

    def process(
        self,
        reflection: ReflectionResult,
    ) -> LearningResult:

        return self.learning.learn(
            reflection.feedback
        )