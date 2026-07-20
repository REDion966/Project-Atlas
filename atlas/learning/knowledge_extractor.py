"""
Atlas Knowledge Extractor
"""

from __future__ import annotations

from atlas.learning.learning_record import LearningRecord


class KnowledgeExtractor:
    """
    Extracts reusable knowledge from experiences.
    """

    def extract(
        self,
        record: LearningRecord,
    ) -> str:

        return record.lesson