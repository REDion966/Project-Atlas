"""
Knowledge Feedback
"""

from __future__ import annotations

from atlas.learning.knowledge_store import KnowledgeStore


class KnowledgeFeedback:

    def __init__(self):

        self.store = KnowledgeStore()

    def remember(
        self,
        knowledge: str,
    ) -> None:

        self.store.add(knowledge)