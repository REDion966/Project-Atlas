"""
Atlas Conversation

Represents a conversation consisting of multiple messages.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid

from atlas.conversation.message import Message


@dataclass(slots=True)
class Conversation:
    """Represents an Atlas conversation."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Conversation"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    messages: list[Message] = field(default_factory=list)

    def add_message(self, message: Message) -> None:
        """Add a message to the conversation."""

        self.messages.append(message)
        self.updated_at = datetime.now(UTC)

    def clear(self) -> None:
        """Remove all messages."""

        self.messages.clear()
        self.updated_at = datetime.now(UTC)

    def message_count(self) -> int:
        """Return the total number of messages."""

        return len(self.messages)