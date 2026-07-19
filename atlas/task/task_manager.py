"""
Atlas Task Manager

Coordinates Atlas task execution.
"""

from __future__ import annotations

from datetime import datetime

from atlas.scheduler.scheduler import Scheduler
from atlas.task.task import Task
from atlas.task.task_queue import TaskQueue


class TaskManager:
    """
    Coordinates task creation and scheduling.
    """

    def __init__(self):

        self._scheduler = Scheduler()

        self._queue = TaskQueue()

        self._active_task: Task | None = None

    @property
    def scheduler(self) -> Scheduler:
        """
        Return the scheduler.
        """

        return self._scheduler

    @property
    def active_task(self) -> Task | None:
        """
        Return the active task.
        """

        return self._active_task

    def submit(
        self,
        task: Task,
    ) -> None:
        """
        Submit a task for immediate execution.
        """

        self.schedule(
            task,
            datetime.now(),
        )

    def schedule(
        self,
        task: Task,
        run_at: datetime,
    ):
        """
        Schedule a task.
        """

        return self._scheduler.schedule(
            task,
            run_at,
        )

    def tick(self) -> None:
        """
        Advance task execution.
        """

        self._scheduler.tick()

    def clear(self) -> None:
        """
        Remove every queued task.
        """

        self._queue.clear()

        self._scheduler.clear()

        self._active_task = None

    def pending(self):
        """
        Return pending scheduled tasks.
        """

        return self._scheduler.pending()

    def count(self) -> int:
        """
        Return pending task count.
        """

        return self._scheduler.count()