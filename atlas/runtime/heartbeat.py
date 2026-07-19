"""
Atlas Runtime Heartbeat

Publishes runtime heartbeat events.
"""

from __future__ import annotations

from atlas.runtime.runtime_events import RuntimeEvents


class Heartbeat:
    """
    Runtime heartbeat publisher.
    """

    def __init__(
        self,
        event_bus,
        interval: int = 20,
    ):

        self._event_bus = event_bus

        self._interval = interval

    @property
    def interval(self) -> int:
        """
        Return heartbeat interval.
        """

        return self._interval

    def should_publish(
        self,
        tick_count: int,
    ) -> bool:
        """
        Determine whether a heartbeat
        should be published.
        """

        if self._interval <= 0:
            return False

        return (
            tick_count % self._interval == 0
        )

    def publish(
        self,
        tick_count: int,
        uptime: float,
        tps: float,
    ):
        """
        Publish a heartbeat event.
        """

        if self._event_bus is None:
            return

        self._event_bus.publish(
            RuntimeEvents.HEARTBEAT,
            {
                "tick": tick_count,
                "uptime": uptime,
                "tps": tps,
            },
        )