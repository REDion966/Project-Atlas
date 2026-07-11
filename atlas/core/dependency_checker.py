"""
Atlas Dependency Checker

Verifies that the Atlas environment is healthy before startup.
"""

from pathlib import Path

from atlas.utils.logger import Logger
from atlas.core.error_handler import ErrorHandler


class DependencyChecker:
    """Checks required Atlas resources."""

    @staticmethod
    def run():
        """Run all dependency checks."""

        Logger.info("Running dependency checks...")

        required_paths = [
            "logs",
            "docs",
            "atlas",
        ]

        all_ok = True

        try:
            for path in required_paths:
                if Path(path).exists():
                    Logger.info(f"Found: {path}")
                else:
                    Logger.error(f"Missing: {path}")
                    all_ok = False

            if all_ok:
                Logger.info("Dependency check passed.")
            else:
                Logger.warning("Dependency check completed with issues.")

            return all_ok

        except Exception as error:
            ErrorHandler.handle(error, "Dependency Checker")
            return False