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
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.reference_resolution import ConversationReferenceResolver
from atlas.conversation.development_outcome_reporter import (
    DevelopmentOutcomeReporter,
    snapshot_from_result,
)
from atlas.conversation.history import History
from atlas.conversation.message import Message
from atlas.conversation.prompt_builder import PromptBuilder
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.memory.context.context_engine import ContextEngine
from atlas.ai.ai_service import AIService
from atlas.storage.conversation_storage import ConversationStorage

if TYPE_CHECKING:
    from atlas.conversation.deterministic_fallback import DeterministicFallbackResolver
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
        fallback_resolver: DeterministicFallbackResolver | None = None,
        development_need_coordinator: DevelopmentNeedCoordinator | None = None,
        outcome_reporter: DevelopmentOutcomeReporter | None = None,
        state_manager: ConversationStateManager | None = None,
        reference_resolver: ConversationReferenceResolver | None = None,
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

            session_context:
                Optional default SessionContext.

            orchestration_resolver:
                Optional orchestration bridge for ACTION/INFORMATION requests.

            fallback_resolver:
                Optional DeterministicFallbackResolver for model-unavailable
                degraded operation.
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
        self._fallback_resolver = fallback_resolver
        self._development_need_coordinator = development_need_coordinator
        self._outcome_reporter = outcome_reporter
        self._state_manager = state_manager or ConversationStateManager()
        self._reference_resolver = reference_resolver or ConversationReferenceResolver()
        self._session_context: SessionContext | None = session_context
        self._last_session_context: SessionContext | None = session_context

        # Create the initial conversation.
        self._conversation = self._history.create()

    @property
    def conversation(self) -> Conversation:
        """Return the active conversation."""

        return self._conversation

    @property
    def state_manager(self) -> ConversationStateManager:
        """Return the conversational state manager for this conversation."""
        return self._state_manager

    @property
    def reference_resolver(self) -> ConversationReferenceResolver:
        """Return the conversational reference resolver."""
        return self._reference_resolver

    def resolve_reference(self, query: str) -> ReferenceResolutionResult:
        """Resolve a conversational reference against current state.

        Convenience wrapper around :meth:`ConversationReferenceResolver.resolve`
        using this service's current :class:`ConversationState`.
        """
        from atlas.conversation.reference_resolution import ReferenceResolutionResult
        return self._reference_resolver.resolve(query, self._state_manager.state)

    @property
    def fallback_resolver(self) -> DeterministicFallbackResolver | None:
        return self._fallback_resolver

    def set_fallback_resolver(self, resolver: DeterministicFallbackResolver | None) -> None:
        self._fallback_resolver = resolver

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

        # P7.4 — route a pending confirmation reply through the local
        # coordinator (conversation-owned; never reaches F9 directly).
        coordinated = self._maybe_handle_development_need_confirmation(text, active_session)
        if coordinated is not None:
            self._conversation.add_message(coordinated)
            return coordinated

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

        try:
            response = self._ai.chat(
                prompt,
                routing_context=self._build_routing_request(text, spec),
            )
            assistant_message = Message(
                role="assistant",
                content=response.text,
            )
        except Exception as exc:
            # External AI unavailable, unreachable, or failed -> deterministic fallback
            if self._fallback_resolver is not None:
                assistant_message = self._fallback_resolver.resolve(
                    text=text,
                    spec=spec,
                    session_context=active_session,
                    error_context=str(exc),
                )
            else:
                assistant_message = Message(
                    role="assistant",
                    content=(
                        "External AI inference is currently unavailable and no deterministic "
                        "fallback resolver is configured."
                    ),
                    metadata={
                        "degraded": True,
                        "model_available": False,
                        "error": str(exc),
                    },
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

        try:
            for chunk in self._ai.stream_chat(
                prompt,
                routing_context=self._build_routing_request(text, spec),
            ):
                assistant_text += chunk
                yield chunk
        except Exception as exc:
            if not assistant_text:
                # Stream failed before/at token generation -> deterministic fallback stream
                if self._fallback_resolver is not None:
                    for chunk in self._fallback_resolver.resolve_stream(
                        text=text,
                        spec=spec,
                        session_context=active_session,
                        error_context=str(exc),
                    ):
                        assistant_text += chunk
                        yield chunk
                else:
                    msg = (
                        "External AI inference is currently unavailable and no deterministic "
                        "fallback resolver is configured."
                    )
                    assistant_text = msg
                    yield msg
            else:
                note = "\n\n[Stream interrupted: external AI model connection lost]"
                assistant_text += note
                yield note

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

    def set_experience_capture(self, accumulator) -> None:
        """Inject the ExperienceAccumulator used for orchestration capture."""
        self._capture_accumulator = accumulator

    def _record_orchestration_experience(
        self,
        *,
        spec: TaskSpec,
        result_obj: object | None,
        text: str,
    ) -> None:
        try:
            acc = getattr(self, "_capture_accumulator", None)
            if acc is None or not hasattr(acc, "record_orchestration"):
                return
            history_len = len(getattr(self._conversation, "messages", ()) or ())
            acc.record_orchestration(
                user_input=text,
                task_spec=spec,
                result=result_obj,
                conversation_history_length=history_len,
            )
        except Exception:
            pass

    @staticmethod
    def _dict_to_orchestration_result(payload: dict):
        try:
            from datetime import datetime as _dt
            steps = []
            for s in (payload.get("steps", ()) or ()):
                if isinstance(s, dict):
                    steps.append(type("_Step", (), {
                        "target": s.get("target", ""),
                        "state": type("_St", (), {"value": s.get("state", "")})(),
                        "kind": type("_K", (), {"value": s.get("kind", "")})(),
                    })())
            obj = type("_R", (), {})()
            obj.status = type("_S", (), {"value": payload.get("status", "")})()
            obj.session_id = payload.get("session_id")
            obj.principal_id = payload.get("principal_id")
            obj.authority = payload.get("authority")
            obj.elapsed_ms = payload.get("elapsed_ms", 0.0)
            obj.completed_count = payload.get("completed_count", 0)
            obj.failed_count = payload.get("failed_count", 0)
            obj.steps = tuple(steps)
            obj.created_at = None
            ca = payload.get("created_at")
            if isinstance(ca, str):
                try:
                    obj.created_at = _dt.fromisoformat(ca)
                except Exception:
                    pass
            return obj
        except Exception:
            return None

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
            # P7.4 — a well-specified ACTION request whose target could not be
            # resolved is a genuine deterministic capability-gap signal. When a
            # coordinator is wired, surface an explanation (which records the
            # pending confirmation) instead of the generic clarification.
            detected = self._maybe_detect_development_need(spec)
            if detected is not None:
                return detected
            return self._orchestration_clarification_message(spec)
        if isinstance(result, Message):
            if isinstance(result.metadata, dict):
                payload = result.metadata.get("orchestration")
                if isinstance(payload, dict):
                    obj = self._dict_to_orchestration_result(payload)
                    if obj is not None:
                        self._record_orchestration_experience(spec=spec, result_obj=obj, text=spec.goal if hasattr(spec, "goal") else "")
            return result
        if isinstance(result, dict):
            content = str(result.get("content", "") or "").strip()
            meta = result.get("metadata", {}) or {}
            role = str(result.get("role", "assistant") or "assistant")
            if content:
                msg = Message(role=role, content=content, metadata=dict(meta))
                orch = meta.get("orchestration") if isinstance(meta, dict) else None
                if isinstance(orch, dict):
                    obj2 = self._dict_to_orchestration_result(orch)
                    if obj2 is not None:
                        self._record_orchestration_experience(spec=spec, result_obj=obj2, text=spec.goal if hasattr(spec, "goal") else "")
                return msg
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
        # P7.5 — the bridge returned an authoritative F9 result object rather
        # than a pre-rendered Message. Project it through the reporter so the
        # conversational surface sees a truthful, provenance-preserving report.
        if self._outcome_reporter is not None:
            provenance = self._provenance_from_spec(spec)
            return self._outcome_reporter.report(
                snapshot_from_result(result, **provenance)
            )
        return Message(
            role="assistant",
            content="The development request could not be prepared.",
        )

    @staticmethod
    def _provenance_from_spec(spec: TaskSpec) -> dict[str, str]:
        """Extract provenance from a spec's context (already attached by the
        conversation service). Never elevates authority."""
        ctx = getattr(spec, "context", {}) or {}
        out: dict[str, str] = {}
        for key in ("session_id", "principal_id", "authority"):
            value = ctx.get(key)
            if isinstance(value, str) and value:
                out[key] = value
        return out

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

    def _maybe_handle_development_need_confirmation(
        self,
        text: str,
        session_context: SessionContext | None,
    ) -> Message | None:
        """Route a reply against a pending P7 confirmation through the local
        coordinator (conversation-owned; never reaches F9 directly)."""
        coordinator = self._development_need_coordinator
        if coordinator is None or not coordinator.has_pending:
            return None

        outcome = coordinator.handle_reply(text, session_context)
        if outcome is None:
            return None
        if isinstance(outcome, Message):
            return outcome
        # CONFIRMED -> DEVELOPMENT_REQUEST TaskSpec -> existing bridge.
        return self._maybe_handle_development_request(outcome)

    def handle_advisory(self, advisory_signal, session_context: SessionContext | None = None):
        """Feed a bounded P5 advisory signal into the P7 detection/dialogue path
        (P7.7).

        Advisory alone NEVER invokes the development bridge. If the signal
        detects an improvement opportunity, this returns an explanation
        :class:`Message` and records a pending confirmation bound to the session
        context. The actual development bridge is reachable ONLY through
        subsequent explicit human confirmation (``send("yes")``).

        Returns ``None`` when no coordinator is wired or no opportunity is
        detected.
        """
        coordinator = self._development_need_coordinator
        if coordinator is None:
            return None
        active_session = session_context if session_context is not None else self._session_context
        message = coordinator.advisory_input(advisory_signal, active_session)
        if message is None:
            return None
        self._conversation.add_message(message)
        return message

    def _maybe_detect_development_need(
        self,
        spec: TaskSpec,
    ) -> Message | None:
        """Surface a P7 explanation for a genuine deterministic unresolved-
        action/capability-gap signal. Returns ``None`` when no coordinator is
        wired or no signal is detected."""
        coordinator = self._development_need_coordinator
        if coordinator is None:
            return None
        if spec is None or spec.task_type is not TaskType.ACTION_REQUEST:
            return None
        if bool(spec.needs_clarification):
            return None
        return coordinator.detect_unresolved_action(spec)

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
