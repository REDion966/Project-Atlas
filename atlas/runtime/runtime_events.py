"""
Atlas Runtime Events

Central event definitions for the
Atlas runtime subsystem.
"""


class RuntimeEvents:
    """
    Runtime event names.
    """

    STARTED = "runtime.started"

    STOPPED = "runtime.stopped"

    HEARTBEAT = "runtime.heartbeat"

    HEALTH_CHANGED = "runtime.health_changed"

    PAUSED = "runtime.paused"

    RESUMED = "runtime.resumed"