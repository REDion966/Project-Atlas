"""
Atlas Schedule Policy

Defines scheduling behavior.
"""

from enum import Enum


class SchedulePolicy(Enum):
    """
    Scheduling strategies.
    """

    IMMEDIATE = "immediate"

    DELAYED = "delayed"

    INTERVAL = "interval"

    CRON = "cron"

    MANUAL = "manual"