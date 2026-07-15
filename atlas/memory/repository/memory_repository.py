"""
Atlas Memory Repository

Provides high-level access to memory persistence.
"""

from atlas.memory.models.memory import Memory
from atlas.memory.storage.json_storage import Storage


class MemoryRepository:
    """Repository for Memory objects."""

    MEMORY_KEY = "memories"

    def __init__(self):
        self._storage = Storage()

    def _load_data(self) -> dict:
        """Load the complete storage file."""
        return self._storage.load()

    def _save_data(self, data: dict) -> None:
        """Save the complete storage file."""
        self._storage.save(data)

    def _memory_section(self) -> dict:
        """Return the memories section."""

        data = self._load_data()

        if self.MEMORY_KEY not in data:
            data[self.MEMORY_KEY] = {}
            self._save_data(data)

        return data[self.MEMORY_KEY]

    def load(self) -> dict:
        """Return only the memories section."""
        return self._memory_section()

    def get(self, memory_id: str) -> Memory | None:
        memories = self._memory_section()

        data = memories.get(memory_id)

        if data is None:
            return None

        return Memory.from_dict(data)

    def add(self, memory: Memory) -> None:
        data = self._load_data()

        memories = data.setdefault(self.MEMORY_KEY, {})

        memories[memory.id] = memory.to_dict()

        self._save_data(data)

    def delete(self, memory_id: str) -> bool:
        data = self._load_data()

        memories = data.setdefault(self.MEMORY_KEY, {})

        if memory_id not in memories:
            return False

        del memories[memory_id]

        self._save_data(data)

        return True