"""
Atlas Conversation Service

Coordinates Atlas conversations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from atlas.ai.routing.models import RoutingRequest
from atlas.cognition.api import CognitionAPI
from atlas.conversation.context import ContextManager
from atlas.conversation.conversation import Conversation
from atlas.conversation.development_intake import task_spec_to_development_need
from atlas.conversation.history import History
from atlas.conversation.message import Message
from atlas.conversation.prompt_builder import PromptBuilder
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.memory.context.context_engine import ContextEngine
from atlas.ai.ai_service import AIService
from atlas.storage.conversation_storage import ConversationStorage

if TYPE_CHECKING:
    from atlas.session.context import SessionContext
    from atlas.session.models import Session


class ConversationService:
    """Coordinates the complete conversation pipeline."""

    def __init__(
        self,
        ai_service: AIService,
        context_engine: ContextEngine | None = None,
        cognition_api: CognitionAPI | None = None,
        task_intake: TaskIntake | None = TaskIntake(),
        development_bridge: Callable[[TaskSpec], Message | str] | None = None,
        session_context: SessionContext | None = None,
        orchestration_resolver: Callable[[TaskSpec, SessionContext | None], object | None] | None = None,
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
        self._orchestration_resolver = orchestration_resolver
        self._session_context: SessionContext | None = session_context
        self._last_session_context: SessionContext | None = session_context

        # Create the initial conversation.
        self._conversation = self._history.create()

    @property
    def conversation(self) -> Conversation:
        """Return the active conversation."""

        return self._conversation

    @property
    def session_context(self) -> SessionContext | None:
        return self._session_context

    @property
    def last_session_context(self) -> SessionContext | None:
        return self._last_session_context

    def set_session_context(self, session_context: SessionContext | None) -> None:
        if session_context is not None:
            from atlas.session.context import SessionContext as _SC

            if not isinstance(session_context, _SC):
                raise ValueError("session_context must be a valid SessionContext or None (fail-closed)")
        self._session_context = session_context
        self._last_session_context = session_context

    def bind_session(self, session: Session) -> SessionContext:
        from atlas.session.context import SessionContext as _SC

        ctx = _SC.from_session(session)
        self.set_session_context(ctx)
        return ctx

    def send(
        self,
        text: str,
        session_context: SessionContext | None = None,
    ) -> Message:
        """
        Send a user message through Atlas.
        """

        active_session = session_context if session_context is not None else self._session_context
        self._last_session_context = active_session

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
            session_context=active_session,
        )

        # --- Phase 5.6: Optional cognition context ---
        # The raw user input is propagated as the processing goal (Phase 20,
        # Batch 2: goal/intent propagation). B2 replaces the raw-input-as-goal
        # seam with deterministic task intake: the raw input is preserved, the
        # structured goal travels in goal, and the full TaskSpec travels in
        # metadata["task"]. task_intake=None restores the legacy behavior.
        # P1/B1.2 — session_context is carried as attribution on TaskSpec and
        # as session/session_context in the cognition metadata so P2
        # orchestration can inspect it.
        spec = self._intake(text, len(self._conversation.messages))
        if spec is not None and active_session is not None:
            spec = self._attach_session_to_spec(spec, active_session)
        # Development semantics win — run it first and never reroute development
        # through orchestration.
        development_response = self._maybe_handle_development_request(spec)
        if development_response is not None:
            self._conversation.add_message(development_response)
            return development_response

        orchestration_response = self._maybe_handle_orchestration_request(spec, active_session)
        if orchestration_response is not None:
            # The orchestration bridge is fail-closed against missing
            # SessionContext at its own layer (so the conversation service
            # does not need to drop the message even when the resolver is
            # bound to a kernel-owned session).
            self._conversation.add_message(orchestration_response)
            return orchestration_response

        if self._cognition_api is not None:
            cognition_metadata: dict | None = None
            if spec is not None:
                cognition_metadata = {"task": spec.to_dict()}
            else:
                cognition_metadata = None
            if active_session is not None:
                _session_meta = {
                    "session_id": active_session.session_id,
                    "principal_id": active_session.principal_id,
                    "authority": active_session.authority.value,
                }
                if cognition_metadata is None:
                    cognition_metadata = {"session": _session_meta, "session_context": _session_meta}
                else:
                    cognition_metadata["session"] = _session_meta
                    cognition_metadata["session_context"] = _session_meta
            decision = self._cognition_api.process(
                user_input=text,
                goal=spec.goal_string() if spec is not None else text,
                metadata=cognition_metadata,
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
        session_context: SessionContext | None = None,
    ):
        """
        Stream a response through Atlas.
        """

        active_session = session_context if session_context is not None else self._session_context
        self._last_session_context = active_session

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
            session_context=active_session,
        )

        # --- Phase 5.6: Optional cognition context ---
        # The raw user input is propagated as the processing goal (Phase 20,
        # Batch 2: goal/intent propagation). B2 replaces the raw-input-as-goal
        # seam with deterministic task intake: the raw input is preserved, the
        # structured goal travels in goal, and the full TaskSpec travels in
        # metadata["task"]. task_intake=None restores the legacy behavior.
        # P1/B1.2 — session attribution as above.
        spec = self._intake(text, len(self._conversation.messages))
        if spec is not None and active_session is not None:
            spec = self._attach_session_to_spec(spec, active_session)
        development_response = self._maybe_handle_development_request(spec)
        if development_response is not None:
            self._conversation.add_message(development_response)
            yield development_response.content
            return

        orchestration_response = self._maybe_handle_orchestration_request(spec, active_session)
        if orchestration_response is not None:
            self._conversation.add_message(orchestration_response)
            yield orchestration_response.content
            return

        if self._cognition_api is not None:
            cognition_metadata = None
            if spec is not None:
                cognition_metadata = {"task": spec.to_dict()}
            if active_session is not None:
                _session_meta = {
                    "session_id": active_session.session_id,
                    "principal_id": active_session.principal_id,
                    "authority": active_session.authority.value,
                }
                if cognition_metadata is None:
                    cognition_metadata = {"session": _session_meta, "session_context": _session_meta}
                else:
                    cognition_metadata["session"] = _session_meta
                    cognition_metadata["session_context"] = _session_meta
            decision = self._cognition_api.process(
                user_input=text,
                goal=spec.goal_string() if spec is not None else text,
                metadata=cognition_metadata,
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

    @staticmethod
    def _attach_session_to_spec(spec: TaskSpec, session_context: SessionContext) -> TaskSpec:
        enriched = dict(spec.context) if isinstance(spec.context, dict) else {}
        enriched["session_id"] = session_context.session_id
        enriched["principal_id"] = session_context.principal_id
        enriched["authority"] = session_context.authority.value
        from dataclasses import replace as _replace

        return _replace(spec, context=enriched)

    def _maybe_handle_orchestration_request(
        self,
        spec: TaskSpec | None,
        session_context: SessionContext | None,
    ) -> Message | None:
        """Route ACTION/INFORMATION requests through the orchestration layer.

        Informationally routed: development requests never arrive here (the
        existing development bridge runs first). Non-actionable types return
        None. When the typed request cannot be safely resolved into a bounded
        target (underspecified / no bounded tool target), a bounded
        clarification message is returned rather than invented work. The
        resolver's ``None`` is always surfaced as clarification, not silent
        fallback.
        """
        if spec is None or self._orchestration_resolver is None:
            return None
        # Development semantics win: never reroute development requests.
        if spec.task_type is TaskType.DEVELOPMENT_REQUEST:
            return None
        if spec.task_type not in (TaskType.ACTION_REQUEST, TaskType.INFORMATION_REQUEST):
            return None
        # Honor TaskIntake's ambiguity gate deterministically.
        if bool(getattr(spec, "needs_clarification", False)):
            return self._orchestration_clarification_message(spec)
        # Resolver is the single decision surface: it never invents targets;
        # a ``None`` return means the typed request is not boundedly
        # actionable → bounded clarification (additive; never silently falls
        # through to the legacy path). The per-request session is forwarded
        # so the kernel bridge can attribute the execution to the exact
        # caller session rather than the kernel-bound default.
        result = self._orchestration_resolver(spec, session_context)
        if result is None:
            return self._orchestration_clarification_message(spec)
        if isinstance(result, Message):
            return result
        if isinstance(result, dict):
            content = str(result.get("content", "") or "").strip()
            meta = result.get("metadata", {}) or {}
            role = str(result.get("role", "assistant") or "assistant")
            if content:
                return Message(role=role, content=content, metadata=dict(meta))
        if isinstance(result, str):
            return Message(role="assistant", content=result.strip())
        # Never swallow a typed, non-clarification request silently.
        return self._orchestration_clarification_message(spec)

    @staticmethod
    def _orchestration_clarification_message(spec: TaskSpec) -> Message:
        """Bounded clarification for orchestrated ACTION/INFORMATION requests."""
        lines = [
            "I need a bit more detail before I can run this.",
        ]
        questions = getattr(spec.ambiguity, "clarification_questions", ()) or ()
        for question in tuple(questions)[:8]:
            lines.append(f"- {question}")
        if len(lines) == 1:
            # Fall back to a deterministic bounded rephrase of the ambiguous
            # slot (the intent is bounded; ambiguity is bounded; together
            # this is still deterministic).
            lines.append("- What outcome or detail would tell me this is done?")
        return Message(role="assistant", content="\n".join(lines))

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
