"""
Atlas Context Manager

Builds the conversational context for Atlas.
"""

from atlas.conversation.conversation import Conversation


class ContextManager:
    """Selects the information required for an AI response."""

    def build(self, conversation: Conversation) -> list:
        """
        Build the context for the current conversation.

        For now, simply return all conversation messages.
        Later this method will:
        - Retrieve long-term memories
        - Retrieve active goals
        - Summarize old conversations
        - Select only relevant information
        """

        return conversation.messages