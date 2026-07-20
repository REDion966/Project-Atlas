"""
Atlas Knowledge Index
"""

from __future__ import annotations

from atlas.knowledge.knowledge_base import KnowledgeBase


class KnowledgeIndex:
    """
    Lightweight knowledge indexing.
    """

    def __init__(
        self,
        base: KnowledgeBase,
    ):

        self.base = base

    def size(self) -> int:

        return len(self.base.all())