"""
Atlas Knowledge Manager
"""

from __future__ import annotations

from atlas.knowledge.knowledge_base import KnowledgeBase
from atlas.knowledge.knowledge_entry import KnowledgeEntry
from atlas.knowledge.knowledge_search import KnowledgeSearch
from atlas.knowledge.knowledge_ranker import KnowledgeRanker


class KnowledgeManager:
    """
    Coordinates Atlas knowledge.
    """

    def __init__(self):

        self.base = KnowledgeBase()

        self.search_engine = KnowledgeSearch(self.base)

        self.ranker = KnowledgeRanker()

    def remember(
        self,
        title: str,
        content: str,
        source: str,
    ) -> None:

        self.base.add(

            KnowledgeEntry(

                title=title,

                content=content,

                source=source,

            )

        )

    def query(
        self,
        text: str,
    ) -> list[KnowledgeEntry]:

        results = self.search_engine.search(text)

        return self.ranker.rank(results)