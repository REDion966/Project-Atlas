"""
Atlas Conversation History

Manages Atlas conversations.
"""

from atlas.conversation.conversation import Conversation


class History:
    """Manages conversation history."""

    def __init__(self):
        self._conversations: list[Conversation] = []
        self._active: Conversation | None = None

    def create(self, title: str = "New Conversation") -> Conversation:
        """Create and activate a new conversation."""

        conversation = Conversation(title=title)

        self._conversations.append(conversation)
        self._active = conversation

        return conversation

    def active(self) -> Conversation | None:
        """Return the active conversation."""

        return self._active

    def conversations(self) -> list[Conversation]:
        """Return all conversations."""

        return self._conversations

    def count(self) -> int:
        """Return the total number of conversations."""

        return len(self._conversations)