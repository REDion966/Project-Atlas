"""
Atlas Startup Module

Responsible for starting Atlas.
"""

from atlas.config.settings import Settings
from atlas.utils.logger import Logger
from atlas.core.application import Application
from atlas.core.boot_screen import BootScreen


def start():
    """Start Atlas."""

    # Display the Atlas boot screen
    BootScreen.show()

    # Create Atlas application
    app = Application()

    # Run Atlas
    if app.run():
        Logger.info(Settings.WELCOME_MESSAGE)

    print()