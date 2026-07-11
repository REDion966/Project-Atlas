"""
Atlas Memory Storage

Handles reading and writing Atlas memory data.
"""

import json
from pathlib import Path

from atlas.memory.constants import MemorySections


class Storage:
    """Handles persistent memory storage."""

    MEMORY_FILE = Path("memory.json")

    DEFAULT_MEMORY = {
        MemorySections.IDENTITY: {},
        MemorySections.USERS: {},
        MemorySections.PROJECTS: {},
        MemorySections.KNOWLEDGE: {},
        MemorySections.SETTINGS: {},
        MemorySections.SYSTEM: {},
    }

    @staticmethod
    def load():
        """Load memory from disk."""

        if not Storage.MEMORY_FILE.exists():
            Storage.save(Storage.DEFAULT_MEMORY)

        with open(Storage.MEMORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def save(data):
        """Save memory to disk."""

        with open(Storage.MEMORY_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)