"""
Atlas Conversation Service

Coordinates Atlas conversations.
"""

from atlas.conversation.history import History
from atlas.conversation.message import Message
from atlas.conversation.context import ContextManager
from atlas.conversation.prompt_builder import PromptBuilder
from atlas.services.ai_service import AIService


class ConversationService:
    """Coordinates the complete conversation pipeline."""

    def __init__(self, ai_service: AIService):
        """
        Initialize the conversation service.

        Args:
            ai_service: A configured AIService instance.
        """

        self._history = History()
        self._context = ContextManager()
        self._prompt_builder = PromptBuilder()
        self._ai = ai_service

        # Create the initial conversation.
        self._conversation = self._history.create()

    @property
    def conversation(self):
        """Return the active conversation."""

        return self._conversation

    def send(self, text: str) -> Message:
        """
        Send a user message through Atlas.
        """

        user_message = Message(
            role="user",
            content=text,
        )

        self._conversation.add_message(user_message)

        context = self._context.build(self._conversation)

        prompt = self._prompt_builder.build(context)

        response = self._ai.chat(prompt)

        assistant_message = Message(
            role="assistant",
            content=response.text,
        )

        self._conversation.add_message(assistant_message)

        return assistant_message