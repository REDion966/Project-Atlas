"""
Atlas Memory Service

Initializes the Atlas memory system.
"""

from atlas.memory.memory_manager import MemoryManager
from atlas.services.service import Service
from atlas.utils.logger import Logger


class MemoryService(Service):
    """Memory service."""

    def __init__(self):
        super().__init__("memory")

    def start(self):
        """Start the memory service."""

        MemoryManager.initialize()
        self.running = True

        Logger.info("Memory Service started.")