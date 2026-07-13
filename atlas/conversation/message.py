"""
Atlas Conversation Message

Represents a single message in a conversation.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid


@dataclass(slots=True)
class Message:
    """Represents a single conversation message."""

    role: str
    content: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = field(default_factory=dict)