"""
Atlas Lifecycle Phases

Defines every lifecycle state Atlas can enter.
"""

from enum import Enum


class LifecyclePhase(str, Enum):
    """
    Atlas lifecycle phases.
    """

    CREATED = "created"

    INITIALIZING = "initializing"

    STARTING = "starting"

    RUNNING = "running"

    STOPPING = "stopping"

    STOPPED = "stopped"