"""
Atlas Application

Main application controller responsible for
initializing and running Atlas.
"""

from atlas.core.boot_manager import BootManager
from atlas.kernel.atlas import Atlas
from atlas.runtime.runtime import AtlasRuntime


class Application:
    """
    Main Atlas application.
    """

    def __init__(self):

        # Main Atlas kernel
        self.kernel = Atlas()


        # Runtime environment
        self.runtime = AtlasRuntime(
            self.kernel.container,
            self.kernel.state,
            self.kernel.events,
        )


        # Startup manager
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

        if self.initialize():

            self.runtime.start()

            return True

        return False


    def shutdown(self):
        """
        Shutdown Atlas.
        """

        self.runtime.stop()

        self.kernel.shutdown()

        print(
            "Atlas shutdown requested."
        )