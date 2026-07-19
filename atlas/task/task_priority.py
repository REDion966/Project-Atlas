"""
Atlas Task Priority

Defines task priority levels.
"""

from enum import IntEnum


class TaskPriority(IntEnum):
    """
    Priority values for Atlas tasks.

    Higher value = higher priority.
    """

    LOW = 10

    NORMAL = 20

    HIGH = 30

    CRITICAL = 40