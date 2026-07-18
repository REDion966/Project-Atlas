"""
Atlas Boot Manager

Coordinates the Atlas startup sequence.
"""

from atlas.core.dependency_checker import DependencyChecker
from atlas.utils.logger import Logger
from atlas.kernel.atlas import Atlas


class BootManager:
    """
    Controls the Atlas startup process.
    """

    def __init__(
        self,
        kernel: Atlas,
    ):
        self.kernel = kernel


    def boot(self):
        """
        Execute Atlas startup sequence.
        """

        Logger.info(
            "Boot sequence started."
        )


        self.kernel.state.update(
            {
                "status": "booting",
                "health": "starting",
            }
        )


        self.kernel.events.publish(
            "atlas.boot.started",
            {
                "status": "booting"
            }
        )


        if not DependencyChecker.run():

            Logger.error(
                "Boot aborted."
            )


            self.kernel.state.update(
                {
                    "status": "failed",
                    "health": "error",
                }
            )


            self.kernel.events.publish(
                "atlas.boot.failed",
                {
                    "reason": "dependency_check_failed"
                }
            )


            return False



        self.kernel.start()


        self.kernel.state.update(
            {
                "status": "running",
                "health": "healthy",
            }
        )


        self.kernel.events.publish(
            "atlas.ready",
            {
                "status": "running"
            }
        )


        Logger.info(
            "Boot sequence completed."
        )


        return True



    def shutdown(self):
        """
        Shutdown Atlas.
        """

        Logger.info(
            "Shutdown sequence started."
        )


        self.kernel.events.publish(
            "atlas.shutdown.started",
            {
                "status": "stopping"
            }
        )


        self.kernel.shutdown()


        self.kernel.events.publish(
            "atlas.shutdown.completed",
            {
                "status": "stopped"
            }
        )


        Logger.info(
            "Shutdown sequence completed."
        )