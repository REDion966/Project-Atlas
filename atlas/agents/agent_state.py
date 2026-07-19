"""
Atlas Agent State

Tracks current execution state
of an Atlas agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentState:
    """
    Runtime state of an agent.
    """

    status: str = "created"

    healthy: bool = True

    created_at: datetime = field(
        default_factory=datetime.now
    )

    started_at: datetime | None = None

    last_action: datetime | None = None

    task_count: int = 0


    def start(self):
        """
        Mark agent as running.
        """

        self.status = "running"

        self.started_at = datetime.now()


    def pause(self):
        """
        Pause agent execution.
        """

        self.status = "paused"


    def stop(self):
        """
        Stop agent execution.
        """

        self.status = "stopped"


    def record_action(self):
        """
        Record agent activity.
        """

        self.last_action = datetime.now()

        self.task_count += 1


    def to_dict(self) -> dict:
        """
        Serialize state.
        """

        return {
            "status": self.status,

            "healthy": self.healthy,

            "created_at": (
                self.created_at.isoformat()
            ),

            "started_at": (
                self.started_at.isoformat()
                if self.started_at
                else None
            ),

            "last_action": (
                self.last_action.isoformat()
                if self.last_action
                else None
            ),

            "task_count": self.task_count,
        }