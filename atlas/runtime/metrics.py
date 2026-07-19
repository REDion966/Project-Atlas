"""
Atlas Runtime Metrics

Tracks runtime performance information.
"""

from __future__ import annotations

from datetime import datetime


class RuntimeMetrics:
    """
    Calculates runtime statistics.
    """

    def __init__(
        self,
        state,
    ):

        self.state = state


    @property
    def uptime(self) -> float:
        """
        Return runtime uptime in seconds.
        """

        if self.state.started_at is None:
            return 0.0

        return (
            datetime.now()
            - self.state.started_at
        ).total_seconds()


    @property
    def ticks_per_second(self) -> float:
        """
        Return average ticks per second.
        """

        uptime = self.uptime

        if uptime <= 0:
            return 0.0

        return (
            self.state.tick_count
            / uptime
        )


    def snapshot(self):
        """
        Return current metrics.
        """

        return {
            "uptime": self.uptime,
            "tick_count": self.state.tick_count,
            "ticks_per_second": self.ticks_per_second,
        }