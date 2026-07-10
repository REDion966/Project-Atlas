"""
Atlas Startup Module

Responsible for starting Atlas and displaying
basic startup information.
"""

from atlas.config.settings import Settings
from atlas.utils.logger import Logger


def start():
    """Start Atlas."""

    print("=" * 40)
    print(Settings.PROJECT_NAME)
    print("=" * 40)

    print(f"Version: {Settings.VERSION}")
    print(f"Author: {Settings.AUTHOR}")
    print()

    Logger.info(Settings.WELCOME_MESSAGE)
    print()