"""
Atlas Memory Repository

Provides high-level access to memory persistence.
"""

from atlas.memory.models.memory import Memory
from atlas.memory.storage.json_storage import Storage


class MemoryRepository:
    """Repository for Memory objects."""

    def __init__(self):
        self._storage = Storage()

    def load(self) -> dict:
        return self._storage.load()

    def save(self, data: dict):
        self._storage.save(data)

    def get(self, memory_id: str) -> Memory | None:
        data = self.load()

        if memory_id not in data:
            return None

        return Memory.from_dict(data[memory_id])

    def add(self, memory: Memory):
        data = self.load()

        data[memory.id] = memory.to_dict()

        self.save(data)

    def delete(self, memory_id: str) -> bool:
        data = self.load()

        if memory_id not in data:
            return False

        del data[memory_id]

        self.save(data)

        return True