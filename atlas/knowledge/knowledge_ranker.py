"""
Atlas Knowledge Ranker
"""

from __future__ import annotations

from atlas.knowledge.knowledge_entry import KnowledgeEntry


class KnowledgeRanker:
    """
    Placeholder ranking system.
    """

    def rank(
        self,
        entries: list[KnowledgeEntry],
    ) -> list[KnowledgeEntry]:

        return entries