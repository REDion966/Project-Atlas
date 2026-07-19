"""
Atlas Task

Represents a unit of work inside Atlas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from atlas.task.task_priority import TaskPriority
from atlas.task.task_status import TaskStatus


@dataclass(slots=True)
class Task:
    """
    Represents a single Atlas task.
    """

    name: str

    priority: TaskPriority = TaskPriority.NORMAL

    status: TaskStatus = TaskStatus.PENDING

    payload: dict = field(default_factory=dict)

    id: str = field(
        default_factory=lambda: str(uuid4())
    )

    created_at: datetime = field(
        default_factory=datetime.now
    )

    started_at: datetime | None = None

    finished_at: datetime | None = None

    error: str | None = None

    def start(self):
        """
        Mark task as running.
        """

        self.status = TaskStatus.RUNNING

        self.started_at = datetime.now()

    def complete(self):
        """
        Mark task as completed.
        """

        self.status = TaskStatus.COMPLETED

        self.finished_at = datetime.now()

    def fail(
        self,
        error: str,
    ):
        """
        Mark task as failed.
        """

        self.status = TaskStatus.FAILED

        self.error = error

        self.finished_at = datetime.now()

    def cancel(self):
        """
        Cancel the task.
        """

        self.status = TaskStatus.CANCELLED

        self.finished_at = datetime.now()

    def pause(self):
        """
        Pause the task.
        """

        self.status = TaskStatus.PAUSED

    def resume(self):
        """
        Resume the task.
        """

        self.status = TaskStatus.RUNNING