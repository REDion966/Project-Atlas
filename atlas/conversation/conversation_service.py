"""
Atlas Conversation Service

Coordinates Atlas conversations.
"""

from pathlib import Path

from atlas.conversation.context import ContextManager
from atlas.conversation.conversation import Conversation
from atlas.conversation.history import History
from atlas.conversation.message import Message
from atlas.conversation.prompt_builder import PromptBuilder
from atlas.memory.context.context_engine import ContextEngine
from atlas.services.ai_service import AIService
from atlas.storage.conversation_storage import ConversationStorage


class ConversationService:
    """Coordinates the complete conversation pipeline."""

    def __init__(
        self,
        ai_service: AIService,
        context_engine: ContextEngine | None = None,
    ):
        """
        Initialize the conversation service.

        Args:
            ai_service:
                A configured AIService instance.

            context_engine:
                Optional memory-aware context engine.
        """

        self._history = History()

        self._context = ContextManager(
            context_engine=context_engine,
        )

        self._prompt_builder = PromptBuilder()
        self._storage = ConversationStorage()

        self._ai = ai_service

        # Create the initial conversation.
        self._conversation = self._history.create()

    @property
    def conversation(self) -> Conversation:
        """Return the active conversation."""

        return self._conversation

    def send(
        self,
        text: str,
    ) -> Message:
        """
        Send a user message through Atlas.
        """

        user_message = Message(
            role="user",
            content=text,
        )

        self._conversation.add_message(
            user_message
        )

        context = self._context.build(
            self._conversation,
            memory_query=text,
        )

        prompt = self._prompt_builder.build(
            context
        )

        response = self._ai.chat(
            prompt
        )

        assistant_message = Message(
            role="assistant",
            content=response.text,
        )

        self._conversation.add_message(
            assistant_message
        )

        return assistant_message

    def stream(
        self,
        text: str,
    ):
        """
        Stream a response through Atlas.
        """

        user_message = Message(
            role="user",
            content=text,
        )

        self._conversation.add_message(
            user_message
        )

        context = self._context.build(
            self._conversation,
            memory_query=text,
        )

        prompt = self._prompt_builder.build(
            context
        )

        assistant_text = ""

        for chunk in self._ai.stream_chat(prompt):
            assistant_text += chunk
            yield chunk

        assistant_message = Message(
            role="assistant",
            content=assistant_text,
        )

        self._conversation.add_message(
            assistant_message
        )

    def save(self) -> Path:
        """
        Save the active conversation.
        """

        return self._storage.save(
            self._conversation
        )

    def load(
        self,
        filepath: Path,
    ) -> Conversation:
        """
        Load a conversation from disk.
        """

        conversation = self._storage.load(
            filepath
        )

        self._history.add(
            conversation
        )

        self._conversation = conversation

        return conversation

    def saved_conversations(self) -> list[Path]:
        """
        Return saved conversations.
        """

        return self._storage.list()