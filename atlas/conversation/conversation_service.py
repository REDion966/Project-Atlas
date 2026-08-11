"""
Atlas Conversation Service

Coordinates Atlas conversations.
"""

from pathlib import Path

from atlas.ai.routing.models import RoutingRequest
from atlas.cognition.api import CognitionAPI
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
        cognition_api: CognitionAPI | None = None,
    ):
        """
        Initialize the conversation service.

        Args:
            ai_service:
                A configured AIService instance.

            context_engine:
                Optional memory-aware context engine.

            cognition_api:
                Optional CognitionAPI for service-based cognition.
        """

        self._history = History()

        self._context = ContextManager(
            context_engine=context_engine,
        )

        self._prompt_builder = PromptBuilder()
        self._storage = ConversationStorage()

        self._ai = ai_service
        self._cognition_api = cognition_api

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

        # --- Phase 5.6: Optional cognition context ---
        # The raw user input is propagated as the processing goal (Phase 20,
        # Batch 2: goal/intent propagation). A future batch may replace this
        # with richer intent extraction.
        if self._cognition_api is not None:
            decision = self._cognition_api.process(
                user_input=text,
                goal=text,
            )

            context.append(
                Message(
                    role="system",
                    content=(
                        f"Cognition analysis: "
                        f"action={decision.action}, "
                        f"reasoning={decision.reasoning}, "
                        f"data={decision.data}"
                    ),
                    metadata={
                        "cognition": {
                            "action": decision.action,
                            "reasoning": decision.reasoning,
                            "data": decision.data,
                        }
                    },
                )
            )
        # --- End cognition context ---

        prompt = self._prompt_builder.build(
            context
        )

        response = self._ai.chat(
            prompt,
            routing_context=self._build_routing_request(text),
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

        # --- Phase 5.6: Optional cognition context ---
        # The raw user input is propagated as the processing goal (Phase 20,
        # Batch 2: goal/intent propagation). A future batch may replace this
        # with richer intent extraction.
        if self._cognition_api is not None:
            decision = self._cognition_api.process(
                user_input=text,
                goal=text,
            )

            context.append(
                Message(
                    role="system",
                    content=(
                        f"Cognition analysis: "
                        f"action={decision.action}, "
                        f"reasoning={decision.reasoning}, "
                        f"data={decision.data}"
                    ),
                    metadata={
                        "cognition": {
                            "action": decision.action,
                            "reasoning": decision.reasoning,
                            "data": decision.data,
                        }
                    },
                )
            )
        # --- End cognition context ---

        prompt = self._prompt_builder.build(
            context
        )

        assistant_text = ""

        for chunk in self._ai.stream_chat(
            prompt,
            routing_context=self._build_routing_request(text),
        ):
            assistant_text += chunk
            yield chunk

        assistant_message = Message(
            role="assistant",
            content=assistant_text,
        )

        self._conversation.add_message(
            assistant_message
        )

    def _build_routing_request(
        self,
        text: str,
    ) -> RoutingRequest:
        """Build a minimal deterministic RoutingRequest from the user input.

        Phase 20 Batch 6 — the direct conversation path (send/stream) can
        bypass the RuntimeCoordinator, so the existing ModelRouter would
        otherwise stay dormant for CLI chat. Complexity here is a
        deterministic function of input length so ordinary messages route
        to the configured Ollama profile (complexity >= 0.5) and longer,
        more involved requests escalate.
        """
        length = max(1, len(text.strip()))
        if length <= 40:
            complexity = 0.5
        elif length <= 120:
            complexity = 0.6
        else:
            complexity = 0.7

        return RoutingRequest(
            complexity=complexity,
            latency_requirement="fast",
            task_type="conversation",
            context_size=length,
            metadata={"source": "conversation_service"},
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
