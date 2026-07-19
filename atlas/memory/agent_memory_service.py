"""
Atlas Agent Memory Service

Connects agents with memory storage.
"""

from __future__ import annotations


class AgentMemoryService:
    """
    Memory layer for agents.
    """

    def __init__(self):

        self._memories: dict[str, list[dict]] = {}


    def remember(
        self,
        agent_id: str,
        memory: dict,
    ) -> None:
        """
        Store agent memory.
        """

        if agent_id not in self._memories:
            self._memories[agent_id] = []

        self._memories[agent_id].append(
            memory
        )


    def recall(
        self,
        agent_id: str,
    ) -> list[dict]:
        """
        Retrieve agent memories.
        """

        return self._memories.get(
            agent_id,
            []
        )


    def clear(
        self,
        agent_id: str,
    ) -> None:
        """
        Clear agent memory.
        """

        self._memories.pop(
            agent_id,
            None
        )