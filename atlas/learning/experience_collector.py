"""
Atlas Experience Collector
"""

from __future__ import annotations

from atlas.learning.learning_record import LearningRecord


class ExperienceCollector:
    """
    Converts raw experience into a structured record.
    """

    def collect(
        self,
        experience: str,
    ) -> LearningRecord:

        return LearningRecord(
            experience=experience,
            lesson="Experience captured."
        )