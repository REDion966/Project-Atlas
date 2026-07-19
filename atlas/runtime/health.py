"""
Atlas Runtime Health

Evaluates runtime execution health.
"""

from __future__ import annotations

from datetime import datetime


class RuntimeHealth:
    """
    Runtime health monitor.
    """

    def __init__(
        self,
        state,
        max_tick_delay: float = 5.0,
    ):

        self.state = state

        self.max_tick_delay = max_tick_delay


    def check(self) -> dict:
        """
        Evaluate runtime health.
        """

        now = datetime.now()

        healthy = True

        reason = "healthy"


        if not self.state.running:

            healthy = False

            reason = "stopped"


        elif self.state.last_tick:

            delay = (
                now - self.state.last_tick
            ).total_seconds()


            if delay > self.max_tick_delay:

                healthy = False

                reason = "tick_timeout"


        self.state.healthy = healthy


        return {
            "healthy": healthy,
            "reason": reason,
        }