"""
Atlas Agent Identity

Defines permanent identity information
for Atlas agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class AgentIdentity:
    """
    Permanent identity of an Atlas agent.
    """

    name: str

    agent_type: str = "general"

    description: str = ""

    id: str = field(
        default_factory=lambda:
        f"agent_{uuid.uuid4().hex[:8]}"
    )

    created_at: datetime = field(
        default_factory=datetime.now
    )

    metadata: dict = field(
        default_factory=dict
    )


    def to_dict(self) -> dict:
        """
        Serialize identity.
        """

        return {
            "id": self.id,

            "name": self.name,

            "agent_type": self.agent_type,

            "description": self.description,

            "created_at": (
                self.created_at.isoformat()
            ),

            "metadata": self.metadata,
        }