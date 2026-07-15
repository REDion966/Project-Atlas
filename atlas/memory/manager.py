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
        """Store a new memory."""
        self._repository.add(memory)

    def get_memory(self, memory_id: str) -> Memory | None:
        """Retrieve a memory by its ID."""
        return self._repository.get(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        return self._repository.delete(memory_id)

    def update_memory(self, memory: Memory) -> None:
        """Update an existing memory."""
        memory.touch()
        self._repository.add(memory)

    def list_memories(self) -> list[Memory]:
        """Return all stored memories."""

        data = self._repository.load()

        return [
            Memory.from_dict(item)
            for item in data.values()
        ]