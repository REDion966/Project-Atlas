"""
Atlas Context Manager

Builds the conversational context for Atlas.
"""

from atlas.conversation.conversation import Conversation
from atlas.memory.context.context_engine import ContextEngine


class ContextManager:
    """Selects the information required for an AI response."""

    def __init__(
        self,
        context_engine: ContextEngine | None = None,
    ):
        self._context_engine = context_engine

    def build(
        self,
        conversation: Conversation,
        memory_query: str | None = None,
    ) -> list:
        """
        Build the context for the current conversation.

        Includes:
        - Conversation messages
        - Relevant memories
        """

        context = []

        if self._context_engine and memory_query:
            memories = self._context_engine.build_context(
                query=memory_query,
            )

            context.extend(memories)

        context.extend(
            conversation.messages
        )

        return context