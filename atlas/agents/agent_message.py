"""
Atlas Agent Message

Communication unit between agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class AgentMessage:
    """
    Message exchanged between agents.
    """

    sender_id: str

    receiver_id: str

    content: dict

    id: str = field(
        default_factory=lambda:
        f"msg_{uuid.uuid4().hex[:8]}"
    )

    created_at: datetime = field(
        default_factory=datetime.now
    )


    def to_dict(self) -> dict:

        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "content": self.content,
            "created_at": (
                self.created_at.isoformat()
            ),
        }