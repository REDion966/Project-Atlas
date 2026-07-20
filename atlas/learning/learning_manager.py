"""
Atlas Learning Manager
"""

from __future__ import annotations

from atlas.learning.experience_collector import ExperienceCollector
from atlas.learning.knowledge_extractor import KnowledgeExtractor
from atlas.learning.learning_result import LearningResult


class LearningManager:
    """
    Coordinates Atlas learning.
    """

    def __init__(self):

        self.collector = ExperienceCollector()

        self.extractor = KnowledgeExtractor()

    def learn(
        self,
        experience: str,
    ) -> LearningResult:

        record = self.collector.collect(experience)

        knowledge = self.extractor.extract(record)

        return LearningResult(
            success=True,
            knowledge=knowledge,
        )