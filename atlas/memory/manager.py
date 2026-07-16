"""
Atlas Memory Manager

Provides high-level business logic for working with memory.
"""

from atlas.memory.models.memory import Memory
from atlas.memory.repository import MemoryRepository


class MemoryManager:
    """Coordinates Atlas memory operations."""

    def __init__(self):
        self._repository = MemoryRepository()

    def add_memory(self, memory: Memory) -> None:
        self._repository.add(memory)

    def get_memory(self, memory_id: str) -> Memory | None:
        return self._repository.get(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        return self._repository.delete(memory_id)

    def update_memory(self, memory: Memory) -> None:
        memory.touch()
        self._repository.add(memory)

    def list_memories(self) -> list[Memory]:
        data = self._repository.load()

        return [
            Memory.from_dict(item)
            for item in data.values()
        ]

    def search(self, query: str) -> list[Memory]:
        """
        Search memories by title or content.
        """

        query = query.lower()

        return [
            memory
            for memory in self.list_memories()
            if (
                query in memory.title.lower()
                or query in memory.content.lower()
            )
        ]

    def filter_by_tag(self, tag: str) -> list[Memory]:
        """
        Return all memories containing the given tag.
        """

        tag = tag.lower()

        return [
            memory
            for memory in self.list_memories()
            if any(
                existing.lower() == tag
                for existing in memory.tags
            )
        ]

    def filter_by_importance(
        self,
        minimum_importance: int,
    ) -> list[Memory]:
        """
        Return memories whose importance is
        greater than or equal to the given value.
        """

        return [
            memory
            for memory in self.list_memories()
            if memory.importance >= minimum_importance
        ]

    def sort_by_newest(self) -> list[Memory]:
        """
        Return memories sorted by newest first.
        """

        return sorted(
            self.list_memories(),
            key=lambda memory: memory.created_at,
            reverse=True,
        )

    def sort_by_oldest(self) -> list[Memory]:
        """
        Return memories sorted by oldest first.
        """

        return sorted(
            self.list_memories(),
            key=lambda memory: memory.created_at,
        )

    def sort_by_importance(self) -> list[Memory]:
        """
        Return memories sorted by highest importance.
        """

        return sorted(
            self.list_memories(),
            key=lambda memory: memory.importance,
            reverse=True,
        )