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

        results = []

        for memory in self.list_memories():

            if (
                query in memory.title.lower()
                or query in memory.content.lower()
            ):
                results.append(memory)

        return results