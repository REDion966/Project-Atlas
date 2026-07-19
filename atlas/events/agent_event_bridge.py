"""
Atlas Agent Event Bridge

Connects agents with Atlas event system.
"""

from __future__ import annotations

from atlas.agents.agent_events import AgentEvents


class AgentEventBridge:
    """
    Handles agent events.
    """

    def __init__(self):

        self._events: list[dict] = []


    def emit(
        self,
        event: AgentEvents,
        agent_id: str,
        data: dict | None = None,
    ) -> None:
        """
        Record agent event.
        """

        self._events.append(
            {
                "event": event.value,
                "agent_id": agent_id,
                "data": data or {},
            }
        )


    def history(self) -> list[dict]:
        """
        Return event history.
        """

        return list(
            self._events
        )