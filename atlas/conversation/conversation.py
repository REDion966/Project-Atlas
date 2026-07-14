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

    id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    title: str = "New Conversation"

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    messages: list[Message] = field(
        default_factory=list
    )

    def add_message(
        self,
        message: Message,
    ) -> None:
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

    # ---------------------------------------
    # Serialization
    # ---------------------------------------

    def to_dict(self) -> dict:
        """
        Convert the conversation to a dictionary.
        """

        return {
            "version": 1,
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in self.messages
            ],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Conversation":
        """
        Create a Conversation from a dictionary.
        """

        conversation = cls(
            id=data.get(
                "id",
                str(uuid.uuid4()),
            ),
            title=data.get(
                "title",
                "New Conversation",
            ),
            created_at=datetime.fromisoformat(
                data["created_at"]
            )
            if "created_at" in data
            else datetime.now(UTC),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            )
            if "updated_at" in data
            else datetime.now(UTC),
        )

        for item in data.get(
            "messages",
            [],
        ):
            conversation.messages.append(
                Message(
                    role=item["role"],
                    content=item["content"],
                )
            )

        return conversation