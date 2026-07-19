"""
Atlas Scheduled Task

Represents a task scheduled for future execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from atlas.task.task import Task


@dataclass(slots=True)
class ScheduledTask:
    """
    Wraps a Task with scheduling metadata.
    """

    task: Task

    run_at: datetime

    id: str = field(
        default_factory=lambda: str(uuid4())
    )

    created_at: datetime = field(
        default_factory=datetime.now
    )

    executed: bool = False

    cancelled: bool = False