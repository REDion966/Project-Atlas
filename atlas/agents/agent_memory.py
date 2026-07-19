"""
Atlas Agent Memory Interface

Connects agents with Atlas memory systems.
"""

from __future__ import annotations


class AgentMemory:
    """
    Agent memory access layer.

    Actual memory backend integration
    will be added later.
    """

    def __init__(self):

        self._context: list[dict] = []


    def remember(
        self,
        item: dict,
    ) -> None:
        """
        Store temporary memory reference.
        """

        self._context.append(
            item
        )


    def recall(self) -> list[dict]:
        """
        Retrieve memory context.
        """

        return list(
            self._context
        )


    def clear(self) -> None:
        """
        Clear temporary context.
        """

        self._context.clear()