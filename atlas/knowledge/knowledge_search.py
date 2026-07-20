"""
Atlas Knowledge Search
"""

from __future__ import annotations

from atlas.knowledge.knowledge_base import KnowledgeBase
from atlas.knowledge.knowledge_entry import KnowledgeEntry


class KnowledgeSearch:
    """
    Searches Atlas knowledge.
    """

    def __init__(
        self,
        base: KnowledgeBase,
    ):

        self.base = base

    def search(
        self,
        text: str,
    ) -> list[KnowledgeEntry]:

        results = []

        for entry in self.base.all():

            if text.lower() in entry.content.lower():

                results.append(entry)

        return results