"""
Atlas Runtime

Central runtime environment for Atlas.
"""

from datetime import datetime


class AtlasRuntime:
    """
    Controls Atlas runtime lifecycle,
    execution state, and environment status.
    """

    def __init__(
        self,
        registry,
        state_manager=None,
        event_bus=None,
    ):
        """
        Initialize runtime.

        Args:
            registry:
                Atlas service registry.

            state_manager:
                Atlas state manager.

            event_bus:
                Atlas event bus.
        """

        self.registry = registry

        self.state_manager = state_manager

        self.event_bus = event_bus

        self.running = False

        self.started_at = None

        self.stopped_at = None


    def start(self):
        """
        Start Atlas runtime.
        """

        if self.running:
            return


        self.running = True

        self.started_at = datetime.now()

        self.stopped_at = None


        if self.state_manager:

            self.state_manager.update(
                {
                    "runtime": "active",
                    "runtime_health": "healthy",
                }
            )


        if self.event_bus:

            self.event_bus.publish(
                "runtime.started",
                {
                    "time": self.started_at.isoformat(),
                    "status": "active",
                }
            )



    def stop(self):
        """
        Stop Atlas runtime.
        """

        if not self.running:
            return


        self.running = False

        self.stopped_at = datetime.now()


        if self.state_manager:

            self.state_manager.update(
                {
                    "runtime": "inactive",
                    "runtime_health": "offline",
                }
            )


        if self.event_bus:

            self.event_bus.publish(
                "runtime.stopped",
                {
                    "time": self.stopped_at.isoformat(),
                    "status": "inactive",
                }
            )



    def get_service(
        self,
        name: str,
    ):
        """
        Retrieve a service from registry.
        """

        return self.registry.get(name)



    def uptime(self):
        """
        Return runtime uptime.
        """

        if not self.running or not self.started_at:
            return None


        return (
            datetime.now()
            - self.started_at
        ).total_seconds()



    def health(self):
        """
        Return runtime health status.
        """

        return {
            "running": self.running,
            "health": (
                "healthy"
                if self.running
                else "offline"
            ),
        }



    def status(self):
        """
        Return complete runtime status.
        """

        return {
            "running": self.running,

            "started_at": (
                self.started_at.isoformat()
                if self.started_at
                else None
            ),

            "stopped_at": (
                self.stopped_at.isoformat()
                if self.stopped_at
                else None
            ),

            "uptime": self.uptime(),

            "services": (
                self.registry.list_services()
            ),
        }