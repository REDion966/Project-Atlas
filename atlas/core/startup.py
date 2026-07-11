"""
Atlas Startup Module

Responsible for starting Atlas.
"""

from atlas.config.settings import Settings
from atlas.utils.logger import Logger
from atlas.core.boot_manager import BootManager
from atlas.core.boot_screen import BootScreen


def start():
    """Start Atlas."""

    # Display the Atlas boot screen
    BootScreen.show()

    # Execute the Atlas boot sequence
    if BootManager.boot():
        Logger.info(Settings.WELCOME_MESSAGE)

    print()