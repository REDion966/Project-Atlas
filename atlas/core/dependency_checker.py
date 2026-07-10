"""
Atlas Dependency Checker

Verifies that the Atlas environment is healthy before startup.
"""

from pathlib import Path

from atlas.utils.logger import Logger


class DependencyChecker:
    """Checks required Atlas resources."""

    @staticmethod
    def run():
        Logger.info("Running dependency checks...")

        required_paths = [
            "logs",
            "docs",
            "atlas",
        ]

        all_ok = True

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