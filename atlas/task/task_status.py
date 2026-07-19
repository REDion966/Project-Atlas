"""
Atlas Task Status

Defines the lifecycle states of a task.
"""

from enum import Enum


class TaskStatus(str, Enum):
    """
    Status values for Atlas tasks.
    """

    PENDING = "pending"

    QUEUED = "queued"

    RUNNING = "running"

    PAUSED = "paused"

    COMPLETED = "completed"

    FAILED = "failed"

    CANCELLED = "cancelled"