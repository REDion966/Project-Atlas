"""
Atlas Kernel

The root application object.
"""

from atlas.kernel.service_container import ServiceContainer


class Atlas:
    """
    Root object for the Atlas application.

    Responsible for assembling and managing
    every Atlas subsystem.
    """

    def __init__(self):
        self._container = ServiceContainer()
        self._started = False

    @property
    def container(self) -> ServiceContainer:
        """Return the application's service container."""
        return self._container

    @property
    def started(self) -> bool:
        """Return whether Atlas has been started."""
        return self._started

    def start(self):
        """
        Start Atlas.
        """

        if self._started:
            return

        # Start every registered service.
        self._container.start_all()

        self._started = True

    def shutdown(self):
        """
        Shutdown Atlas.
        """

        if not self._started:
            return

        # Stop every registered service.
        self._container.stop_all()

        self._started = False