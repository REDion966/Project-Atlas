"""
Atlas Knowledge Store
"""

from __future__ import annotations


class KnowledgeStore:
    """
    Stores learned knowledge in memory.
    """

    def __init__(self):

        self._knowledge: list[str] = []

    def add(
        self,
        knowledge: str,
    ) -> None:

        self._knowledge.append(knowledge)

    def all(self) -> list[str]:

        return list(self._knowledge)