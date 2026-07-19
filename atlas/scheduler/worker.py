"""
Atlas Scheduler Worker

Executes scheduled tasks.
"""

from atlas.scheduler.scheduled_task import ScheduledTask


class Worker:
    """
    Executes scheduled tasks.
    """

    def execute(
        self,
        scheduled_task: ScheduledTask,
    ) -> None:
        """
        Execute a scheduled task.
        """

        if scheduled_task.cancelled:
            return

        if scheduled_task.executed:
            return

        scheduled_task.task.run()

        scheduled_task.executed = True