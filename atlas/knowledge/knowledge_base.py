"""
Atlas Knowledge Base
"""

from __future__ import annotations

from atlas.knowledge.knowledge_entry import KnowledgeEntry


class KnowledgeBase:
    """
    Stores Atlas knowledge.
    """

    def __init__(self):

        self._entries: list[KnowledgeEntry] = []

    def add(
        self,
        entry: KnowledgeEntry,
    ) -> None:

        self._entries.append(entry)

    def all(
        self,
    ) -> list[KnowledgeEntry]:

        return list(self._entries)