"""
Atlas Scheduler

Coordinates scheduled task execution.
"""

from __future__ import annotations

import heapq
from datetime import datetime

from atlas.scheduler.scheduled_task import ScheduledTask
from atlas.scheduler.worker import Worker
from atlas.task.task import Task


class Scheduler:
    """
    Coordinates scheduled task execution.
    """

    def __init__(self):

        self._tasks: list[
            tuple[datetime, ScheduledTask]
        ] = []

        self._worker = Worker()

    def schedule(
        self,
        task: Task,
        run_at: datetime,
    ) -> ScheduledTask:
        """
        Schedule a task.
        """

        scheduled = ScheduledTask(
            task=task,
            run_at=run_at,
        )

        heapq.heappush(
            self._tasks,
            (
                scheduled.run_at,
                scheduled,
            ),
        )

        return scheduled

    def tick(self) -> None:
        """
        Execute every task whose time has arrived.
        """

        now = datetime.now()

        while self._tasks:

            run_at, scheduled = self._tasks[0]

            if run_at > now:
                break

            heapq.heappop(
                self._tasks
            )

            if scheduled.cancelled:
                continue

            if scheduled.executed:
                continue

            self._worker.execute(
                scheduled
            )

    def pending(
        self,
    ) -> list[ScheduledTask]:
        """
        Return pending tasks.
        """

        return [
            scheduled
            for _, scheduled in self._tasks
            if (
                not scheduled.executed
                and not scheduled.cancelled
            )
        ]

    def clear(self) -> None:
        """
        Remove every scheduled task.
        """

        self._tasks.clear()

    def count(self) -> int:
        """
        Return pending task count.
        """

        return len(
            self.pending()
        )