"""
Atlas Memory Manager

Public interface for Atlas memory.
"""

from atlas.memory.storage import Storage


class MemoryManager:
    """Manages Atlas memory."""

    @staticmethod
    def initialize():
        """Initialize Atlas memory."""

        return Storage.load()

    @staticmethod
    def get_memory():
        """Return all memory."""

        return Storage.load()

    @staticmethod
    def save_memory(data):
        """Save all memory."""

        Storage.save(data)

    @staticmethod
    def get_section(section):
        """Return one memory section."""

        memory = Storage.load()
        return memory.get(section, {})

    @staticmethod
    def update_section(section, data):
        """Update one memory section."""

        memory = Storage.load()
        memory[section] = data
        Storage.save(memory)

    @staticmethod
    def reset():
        """Reset Atlas memory."""

        Storage.save(Storage.DEFAULT_MEMORY)