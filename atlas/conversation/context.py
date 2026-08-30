"""
Atlas Context Manager

Builds the conversational context for Atlas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas.conversation.conversation import Conversation
from atlas.memory.context.context_engine import ContextEngine

if TYPE_CHECKING:
    from atlas.session.context import SessionContext


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
        session_context: SessionContext | None = None,
    ) -> list:
        """
        Build the context for the current conversation.

        Includes:
        - Conversation messages
        - Relevant memories (scoped by session when provided)
        """

        context: list[Any] = []

        if self._context_engine and memory_query:
            kwargs: dict[str, Any] = {"query": memory_query}
            if session_context is not None:
                kwargs["session_context"] = session_context
            memories = self._context_engine.build_context(**kwargs)  # type: ignore[arg-type]

            context.extend(memories)

        context.extend(
            conversation.messages
        )

        return context