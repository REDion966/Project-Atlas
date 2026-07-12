"""
Atlas Boot Manager

Coordinates the Atlas startup sequence.
"""

from atlas.core.dependency_checker import DependencyChecker
from atlas.utils.logger import Logger
from atlas.services.registry import ServiceRegistry
from atlas.services.memory_service import MemoryService


class BootManager:
    """Controls the Atlas startup process."""

    @staticmethod
    def boot():
        """Execute the Atlas boot sequence."""

        Logger.info("Boot sequence started.")

        # Run dependency checks
        if not DependencyChecker.run():
            Logger.error("Boot aborted.")
            return False

        # Create the service registry
        registry = ServiceRegistry()

        # Register Atlas services
        registry.register(MemoryService())

        # Start all registered services
        registry.start_all()

        Logger.info("Boot sequence completed.")
        return True