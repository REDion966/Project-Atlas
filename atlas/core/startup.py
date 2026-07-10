"""
Atlas Startup Module

Responsible for starting Atlas and displaying
basic startup information.
"""

from atlas.config.settings import Settings
from atlas.utils.logger import Logger
from atlas.core.dependency_checker import DependencyChecker


def start():
    """Start Atlas."""

    print("=" * 40)
    print(Settings.PROJECT_NAME)
    print("=" * 40)

    print(f"Version: {Settings.VERSION}")
    print(f"Author: {Settings.AUTHOR}")
    print()

    # Run Atlas health check
    DependencyChecker.run()

    # Startup message
    Logger.info(Settings.WELCOME_MESSAGE)
    print()