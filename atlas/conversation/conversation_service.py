"""
Atlas Conversation Service

Coordinates Atlas conversations.
"""

from pathlib import Path
from typing import Callable

from atlas.ai.routing.models import RoutingRequest
from atlas.cognition.api import CognitionAPI
from atlas.conversation.context import ContextManager
from atlas.conversation.conversation import Conversation
from atlas.conversation.history import History
from atlas.conversation.message import Message
from atlas.conversation.prompt_builder import PromptBuilder
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.memory.context.context_engine import ContextEngine
from atlas.ai.ai_service import AIService
from atlas.storage.conversation_storage import ConversationStorage


class ConversationService:
    """Coordinates the complete conversation pipeline."""

    def __init__(
        self,
        ai_service: AIService,
        context_engine: ContextEngine | None = None,
        cognition_api: CognitionAPI | None = None,
        task_intake: TaskIntake | None = TaskIntake(),
        development_bridge: Callable[[TaskSpec], Message | str] | None = None,
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

            task_intake:
                Optional conversational task intake. When ``None``, the legacy
                raw-input-as-goal behavior is preserved exactly. Defaults to a
                deterministic :class:`TaskIntake` (no model calls).

            development_bridge:
                Optional duck-typed callable mapping a DEVELOPMENT_REQUEST
                :class:`TaskSpec` into a conversational :class:`Message` or
                string. Wired by the composition root; this module never
                imports the evolution package. When absent, a development
                request falls through to the normal conversation path.
        """

        self._history = History()

        self._context = ContextManager(
            context_engine=context_engine,
        )

        self._prompt_builder = PromptBuilder()
        self._storage = ConversationStorage()

        self._ai = ai_service
        self._cognition_api = cognition_api
        self._task_intake = task_intake
        self._development_bridge = development_bridge

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
        # Batch 2: goal/intent propagation). B2 replaces the raw-input-as-goal
        # seam with deterministic task intake: the raw input is preserved, the
        # structured goal travels in goal, and the full TaskSpec travels in
        # metadata["task"]. task_intake=None restores the legacy behavior.
        spec = self._intake(text, len(self._conversation.messages))
        development_response = self._maybe_handle_development_request(spec)
        if development_response is not None:
            self._conversation.add_message(development_response)
            return development_response

        if self._cognition_api is not None:
            decision = self._cognition_api.process(
                user_input=text,
                goal=spec.goal_string() if spec is not None else text,
                metadata={"task": spec.to_dict()} if spec is not None else None,
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
                            "task": spec.to_dict() if spec is not None else None,
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
            routing_context=self._build_routing_request(text, spec),
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
        # Batch 2: goal/intent propagation). B2 replaces the raw-input-as-goal
        # seam with deterministic task intake: the raw input is preserved, the
        # structured goal travels in goal, and the full TaskSpec travels in
        # metadata["task"]. task_intake=None restores the legacy behavior.
        spec = self._intake(text, len(self._conversation.messages))
        development_response = self._maybe_handle_development_request(spec)
        if development_response is not None:
            self._conversation.add_message(development_response)
            yield development_response.content
            return

        if self._cognition_api is not None:
            decision = self._cognition_api.process(
                user_input=text,
                goal=spec.goal_string() if spec is not None else text,
                metadata={"task": spec.to_dict()} if spec is not None else None,
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
                            "task": spec.to_dict() if spec is not None else None,
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
            routing_context=self._build_routing_request(text, spec),
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
        spec: TaskSpec | None = None,
    ) -> RoutingRequest:
        """Build a minimal deterministic RoutingRequest from the user input.

        Phase 20 Batch 6 — the direct conversation path (send/stream) can
        bypass the RuntimeCoordinator, so the existing ModelRouter would
        otherwise stay dormant for CLI chat. Complexity here is a
        deterministic function of input length so ordinary messages route
        to the configured Ollama profile (complexity >= 0.5) and longer,
        more involved requests escalate.

        B2 — when a TaskSpec is available, its deterministic task type is
        reflected in the routing request (no behavioral change to the
        model router; the spec only supplies the existing task_type field).
        """
        length = max(1, len(text.strip()))
        if length <= 40:
            complexity = 0.5
        elif length <= 120:
            complexity = 0.6
        else:
            complexity = 0.7

        task_type = "conversation"
        if spec is not None:
            task_type = spec.task_type.value

        return RoutingRequest(
            complexity=complexity,
            latency_requirement="fast",
            task_type=task_type,
            context_size=length,
            metadata={"source": "conversation_service"},
        )

    def _intake(self, text: str, history_length: int = 0) -> TaskSpec | None:
        """Run the optional task intake, preserving legacy behavior when None."""
        if self._task_intake is None:
            return None
        return self._task_intake.intake(text, history_length=history_length)

    def _maybe_handle_development_request(
        self,
        spec: TaskSpec | None,
    ) -> Message | None:
        """Route a DEVELOPMENT_REQUEST TaskSpec to the injected bridge.

        Returns a conversational ``Message`` when the request is handled here,
        or ``None`` when processing should continue through the normal
        cognition + AI path. Clarification-needed development requests are
        answered directly (never bridged); a missing bridge preserves the
        legacy behavior by returning ``None``.
        """
        if spec is None or spec.task_type is not TaskType.DEVELOPMENT_REQUEST:
            return None

        if spec.needs_clarification:
            return self._clarification_message(spec)

        if self._development_bridge is None:
            return None

        result = self._development_bridge(spec)
        if isinstance(result, Message):
            return result
        if isinstance(result, str):
            return Message(role="assistant", content=result)
        return Message(
            role="assistant",
            content="The development request could not be prepared.",
        )

    @staticmethod
    def _clarification_message(spec: TaskSpec) -> Message:
        """Build a bounded clarification response from the TaskSpec."""
        lines = [
            "I need a bit more detail before I can prepare this as a governed "
            "development request."
        ]
        questions = getattr(spec.ambiguity, "clarification_questions", ()) or ()
        for question in tuple(questions)[:8]:
            lines.append(f"- {question}")
        return Message(role="assistant", content="\n".join(lines))

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
