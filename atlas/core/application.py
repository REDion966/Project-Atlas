"""
Atlas Application

Main application controller.
"""

from atlas.core.boot_manager import BootManager
from atlas.kernel.atlas import Atlas
from atlas.runtime.runtime import AtlasRuntime


class Application:
    """
    Main Atlas application.
    """

    def __init__(self):

        self.kernel = Atlas()

        self.runtime = AtlasRuntime(
            kernel=self.kernel,
            state_manager=self.kernel.state,
            event_bus=self.kernel.events,
        )

        self.boot_manager = BootManager(
            self.kernel
        )

    def initialize(self):
        """
        Initialize Atlas.
        """

        return self.boot_manager.boot()

    def run(self):
        """
        Run Atlas.
        """

        if not self.initialize():
            return False

        self.runtime.run()

        return True

    def shutdown(self):
        """
        Shutdown Atlas.
        """

        self.runtime.stop()

        self.boot_manager.shutdown()