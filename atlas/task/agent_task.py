"""
Atlas Agent Task

Tasks assigned to agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class AgentTask:
    """
    Task created for an agent.
    """

    name: str

    agent_id: str

    id: str = field(
        default_factory=lambda:
        f"task_{uuid.uuid4().hex[:8]}"
    )

    created_at: datetime = field(
        default_factory=datetime.now
    )

    status: str = "pending"


    def start(self):
        self.status = "running"


    def complete(self):
        self.status = "completed"


    def fail(self):
        self.status = "failed"


    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "agent_id": self.agent_id,
            "status": self.status,
            "created_at": (
                self.created_at.isoformat()
            ),
        }