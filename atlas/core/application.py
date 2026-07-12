"""
Atlas Application

Main application controller responsible for
initializing and running Atlas.
"""

from atlas.core.boot_manager import BootManager


class Application:
    """Main Atlas application."""

    def __init__(self):
        """Create the application."""
        self.boot_manager = BootManager()

    def initialize(self):
        """Initialize Atlas."""
        return self.boot_manager.boot()

    def run(self):
        """Run Atlas."""

        if self.initialize():
            return True

        return False

    def shutdown(self):
        """Shutdown Atlas."""
        print("Atlas shutdown requested.")