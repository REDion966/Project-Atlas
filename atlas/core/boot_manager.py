"""
Atlas Boot Manager

Coordinates the Atlas startup sequence.
"""

from atlas.core.dependency_checker import DependencyChecker
from atlas.utils.logger import Logger


class BootManager:
    """Controls the Atlas startup process."""

    @staticmethod
    def boot():
        """Execute the Atlas boot sequence."""

        Logger.info("Boot sequence started.")

        if not DependencyChecker.run():
            Logger.error("Boot aborted.")
            return False

        Logger.info("Boot sequence completed.")
        return True