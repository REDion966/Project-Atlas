"""
Atlas Conversation Service

Coordinates Atlas conversations.
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from atlas.ai.routing.models import RoutingRequest
from atlas.cognition.api import CognitionAPI
from atlas.conversation.context import ContextManager
from atlas.conversation.conversation import Conversation
from atlas.conversation.development_intake import task_spec_to_development_need
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.execution import Level3ExecutionService
from atlas.conversation.investigation import (
    InvestigationProposal,
    InvestigationProposalConverter,
    InvestigationProposalGenerator,
    InvestigationService,
)
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
from atlas.evolution.approval_manager import ApprovalManager
from atlas.memory.context.context_engine import ContextEngine
from atlas.ai.ai_service import AIService
from atlas.storage.conversation_storage import ConversationStorage

if TYPE_CHECKING:
    from atlas.conversation.deterministic_fallback import DeterministicFallbackResolver
    from atlas.session.context import SessionContext
    from atlas.session.models import Session


class _RecoveryResultStandin:
    """Minimal evidence-carrying stand-in for a failed DevelopmentRunResult.

    The conversation service does not retain the full run result object (it is
    owned by the kernel). This standin reconstructs just enough structure for
    the read-only diagnostic and recovery engines to analyze the failure
    evidence preserved on the proposal. It is used ONLY for post-execution
    diagnosis and never participates in execution.
    """

    def __init__(
        self,
        status: Any = None,
        outcomes: list[Any] | None = None,
        iterations_used: int = 0,
        message: str = "",
    ) -> None:
        self.status = status
        self.outcomes = outcomes or []
        self.iterations_used = iterations_used
        self.message = message

    @classmethod
    def from_proposal(cls, proposal: Any) -> "_RecoveryResultStandin":
        """Build a stand-in from a preserved EvolutionProposal.

        Derives the failure status from the proposal's metadata, which the
        kernel bridge populates with the execution result status and the last
        outcome's evidence.
        """
        from atlas.evolution.development_models import DevelopmentOutcomeStatus

        meta = getattr(proposal, "metadata", {}) or {}
        execution = meta.get("execution") or {}
        last_outcome = meta.get("last_outcome") or {}

        status_name = execution.get("result_status", "FAILED")
        try:
            status = DevelopmentOutcomeStatus[status_name]
        except KeyError:
            status = DevelopmentOutcomeStatus.FAILED

        outcome = type(
            "_S",
            (),
            {
                "outcome": status,
                "verification_passed": bool(last_outcome.get("verification_passed", False)),
                "rollback_occurred": bool(last_outcome.get("rollback_occurred", False)),
                "test_outcome": str(last_outcome.get("test_outcome", "")),
                "message": str(last_outcome.get("message", "") or execution.get("message", "")),
            },
        )()

        return cls(
            status=status,
            outcomes=[outcome],
            iterations_used=int(execution.get("iterations_used", 0)),
            message=str(execution.get("message", "")),
        )


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
        investigation_service: InvestigationService | None = None,
        execution_service: Level3ExecutionService | None = None,
        approval_manager: ApprovalManager | None = None,
        development_execution_bridge: Callable[..., Any] | None = None,
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

            approval_manager:
                Optional ApprovalManager for creating real approval requests.
                When ``None``, planning requests cannot create approval requests.

            development_execution_bridge:
                Optional duck-typed callable that bridges an already-approved
                conversational proposal/request into the EXISTING kernel
                governed-development-execution infrastructure. Signature:

                    (session_context, proposal, request) -> Message

                When ``None``, execution requests cannot be carried out.
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
        self._investigation_service = investigation_service
        self._proposal_generator = InvestigationProposalGenerator()
        self._proposal_converter = InvestigationProposalConverter()
        self._execution_service = execution_service
        self._approval_manager = approval_manager
        self._development_execution_bridge = development_execution_bridge
        self._reference_resolver = reference_resolver or ConversationReferenceResolver()
        self._session_context: SessionContext | None = session_context
        self._last_session_context: SessionContext | None = session_context

        # Transient registry of active InvestigationProposals keyed by proposal_id.
        # Conversation-scoped (not global) to preserve cross-session isolation.
        self._active_proposals: dict[str, InvestigationProposal] = {}

        # Transient registries of live EvolutionProposals and ApprovalRequests
        # created by the planning handler, keyed by proposal_id / request_id.
        # Conversation-scoped (not global), never persisted. Required so the
        # approval handler can resolve the exact objects bound by fingerprint.
        self._active_evolution_proposals: dict[str, Any] = {}
        self._active_approval_requests: dict[str, Any] = {}

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
        # Investigation semantics — read-only, takes precedence over
        # development because investigation cannot mutate state.
        if spec is not None and spec.task_type is TaskType.INVESTIGATION_REQUEST:
            investigation_response = self._maybe_handle_investigation_request(
                spec, original_text=text
            )
            if investigation_response is not None:
                self._conversation.add_message(investigation_response)
                return investigation_response
        # Approval semantics — explicit approval/rejection for a pending
        # proposal. Must be explicit; ambiguous responses are not treated
        # as approval.
        if spec is not None and spec.task_type in (
            TaskType.APPROVAL,
            TaskType.REJECTION_REQUEST,
        ):
            approval_response = self._maybe_handle_approval(spec)
            if approval_response is not None:
                self._conversation.add_message(approval_response)
                return approval_response
        # Planning semantics — convert an investigation proposal into a
        # governed development proposal that enters the ApprovalManager lifecycle.
        # Must be explicit; requires an active InvestigationProposal.
        if spec is not None and spec.task_type is TaskType.PLANNING_REQUEST:
            planning_response = self._maybe_handle_planning_request(spec)
            if planning_response is not None:
                self._conversation.add_message(planning_response)
                return planning_response
        # Execution semantics — explicit execution of an approved proposal.
        # Must be explicit; approval alone does not execute.
        if spec is not None and spec.task_type is TaskType.EXECUTION_REQUEST:
            execution_response = self._maybe_handle_execution_request(spec)
            if execution_response is not None:
                self._conversation.add_message(execution_response)
                return execution_response
        # Recovery semantics — explicit recovery from a previous development
        # failure. Read-only decision; never auto-executes.
        if spec is not None and spec.task_type is TaskType.RECOVERY_REQUEST:
            recovery_response = self._maybe_handle_recovery_request(spec)
            if recovery_response is not None:
                self._conversation.add_message(recovery_response)
                return recovery_response
        # Verification semantics — explicit verification of an already-completed
        # development result. Read-only; never executes or mutates.
        if spec is not None and spec.task_type is TaskType.VERIFICATION_REQUEST:
            verification_response = self._maybe_handle_verify(spec)
            if verification_response is not None:
                self._conversation.add_message(verification_response)
                return verification_response
        # Report semantics — explicit final lifecycle report. Read-only.
        if spec is not None and spec.task_type is TaskType.REPORT_REQUEST:
            report_response = self._maybe_handle_report(spec)
            if report_response is not None:
                self._conversation.add_message(report_response)
                return report_response
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
        # Investigation semantics — read-only, takes precedence over
        # development because investigation cannot mutate state.
        if spec is not None and spec.task_type is TaskType.INVESTIGATION_REQUEST:
            investigation_response = self._maybe_handle_investigation_request(
                spec, original_text=text
            )
            if investigation_response is not None:
                self._conversation.add_message(investigation_response)
                yield investigation_response.content
                return
        # Planning semantics — convert an investigation proposal into a
        # governed development proposal that enters the ApprovalManager lifecycle.
        if spec is not None and spec.task_type is TaskType.PLANNING_REQUEST:
            planning_response = self._maybe_handle_planning_request(spec)
            if planning_response is not None:
                self._conversation.add_message(planning_response)
                yield planning_response.content
                return
        # Approval semantics — explicit approval/rejection of the pending
        # request through the governed ApprovalManager path (same handler
        # as send()).
        if spec is not None and spec.task_type in (
            TaskType.APPROVAL,
            TaskType.REJECTION_REQUEST,
        ):
            approval_response = self._maybe_handle_approval(spec)
            if approval_response is not None:
                self._conversation.add_message(approval_response)
                yield approval_response.content
                return
        # Execution semantics — explicit execution of an approved proposal.
        if spec is not None and spec.task_type is TaskType.EXECUTION_REQUEST:
            execution_response = self._maybe_handle_execution_request(spec)
            if execution_response is not None:
                self._conversation.add_message(execution_response)
                yield execution_response.content
                return
        # Recovery semantics — explicit recovery from a previous development
        # failure. Read-only decision; never auto-executes.
        if spec is not None and spec.task_type is TaskType.RECOVERY_REQUEST:
            recovery_response = self._maybe_handle_recovery_request(spec)
            if recovery_response is not None:
                self._conversation.add_message(recovery_response)
                yield recovery_response.content
                return
        # Verification semantics — explicit verification of an already-completed
        # development result. Read-only; never executes or mutates.
        if spec is not None and spec.task_type is TaskType.VERIFICATION_REQUEST:
            verification_response = self._maybe_handle_verify(spec)
            if verification_response is not None:
                self._conversation.add_message(verification_response)
                yield verification_response.content
                return
        # Report semantics — explicit final lifecycle report. Read-only.
        if spec is not None and spec.task_type is TaskType.REPORT_REQUEST:
            report_response = self._maybe_handle_report(spec)
            if report_response is not None:
                self._conversation.add_message(report_response)
                yield report_response.content
                return
        # Development semantics win — run it first and never reroute development
        # through orchestration.
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

    def _maybe_handle_investigation_request(
        self,
        spec: TaskSpec,
        original_text: str | None = None,
    ) -> Message | None:
        """Route an INVESTIGATION_REQUEST to a read-only investigation.

        Investigation is strictly read-only: it inspects the repository and
        produces a report, but never modifies anything. The investigation
        result is recorded in ConversationState.current_investigation.

        When the investigation uncovers a meaningful improvement, a governed
        development proposal is generated and presented. No changes are made;
        the proposal requires explicit approval before any work begins.
        """
        if self._investigation_service is None:
            return None

        # Prefer the original user text as the investigation target so the
        # investigation service can extract the real subject (e.g. "F17
        # failures") rather than the development-oriented intent extraction.
        target = original_text or spec.goal or spec.intent or "unspecified issue"
        report = self._investigation_service.investigate(target)

        # Record the investigation in conversation state
        if self._state_manager is not None:
            self._state_manager.update(
                current_investigation=report.target,
                latest_result=report.diagnosis,
            )

        # Build the base investigation report content.
        content_parts = [report.to_markdown()]

        # Attempt proposal generation when a meaningful improvement exists.
        proposal = self._proposal_generator.generate_proposal(report)
        proposal_meta: dict[str, Any] = {}
        if proposal is not None:
            # Register the proposal for later resolution (e.g., planning).
            self._register_proposal(proposal)
            # Record the proposal in conversation state for continuity.
            if self._state_manager is not None:
                self._state_manager.update(
                    active_proposal_id=proposal.proposal_id,
                    active_proposal_fingerprint=proposal.fingerprint,
                )
            content_parts.append(
                "\n---\n\n"
                f"## Development Proposal: {proposal.title}\n\n"
                f"{proposal.evidence_summary}\n\n"
                f"**Components:** {', '.join(proposal.components[:5])}\n"
                f"**Proposal ID:** {proposal.proposal_id}\n"
                f"**Status:** {proposal.status}\n\n"
                "No changes have been made. This proposal requires your "
                "explicit approval before any work begins."
            )
            proposal_meta = {
                "proposal_id": proposal.proposal_id,
                "proposal_status": proposal.status,
                "proposal_fingerprint": proposal.fingerprint,
            }
        else:
            content_parts.append(
                "\n---\n\n"
                "No actionable development proposal was generated from this "
                "investigation."
            )

        metadata: dict[str, Any] = {
            "investigation": {
                "target": report.target,
                "modification_status": report.modification_status,
                "findings_count": len(report.findings),
                "affected_files": list(report.affected_files),
            },
        }
        if proposal_meta:
            metadata["proposal"] = proposal_meta

        return Message(
            role="assistant",
            content="\n".join(content_parts),
            metadata=metadata,
        )

    def _register_proposal(self, proposal: InvestigationProposal) -> None:
        """Register an InvestigationProposal for later resolution.

        Stores the proposal in a transient, conversation-scoped registry
        so it can be resolved by ID during planning requests.

        Args:
            proposal: The InvestigationProposal to register.
        """
        self._active_proposals[proposal.proposal_id] = proposal

    def _resolve_proposal(self, proposal_id: str) -> InvestigationProposal | None:
        """Resolve an InvestigationProposal by ID.

        Args:
            proposal_id: The ID of the proposal to resolve.

        Returns:
            The InvestigationProposal if found, None otherwise.
        """
        return self._active_proposals.get(proposal_id)

    def _register_evolution_proposal(self, proposal: Any) -> None:
        """Register a live EvolutionProposal for later approval resolution."""
        self._active_evolution_proposals[proposal.proposal_id] = proposal

    def _resolve_evolution_proposal(self, proposal_id: str) -> Any | None:
        """Resolve a live EvolutionProposal by ID, or None when unknown."""
        return self._active_evolution_proposals.get(proposal_id)

    def _register_approval_request(self, request: Any) -> None:
        """Register a live ApprovalRequest for later approval resolution."""
        self._active_approval_requests[request.request_id] = request

    def _resolve_approval_request(self, request_id: str) -> Any | None:
        """Resolve a live ApprovalRequest by ID, or None when unknown."""
        return self._active_approval_requests.get(request_id)

    def _maybe_handle_planning_request(self, spec: TaskSpec) -> Message | None:
        """Handle an explicit PLANNING_REQUEST.

        Converts the active InvestigationProposal into a governed
        EvolutionProposal (DRAFT) and submits it to ApprovalManager
        for approval.

        Planning is only valid when:
        1. There is an active InvestigationProposal (active_proposal_id in state).
        2. The planning request is explicit (not ambiguous like "okay").
        3. An ApprovalManager is wired.

        Planning does NOT:
        - Modify any files
        - Call ApplicationEngine.apply()
        - Create execution authorization
        - Auto-approve anything
        - Bypass ApprovalManager

        Args:
            spec: the classified PLANNING_REQUEST TaskSpec.

        Returns:
            A Message describing the planning result, or None if no active
            proposal exists to plan.
        """
        state = self._state_manager.state if self._state_manager else None
        if state is None or not state.active_proposal_id:
            return Message(
                role="assistant",
                content=(
                    "There is no active investigation proposal to plan. "
                    "Please investigate an issue first to create a proposal."
                ),
                metadata={"planning": {"status": "no_active_proposal"}},
            )

        # Resolve the actual InvestigationProposal object
        inv_proposal = self._resolve_proposal(state.active_proposal_id)
        if inv_proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The active proposal could not be resolved. "
                    "Please investigate the issue again to create a new proposal."
                ),
                metadata={"planning": {"status": "proposal_not_found"}},
            )

        # Verify the proposal fingerprint matches (strict binding)
        if state.active_proposal_fingerprint != inv_proposal.fingerprint:
            return Message(
                role="assistant",
                content=(
                    "The proposal fingerprint does not match. "
                    "The proposal may have changed. "
                    "Please investigate the issue again."
                ),
                metadata={"planning": {"status": "fingerprint_mismatch"}},
            )

        # Check ApprovalManager is available
        if self._approval_manager is None:
            return Message(
                role="assistant",
                content=(
                    "Approval manager is not available. "
                    "The proposal could not be submitted for approval."
                ),
                metadata={"planning": {"status": "no_approval_manager"}},
            )

        # Refuse duplicate planning while a pending request already exists.
        # Minting a second request for the same proposal would orphan the
        # first and weaken the single-pending-request invariant.
        if state.pending_approval_id:
            pending = self._resolve_approval_request(state.pending_approval_id)
            if pending is not None and getattr(pending.decision, "name", "") == "PENDING":
                return Message(
                    role="assistant",
                    content=(
                        f"Proposal '{state.evolution_proposal_id}' already has a "
                        f"pending approval request '{state.pending_approval_id}'. "
                        "Please approve or reject it before planning again."
                    ),
                    metadata={"planning": {"status": "already_pending"}},
                )

        # Convert InvestigationProposal → EvolutionProposal (DRAFT)
        try:
            ev_proposal = self._proposal_converter.convert(inv_proposal)
        except Exception as exc:
            return Message(
                role="assistant",
                content=(
                    f"Failed to convert proposal: {exc}. "
                    "Please investigate the issue again."
                ),
                metadata={"planning": {"status": "conversion_failed", "error": str(exc)}},
            )

        # Submit to ApprovalManager
        try:
            approval_request = self._approval_manager.create_approval_request(ev_proposal)
        except Exception as exc:
            return Message(
                role="assistant",
                content=(
                    f"Failed to submit proposal for approval: {exc}. "
                    "Please try again."
                ),
                metadata={"planning": {"status": "approval_failed", "error": str(exc)}},
            )

        # Retain the live objects so the approval handler can resolve the
        # exact instances bound by fingerprint. Registries are instance-scoped
        # and never persisted.
        self._register_evolution_proposal(ev_proposal)
        self._register_approval_request(approval_request)

        # Update conversation state
        if self._state_manager is not None:
            self._state_manager.update(
                evolution_proposal_id=ev_proposal.proposal_id,
                pending_approval_id=approval_request.request_id,
                latest_result=(
                    f"Proposal '{ev_proposal.proposal_id}' submitted for approval "
                    f"as '{approval_request.request_id}'"
                ),
            )

        return Message(
            role="assistant",
            content=(
                f"## Development Proposal Prepared\n\n"
                f"**Title:** {ev_proposal.title}\n"
                f"**Evolution Proposal ID:** {ev_proposal.proposal_id}\n"
                f"**Approval Request ID:** {approval_request.request_id}\n"
                f"**Status:** {ev_proposal.status.name}\n\n"
                f"This proposal was derived from investigation "
                f"'{inv_proposal.investigation_target}'.\n\n"
                f"**Components:** {', '.join(ev_proposal.plan.target_components[:5])}\n"
                f"**Affected files:** {', '.join(ev_proposal.metadata.get('affected_files', [])[:5])}\n\n"
                f"No changes have been made. This proposal requires your "
                f"explicit approval before any work begins."
            ),
            metadata={
                "planning": {
                    "status": "prepared",
                    "investigation_proposal_id": inv_proposal.proposal_id,
                    "evolution_proposal_id": ev_proposal.proposal_id,
                    "approval_request_id": approval_request.request_id,
                    "proposal_status": ev_proposal.status.name,
                    "approval_status": approval_request.decision.name,
                },
            },
        )

    def _maybe_handle_approval(self, spec: TaskSpec) -> Message | None:
        """Handle an explicit APPROVAL or REJECTION request.

        Routes the decision through the EXISTING ApprovalManager contract:

            resolve EvolutionProposal + ApprovalRequest
                → validate identity + fingerprint
                → OWNER authorization
                → approve()/reject()
                → update_proposal_from_decision()
                → ConversationState update
                → STOP

        Approval does NOT:
        - Modify any files
        - Call ApplicationEngine.apply()
        - Create execution authorization
        - Automatically transition to Level 3
        - Invoke DevelopmentPlanner or any execution infrastructure

        All resolution and validation occur BEFORE the manager decision
        call. Any validation failure leaves ConversationState unchanged.

        Args:
            spec: the classified APPROVAL or REJECTION_REQUEST TaskSpec.

        Returns:
            A Message describing the approval result.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. Approval requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"approval": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "Approval requires OWNER authority. "
                    "This session is not authorized to approve proposals."
                ),
                metadata={"approval": {"status": "unauthorized"}},
            )

        state = self._state_manager.state if self._state_manager else None
        if state is None:
            return Message(
                role="assistant",
                content=(
                    "There is no development proposal awaiting approval. "
                    "Please investigate an issue and plan it first."
                ),
                metadata={"approval": {"status": "no_active_proposal"}},
            )

        # Recovery approvals are processed first: a pending recovery approval
        # represents a distinct recovery attempt that must be explicitly
        # approved separately from the original development.
        if state.recovery_approval_id:
            return self._handle_recovery_approval(spec, state, active_session)

        if not state.evolution_proposal_id:
            return Message(
                role="assistant",
                content=(
                    "There is no development proposal awaiting approval. "
                    "Please investigate an issue and plan it first."
                ),
                metadata={"approval": {"status": "no_active_proposal"}},
            )
        if not state.pending_approval_id:
            return Message(
                role="assistant",
                content=(
                    f"Proposal '{state.evolution_proposal_id}' has no pending "
                    "approval request. It may already have been decided."
                ),
                metadata={"approval": {"status": "no_pending_request"}},
            )

        # 3. Resolve the live objects from the instance-scoped registries.
        proposal = self._resolve_evolution_proposal(state.evolution_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The development proposal could not be resolved. "
                    "Please plan the proposal again."
                ),
                metadata={"approval": {"status": "proposal_not_found"}},
            )
        request = self._resolve_approval_request(state.pending_approval_id)
        if request is None:
            return Message(
                role="assistant",
                content=(
                    "The approval request could not be resolved. "
                    "Please plan the proposal again."
                ),
                metadata={"approval": {"status": "request_not_found"}},
            )

        # 4. Cross-validate identity BEFORE the manager decision call.
        if request.proposal_id != proposal.proposal_id:
            return Message(
                role="assistant",
                content=(
                    "The approval request does not match the active proposal. "
                    "Approval refused."
                ),
                metadata={"approval": {"status": "identity_mismatch"}},
            )
        if not request.is_valid_for(proposal):
            return Message(
                role="assistant",
                content=(
                    "The proposal has changed since the approval request was "
                    "created. Approval refused. Please plan the proposal again."
                ),
                metadata={"approval": {"status": "fingerprint_mismatch"}},
            )

        # 5. Check the ApprovalManager is wired.
        if self._approval_manager is None:
            return Message(
                role="assistant",
                content=(
                    "Approval manager is not available. "
                    "The decision could not be recorded."
                ),
                metadata={"approval": {"status": "no_approval_manager"}},
            )

        # 6. Determine approve vs reject from the classified task type.
        is_rejection = spec.task_type is TaskType.REJECTION_REQUEST

        # 7. Record the governed decision. update_proposal_from_decision
        # maps the decision onto the proposal status.
        try:
            if is_rejection:
                reason = self._rejection_reason_from_spec(spec)
                self._approval_manager.reject(request, reason=reason)
            else:
                comment = self._approval_comment_from_spec(spec)
                self._approval_manager.approve(request, comment=comment)
            self._approval_manager.update_proposal_from_decision(proposal, request)
        except Exception as exc:
            return Message(
                role="assistant",
                content=(
                    f"Approval decision could not be recorded: {exc}. "
                    "No state was changed."
                ),
                metadata={"approval": {"status": "decision_failed", "error": str(exc)}},
            )

        # 8. Only after the complete governed lifecycle succeeds, consume
        # the pending request while retaining the decided proposal identity.
        decision_name = request.decision.name
        if self._state_manager is not None:
            self._state_manager.update(
                pending_approval_id=None,  # request consumed (anti-replay)
                latest_result=(
                    f"Proposal '{proposal.proposal_id}' {decision_name} "
                    f"as '{request.request_id}'"
                ),
            )

        if is_rejection:
            return Message(
                role="assistant",
                content=(
                    f"Proposal '{proposal.proposal_id}' has been rejected. "
                    "No changes have been made."
                ),
                metadata={
                    "approval": {
                        "status": "rejected",
                        "proposal_id": proposal.proposal_id,
                        "request_id": request.request_id,
                        "reason": request.decision_comment,
                        "modification_status": "NONE",
                    },
                },
            )
        return Message(
            role="assistant",
            content=(
                f"Proposal '{proposal.proposal_id}' has been approved. "
                "No changes have been made. "
                "Implementation will require a separate explicit step."
            ),
            metadata={
                "approval": {
                    "status": "approved",
                    "proposal_id": proposal.proposal_id,
                    "request_id": request.request_id,
                    "modification_status": "NONE",
                },
            },
        )

    @staticmethod
    def _approval_comment_from_spec(spec: TaskSpec) -> str:
        """Derive a bounded approval comment from the classified request."""
        intent = (getattr(spec, "intent", "") or "").strip()
        return intent[:200]

    @staticmethod
    def _rejection_reason_from_spec(spec: TaskSpec) -> str:
        """Derive a non-blank rejection reason from the classified request.

        ApprovalManager.reject() requires a non-blank reason, so an empty
        or unusable message falls back to a fixed default.
        """
        intent = (getattr(spec, "intent", "") or "").strip()
        if intent:
            return intent[:200]
        return "Rejected via conversation."

    def _handle_recovery_approval(
        self,
        spec: TaskSpec,
        state: Any,
        active_session: Any,
    ) -> Message | None:
        """Process explicit approval/rejection of a pending recovery request.

        A recovery approval is a DISTINCT approval request with its own
        identity, separate from the original development approval. It must be
        explicitly approved; the original approval does not authorize recovery.

        Args:
            spec: the classified APPROVAL or REJECTION_REQUEST TaskSpec.
            state: the current ConversationState.
            active_session: the active SessionContext.

        Returns:
            A Message describing the recovery approval result.
        """
        recovery_proposal_id = state.recovery_proposal_id
        recovery_approval_id = state.recovery_approval_id

        # Resolve the recovery objects from the instance-scoped registries.
        proposal = self._resolve_evolution_proposal(recovery_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The recovery proposal could not be resolved. "
                    "Please run recovery assessment again."
                ),
                metadata={"recovery_approval": {"status": "proposal_not_found"}},
            )
        request = self._resolve_approval_request(recovery_approval_id)
        if request is None:
            return Message(
                role="assistant",
                content=(
                    "The recovery approval request could not be resolved. "
                    "Please run recovery assessment again."
                ),
                metadata={"recovery_approval": {"status": "request_not_found"}},
            )

        # Cross-validate identity BEFORE the manager decision call.
        if request.proposal_id != proposal.proposal_id:
            return Message(
                role="assistant",
                content=(
                    "The recovery approval request does not match the recovery "
                    "proposal. Approval refused."
                ),
                metadata={"recovery_approval": {"status": "identity_mismatch"}},
            )
        if not request.is_valid_for(proposal):
            return Message(
                role="assistant",
                content=(
                    "The recovery proposal has changed since the approval "
                    "request was created. Please run recovery assessment again."
                ),
                metadata={"recovery_approval": {"status": "fingerprint_mismatch"}},
            )

        # Check the ApprovalManager is wired.
        if self._approval_manager is None:
            return Message(
                role="assistant",
                content=(
                    "Approval manager is not available. "
                    "The decision could not be recorded."
                ),
                metadata={"recovery_approval": {"status": "no_approval_manager"}},
            )

        # Record the governed decision.
        is_rejection = spec.task_type is TaskType.REJECTION_REQUEST
        try:
            if is_rejection:
                reason = self._rejection_reason_from_spec(spec)
                self._approval_manager.reject(request, reason=reason)
            else:
                comment = self._approval_comment_from_spec(spec)
                self._approval_manager.approve(request, comment=comment)
            self._approval_manager.update_proposal_from_decision(proposal, request)
        except Exception as exc:
            return Message(
                role="assistant",
                content=(
                    f"Recovery approval decision could not be recorded: {exc}. "
                    "No state was changed."
                ),
                metadata={
                    "recovery_approval": {"status": "decision_failed", "error": str(exc)},
                },
            )

        # Consume the recovery approval request (anti-replay).
        decision_name = request.decision.name
        if self._state_manager is not None:
            self._state_manager.update(
                recovery_approval_id=None,  # recovery request consumed
                latest_result=(
                    f"Recovery proposal '{proposal.proposal_id}' {decision_name} "
                    f"as '{request.request_id}'"
                ),
            )

        if is_rejection:
            return Message(
                role="assistant",
                content=(
                    f"Recovery proposal '{proposal.proposal_id}' has been "
                    "rejected. No changes have been made."
                ),
                metadata={
                    "recovery_approval": {
                        "status": "rejected",
                        "proposal_id": proposal.proposal_id,
                        "request_id": request.request_id,
                        "reason": request.decision_comment,
                    },
                },
            )
        return Message(
            role="assistant",
            content=(
                f"Recovery proposal '{proposal.proposal_id}' has been approved. "
                "No changes have been made. "
                "Recovery implementation will require a separate explicit step."
            ),
            metadata={
                "recovery_approval": {
                    "status": "approved",
                    "proposal_id": proposal.proposal_id,
                    "request_id": request.request_id,
                    "original_proposal_id": proposal.metadata.get("original_proposal_id"),
                },
            },
        )

    def _maybe_handle_execution_request(
        self,
        spec: TaskSpec,
    ) -> Message | None:
        """Handle an explicit EXECUTION_REQUEST via the D2 governed bridge.

        Bridges an ALREADY-APPROVED conversational EvolutionProposal and its
        decided ApprovalRequest into the EXISTING kernel governed-development-
        execution infrastructure:

            resolve real proposal + request
                → validate identity / fingerprint / status / decision
                → OWNER authority
                → existing EvolutionMemory stores
                → existing governed development execution
                → STOP

        Execution is only valid when:
        1. There is an active approved proposal (evolution_proposal_id in state).
        2. The execution request is explicit (not ambiguous like "okay").
        3. The real proposal/request can be resolved from conversation registries.
        4. The proposal is APPROVED and the request is APPROVED.
        5. Identity and fingerprint bind exactly.
        6. OWNER authority is granted (enforced by the kernel bridge).

        Execution does NOT:
        - Treat approval as authorization
        - Execute without explicit execution request
        - Allow stale approvals to execute
        - Allow replay of already-executed proposals
        - Call Level3ExecutionService, ApplicationEngine, or AuthorizationManager
        - Mutate any files directly

        Args:
            spec: the classified EXECUTION_REQUEST TaskSpec.

        Returns:
            A Message describing the execution result.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. Execution requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"execution": {"status": "no_session"}},
            )

        # 2. OWNER authority is required at the conversation boundary.
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "Execution requires OWNER authority. "
                    "This session is not authorized to execute proposals."
                ),
                metadata={"execution": {"status": "unauthorized"}},
            )

        # 3. The development-execution bridge must be wired.
        if self._development_execution_bridge is None:
            return Message(
                role="assistant",
                content=(
                    "Development execution bridge is not available. "
                    "Proposal remains approved but not executed."
                ),
                metadata={"execution": {"status": "no_bridge"}},
            )

        state = self._state_manager.state if self._state_manager else None
        if state is None:
            return Message(
                role="assistant",
                content=(
                    "There is no approved development proposal to execute. "
                    "Please investigate an issue, plan it, and approve it first."
                ),
                metadata={"execution": {"status": "no_active_proposal"}},
            )

        # Recovery execution: if a recovery proposal has been explicitly
        # approved, execute the recovery proposal (distinct identity) instead
        # of the original. The original failure evidence is preserved.
        is_recovery = (
            state.recovery_proposal_id is not None
            and state.recovery_approval_id is None  # recovery approval consumed
            and state.evolution_proposal_id is not None
        )
        if is_recovery:
            return self._handle_recovery_execution(spec, state, active_session)

        if not state.evolution_proposal_id:
            return Message(
                role="assistant",
                content=(
                    "There is no approved development proposal to execute. "
                    "Please investigate an issue, plan it, and approve it first."
                ),
                metadata={"execution": {"status": "no_active_proposal"}},
            )

        # 4. Resolve the REAL live objects from the conversation registries.
        proposal = self._resolve_evolution_proposal(state.evolution_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The approved proposal could not be resolved. "
                    "Please plan the proposal again."
                ),
                metadata={"execution": {"status": "proposal_not_found"}},
            )
        request = self._resolve_approved_request(state.evolution_proposal_id)
        if request is None:
            return Message(
                role="assistant",
                content=(
                    "The approved request could not be resolved. "
                    "Please approve the proposal again."
                ),
                metadata={"execution": {"status": "request_not_found"}},
            )

        # 5. Cross-validate identity + status + fingerprint BEFORE the bridge.
        from atlas.evolution.models import ApprovalDecision, ProposalStatus

        if proposal.status != ProposalStatus.APPROVED:
            return Message(
                role="assistant",
                content=(
                    f"Proposal '{proposal.proposal_id}' is "
                    f"'{proposal.status.name}', not APPROVED. "
                    "Only approved proposals can be executed."
                ),
                metadata={"execution": {"status": "not_approved"}},
            )
        if request.decision != ApprovalDecision.APPROVED:
            return Message(
                role="assistant",
                content=(
                    "The approval request has not been approved. "
                    "Please approve the proposal before execution."
                ),
                metadata={"execution": {"status": "not_approved"}},
            )
        if request.proposal_id != proposal.proposal_id:
            return Message(
                role="assistant",
                content=(
                    "The approval request does not match the active proposal. "
                    "Execution refused."
                ),
                metadata={"execution": {"status": "identity_mismatch"}},
            )
        if not request.is_valid_for(proposal):
            return Message(
                role="assistant",
                content=(
                    "The proposal has changed since the approval request was "
                    "created. Execution refused. Please approve again."
                ),
                metadata={"execution": {"status": "fingerprint_mismatch"}},
            )

        # 6. Delegate to the existing governed development-execution bridge.
        try:
            message = self._development_execution_bridge(
                active_session, proposal, request
            )
        except Exception as exc:
            return Message(
                role="assistant",
                content=(
                    f"Development execution could not proceed: {exc}. "
                    "No changes were made."
                ),
                metadata={"execution": {"status": "execution_failed", "error": str(exc)}},
            )

        # 7. Record the result.
        if self._state_manager is not None:
            exec_status = getattr(
                getattr(message, "metadata", None),
                "get",
                lambda *_a, **_k: None,
            )
            latest = "Execution requested"
            if isinstance(message.metadata, dict):
                latest = (
                    f"Execution {message.metadata.get('execution', {}).get('status', 'requested')}"
                )
            self._state_manager.update(latest_result=latest)

        return message

    def _resolve_approved_request(self, proposal_id: str) -> Any | None:
        """Resolve the decided APPROVED ApprovalRequest for a proposal.

        After approval, ``pending_approval_id`` is consumed (set to None), so
        the request is found by scanning the live registry for the entry whose
        proposal_id matches and whose decision is APPROVED.
        """
        for req in self._active_approval_requests.values():
            if (
                getattr(req, "proposal_id", None) == proposal_id
                and getattr(getattr(req, "decision", None), "name", "") == "APPROVED"
            ):
                return req
        return None

    def _handle_recovery_execution(
        self,
        spec: TaskSpec,
        state: Any,
        active_session: Any,
    ) -> Message | None:
        """Execute an explicitly approved recovery proposal.

        The recovery proposal has a distinct identity from the original
        development proposal. Execution is delegated to the EXISTING governed
        development-execution bridge (single authority), which invokes the
        existing kernel development execution with its own OWNER gate.

        The original failure evidence is preserved; the recovery result is
        recorded separately.

        Args:
            spec: the classified EXECUTION_REQUEST TaskSpec.
            state: the current ConversationState.
            active_session: the active SessionContext.

        Returns:
            A Message describing the recovery execution result.
        """
        recovery_proposal_id = state.recovery_proposal_id

        # Resolve the recovery proposal from the instance-scoped registry.
        proposal = self._resolve_evolution_proposal(recovery_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The recovery proposal could not be resolved. "
                    "Please run recovery assessment again."
                ),
                metadata={"recovery_execution": {"status": "proposal_not_found"}},
            )

        # Validate the recovery proposal is APPROVED.
        from atlas.evolution.models import ProposalStatus

        if proposal.status != ProposalStatus.APPROVED:
            return Message(
                role="assistant",
                content=(
                    f"Recovery proposal '{proposal.proposal_id}' is "
                    f"'{proposal.status.name}', not APPROVED. "
                    "Please approve the recovery proposal before executing."
                ),
                metadata={"recovery_execution": {"status": "not_approved"}},
            )

        # Resolve the approved recovery approval request.
        request = self._resolve_approved_request(recovery_proposal_id)
        if request is None:
            return Message(
                role="assistant",
                content=(
                    "The approved recovery request could not be resolved. "
                    "Please approve the recovery proposal again."
                ),
                metadata={"recovery_execution": {"status": "request_not_found"}},
            )

        # Cross-validate identity + fingerprint BEFORE the bridge.
        from atlas.evolution.models import ApprovalDecision

        if request.proposal_id != proposal.proposal_id:
            return Message(
                role="assistant",
                content=(
                    "The recovery approval request does not match the recovery "
                    "proposal. Execution refused."
                ),
                metadata={"recovery_execution": {"status": "identity_mismatch"}},
            )
        if request.decision != ApprovalDecision.APPROVED:
            return Message(
                role="assistant",
                content=(
                    "The recovery request has not been approved. "
                    "Please approve the recovery proposal first."
                ),
                metadata={"recovery_execution": {"status": "not_approved"}},
            )
        if not request.is_valid_for(proposal):
            return Message(
                role="assistant",
                content=(
                    "The recovery proposal has changed since the approval "
                    "request was created. Execution refused."
                ),
                metadata={"recovery_execution": {"status": "fingerprint_mismatch"}},
            )

        # Delegate to the EXISTING governed development-execution bridge.
        # This is the single development execution authority, OWNER-gated.
        try:
            message = self._development_execution_bridge(
                active_session, proposal, request
            )
        except Exception as exc:
            return Message(
                role="assistant",
                content=(
                    f"Recovery execution could not proceed: {exc}. "
                    "No changes were made."
                ),
                metadata={
                    "recovery_execution": {"status": "execution_failed", "error": str(exc)},
                },
            )

        # Record the recovery result, preserving the original failure identity.
        if self._state_manager is not None:
            original_id = proposal.metadata.get("original_proposal_id", "unknown")
            exec_status = "requested"
            if isinstance(message.metadata, dict):
                exec_status = message.metadata.get("execution", {}).get("status", "requested")
            self._state_manager.update(
                latest_result=(
                    f"Recovery '{proposal.proposal_id}' (from '{original_id}'): "
                    f"{exec_status}"
                ),
            )

        return message

    def _maybe_handle_recovery_request(self, spec: TaskSpec) -> Message | None:
        """Handle an explicit RECOVERY_REQUEST.

        Produces a read-only RecoveryDecision from the failed development run's
        preserved evidence and diagnosis. For REVISE_AND_RETRY, creates a NEW
        recovery proposal + approval request (distinct identity from the
        original) and presents it for explicit user approval.

        Recovery NEVER executes automatically. The actual recovery execution
        must go through the existing governed development execution path with
        explicit approval of the recovery request.

        Args:
            spec: the classified RECOVERY_REQUEST TaskSpec.

        Returns:
            A Message describing the recovery decision.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. Recovery requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"recovery": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "Recovery requires OWNER authority. "
                    "This session is not authorized to recover proposals."
                ),
                metadata={"recovery": {"status": "unauthorized"}},
            )

        state = self._state_manager.state if self._state_manager else None
        if state is None or not state.evolution_proposal_id:
            return Message(
                role="assistant",
                content=(
                    "There is no failed development run to recover from. "
                    "Please investigate an issue, plan it, approve it, and "
                    "execute it first."
                ),
                metadata={"recovery": {"status": "no_failed_run"}},
            )

        # 3. Resolve the failed run's evidence from the live registries.
        proposal = self._resolve_evolution_proposal(state.evolution_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The failed proposal could not be resolved. "
                    "Please execute the development again."
                ),
                metadata={"recovery": {"status": "proposal_not_found"}},
            )

        # 4. Reconstruct the DevelopmentRunResult from preserved evidence and
        # produce diagnosis + recovery decision.
        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
        from atlas.evolution.development_recovery import DevelopmentRecovery

        result_standin = _RecoveryResultStandin.from_proposal(proposal)
        diagnostic = DevelopmentDiagnostic().diagnose(result_standin)
        recovery = DevelopmentRecovery().decide(result_standin, diagnostic)

        # 5. For REVISE_AND_RETRY, create a NEW recovery proposal + approval
        # request with a distinct identity, then present it for approval.
        recovery_proposal_id = None
        recovery_approval_id = None
        if recovery.recoverable and recovery.strategy.value == "revise_and_retry":
            try:
                recovery_proposal_id, recovery_approval_id = (
                    self._create_recovery_proposal(proposal, diagnostic, recovery)
                )
            except Exception as exc:
                return Message(
                    role="assistant",
                    content=(
                        f"Recovery decision was {recovery.strategy.value}, but "
                        f"creating the recovery proposal failed: {exc}."
                    ),
                    metadata={"recovery": {"status": "creation_failed", "error": str(exc)}},
                )

        # 6. Update conversation state with recovery identity.
        if self._state_manager is not None and (
            recovery_proposal_id or recovery_approval_id
        ):
            self._state_manager.update(
                recovery_proposal_id=recovery_proposal_id,
                recovery_approval_id=recovery_approval_id,
            )

        # 7. Report the read-only recovery decision. Never auto-execute.
        lines = [
            "## Recovery Assessment",
            "",
            f"**Original Proposal:** {proposal.proposal_id}",
            f"**Recoverable:** {'yes' if recovery.recoverable else 'no'}",
            f"**Strategy:** {recovery.strategy.value}",
            f"**Rationale:** {recovery.rationale}",
        ]
        if recovery.evidence:
            lines.append(f"**Evidence:** {recovery.evidence}")

        if recovery_proposal_id:
            lines.append("")
            lines.append(f"**Recovery Proposal:** {recovery_proposal_id}")
            lines.append(f"**Recovery Approval Request:** {recovery_approval_id}")
            lines.append("")
            lines.append(
                "A new recovery proposal has been created with a distinct "
                "identity from the original. Please **explicitly approve** "
                "this recovery request before any recovery attempt can be "
                "executed. The original approval does NOT authorize recovery."
            )

        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={
                "recovery": {
                    "status": "decided",
                    "recoverable": recovery.recoverable,
                    "strategy": recovery.strategy.value,
                    "rationale": recovery.rationale,
                    "original_proposal_id": proposal.proposal_id,
                    "recovery_proposal_id": recovery_proposal_id,
                    "recovery_approval_id": recovery_approval_id,
                    "diagnostic": {
                        "failure_class": diagnostic.failure_class.value,
                        "confidence": diagnostic.confidence.value,
                        "cause": diagnostic.cause,
                    },
                },
            },
        )

    def _create_recovery_proposal(
        self,
        original_proposal: Any,
        diagnostic: Any,
        recovery: Any,
    ) -> tuple[str, str]:
        """Create a NEW recovery proposal + approval request.

        The recovery proposal has a distinct identity from the original and
        references the original failure evidence. It is submitted to the
        EXISTING ApprovalManager, producing a new pending ApprovalRequest.

        Args:
            original_proposal: The failed EvolutionProposal.
            diagnostic: The DiagnosticResult for the failure.
            recovery: The RecoveryDecision (must be REVISE_AND_RETRY).

        Returns:
            A tuple of (recovery_proposal_id, recovery_approval_id).

        Raises:
            RuntimeError: If the ApprovalManager is not wired.
        """
        from atlas.evolution.development_models import (
            DevelopmentPlan,
            ImprovementPlan,
            ImprovementPriority,
        )
        from atlas.evolution.models import EvolutionProposal, ProposalStatus

        if self._approval_manager is None:
            raise RuntimeError("Approval manager is not available.")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        recovery_proposal_id = f"RECOVERY-{original_proposal.proposal_id}-{timestamp}"

        # Build a minimal ImprovementPlan for the recovery proposal.
        recovery_plan = ImprovementPlan(
            plan_id=f"PLAN-RECOVERY-{timestamp}",
            title=f"Recovery: {original_proposal.title}",
            description=(
                f"Recovery attempt for failed development "
                f"'{original_proposal.proposal_id}'. "
                f"Diagnosis: {diagnostic.cause}"
            ),
            priority=ImprovementPriority.HIGH,
        )

        # Create the recovery proposal referencing the original failure.
        recovery_proposal = EvolutionProposal(
            proposal_id=recovery_proposal_id,
            title=f"Recovery: {original_proposal.title}",
            summary=(
                f"Recovery attempt addressing {diagnostic.failure_class.value} "
                f"failure: {diagnostic.cause}"
            ),
            rationale=(
                f"Original development '{original_proposal.proposal_id}' failed "
                f"with {diagnostic.confidence.value} confidence. "
                f"Recovery rationale: {recovery.rationale}"
            ),
            expected_benefit=(
                f"Corrected implementation addressing: {diagnostic.cause}"
            ),
            risks=(
                "Recovery attempt based on diagnosis evidence. "
                "Original failure preserved for audit."
            ),
            impact_analysis=(
                f"Derived from original proposal components: "
                f"{', '.join(original_proposal.plan.target_components[:5]) or 'to be determined'}"
            ),
            implementation_approach=(
                f"1. Review original failure evidence.\n"
                f"2. Apply corrective strategy for: {diagnostic.cause}\n"
                f"3. Verify with existing test suite."
            ),
            plan=recovery_plan,
            status=ProposalStatus.DRAFT,
            metadata={
                "recovery": True,
                "original_proposal_id": original_proposal.proposal_id,
                "original_fingerprint": original_proposal.proposal_fingerprint,
                "diagnostic_failure_class": diagnostic.failure_class.value,
                "diagnostic_confidence": diagnostic.confidence.value,
                "diagnostic_cause": diagnostic.cause,
                "recovery_strategy": recovery.strategy.value,
            },
        )

        # Retain the live object and submit to ApprovalManager for a NEW
        # approval request with a distinct identity.
        self._register_evolution_proposal(recovery_proposal)
        approval_request = self._approval_manager.create_approval_request(recovery_proposal)
        self._register_approval_request(approval_request)

        return recovery_proposal.proposal_id, approval_request.request_id

    def _maybe_handle_verify(self, spec: TaskSpec) -> Message | None:
        """Handle an explicit VERIFICATION_REQUEST.

        Produces a read-only VerificationReport from an existing development
        result (original execution or recovery). Verifies ONLY the evidence
        already present in the DevelopmentRunResult. Never mutates anything,
        never executes, never recovers.

        Args:
            spec: the classified VERIFICATION_REQUEST TaskSpec.

        Returns:
            A Message describing the verification result.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. Verification requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"verification": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "Verification requires OWNER authority. "
                    "This session is not authorized to verify developments."
                ),
                metadata={"verification": {"status": "unauthorized"}},
            )

        state = self._state_manager.state if self._state_manager else None
        if state is None or not state.evolution_proposal_id:
            return Message(
                role="assistant",
                content=(
                    "There is no development result to verify. "
                    "Please investigate an issue, plan it, approve it, and "
                    "execute it first."
                ),
                metadata={"verification": {"status": "no_result"}},
            )

        # 3. Resolve the existing development result from the live registry.
        # The conversation service retains the EvolutionProposal; the full
        # DevelopmentRunResult evidence is reconstructed from preserved state.
        proposal = self._resolve_evolution_proposal(state.evolution_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The development proposal could not be resolved. "
                    "Please execute the development again."
                ),
                metadata={"verification": {"status": "proposal_not_found"}},
            )

        # 4. Reconstruct the DevelopmentRunResult evidence.
        result_standin = _RecoveryResultStandin.from_proposal(proposal)

        # 5. Produce the read-only verification report.
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        report = DevelopmentVerification().verify(result_standin)

        # 6. Report the verification result. Read-only; no mutation.
        lines = [
            "## Development Verification",
            "",
            f"**Proposal:** {proposal.proposal_id}",
            f"**Status:** {report.status.value}",
            f"**Iterations examined:** {report.iterations_examined}",
        ]
        if report.all_tests_passed is not None:
            lines.append(
                f"**All tests passed:** {'yes' if report.all_tests_passed else 'no'}"
            )
        if report.any_rollback:
            lines.append("**Rollback occurred:** yes")
        if report.changed_files:
            lines.append(f"**Changed files:** {', '.join(report.changed_files[:5])}")
        lines.append("")
        lines.append(f"**Evidence:** {report.evidence}")
        if report.message:
            lines.append(f"**Conclusion:** {report.message}")

        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={
                "verification": {
                    "status": report.status.value,
                    "iterations_examined": report.iterations_examined,
                    "all_tests_passed": report.all_tests_passed,
                    "any_rollback": report.any_rollback,
                    "changed_files": list(report.changed_files),
                    "evidence": report.evidence,
                    "proposal_id": proposal.proposal_id,
                },
            },
        )

    def _maybe_handle_report(self, spec: TaskSpec) -> Message | None:
        """Handle an explicit REPORT_REQUEST.

        Produces a read-only final lifecycle report aggregating evidence from
        the current session's completed development lifecycle:
        investigation → planning → approval → execution → failure → diagnosis →
        recovery → verification → final conclusion.

        Report NEVER:
        - Modifies any files
        - Calls ApplicationEngine.apply()
        - Creates execution authorization
        - Approves, authorizes, recovers, or retries anything
        - Invokes pytest/subprocesses

        Args:
            spec: the classified REPORT_REQUEST TaskSpec.

        Returns:
            A Message containing the structured lifecycle report.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. Reporting requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"report": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "Reporting requires OWNER authority. "
                    "This session is not authorized to request reports."
                ),
                metadata={"report": {"status": "unauthorized"}},
            )

        state = self._state_manager.state if self._state_manager else None
        if state is None or not state.evolution_proposal_id:
            return Message(
                role="assistant",
                content=(
                    "There is no development lifecycle to report on. "
                    "Please investigate an issue, plan it, approve it, and "
                    "execute it first."
                ),
                metadata={"report": {"status": "no_lifecycle"}},
            )

        # 3. Resolve the original proposal + approval from the live registries.
        proposal = self._resolve_evolution_proposal(state.evolution_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The development proposal could not be resolved. "
                    "Please execute the development again."
                ),
                metadata={"report": {"status": "proposal_not_found"}},
            )
        approval = self._resolve_approved_request(state.evolution_proposal_id)
        if approval is None:
            return Message(
                role="assistant",
                content=(
                    "The approval request could not be resolved. "
                    "Please approve the proposal again."
                ),
                metadata={"report": {"status": "approval_not_found"}},
            )

        # 4. Resolve recovery proposal + approval if present.
        recovery_proposal = None
        recovery_approval = None
        if state.recovery_proposal_id:
            recovery_proposal = self._resolve_evolution_proposal(
                state.recovery_proposal_id
            )
            if recovery_proposal is not None:
                recovery_approval = self._resolve_approved_request(
                    state.recovery_proposal_id
                )

        # 5. Build the lifecycle report from existing evidence.
        from atlas.evolution.development_report import DevelopmentReportBuilder

        report = DevelopmentReportBuilder().build(
            state=state,
            proposal=proposal,
            approval=approval,
            recovery_proposal=recovery_proposal,
            recovery_approval=recovery_approval,
        )

        # 6. Render the report as a conversational Message.
        lines = [
            "## Development Lifecycle Report",
            "",
            f"**Investigation target:** {report.investigation_target or 'unknown'}",
            f"**Original proposal:** {report.original_proposal_id or 'unknown'}",
            f"**Original approval:** {report.original_approval_id or 'unknown'}",
            f"**Original execution status:** {report.original_execution_status or 'unknown'}",
        ]

        if report.recovery_proposal_id:
            lines.append("")
            lines.append(f"**Recovery proposal:** {report.recovery_proposal_id}")
            lines.append(f"**Recovery approval:** {report.recovery_approval_id or 'unknown'}")
            lines.append(
                f"**Recovery execution status:** "
                f"{report.recovery_execution_status or 'unknown'}"
            )

        if report.diagnosis is not None:
            lines.append("")
            lines.append("### Diagnosis")
            lines.append(f"- **Failure class:** {report.diagnosis.failure_class.value}")
            lines.append(f"- **Confidence:** {report.diagnosis.confidence.value}")
            lines.append(f"- **Cause:** {report.diagnosis.cause}")

        if report.recovery_decision is not None:
            lines.append("")
            lines.append("### Recovery Decision")
            lines.append(f"- **Recoverable:** {'yes' if report.recovery_decision.recoverable else 'no'}")
            lines.append(f"- **Strategy:** {report.recovery_decision.strategy.value}")
            lines.append(f"- **Rationale:** {report.recovery_decision.rationale}")

        if report.verification is not None:
            lines.append("")
            lines.append("### Verification")
            lines.append(f"- **Status:** {report.verification.status.value}")
            lines.append(f"- **Iterations examined:** {report.verification.iterations_examined}")
            if report.verification.all_tests_passed is not None:
                lines.append(
                    f"- **All tests passed:** "
                    f"{'yes' if report.verification.all_tests_passed else 'no'}"
                )
            if report.verification.any_rollback:
                lines.append("- **Rollback occurred:** yes")
            if report.verification.changed_files:
                lines.append(
                    f"- **Changed files:** "
                    f"{', '.join(report.verification.changed_files[:5])}"
                )

        lines.append("")
        lines.append(f"### Final Conclusion: {report.final_conclusion.value.upper()}")
        lines.append("")
        lines.append(report.evidence)

        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={
                "report": {
                    "status": "complete",
                    "final_conclusion": report.final_conclusion.value,
                    "investigation_target": report.investigation_target,
                    "original_proposal_id": report.original_proposal_id,
                    "original_approval_id": report.original_approval_id,
                    "original_execution_status": report.original_execution_status,
                    "recovery_proposal_id": report.recovery_proposal_id,
                    "recovery_approval_id": report.recovery_approval_id,
                    "recovery_execution_status": report.recovery_execution_status,
                    "has_diagnosis": report.diagnosis is not None,
                    "has_recovery_decision": report.recovery_decision is not None,
                    "verification_status": (
                        report.verification.status.value
                        if report.verification is not None
                        else None
                    ),
                },
            },
        )

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
