"""
Atlas Conversation Service

Coordinates Atlas conversations.
"""

from __future__ import annotations

import json
import re

from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol

from atlas.ai.routing.models import LOCAL_PROVIDER_NAMES, RoutingRequest
from atlas.cognition.api import CognitionAPI
from atlas.conversation.context import ContextManager
from atlas.conversation.conversation import Conversation
from atlas.conversation.development_intake import task_spec_to_development_need
from atlas.conversation.engine import ConversationEngine
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.execution import Level3ExecutionService
from atlas.conversation.investigation import (
    InvestigationProposal,
    InvestigationProposalConverter,
    InvestigationProposalGenerator,
    InvestigationReport,
    InvestigationService,
)
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.reference_resolution import (
    CAPTURED_ENTITY_FIELD,
    ConversationReferenceResolver,
    is_repeat_request,
)
from atlas.conversation.world_state import (
    MAX_WORLD_TOPICS,
    match_topics,
)
from atlas.conversation.clarification import (
    KIND_REFERENCE,
    KIND_SUBJECT,
    KIND_TOPIC,
    build_question,
    candidate_matches,
)
from atlas.conversation.multi_step import (
    DEP_RESULT,
    EXEC_ANALYSIS,
    STATUS_BLOCKED,
    STATUS_GOVERNED,
    STATUS_UNSUPPORTED,
    build_execution_steps,
    build_multi_step,
)
from atlas.conversation.research_objective import research_subject_gap
from atlas.conversation.entity_capture import CapturedEntity, capture_named_entities
from atlas.conversation.development_outcome_reporter import (
    DevelopmentOutcomeReporter,
    snapshot_from_result,
)
from atlas.conversation.history import History
from atlas.conversation.conversation_context import build_conversation_context
# L7 (entry) — the deterministic floor's no-answer outcome is the only existing
# signal that separates "answered deterministically" from "declined", so the
# eligibility boundary reads its bound name rather than a string literal.
from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_UNSUPPORTED,
    BUILTIN_INTENT_VALIDATED_KNOWLEDGE,
    is_bounded_reference_subject,
    is_explanatory_self_knowledge,
    is_store_recall_shaped,
    is_validated_knowledge_shaped,
    knowledge_topic,
    research_request_subject,
    substitute_reference_subject,
)
from atlas.conversation.turn_role import TurnRole, detect_turn_role
from atlas.conversation.turn_meaning import TurnMeaning, build_turn_meaning
from atlas.conversation.meaning import (
    ATLAS_MEANING_KEY,
    AtlasMeaning,
    build_atlas_meaning,
)
from atlas.conversation.dialogue_state import outcome_from
from atlas.conversation.communicative_function import (
    FUNCTION_QUERY_CAUSE,
    FUNCTION_QUERY_RESULT,
    FUNCTION_QUERY_STATUS,
    QUERY_FUNCTIONS,
    resolve_routing,
)
from atlas.conversation.dialogue_thread import thread_outcome_from
from atlas.conversation.response import (
    SHAPE_CLARIFICATION,
    SHAPE_EXPLANATION,
    SHAPE_RESULT_SUMMARY,
    SHAPE_UNAVAILABLE,
    compose_from_decision,
    render_response,
)
from atlas.conversation.linguistic import (
    LINGUISTIC_EVIDENCE_KEY,
    LinguisticEvidence,
    LinguisticEvidenceService,
    NeutralLinguisticProvider,
)
from atlas.conversation.learned_proposer import REFERENCE_PROPOSALS_KEY
from atlas.conversation.message import Message
from atlas.conversation.prompt_builder import PromptBuilder
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.memory.context.context_engine import ContextEngine
from atlas.ai.ai_service import AIService
from atlas.storage.conversation_storage import ConversationStorage

if TYPE_CHECKING:
    from atlas.conversation.builtin_response import BuiltinResponseService
    from atlas.conversation.conversation_context import ConversationContext
    from atlas.conversation.deterministic_fallback import DeterministicFallbackResolver
    from atlas.conversation.entity_identification import EntityCatalog
    from atlas.session.context import SessionContext
    from atlas.session.models import Session

#: Bound applied to the recorded pending clarification question (L6).
_MAX_PENDING_QUESTION_CHARS: int = 400

#: Bound applied to a retained orchestration result recorded in the existing
#: ``ConversationState.latest_result`` slot (L5). Only a bounded, already
#: produced report line is retained; no report object or source corpus is
#: stored.
_MAX_ORCHESTRATION_RESULT_CHARS: int = 500

#: Bounded metadata key carrying the L7 cognition-entry eligibility signal on
#: the deterministic floor's reply. Data only — it never routes anything.
REASONING_ELIGIBILITY_KEY: str = "reasoning_eligibility"


def _normalized_subject(text: str) -> str:
    """Case/punctuation-insensitive comparison key for a knowledge subject."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


#: A leading subordinate clause marks a turn whose existing path (clarification
#: or a governed route) must keep precedence over the G1 knowledge seam.
_SUBORDINATE_CLAUSE_RE = re.compile(
    r",\s*(?:but|and|then)\b|"
    r"^\s*(?:before|after|while|when|if|once|although|though|as soon as)\b",
    re.IGNORECASE,
)


#: Casual task types the deterministic builtin floor may claim. Local mirror of
#: the builtin claim contract so this module can state the eligibility boundary
#: without depending on the claim logic; every governed / Phase 3-5 task type is
#: excluded by construction.
_CASUAL_TASK_TYPES: frozenset[TaskType] = frozenset(
    {TaskType.CONVERSATION, TaskType.UNKNOWN, TaskType.QUESTION}
)

#: Checkpoint 4 — task types whose turn is INFORMATIONAL, so an already-bound
#: reference is answered from retained conversation state instead of being
#: handed to a research/knowledge/orchestration route. Governed request types
#: are deliberately absent: they keep their own governed route.
_INFORMATIONAL_TASK_TYPES: frozenset[str] = frozenset(
    {task.value for task in _CASUAL_TASK_TYPES} | {TaskType.INFORMATION_REQUEST.value}
)

#: The shared semantic frame's SELF_KNOWLEDGE domain value (``SemanticDomain``):
#: questions about Atlas itself, owned by the self-knowledge/architecture surfaces.
_SELF_KNOWLEDGE_DOMAIN: str = "self_knowledge"

#: The shared semantic frame's CASUAL domain value: open-ended conversation with
#: no operational subject, owned by the open-ended/model path.
_CASUAL_DOMAIN: str = "casual"

#: Stage 1–10 audit (ownership boundary) — deterministic TaskTypes owned by an
#: EXISTING surface whose handler must keep FIRST opportunity over the additive
#: contextual result-query route. Two groups:
#:
#:   * a DEDICATED governed operation surface (impact / development / planning /
#:     execution / recovery / verification / report / autonomy / action);
#:   * the INFORMATIONAL family, owned by the existing local-first knowledge path
#:     and the builtin knowledge / self-knowledge / architecture / recall
#:     surfaces.
#:
#: Investigation is deliberately EXCLUDED: its cue family is noisy (noun forms),
#: so the communicative-function layer must adjudicate those turns — that is the
#: Stage 4 capability this route exists to provide.
_CONTEXTUAL_DEFERRED_TASK_TYPES: frozenset[str] = frozenset(
    {
        TaskType.REPOSITORY_IMPACT_REQUEST.value,
        TaskType.DEVELOPMENT_REQUEST.value,
        TaskType.ACTION_REQUEST.value,
        TaskType.PLANNING_REQUEST.value,
        TaskType.EXECUTION_REQUEST.value,
        TaskType.RECOVERY_REQUEST.value,
        TaskType.VERIFICATION_REQUEST.value,
        TaskType.REPORT_REQUEST.value,
        TaskType.AUTONOMY_REQUEST.value,
        TaskType.L2_AUTONOMY_REQUEST.value,
        TaskType.L3_AUTONOMY_REQUEST.value,
        TaskType.L4_AUTONOMY_REQUEST.value,
        TaskType.L5_AUTONOMY_REQUEST.value,
    }
)

#: Step 2 — bounded, explicit status forms for the ACTIVE goal/plan. A turn is
#: answered from retained plan state ONLY when the whole (normalized) turn is
#: exactly one of these; every other turn keeps its existing route unchanged.
_GOAL_STATUS_FORMS: frozenset[str] = frozenset(
    {
        "plan status",
        "goal status",
        "what is the plan status",
        "what is the goal status",
        "what s the plan status",
        "what s the goal status",
    }
)

#: Step 2 (plan resumption) — bounded, explicit resumption forms. These are
#: ADDITIVE to the existing continuation semantics (``TurnRole.CONTINUATION``,
#: which already covers "continue" / "go on" / "keep going" / "carry on"): a
#: turn matching one of these, with an UNFINISHED retained plan, continues it.
_GOAL_RESUME_FORMS: frozenset[str] = frozenset(
    {
        "continue the plan",
        "continue the goal",
        "resume the plan",
        "resume the goal",
        "complete the goal",
        "finish the plan",
        "finish the goal",
        "finish the remaining step",
        "finish the remaining steps",
        "go ahead with the remaining step",
        "go ahead with the remaining steps",
        "carry out the remaining step",
        "do the remaining step",
    }
)

#: L3 illocutions that describe something the user is asking FOR; a bare
#: statement is not a reasoning request.
_ELIGIBLE_ILLOCUTIONS: frozenset[str] = frozenset({"question", "request"})


def reasoning_eligibility(
    spec: TaskSpec | None,
    builtin_intent: str | None,
) -> dict[str, Any] | None:
    """Return the bounded L7 cognition-entry eligibility signal, or ``None``.

    L7 (entry) — the deterministic floor has exactly one outcome that admits it
    had no answer: :data:`BUILTIN_INTENT_UNSUPPORTED`. That outcome is the only
    signal the current architecture produces for "declined" as opposed to
    "answered deterministically", so this helper makes it explicit, bounded and
    testable as data.

    It is deliberately conservative and fail-closed. A signal is returned only
    when ALL of the following hold, and ``None`` otherwise:

      * the turn has a :class:`TaskSpec` (intake ran);
      * the builtin floor answered with its no-answer outcome;
      * L6 does not require clarification first;
      * the task type is casual (governed / Phase 3-5 ownership is preserved by
        construction);
      * the existing L3 utterance meaning says the user asked a question or made
        a request.

    Nothing is delegated: it does not route, does not call cognition, does not
    touch the AI path, and never alters a user-visible value.
    """
    if spec is None or not isinstance(spec, TaskSpec):
        return None
    if builtin_intent != BUILTIN_INTENT_UNSUPPORTED:
        return None
    if bool(getattr(spec, "needs_clarification", False)):
        return None
    if spec.task_type not in _CASUAL_TASK_TYPES:
        return None
    context = getattr(spec, "context", None)
    meaning = context.get("utterance_meaning") if isinstance(context, dict) else None
    if not isinstance(meaning, dict):
        return None
    illocution = meaning.get("illocution")
    if not isinstance(illocution, str) or illocution not in _ELIGIBLE_ILLOCUTIONS:
        return None
    operation = meaning.get("operation")
    return {
        "eligible": True,
        "task_type": spec.task_type.value,
        "illocution": illocution,
        "operation": operation if isinstance(operation, str) else None,
    }


def _delegated_by_eligibility(message: Message) -> bool:
    """L8-c — True when the L7 eligibility signal explicitly permits cognition.

    Consumes the bounded signal the deterministic floor already produced
    (``REASONING_ELIGIBILITY_KEY``) instead of recreating the eligibility
    contract here. The signal is only ever attached to casual,
    non-clarification turns the floor could not answer, so Phase 3-5 ownership
    is preserved by construction.
    """
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    signal = metadata.get(REASONING_ELIGIBILITY_KEY)
    return bool(isinstance(signal, dict) and signal.get("eligible") is True)


def _pipeline_requires_clarification(data: Any) -> bool:
    """L8-b-ii — the L6 veto, read from the transported pipeline payload.

    Fail-closed: a blocked plan or an explicit clarification requirement in
    either the reasoning or the planning payload means the pipeline did not
    complete an answer, so nothing it produced may be surfaced.
    """
    if not isinstance(data, dict):
        return False
    for key in ("planning", "reasoning"):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        if bool(block.get("requires_clarification")):
            return True
        status = block.get("status")
        if isinstance(status, str) and status.strip().lower() == "blocked":
            return True
    return False


def _usable_pipeline_response(data: Any) -> str | None:
    """L8-b-ii — the bounded, evidence-backed response-precedence test.

    A pipeline answer is usable only when it is a non-empty string, the turn is
    not L6-blocked, a provider identity is present, and that provider is NOT the
    existing local no-network tier (``LOCAL_PROVIDER_NAMES``). Non-empty text
    alone is never sufficient, and no answer is ever invented from planning
    data.
    """
    if not isinstance(data, dict):
        return None
    if _pipeline_requires_clarification(data):
        return None
    answer = data.get("final_response")
    if not isinstance(answer, str) or not answer.strip():
        return None
    provenance = data.get("ai_provenance")
    if not isinstance(provenance, dict):
        return None
    provider = provenance.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        return None
    if provider.strip() in LOCAL_PROVIDER_NAMES:
        return None
    return answer.strip()


def _external_provider_provenance(provider: Any, model: Any) -> dict[str, str] | None:
    """Bounded provider/model provenance for a NON-local provider answer.

    Task 1.1 — the conversation layer now reports whether its final answer came
    from an actual external/model provider. The classification reuses the
    EXISTING authoritative boundary (``LOCAL_PROVIDER_NAMES``, already consulted
    by the L8-b-ii precedence gate above) instead of any provider-specific
    check: an absent identity, or the deterministic local no-network tier,
    yields ``None``, so a response can never be reported as model-backed merely
    because a model request was attempted.
    """
    provider_name = str(provider or "").strip()
    if not provider_name or provider_name in LOCAL_PROVIDER_NAMES:
        return None
    provenance = {"provider": provider_name}
    model_name = str(model or "").strip()
    if model_name:
        provenance["model"] = model_name
    return provenance


def _pipeline_provider_provenance(data: Any) -> dict[str, str] | None:
    """Bounded external-provider provenance of a pipeline answer, or ``None``.

    Reads the same ``ai_provenance`` payload the L8-b-ii precedence gate already
    validated; nothing is inferred from a mere attempt.
    """
    if not isinstance(data, dict):
        return None
    provenance = data.get("ai_provenance")
    if not isinstance(provenance, dict):
        return None
    return _external_provider_provenance(
        provenance.get("provider"), provenance.get("model")
    )


def _pipeline_response_metadata(data: Any) -> dict[str, Any]:
    """Metadata for an accepted pipeline answer (L8-b-ii).

    The existing cognition marker is always present. Task 1.1 additionally
    reports a genuine external/model answer as model-backed, together with its
    bounded provenance, so a model-generated answer is not indistinguishable
    from the deterministic floor.
    """
    metadata: dict[str, Any] = {"cognition": {"source": "pipeline_final_response"}}
    provenance = _pipeline_provider_provenance(data)
    if provenance is not None:
        metadata["model_used"] = True
        metadata["ai_provenance"] = provenance
    return metadata


def _model_response_metadata(response: Any) -> dict[str, Any]:
    """Metadata for an answer returned by the residual AI path (Task 1.1).

    ``model_used`` is True only for a genuine external/model provider — never the
    deterministic local no-network tier, and never merely because a request was
    attempted. Absent/unknown provider identity reports False and claims no
    provenance.
    """
    provenance = _external_provider_provenance(
        getattr(response, "provider", None),
        getattr(response, "model", None),
    )
    metadata: dict[str, Any] = {"model_used": provenance is not None}
    if provenance is not None:
        metadata["ai_provenance"] = provenance
    return metadata

#: Governed operations whose handler is read-only and accepts a retained text
#: operand, so a bounded repeat request may safely re-enter the SAME existing
#: handler with the retained operand. Every other retained operation kind is
#: refused on repeat (never silently re-executed).
_REPEATABLE_READ_ONLY_KINDS: frozenset[str] = frozenset(
    {
        TaskType.INVESTIGATION_REQUEST.value,
        TaskType.REPOSITORY_IMPACT_REQUEST.value,
    }
)


class ApprovalManagerProtocol(Protocol):
    """Interface for the approval manager injected by the kernel.

    The conversation layer depends on this protocol, not on the concrete
    evolution.approval_manager.ApprovalManager, preserving the dependency
    direction: conversation -> injected boundary -> kernel -> evolution.
    """

    def create_approval_request(self, proposal: Any) -> Any:
        """Create an approval request for a proposal."""
        ...

    def approve(self, request: Any, comment: str) -> None:
        """Approve a pending request."""
        ...

    def reject(self, request: Any, reason: str) -> None:
        """Reject a pending request."""
        ...

    def update_proposal_from_decision(self, proposal: Any, request: Any) -> None:
        """Update a proposal's status based on the approval decision."""
        ...


class AutonomyDecisionProtocol(Protocol):
    """Interface for an autonomy decision returned by the injected boundary.

    The conversation layer consumes these attributes without constructing
    evolution autonomy machinery directly.
    """

    can_proceed: bool
    reason: str
    escalation_required: bool
    authorization_mode: Any
    evidence: dict[str, Any]


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
        builtin_response: BuiltinResponseService | None = None,
        provider_call_timeout_s: float | None = None,
        development_need_coordinator: DevelopmentNeedCoordinator | None = None,
        outcome_reporter: DevelopmentOutcomeReporter | None = None,
        state_manager: ConversationStateManager | None = None,
        reference_resolver: ConversationReferenceResolver | None = None,
        entity_catalog: EntityCatalog | None = None,
        investigation_service: InvestigationService | None = None,
        execution_service: Level3ExecutionService | None = None,
        approval_manager: ApprovalManagerProtocol | None = None,
        development_execution_bridge: Callable[..., Any] | None = None,
        proposal_change_supplier: Any | None = None,
        development_driver_bridge: Callable[..., Any] | None = None,
        external_research_bridge: Callable[..., Any] | None = None,
        autonomy_check: Callable[..., AutonomyDecisionProtocol] | None = None,
        goal_orchestration_resolver: Callable[..., Any] | None = None,
        goal_resume_resolver: Callable[..., Any] | None = None,
        linguistic_provider: Any | None = None,
        learned_reference_proposer: Any | None = None,
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

            builtin_response:
                Optional BuiltinResponseService for the model-independent
                conversational path. When set, casual conversational turns
                (CONVERSATION / UNKNOWN / QUESTION, never needs-clarification)
                are answered deterministically without calling any AI
                provider. Governed lifecycle turns always return ``None`` from
                the builtin service and continue through the existing
                pipeline unchanged. Provider interfaces are preserved for
                optional future augmentation but are not used by this path.

            provider_call_timeout_s:
                Optional per-call bound (seconds) for an opted-in external
                provider reached through the residual AI path. Carried in
                the routing metadata so the provider call can never hang
                for the full configured provider timeout during ordinary
                conversation. None (default) keeps provider defaults.

            approval_manager:
                Optional approval manager (injected by the kernel) for creating
                real approval requests. When ``None``, planning requests cannot
                create approval requests.

            development_execution_bridge:
                Optional duck-typed callable that bridges an already-approved
                conversational proposal/request into the EXISTING kernel
                governed-development-execution infrastructure. Signature:

                    (session_context, proposal, request) -> Message

                When ``None``, execution requests cannot be carried out.

            proposal_change_supplier:
                Optional F9 ``ChangeSupplier`` consulted during planning-proposal
                conversion (BEFORE approval) so the conversational proposal can
                carry an exact, bounded sandbox workload under the existing F9
                metadata convention. When ``None`` (the default), planning
                remains evidence-only and execution fails closed with
                ``INVALID_OBJECTIVE`` exactly as before. The supplier receives
                data only and can never mutate proposals, approvals, or state.

            development_driver_bridge:
                G3 — optional duck-typed callable mapping a DEVELOPMENT_REQUEST
                :class:`TaskSpec` into a conversational :class:`Message` (or
                string) by routing it through the EXISTING governed
                DevelopmentDriver. Consulted AFTER the B3 clarification gate and
                BEFORE the legacy F9 ``development_bridge``; this module never
                imports the evolution package, never approves, never promotes, and
                ``tick()`` never invokes it. When ``None`` (or raising), the
                legacy route is preserved verbatim.

            autonomy_check:
                Optional callable injected by the kernel that performs an
                autonomy check for a given proposal, session, and level,
                returning an :class:`AutonomyDecisionProtocol`. The conversation
                layer never constructs evolution autonomy machinery directly;
                this boundary keeps the dependency direction correct
                (conversation -> kernel -> evolution). When ``None``, autonomy
                requests fail closed and are denied.

            external_research_bridge:
                Temporary Roadmap Step 4 — optional duck-typed callable mapping a
                bounded external-research turn into a conversational
                :class:`Message`. Signature:

                    (text, target) -> Message | None

                where ``target`` is the parse of the turn's explicit external
                source (a URL or a GitHub repository). The kernel performs the
                acquisition through the EXISTING governed mechanisms; this module
                never imports the research package, never enables a source, never
                authorizes, and ``tick()`` never invokes it. When ``None`` (or
                raising/declining), every existing route is preserved verbatim.
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
        # D1 — deterministic Conversation Engine: interpretation + bounded
        # semantic projection only. It never routes, authorizes, or executes;
        # the existing governed handler cascade below remains authoritative.
        self._engine: ConversationEngine | None = (
            ConversationEngine(task_intake=task_intake)
            if task_intake is not None
            else None
        )
        self._development_bridge = development_bridge
        #: G3 — optional duck-typed governed self-development route (the existing
        #: bounded DevelopmentDriver, kernel-owned). Consulted for a
        #: DEVELOPMENT_REQUEST after the B3 clarification gate and before the
        #: legacy F9 bridge. Duck-typed and fail-soft: absent or raising keeps the
        #: legacy route verbatim. It grants no authority here and never promotes.
        self._development_driver_bridge = development_driver_bridge
        #: Temporary Roadmap Step 4 — optional duck-typed bridge that performs ONE
        #: GOVERNED external-research turn. Signature: ``(text, target) -> Message
        #: | None`` where ``target`` is the bounded parse of the turn's external
        #: source. Kernel-owned and duck-typed (this module never imports
        #: atlas.research). Absent, declining or raising keeps every existing route
        #: verbatim; it authorizes nothing and acquires nothing by itself.
        self._external_research_bridge = external_research_bridge
        self._orchestration_resolver = orchestration_resolver
        #: Step 2 — optional duck-typed bridge that SEQUENCES a bounded
        #: multi-step goal through the EXISTING OrchestrationExecutor. Signature:
        #: ``(text, steps, session_context) -> Message | None``. Kernel-owned and
        #: duck-typed (this module never imports atlas.orchestration). Absent or
        #: raising keeps every existing route verbatim; it grants no authority.
        self._goal_orchestration_resolver = goal_orchestration_resolver
        #: Step 2 (plan resumption) — optional duck-typed bridge that CONTINUES
        #: the retained unfinished plan through the EXISTING executor.
        #: Signature: ``(plan_state, session_context) -> Message | None``.
        #: Kernel-owned and duck-typed; absent or raising keeps every existing
        #: route verbatim and grants no authority.
        self._goal_resume_resolver = goal_resume_resolver
        self._fallback_resolver = fallback_resolver
        self._builtin_response = builtin_response
        self._provider_call_timeout_s = (
            float(provider_call_timeout_s)
            if provider_call_timeout_s is not None
            else None
        )
        self._development_need_coordinator = development_need_coordinator
        self._outcome_reporter = outcome_reporter
        self._state_manager = state_manager or ConversationStateManager()
        self._investigation_service = investigation_service
        self._proposal_generator = InvestigationProposalGenerator()
        self._proposal_converter = InvestigationProposalConverter(
            change_supplier=proposal_change_supplier
        )
        self._execution_service = execution_service
        self._approval_manager = approval_manager
        self._development_execution_bridge = development_execution_bridge
        self._autonomy_check = autonomy_check
        self._reference_resolver = reference_resolver or ConversationReferenceResolver()
        self._entity_catalog = entity_catalog
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

        # C3.3 — Retained evidence for the most recent read-only investigation,
        # so the report path can synthesize it deterministically without
        # re-gathering evidence. Conversation-scoped and never persisted;
        # mirrors the existing transient registries above.
        self._last_investigation_report: InvestigationReport | None = None

        # Stage 1 — the bounded L1 meaning of the most recent interpreted turn.
        # Conversation-scoped, transient and authority-free; observable by tests
        # and available to later conversational stages. Never persisted.
        self._last_meaning: AtlasMeaning | None = None

        # Stage 4 — the most recent communicative-function routing decision
        # (inspectable/testing seam). Conversation-scoped, transient, and
        # descriptive only: it never authorizes or executes anything.
        self._last_routing_decision: Any | None = None

        # Stage 6 — expose the bounded salience/ambiguity assessment this turn
        # produced (inspectable/testing seam; descriptive only).
        self._last_salience_assessment: dict | None = None

        # Stage 7 — the bounded response plan this turn produced (inspectable/
        # testing seam; descriptive only, never authority).
        self._last_response_plan: dict | None = None

        # Stage 8 — optional linguistic-evidence seam. Advisory only: it produces
        # bounded evidence for the turn; Atlas's deterministic interpretation
        # remains authoritative. Defaults to the Atlas-native deterministic
        # provider, so the seam is live without any external dependency.
        self._linguistic = LinguisticEvidenceService(
            providers=(linguistic_provider,)
            if linguistic_provider is not None
            else (NeutralLinguisticProvider(),)
        )
        self._last_linguistic_evidence: LinguisticEvidence | None = None
        self._last_linguistic_adjudication: dict | None = None

        # Stage 9 — optional LOCAL learned reference proposer. OFF by default
        # (None): deterministic operation is unchanged. When wired, its bounded
        # proposals are advisory evidence only — Atlas (Stage 6) decides.
        self._learned_proposer = learned_reference_proposer
        self._last_reference_proposals: dict | None = None

        # Stage 5 — the latest discourse-operation referent id from BEFORE the
        # current turn, so the thread update can tell a NEWLY completed operation
        # from a previously retained one. Conversation-scoped and transient.
        self._pre_turn_operation_id: str = ""

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

    @property
    def entity_catalog(self) -> EntityCatalog | None:
        """Return the bounded known-entity catalog used for L4 identification."""
        return self._entity_catalog

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
    def builtin_response(self) -> BuiltinResponseService | None:
        return self._builtin_response

    def set_builtin_response(self, service: BuiltinResponseService | None) -> None:
        self._builtin_response = service

    def _maybe_handle_builtin_response(
        self,
        spec: TaskSpec | None,
        text: str,
    ) -> Message | None:
        """Answer a casual conversational turn without any AI provider.

        Runs after every governed lifecycle handler and before
        orchestration/cognition/AI. Returns ``None`` (fall through) unless
        the builtin service is wired and claims the turn. Governed,
        clarification-pending, legacy (spec-less), and non-casual turns are
        never claimed.
        """
        if self._builtin_response is None or spec is None:
            return None
        message = self._builtin_response.respond(
            text,
            spec=spec,
            message_count=len(self._conversation.messages),
            context=self._build_conversation_context(),
        )
        # L7 (entry) — record the bounded eligibility signal as DATA when the
        # deterministic floor answered with its no-answer outcome. Purely
        # additive metadata: the reply text and the cascade are unchanged and no
        # turn is delegated anywhere.
        if isinstance(message, Message) and isinstance(message.metadata, dict):
            signal = reasoning_eligibility(
                spec, message.metadata.get("builtin_intent")
            )
            if signal is not None:
                message.metadata[REASONING_ELIGIBILITY_KEY] = signal
            self._record_knowledge_result(message)
        return message

    def _record_knowledge_result(self, message: Message) -> None:
        """Retain a bounded snapshot of a knowledge answer for follow-ups.

        Evidence-driven improvement 1 — facts only (query/status/content),
        bounded to ``last_knowledge``; never authority, never a second store.
        """
        metadata = message.metadata or {}
        if metadata.get("builtin_intent") != BUILTIN_INTENT_VALIDATED_KNOWLEDGE:
            return
        content = message.content if isinstance(message.content, str) else ""
        self._state_manager.update(
            last_knowledge={
                "query": metadata.get("validated_query"),
                "status": metadata.get("validated_knowledge_status"),
                "content": content[:600],
            }
        )
        # Step 8 — a knowledge turn establishes the queried subject as the ACTIVE
        # world topic (a topic switch demotes the previous active topic to
        # bounded history). Facts only; no authority, no execution.
        self._observe_world_topic(
            metadata.get("validated_query"), "knowledge", result_ref=""
        )

    def _observe_world_topic(
        self,
        label: Any,
        kind: str,
        *,
        result_ref: Any = "",
    ) -> None:
        """Record a bounded conversational world topic (Step 8). Fail-soft.

        Conversation-scoped, deterministic representation only. A blank label or
        a missing state manager is ignored, so this can never break a turn and
        never invents state.
        """
        if self._state_manager is None:
            return
        if not isinstance(label, str) or not label.strip():
            return
        try:
            self._state_manager.observe_world_topic(
                label.strip(),
                kind,
                result_ref=result_ref if isinstance(result_ref, str) else "",
                turn_index=len(self._conversation.messages),
            )
        except Exception:  # fail-soft: world-state recording never breaks a turn
            return

    def _maybe_handle_capability_state_question(self, text: str) -> Message | None:
        """Step 13 — answer a bounded capability-STATE question (read-only).

        Delegates to the builtin service, whose single authoritative matcher
        answers ONLY a bounded state-question form naming a capability that
        resolves against the SAME unified capability model the kernel exposes
        (or the bounded "which capabilities are unavailable" inventory form).
        An unresolvable name declines, so an ordinary request keeps its existing
        route; nothing is executed, authorized or mutated.
        """
        if self._builtin_response is None:
            return None
        return self._builtin_response.match_capability_state_question(text)

    def _maybe_handle_architecture_question(self, text: str) -> Message | None:
        """Step 14 — answer a bounded architecture self-understanding question.

        Delegates to the builtin service, whose single authoritative matcher
        answers ONLY a bounded ownership / component-responsibility /
        governance-boundary / known-unknown form from the SAME architecture and
        capability models the kernel exposes. A named form that does not resolve
        declines, so an ordinary request keeps its existing route (an architecture
        question is never turned into an operational one); nothing is executed,
        authorized or mutated.
        """
        if self._builtin_response is None:
            return None
        return self._builtin_response.match_architecture_question(text)

    def _maybe_handle_capability_detail_request(self, text: str) -> Message | None:
        """C4.1 — honour an explicit ``explain <name>`` request for a
        REGISTERED capability/tool before generic investigation/research cue
        matching can preempt it.

        The builtin service is the single authoritative matcher: it claims the
        turn ONLY when the named capability/tool actually resolves against the
        registries, so nothing is fabricated and an unknown name still falls
        through to the existing fail-closed path. No investigation, research,
        development, or governance behavior is consulted or changed here, and
        no authority is created.
        """
        if self._builtin_response is None:
            return None
        detail = self._builtin_response.match_registered_capability_detail(text)
        if detail is not None:
            return detail
        # Temporary Roadmap Step 1 — the SAME capability-detail surface also owns
        # the bounded REQUIREMENTS phrasing for a named capability ("what does
        # the research capability require?"), which previously fell through to
        # the generic knowledge route. Same owner, same unified model, same
        # fail-closed rule: an unresolvable name declines.
        return self._builtin_response.match_capability_requirements(text)

    def _maybe_handle_knowledge_state_question(self, text: str) -> Message | None:
        """Temporary Roadmap Step 1 — the state of Atlas's OWN retained knowledge.

        Read-only: the builtin service projects the EXISTING temporal seam's own
        verdict (temporal status / age / standing), so no freshness is ever
        claimed from missing evidence and nothing is acquired or changed. Declines
        when the seam is unwired, so the existing route is preserved.
        """
        if self._builtin_response is None:
            return None
        return self._builtin_response.match_knowledge_state_question(text)

    def _maybe_handle_source_authorization_request(self, text: str) -> Message | None:
        """Temporary Roadmap Step 1 — EXPLAIN source authorization, never change it.

        A bounded explanation of the EXISTING deny-by-default host policy and of
        the fact that authorizing a source is an OWNER configuration act. It
        performs no authorization, writes no configuration, and discloses no
        configured value; a turn that does not name a source/host object (e.g. a
        development approval) is never claimed here.
        """
        if self._builtin_response is None:
            return None
        return self._builtin_response.match_source_authorization_question(text)

    def _maybe_handle_external_research(self, text: str) -> Message | None:
        """Temporary Roadmap Step 4 — a GOVERNED external-research request.

        The conversation layer only parses the bounded TARGET (a URL or a GitHub
        repository) of a turn that also carries a research/acquisition cue; the
        kernel's injected bridge performs the acquisition through the EXISTING
        governed mechanisms (deny-by-default host policy, provenance, retention)
        and reports exactly what they returned. Declines when the turn names no
        target, when the bridge is unwired, or when the bridge raises — so every
        other turn keeps its existing route and nothing is acquired implicitly.
        """
        if self._builtin_response is None or self._external_research_bridge is None:
            return None
        target = self._builtin_response.parse_external_research_target(text)
        if not target:
            return None
        try:
            message = self._external_research_bridge(text, target)
        except Exception:  # fail closed -> the existing route is preserved
            return None
        if isinstance(message, Message):
            return message
        return None

    def _maybe_handle_evidence_self_knowledge(self, text: str) -> Message | None:
        """Evidence-driven: Atlas-specific self-knowledge topics (read-only).

        Claimed before the development/execution handlers so an informational
        question about Atlas's own flow/governance can never be answered as a
        development action. Grants no authority; creates no proposal.
        """
        if self._builtin_response is None:
            return None
        return self._builtin_response.match_self_knowledge_topic(text)

    def _maybe_answer_resolved_reference(
        self, text: str, spec: TaskSpec | None
    ) -> Message | None:
        """Checkpoint 4 — answer a PURE reference turn from the bound referent.

        The deterministic resolver has already bound the reference to a retained
        :class:`ConversationState` fact; this surfaces that fact through the
        existing reference renderer, before the research/knowledge/orchestration
        routes can reinterpret the turn as a new operation.

        Guarded twice, so nothing else can be captured:

        * the frame must read the turn as a reference/follow-up (a turn that
          introduces a new objective — "compare that with X" — is not one); and
        * the intake type must be informational. A governed request that happens
          to carry a bound reference ("Investigate this further.", "Develop that
          capability.") keeps its own governed route.

        Returns None whenever nothing was bound (fail-closed), so every other
        turn is byte-for-byte unchanged.
        """
        if spec is None or self._builtin_response is None:
            return None
        from atlas.conversation import semantic_frame as _frame

        frame = _frame.interpret(text)
        if frame.role not in (
            _frame.SemanticRole.REFERENCE,
            _frame.SemanticRole.FOLLOW_UP,
        ):
            return None
        if getattr(spec.task_type, "value", "") not in _INFORMATIONAL_TASK_TYPES:
            return None
        return self._builtin_response.match_resolved_reference_answer(text, spec)

    def _maybe_handle_evidence_gap_analysis(self, text: str) -> Message | None:
        """Analyze the retained investigation findings for concrete gaps.

        Consumes ONLY the retained :class:`InvestigationReport` evidence through
        the existing deterministic ``EvidenceGapAnalyzer``. Read-only and
        model-free: it gathers no new evidence, never re-investigates, never
        mutates the retained investigation/result state, and never authorizes,
        approves, executes, or promotes anything.

        Fail-closed: a recognized analysis request with no retained
        investigation report is told the antecedent is missing instead of
        silently running a fresh investigation on the literal words. Every
        other turn returns ``None`` so the existing cascade is unchanged.
        """
        from atlas.conversation.evidence_gap_analysis import (
            EvidenceGapAnalyzer,
            is_evidence_gap_analysis_request,
        )

        if not is_evidence_gap_analysis_request(text):
            return None

        # Step 10 — a genuine MULTI-STEP request (a runnable work step followed by
        # an analysis of its RESULT) belongs to the multi-step route, not to a gap
        # analysis over whatever report happened to be retained. Without this, the
        # dependent request "Investigate X and then analyze the findings." analyses
        # STALE evidence instead of the step's own result.
        try:
            multi = build_multi_step(text)
        except Exception:
            multi = None
        if multi is not None and any(
            step.executor == EXEC_ANALYSIS and step.dependency == DEP_RESULT
            for step in multi.steps
        ):
            return None

        report = self._last_investigation_report
        if report is None:
            return Message(
                role="assistant",
                content=(
                    "There is no retained investigation to analyze. Please "
                    "investigate a subject first, then ask me to analyze the "
                    "findings. No new investigation was started."
                ),
                metadata={"gap_analysis": {"status": "no_investigation"}},
            )

        analysis = EvidenceGapAnalyzer().analyze(report)
        return Message(
            role="assistant",
            content=analysis.to_markdown(),
            metadata={
                "gap_analysis": {
                    "status": "complete",
                    "target": analysis.target,
                    "objective": analysis.objective,
                    "gap_count": len(analysis.gaps),
                    "insufficient_evidence": analysis.insufficient_evidence,
                    "evidence_basis": list(analysis.evidence_basis),
                    "modification_status": analysis.modification_status,
                    "gaps": [gap.to_dict() for gap in analysis.gaps],
                },
            },
        )

    def _maybe_handle_external_knowledge(self, text: str) -> Message | None:
        """Evidence-driven: external-knowledge requests routed via D3/D2.

        Reuses the existing validated-knowledge surface (local-first, then the
        D3 knowledge decision and the governed D2 boundary). Never calls an
        external provider directly and never makes the result authoritative.
        """
        if self._builtin_response is None:
            return None
        message = self._builtin_response.match_external_knowledge(text)
        if message is not None:
            self._record_knowledge_result(message)
        return message

    # ------------------------------------------------------------------
    # Evidence-Driven Improvement 3 — conversational knowledge integration
    # ------------------------------------------------------------------

    def _has_prior_objective(self) -> bool:
        """True when the conversation already carries an objective or subject.

        Deterministic and read-only: reads the existing bounded conversation
        state (no knowledge operation, no acquisition, no state change). Used so
        a bare reference is interpreted as a FOLLOW_UP — resolvable by the
        existing reference surface — rather than as an ambiguous request.
        """
        if self._state_manager is None:
            return False
        state = self._state_manager.state
        for field in (
            "current_objective",
            "current_subject",
            "current_task",
            "current_investigation",
        ):
            if str(getattr(state, field, "") or "").strip():
                return True
        return bool(tuple(getattr(state, "captured_entities", ()) or ()))

    def _active_knowledge_subject(self) -> str | None:
        """The subject a knowledge operation should use right now (I3).

        Deterministic and bounded, in priority order:

          1. the most recent APPLIED correction's subject, when it differs from
             the retained knowledge query (the user superseded the subject, so
             the retained answer is stale), else
          2. the retained knowledge query (``last_knowledge.query``), else
          3. ``None`` (fail closed).

        Read-only: it never performs a knowledge operation, acquires anything,
        or changes state.
        """
        if self._state_manager is None:
            return None
        state = self._state_manager.state
        recorded = (
            state.last_knowledge
            if isinstance(state.last_knowledge, dict)
            else None
        )
        query = str((recorded or {}).get("query") or "").strip()
        corrections = getattr(state, "corrections", ()) or ()
        if corrections:
            corrected = str(getattr(corrections[-1], "corrected", "") or "").strip()
            if corrected and _normalized_subject(corrected) != _normalized_subject(
                query
            ):
                return corrected
        return query or None

    def _knowledge_message_for(self, subject: str) -> Message | None:
        """Answer a knowledge operation for ``subject`` and retain the result.

        Uses the builtin service's local-first D3/D2 claim (the same path as the
        validated-knowledge bridge) and records the answer into the existing
        ``ConversationState.last_knowledge`` slot so the existing follow-up
        surface can consume it. Nothing is invented; when no authorized
        knowledge exists the retrieval's own honest outcome is reported.
        """
        if self._builtin_response is None:
            return None
        topic = knowledge_topic(subject)
        if topic is None:
            return None
        message = self._builtin_response.match_knowledge_request(topic)
        if message is not None:
            self._record_knowledge_result(message)
        return message

    def _maybe_handle_knowledge_request(
        self, text: str, spec: TaskSpec | None
    ) -> Message | None:
        """I3 — route an explicit research/knowledge request through D3.

        A turn such as "Research the Europa Clipper mission." is primarily a
        request for INFORMATION, so it enters the existing local-first knowledge
        path instead of the generic work-acquisition flow (which could report a
        completion without producing knowledge).

        Claimed only when the knowledge bridge is actually wired, the turn is a
        bounded single-clause research request, the subject is not an
        underspecified generic one (the existing NLU-2 clarification keeps that
        case), and a bare bounded reference can be resolved from the active
        subject. Otherwise ``None`` — existing behaviour is unchanged.
        """
        if self._builtin_response is None:
            return None
        if self._builtin_response.validated_knowledge_provider is None:
            return None
        # An unresolved/ambiguous reference keeps the EXISTING governed
        # clarification (the same deterministic intake ambiguity report the
        # research bridge honours): the knowledge path never guesses a subject.
        ambiguity = getattr(spec, "ambiguity", None)
        if bool(getattr(spec, "needs_clarification", False)) or tuple(
            getattr(ambiguity, "ambiguities", ()) or ()
        ):
            return None
        # Temporary Roadmap Step 2 — precedence: a turn the deterministic intake
        # classified as an INVESTIGATION request keeps the read-only investigation
        # route. Investigation is the authoritative owner for its language
        # ("look into why X fails" also matches a knowledge cue), so this generic
        # knowledge route declines rather than answering it as a knowledge lookup.
        if spec is not None and spec.task_type is TaskType.INVESTIGATION_REQUEST:
            return None
        objective = ""
        if spec is not None:
            objective = str(
                getattr(spec, "intent", "") or getattr(spec, "goal", "") or ""
            )
        # A continuation / follow-up / reference role with prior context takes
        # precedence over generic new-objective knowledge matching.
        from atlas.conversation import semantic_frame as _frame

        if _frame.interpret(
            text, has_prior_objective=bool(self._active_knowledge_subject())
        ).role is not _frame.SemanticRole.NEW_OBJECTIVE:
            return None
        raw_subject = research_request_subject(text)
        if raw_subject is None:
            # G1 — not a bounded research-cue request; the semantic frame may
            # still recognize an ordinary knowledge request.
            return self._frame_knowledge_message(text, objective, spec)

        reference_resolved = False
        if is_bounded_reference_subject(raw_subject):
            active = self._active_knowledge_subject()
            if active is None:
                return None
            raw_subject = substitute_reference_subject(raw_subject, active)
            reference_resolved = True

        if (
            research_subject_gap(
                objective or text, reference_resolved=reference_resolved
            )
            is not None
        ):
            return None

        message = self._knowledge_message_for(raw_subject)
        if message is not None:
            return message

        # G1 — semantic-frame knowledge seam: an ordinary knowledge request the
        # bounded research cue vocabulary did not claim ("I'd like to know more
        # about X", "What can you tell me about X?"). Guarded so every existing
        # precedence survives (see _frame_knowledge_message).
        return self._frame_knowledge_message(text, objective, spec)

    def _maybe_handle_frame_clarification(self, text: str) -> Message | None:
        """G1 — ask when the semantic frame says the request is ambiguous.

        Only claims a turn the frame explicitly marked ``needs_clarification``
        (a bare reference or an unresolved work/knowledge object with no prior
        context). It never invents a subject and never routes work.
        """
        if self._builtin_response is None or not isinstance(text, str):
            return None
        from atlas.conversation import semantic_frame as _frame
        from atlas.conversation.builtin_response import (
            is_store_recall_shaped,
            is_validated_knowledge_shaped,
        )

        # Only a SHORT bare-reference command asks for its subject here; a
        # prose turn keeps its existing path, and a turn an existing surface
        # already owns (store recall / validated-knowledge cue) keeps that
        # surface.
        if is_store_recall_shaped(text) or is_validated_knowledge_shaped(text):
            return None
        # A bounded knowledge follow-up keeps its existing (pinned) behaviour.
        if any(
            pattern.match(text.strip())
            for pattern in (
                self._KNOWLEDGE_FIND_RE,
                self._KNOWLEDGE_SOURCE_RE,
                self._KNOWLEDGE_CONTINUE_RE,
            )
        ):
            return None
        if len(_frame.tokens(text)) > 6:
            return None
        # G1/G2 — the frame must see the ESTABLISHED context, exactly as the
        # knowledge path does: with an active objective/subject a bare reference
        # is a FOLLOW_UP the existing reference surface resolves, NOT an
        # ambiguous request. Without this the clarification seam preempted the
        # existing reference answer.
        has_prior = self._has_prior_objective()
        frame = _frame.interpret(
            text,
            has_prior_objective=has_prior,
            has_knowledge_context=bool(self._active_knowledge_subject()),
        )
        # Step 9 — an INVESTIGATION request whose whole object is a bare
        # reference ("Investigate it.") with no antecedent is UNDERSPECIFIED, not
        # determined: asking for the subject is correct, and acting on the
        # literal reference would silently invent the target. (The frame's
        # knowledge/work branches already raise needs_clarification for this
        # shape; the investigation branch does not, so the check is bounded to
        # exactly that case here.)
        underspecified_investigation = bool(
            frame.role is _frame.SemanticRole.NEW_OBJECTIVE
            and frame.domain is _frame.SemanticDomain.INVESTIGATION
            and not has_prior
            and frame.reference
            and not _frame.operation_object(text)
        )
        if not frame.needs_clarification and not underspecified_investigation:
            return None
        question = (
            "I need a bit more detail before I can act on that:\n"
            "- Which subject should I use?"
        )
        # Step 9 — preserve the missing-information request so the next turn is
        # interpreted against it rather than reinterpreting unrelated context.
        # No candidate is invented; there is genuinely none to offer.
        self._record_pending_clarification(KIND_SUBJECT, question, (), text)
        return Message(
            role="assistant",
            content=question,
            metadata={
                "frame_clarification": {
                    "domain": frame.domain.value,
                    "operation": frame.operation,
                }
            },
        )

    def _record_pending_clarification(
        self,
        kind: str,
        question: str,
        candidates: "tuple[str, ...] | list[str]" = (),
        original_text: str = "",
    ) -> None:
        """Record an outstanding clarification (Step 9). Fail-soft.

        Bounded representation only: it never executes, authorizes or mutates
        governed state, and it never invents a candidate.
        """
        if self._state_manager is None:
            return
        try:
            self._state_manager.record_pending_clarification(
                kind, question, candidates, original_text=original_text
            )
        except Exception:  # fail-soft: recording must never break a turn
            return

    def _maybe_resolve_clarification(
        self, text: str, spec: TaskSpec | None
    ) -> Message | None:
        """Step 9 — resolve an outstanding clarification deterministically.

        Claims a turn ONLY when a bounded clarification is outstanding. A
        candidate-selection reply ("the handling one", "the second one", "the
        research task") resolves the pending ambiguity and resumes the correct
        existing route; a genuine new request CLEARS the clarification and lets
        the normal cascade run; anything else keeps the ambiguity open and
        restates the question. Nothing is guessed, executed, authorized or
        mutated.
        """
        if self._state_manager is None or not isinstance(text, str) or not text.strip():
            return None
        pending = self._state_manager.state.pending_clarification
        if pending is None:
            return None

        if pending.candidates:
            matches = candidate_matches(text, pending.candidates)
            if len(matches) == 1:
                return self._resolve_clarification_candidate(pending, matches[0], spec)
            if len(matches) > 1:
                # Still genuinely ambiguous: keep it open with the narrower set.
                question = build_question(
                    pending.kind, matches, "Which one do you mean?"
                )
                self._record_pending_clarification(
                    pending.kind, question, matches, pending.original_text
                )
                return Message(
                    role="assistant",
                    content=question,
                    metadata={
                        "clarification": {
                            "kind": pending.kind,
                            "candidates": list(matches),
                            "status": "still_ambiguous",
                        }
                    },
                )

        # No unique selection. A turn that is NOT a reference/follow-up is a
        # genuine new request (or a casual/meta turn): it supersedes the
        # clarification and keeps its existing route.
        from atlas.conversation import semantic_frame as _frame

        frame = _frame.interpret(
            text,
            has_prior_objective=bool(self._has_prior_objective()),
            has_knowledge_context=bool(self._active_knowledge_subject()),
        )
        if frame.role not in (_frame.SemanticRole.REFERENCE, _frame.SemanticRole.FOLLOW_UP):
            self._state_manager.clear_pending_clarification()
            return None

        # A reference/follow-up that did not select a candidate keeps the
        # ambiguity open (no candidate is invented).
        return Message(
            role="assistant",
            content=pending.question,
            metadata={
                "clarification": {
                    "kind": pending.kind,
                    "candidates": list(pending.candidates),
                    "status": "unresolved",
                }
            },
        )

    def _resolve_clarification_candidate(
        self,
        pending: Any,
        candidate: str,
        spec: TaskSpec | None,
    ) -> Message | None:
        """Resume the correct existing route for a selected candidate."""
        candidates = list(pending.candidates)
        if pending.kind == KIND_TOPIC:
            reactivated = self._state_manager.reactivate_world_topic(candidate)
            if not reactivated:
                return None
            self._state_manager.clear_pending_clarification()
            return Message(
                role="assistant",
                content=(
                    f"Returning to a prior topic: '{reactivated}'. It is the "
                    "active context again. Nothing was executed or authorized."
                ),
                metadata={
                    "clarification_resolved": {
                        "kind": KIND_TOPIC,
                        "resolved": reactivated,
                        "candidates": candidates,
                    }
                },
            )

        # A reference/subject candidate: adopt it as the active world topic and
        # resume the existing bounded reference-restatement route.
        self._state_manager.clear_pending_clarification()
        self._observe_world_topic(candidate, "clarification")
        message: Message | None = None
        if self._builtin_response is not None and isinstance(spec, TaskSpec):
            from dataclasses import replace as _replace

            enriched = _replace(
                spec,
                context={
                    **(spec.context if isinstance(spec.context, dict) else {}),
                    "resolved_reference": {
                        "field": "current_subject",
                        "value": candidate,
                    },
                },
            )
            message = self._builtin_response.match_resolved_reference_answer(
                text=pending.original_text or candidate, spec=enriched
            )
        if message is None:
            message = Message(
                role="assistant",
                content=f"The current subject: {candidate}",
                metadata={"builtin_intent": "reference"},
            )
        metadata = dict(message.metadata or {})
        metadata["clarification_resolved"] = {
            "kind": pending.kind,
            "resolved": candidate,
            "candidates": candidates,
            "original": pending.original_text,
        }
        message.metadata = metadata
        return message

    #: Step 7 — bounded ORDINAL / earlier-item reference surface. These name an
    #: item in a LIST of earlier things; Atlas retains the ACTIVE context (and the
    #: single most recent result), not a numbered history, so such a reference can
    #: only be answered by saying so — never by guessing which one was meant.
    _ORDINAL_REFERENCE_RE = re.compile(
        r"\b(?:the\s+)?(?:previous|last|former|earlier|first|second|third|other)\s+"
        r"(?:one|ones|result|investigation|answer|subject|topic|item|thing)\b"
        r"|\bthe\s+one\s+(?:we|i)\s+(?:discussed|talked\s+about|mentioned|looked\s+at)\b"
        r"|\b(?:go\s+back|back)\s+to\s+(?:that|the\s+one)\b",
        re.IGNORECASE,
    )

    #: Step 8 — bounded "return to a prior topic" surface. These name a TOPIC the
    #: conversation has already covered ("go back to the storage layer"), so the
    #: world state can reactivate it. A pure reference target ("go back to that")
    #: is deliberately excluded — that shape belongs to the existing Step 7
    #: reference surface.
    _TOPIC_RETURN_RE = re.compile(
        r"^\s*(?:let'?s\s+|let\s+us\s+|please\s+|can\s+we\s+|could\s+we\s+)?"
        r"(?:go\s+back\s+to|back\s+to|return\s+to|switch\s+back\s+to|revisit"
        r"|re-?examine)\s+(?P<target>.+?)\s*[.!?]*\s*$",
        re.IGNORECASE,
    )

    #: Bounded reference targets that are NOT a named prior topic; they keep the
    #: existing Step 7 reference handler (never claimed as a topic return).
    _TOPIC_RETURN_REFERENCE_TARGETS: frozenset[str] = frozenset(
        {
            "that", "this", "it", "them", "those", "these", "the one", "the ones",
            "the other", "the previous one", "the last one", "the first one",
            "the second one", "the other one", "the current one",
        }
    )

    def _maybe_handle_topic_return(self, text: str) -> Message | None:
        """Step 8 — return to a topic the conversation already covered.

        Claims ONLY a bounded return form naming a specifically matching PRIOR
        topic in the world state. It REACTIVATES that topic (making it the active
        context, demoting the previously active one to bounded history) and
        restates it. It never executes, approves, invents a topic, or contacts a
        model, and it fails closed (``None``) when nothing matches — so every
        existing route is unchanged.
        """
        if self._state_manager is None or not isinstance(text, str):
            return None
        match = self._TOPIC_RETURN_RE.match(text.strip())
        if match is None:
            return None
        target = match.group("target").strip(" \t.,!?;:")
        if not target:
            return None
        from atlas.conversation.normalization import collapse_whitespace

        if collapse_whitespace(target).lower() in self._TOPIC_RETURN_REFERENCE_TARGETS:
            return None

        world = self._state_manager.state.world
        if world is None or not world.topics:
            return None
        matches = match_topics(world, target)
        if not matches:
            return None
        if len(matches) > 1:
            candidates = [topic.label for topic in matches[:MAX_WORLD_TOPICS]]
            lines = [
                f"More than one topic in this conversation matches '{target}':",
            ]
            lines.extend(f"- {candidate}" for candidate in candidates)
            lines.append("Tell me which one you mean. Nothing was executed.")
            # Step 9 — preserve the competing topics so the follow-up ("the
            # handling one", "the second one") resolves deterministically and the
            # topic-return route resumes.
            self._record_pending_clarification(
                KIND_TOPIC, "\n".join(lines), candidates, text
            )
            return Message(
                role="assistant",
                content="\n".join(lines),
                metadata={
                    "world_state": {
                        "status": "ambiguous",
                        "requested": target,
                        "candidates": candidates,
                    }
                },
            )

        reactivated = self._state_manager.reactivate_world_topic(target)
        if not reactivated:
            return None
        topic = matches[0]
        return Message(
            role="assistant",
            content=(
                f"Returning to a prior topic: '{reactivated}' "
                f"({topic.kind}). It is the active context again. Nothing was "
                "executed or authorized."
            ),
            metadata={
                "world_state": {
                    "status": "reactivated",
                    "topic": reactivated,
                    "kind": topic.kind,
                    "active_topic": reactivated,
                }
            },
        )

    def _maybe_handle_ordinal_reference(self, text: str) -> Message | None:
        """Step 7 — represent an UNRESOLVED earlier-item reference honestly.

        Claims ONLY a turn that names an item in a list of earlier things (the
        bounded surface above) after the existing reference surfaces have already
        declined it, and asks which item is meant instead of guessing. The active
        context, when there is one, is restated so the question is answerable, and
        nothing is executed, authorized or invented.

        Returns ``None`` for every other turn, so no existing route changes.
        """
        if not isinstance(text, str) or not text.strip():
            return None
        if self._ORDINAL_REFERENCE_RE.search(text.strip()) is None:
            return None

        active = ""
        try:
            active = str(self._active_knowledge_subject() or "").strip()
        except Exception:
            active = ""
        has_context = False
        try:
            has_context = bool(self._has_prior_objective())
        except Exception:
            has_context = bool(active)

        lines = [
            "I cannot tell which earlier item you mean: I keep the ACTIVE "
            "conversation context and the most recent result, not a numbered list "
            "of everything we have covered.",
        ]
        if active:
            lines.append(f"The active subject is '{active[:160]}'.")
            lines.append("Name the item you want (or say 'the current one') and I will use it.")
        elif has_context:
            lines.append(
                "Tell me which subject or result you mean, or repeat the item's "
                "name, and I will use that."
            )
        else:
            lines.append(
                "There is no earlier subject or result in this conversation yet, so "
                "please name the item you want."
            )
        lines.append("Nothing was invented or executed.")
        # Step 8 — keep the unresolved reference visibly unresolved in the world
        # state; it is NEVER promoted to the active topic. Fail-soft.
        if self._state_manager is not None:
            try:
                self._state_manager.record_unresolved_reference(text.strip())
            except Exception:
                pass
        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={
                "reference_clarification": {
                    "requested": "earlier_item",
                    "active_subject": active[:160],
                    "has_prior_context": has_context,
                }
            },
        )

    def _maybe_handle_multi_step(self, text: str) -> Message | None:
        """Step 10 — understand and route a multi-intent/multi-step request.

        Claims ONLY a genuinely multi-intent/multi-step OPERATIONAL request (two
        or more bounded clauses of which at least one is a runnable read-only
        step) that the existing routes did not already own. It:

          * represents every step (order only when the language expressed it,
            dependency only when a later step reasons over an earlier RESULT);
          * runs the runnable read-only steps through the EXISTING kernel-owned
            orchestration bridge (the same mechanism Step 2 uses), preserving
            order and `depends_on`/`carry_from`;
          * answers understood CASUAL clauses through the EXISTING builtin
            surface;
          * REPORTS every other step truthfully (unsupported / governed /
            blocked) — nothing is invented, executed or authorized.

        Returns ``None`` for every other turn, so all existing routes keep their
        precedence. No new execution engine and no second persistence mechanism
        is introduced: the retained plan is the existing ``current_plan``.
        """
        if self._goal_orchestration_resolver is None or self._state_manager is None:
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        try:
            request = build_multi_step(text)
        except Exception:  # fail-soft: the existing cascade is unchanged
            return None
        if request is None or not request.has_operational_step:
            return None
        plan = build_execution_steps(request)
        if not plan:
            return None
        try:
            message = self._goal_orchestration_resolver(
                text, plan, self._last_session_context
            )
        except Exception:  # fail-soft: the bridge never breaks conversation
            return None
        if not isinstance(message, Message):
            return None
        self._retain_goal_plan(text, plan, message)

        lines = [message.content]
        for step in request.builtin_steps:
            if self._builtin_response is None:
                continue
            try:
                reply = self._builtin_response.respond(
                    step.clause,
                    spec=None,
                    message_count=len(self._conversation.messages),
                    context=None,
                )
            except Exception:
                reply = None
            if reply is not None and isinstance(reply.content, str) and reply.content.strip():
                lines.append("")
                lines.append(f"**{step.clause}**")
                lines.append(reply.content)
        reported = request.reported_steps
        if reported:
            reasons = {
                STATUS_UNSUPPORTED: "not supported",
                STATUS_GOVERNED: "requires the existing OWNER approval flow",
                STATUS_BLOCKED: "blocked — its prerequisite was not satisfied",
            }
            lines.append("")
            lines.append("Recognized but not attempted:")
            for step in reported:
                lines.append(f"- {step.clause} — {reasons.get(step.status, 'not attempted')}")
        lines.append("")
        lines.append("Nothing was executed or authorized beyond the steps reported above.")

        metadata = dict(message.metadata or {})
        representation = request.to_dict()
        run = metadata.get("orchestration")
        if isinstance(run, dict):
            states = {
                str(entry.get("step_id")): str(entry.get("state") or "")
                for entry in (run.get("steps") or ())
                if isinstance(entry, dict)
            }
            for step in representation["steps"]:
                executed = states.get(step["step_id"])
                if executed:
                    step["status"] = executed
        representation["run_status"] = (
            str(run.get("status") or "") if isinstance(run, dict) else ""
        )
        metadata["multi_step"] = representation
        return Message(role="assistant", content="\n".join(lines), metadata=metadata)

    def _maybe_handle_multi_intent(self, text: str) -> Message | None:
        """Step 6 — answer every understood intent and REPORT the unhandled one.

        Claims ONLY a turn that carries more than one bounded reading
        (``semantic_frame.split_intents``, a bounded coordinator split of the
        EXISTING frame) and whose clauses the EXISTING deterministic builtin
        surface can answer — so a multi-intent request is never silently reduced
        to its first clause. Each understood clause is answered by that SAME
        surface (no new answering path), and any clause it cannot map is reported
        explicitly as not attempted. Returns ``None`` when nothing is understood
        (the Step 5 uninterpreted floor owns it) or when the turn is not a
        multi-intent request, so all existing routing is unchanged. Nothing is
        executed, approved or authorized by this path.
        """
        if self._builtin_response is None or not isinstance(text, str):
            return None
        from atlas.conversation import semantic_frame as _frame

        try:
            subs = _frame.split_intents(text)
        except Exception:  # fail-soft: the existing cascade is unchanged
            return None
        if len(subs) < 2:
            return None

        handled: list[tuple[str, str]] = []
        unhandled: list[str] = []
        for sub in subs:
            clause = str(getattr(sub, "subject", "") or "").strip()
            if not clause:
                continue
            reply = None
            if not bool(getattr(sub, "governance_sensitive", False)):
                try:
                    reply = self._builtin_response.respond(
                        clause,
                        spec=None,
                        message_count=len(self._conversation.messages),
                        context=None,
                    )
                except Exception:
                    reply = None
            intent = (
                (reply.metadata or {}).get("builtin_intent")
                if reply is not None
                else ""
            )
            if reply is not None and intent and intent != "unsupported":
                handled.append((clause, reply.content))
            else:
                unhandled.append(clause)
        if not handled:
            return None

        lines = [
            f"That request carries more than one intent. I answered "
            f"{len(handled)} of {len(handled) + len(unhandled)}:",
        ]
        for clause, content in handled:
            lines.append("")
            lines.append(f"**{clause}**")
            lines.append(content)
        if unhandled:
            lines.append("")
            lines.append(
                "This part could not be mapped to anything I can do, so it was "
                "not attempted:"
            )
            lines.extend(f"- {clause}" for clause in unhandled)
        lines.append("")
        lines.append("Nothing was executed or authorized.")
        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={
                "multi_intent": {
                    "handled": [clause for clause, _ in handled],
                    "unhandled": list(unhandled),
                }
            },
        )

    def _maybe_handle_compound_request(self, text: str) -> Message | None:
        """G1 — boundedly handle a compound research request.

        A compound whose LEADING subrequest is research/knowledge is answered
        from the existing local-first knowledge path; every remaining bounded
        subrequest is reported honestly as recognized-but-not-executed (and a
        governance-sensitive clause is reported as requiring the existing OWNER
        approval flow). Nothing is planned, dispatched, or executed here, and
        the frame never grants authority.
        """
        if self._builtin_response is None or not isinstance(text, str):
            return None
        from atlas.conversation import semantic_frame as _frame

        subs = _frame.decompose(text)
        if len(subs) < 2:
            return None
        lead = subs[0]
        if lead.domain != "knowledge" or lead.operation != "research":
            return None
        if lead.governance_sensitive:
            return None
        topic = knowledge_topic(lead.subject)
        if topic is None:
            return None
        message = self._builtin_response.match_knowledge_request(topic)
        if message is None:
            return None
        self._record_knowledge_result(message)

        lines = [message.content, "", "Recognized additional subrequests:"]
        for sub in subs[1:]:
            if sub.governance_sensitive:
                lines.append(
                    f"- {sub.operation}: governance-sensitive — it requires the "
                    "existing OWNER approval flow and was not executed."
                )
            elif sub.operation == "research":
                lines.append(
                    f"- {sub.operation}: a further research step; ask it as its "
                    "own request for a separate answer."
                )
            else:
                lines.append(
                    f"- {sub.operation}: not available as a bounded conversational "
                    "step; it was not executed."
                )
        metadata = dict(message.metadata or {})
        metadata["compound"] = {"subrequests": [s.to_dict() for s in subs]}
        return Message(role="assistant", content="\n".join(lines), metadata=metadata)

    # ------------------------------------------------------------------
    # Step 2 — Goal-Centered Orchestration (bounded two-stage slice)
    # ------------------------------------------------------------------

    def _maybe_handle_goal_request(self, text: str) -> Message | None:
        """Sequence a bounded multi-stage conversational goal.

        Builds a SMALL ordered plan from the EXISTING semantic decomposition
        (``SemanticFrame.decompose`` — no new parser or planner) and hands it to
        the kernel-owned bridge, which runs it through the EXISTING
        ``OrchestrationExecutor``. The bounded plan and its per-step statuses are
        retained in ``ConversationState.current_plan`` so a later turn can
        continue the goal. This layer never dispatches, authorizes, or executes
        anything itself, and it claims a turn ONLY when the existing
        decomposition yields at least two composable steps.
        """
        if self._goal_orchestration_resolver is None or not isinstance(text, str):
            return None
        from atlas.orchestration.goal_plan import build_goal_plan

        try:
            steps = build_goal_plan(text)
        except Exception:  # fail-soft: any failure keeps existing routing
            return None
        if not steps:
            return None
        # Step 10 — the closed two-stage slices never cover a request that also
        # carries a THIRD intent; when the bounded multi-step reading sees more
        # steps than this plan covers, the multi-step route owns the turn (so a
        # legitimate third intent is never silently dropped).
        try:
            multi = build_multi_step(text)
        except Exception:
            multi = None
        if multi is not None and len(multi.steps) > len(steps):
            return None
        try:
            message = self._goal_orchestration_resolver(
                text, steps, self._last_session_context
            )
        except Exception:  # fail-soft: the bridge never breaks conversation
            return None
        if not isinstance(message, Message):
            return None
        self._retain_goal_plan(text, steps, message)
        return message

    @staticmethod
    def _plan_step_field(step: Any, name: str, default: Any = None) -> Any:
        """Read one bounded field from a plan step (an ExecutionStep or a dict)."""
        if isinstance(step, dict):
            return step.get(name, default)
        return getattr(step, name, default)

    def _retain_goal_plan(
        self,
        objective: str,
        plan_steps: Any,
        message: Message,
    ) -> None:
        """Retain a BOUNDED, authority-free record of the ACTIVE goal/plan.

        Representation only: objective, ordered steps (id / kind / target /
        bounded inputs / dependency + carry references), per-step status and the
        bounded OUTPUT of completed steps, the current step, and the run state.
        The retained inputs + outputs are what let a later turn RESUME the
        unfinished steps without rebuilding the plan or repeating completed work.
        Never an event store, workflow database, or second persistence mechanism.
        """
        if self._state_manager is None:
            return
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        run = metadata.get("orchestration")
        results: dict[str, dict[str, Any]] = {}
        run_state = ""
        if isinstance(run, dict):
            run_state = str(run.get("status", ""))[:32]
            for entry in run.get("steps") or ():
                if isinstance(entry, dict) and isinstance(entry.get("step_id"), str):
                    output = entry.get("output")
                    results[entry["step_id"]] = {
                        "state": str(entry.get("state", ""))[:32],
                        "error": str(entry.get("error", ""))[:160],
                        "output": dict(output) if isinstance(output, dict) else {},
                    }
        bounded_steps: list[dict[str, Any]] = []
        current_step: str | None = None
        for step in tuple(plan_steps or ())[:8]:
            step_id = str(self._plan_step_field(step, "step_id", "") or "")
            if not step_id:
                continue
            info = results.get(step_id, {})
            state = str(info.get("state", "") or "")
            if current_step is None and state != "completed":
                current_step = step_id
            inputs = self._plan_step_field(step, "inputs", {})
            depends_on = self._plan_step_field(step, "depends_on", ())
            carry_from = self._plan_step_field(step, "carry_from", ())
            bounded_steps.append(
                {
                    "step_id": step_id,
                    "kind": str(
                        getattr(self._plan_step_field(step, "kind"), "value", "")
                        or self._plan_step_field(step, "kind", "")
                    )[:32],
                    "target": str(self._plan_step_field(step, "target", ""))[:200],
                    "inputs": dict(inputs) if isinstance(inputs, dict) else {},
                    "depends_on": [
                        d for d in (depends_on or ()) if isinstance(d, str)
                    ][:4],
                    "carry_from": [
                        c for c in (carry_from or ()) if isinstance(c, str)
                    ][:4],
                    "state": state,
                    "error": str(info.get("error", "") or ""),
                    "output": dict(info.get("output", {}) or {}),
                }
            )
        self._state_manager.update(
            current_plan={
                "objective": str(objective).strip()[:400],
                "steps": bounded_steps,
                "current_step": current_step,
                "state": run_state,
            }
        )
        # Step 8 — the goal's objective becomes the ACTIVE world topic. A later
        # topic demotes it to bounded history; the retained plan is unchanged.
        self._observe_world_topic(str(objective).strip(), "goal")
        # ...and a GENUINELY finished goal is marked COMPLETE (distinct from
        # ACTIVE) so completed work is never re-read as the active context.
        if run_state == "completed" and self._state_manager is not None:
            try:
                self._state_manager.mark_world_topic_complete(
                    str(objective).strip()
                )
            except Exception:
                pass

    def _maybe_handle_goal_resume(self, text: str) -> Message | None:
        """Step 2 — RESUME the retained, unfinished plan from a later turn.

        Claimed only when ALL of the following hold, else ``None`` (fail closed
        to the existing route):

          * a bounded continuation/resumption turn was recognized (the existing
            ``TurnRole.CONTINUATION`` semantics, or an explicit bounded form);
          * ``ConversationState.current_plan`` holds a genuinely INCOMPLETE plan
            (run state ``partial``/``failed`` and at least one step not
            ``completed``).

        The kernel-owned bridge re-runs ONLY the incomplete steps, seeding the
        already-completed ones so their bounded result is reused through the
        existing ``carry_from`` — the completed work is never repeated.
        """
        if self._goal_resume_resolver is None or self._state_manager is None:
            return None
        if not isinstance(text, str) or not self._is_goal_resume_request(text):
            return None
        plan = self._state_manager.state.current_plan
        if not isinstance(plan, dict) or not plan.get("steps"):
            return None
        if str(plan.get("state") or "") not in ("partial", "failed"):
            return None
        plan_steps = [s for s in (plan.get("steps") or []) if isinstance(s, dict)]
        if not plan_steps or all(
            str(s.get("state") or "") == "completed" for s in plan_steps
        ):
            return None
        try:
            message = self._goal_resume_resolver(plan, self._last_session_context)
        except Exception:  # fail-soft: the bridge never breaks conversation
            return None
        if not isinstance(message, Message):
            return None
        self._retain_goal_plan(
            str(plan.get("objective") or text), plan_steps, message
        )
        return message

    @staticmethod
    def _is_goal_resume_request(text: str) -> bool:
        """True when the turn deterministically asks to CONTINUE the active goal.

        Reuses the EXISTING bounded continuation semantics (``TurnRole`` derived
        from the shared semantic frame) plus a small explicit resumption form
        set. A plain statement is never matched.
        """
        from atlas.conversation.turn_role import TurnRole, detect_turn_role

        try:
            if detect_turn_role(text, has_prior_objective=True) is TurnRole.CONTINUATION:
                return True
        except Exception:
            pass
        from atlas.conversation.normalization import (
            canonicalize_surface,
            collapse_whitespace,
        )

        normalized = collapse_whitespace(canonicalize_surface(text)).lower().strip()
        return normalized in _GOAL_RESUME_FORMS

    def _maybe_handle_goal_followup(self, text: str) -> Message | None:
        """Report the ACTIVE goal/plan from retained state (read-only).

        Only a bounded, explicit status form is recognized, and the reply is
        built from the retained bounded plan — it starts no new operation. With
        no active plan the turn keeps its existing route (fail closed).
        """
        if self._state_manager is None or not isinstance(text, str):
            return None
        from atlas.conversation.normalization import (
            canonicalize_surface,
            collapse_whitespace,
        )

        normalized = collapse_whitespace(canonicalize_surface(text)).lower().strip()
        if normalized not in _GOAL_STATUS_FORMS:
            return None
        plan = self._state_manager.state.current_plan
        if not isinstance(plan, dict) or not plan.get("steps"):
            return None
        lines = [f"Active goal: {plan.get('objective', '')}", "Plan status:"]
        for step in list(plan.get("steps") or ())[:8]:
            if not isinstance(step, dict):
                continue
            lines.append(
                f"- {step.get('step_id')}: {step.get('kind')} "
                f"{step.get('target')} — {step.get('state') or 'pending'}"
            )
        lines.append(f"Current step: {plan.get('current_step') or 'none'}")
        lines.append(f"Goal state: {plan.get('state') or 'in_progress'}")
        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={"goal_plan": dict(plan)},
        )

    def _frame_knowledge_message(
        self, text: str, objective: str, spec: TaskSpec | None = None
    ) -> Message | None:
        """G1 — route a KNOWLEDGE-classified turn into the existing D3 path.

        Guards (each one preserves pinned behaviour):
          * store-recall shaped and validated-knowledge-cue shaped turns keep
            their existing surfaces;
          * compound turns are REPRESENTED (subrequests) and not claimed here;
          * comparisons keep their existing answerable path;
          * the NLU-2 subject-gap gate still decides when a subject is too
            thin to answer, and a turn with no usable subject fails closed.
        """
        if self._builtin_response is None:
            return None
        from atlas.conversation import semantic_frame as _frame
        from atlas.conversation.builtin_response import (
            is_compound_shaped,
            is_store_recall_shaped,
            is_validated_knowledge_shaped,
        )

        if is_store_recall_shaped(text) or is_validated_knowledge_shaped(text):
            return None
        # Only CASUAL-shaped turns are claimed here: a research-shaped task type
        # already has its existing path (the bounded research cue vocabulary
        # above, or the orchestration bridge with its own clarification), and
        # that path must keep its pinned behaviour. A turn carrying a leading
        # subordinate clause ("Before I decide what to test, find ...") also
        # keeps its existing path.
        task_type = str(getattr(getattr(spec, "task_type", None), "value", "") or "")
        if task_type not in (
            "", "conversation", "question", "unknown", "information_request",
            "action_request",
        ):
            return None
        if _SUBORDINATE_CLAUSE_RE.search(text):
            return None
        if is_compound_shaped(text) or len(_frame.decompose(text)) >= 2:
            return None
        frame = _frame.interpret(text)
        if frame.domain is not _frame.SemanticDomain.KNOWLEDGE:
            return None
        if frame.operation not in ("research", "explain", "status"):
            return None
        if (
            research_subject_gap(objective or text, reference_resolved=False)
            is not None
        ):
            return None
        topic = knowledge_topic(_frame.knowledge_subject(text))
        if topic is None:
            return None
        message = self._builtin_response.match_knowledge_request(topic)
        if message is not None:
            self._record_knowledge_result(message)
        return message

    #: Evidence-driven improvement 1 — bare knowledge follow-ups. Whole-turn
    #: anchored so they can never capture a topic-bearing request (e.g. "what
    #: did you find about memory storage?" keeps its existing knowledge path).
    _KNOWLEDGE_FIND_RE = re.compile(
        r"^\s*(?:and\s+)?what\s+did\s+(?:you|we)\s+(?:find|learn|discover)"
        r"\s*[.?]*\s*$",
        re.IGNORECASE,
    )
    _KNOWLEDGE_SOURCE_RE = re.compile(
        r"^\s*(?:and\s+)?what\s+sources?\s+supports?\s+(?:that|this)\s*[.?]*\s*$"
        r"|^\s*(?:and\s+)?what\s+(?:source|evidence)\s+supports?\s+(?:that|this)"
        r"\s*[.?]*\s*$",
        re.IGNORECASE,
    )
    _KNOWLEDGE_CONTINUE_RE = re.compile(
        r"^\s*(?:can\s+you\s+)?(?:continue|go\s+on|keep\s+going)\s*[.?]*\s*$",
        re.IGNORECASE,
    )

    #: I3 — follow-up forms that carry a TOPIC. Claimed only when that topic is
    #: a bare bounded reference, so a real subject keeps its existing knowledge
    #: path (and Improvement 1's contract is preserved verbatim).
    _KNOWLEDGE_ABOUT_RE = re.compile(
        r"^\s*(?:and\s+)?what\s+did\s+(?:you|we)\s+(?:find|learn|discover)\s+about\s+"
        r"(?P<topic>.+?)\s*[.?]*\s*$",
        re.IGNORECASE,
    )
    _KNOWLEDGE_MORE_ABOUT_RE = re.compile(
        r"^\s*(?:and\s+)?(?:tell\s+me\s+)?(?:more\s+)?about\s+"
        r"(?P<topic>.+?)\s*[.?]*\s*$",
        re.IGNORECASE,
    )
    _KNOWLEDGE_WHAT_ABOUT_RE = re.compile(
        r"^\s*(?:and\s+)?what\s+about\s+(?P<topic>.+?)\s*[.?]*\s*$",
        re.IGNORECASE,
    )
    #: G1 — the shared recall cue form carrying a BOUNDED REFERENCE
    #: ("what do you know about that?") resolves against the retained/active
    #: knowledge subject instead of the literal reference.
    _KNOWLEDGE_KNOW_ABOUT_RE = re.compile(
        r"^\s*(?:and\s+)?what\s+do\s+you\s+(?:know|remember)\s+about\s+"
        r"(?P<topic>.+?)\s*[.?]*\s*$",
        re.IGNORECASE,
    )

    def _maybe_handle_knowledge_followup(self, text: str) -> Message | None:
        """Resolve a knowledge follow-up against the retained result.

        Only claims the turn when the immediately preceding knowledge answer was
        retained (``ConversationState.last_knowledge``); otherwise returns
        ``None`` so existing behaviour is unchanged. Read-only and bounded:
        nothing is acquired, invented, or executed.

        I3 adds two bounded behaviours on top of the unchanged replay:

          * a topic-bearing follow-up whose topic is a bare bounded reference
            ("what did you find about that?", "tell me more about that.")
            resolves that reference from the active subject — the literal
            pronoun is never passed to the knowledge operation; and
          * when the active subject has been SUPERSEDED (the user corrected it),
            the follow-up performs a fresh knowledge operation for the corrected
            subject instead of replaying the stale answer.
        """
        if self._state_manager is None or not isinstance(text, str):
            return None
        recorded = self._state_manager.state.last_knowledge
        if not isinstance(recorded, dict):
            return None
        stripped = text.strip()

        kind: str | None = None
        if self._KNOWLEDGE_FIND_RE.match(stripped):
            kind = "find"
        elif self._KNOWLEDGE_SOURCE_RE.match(stripped):
            kind = "source"
        elif self._KNOWLEDGE_CONTINUE_RE.match(stripped):
            kind = "continue"

        requested_subject: str | None = None
        if kind is None:
            for pattern in (
                self._KNOWLEDGE_ABOUT_RE,
                self._KNOWLEDGE_MORE_ABOUT_RE,
                self._KNOWLEDGE_WHAT_ABOUT_RE,
                self._KNOWLEDGE_KNOW_ABOUT_RE,
            ):
                match = pattern.match(stripped)
                if match is None:
                    continue
                raw_topic = match.group("topic").strip()
                if not is_bounded_reference_subject(raw_topic):
                    return None
                active = self._active_knowledge_subject()
                if active is None:
                    return None
                requested_subject = substitute_reference_subject(raw_topic, active)
                kind = "find"
                break
        if kind is None:
            return None

        # The corrected/active subject supersedes the retained answer: answer
        # the actual question instead of replaying stale knowledge (I3, G-C).
        target = requested_subject or self._active_knowledge_subject()
        retained_query = str(recorded.get("query") or "")
        if target and _normalized_subject(target) != _normalized_subject(
            retained_query
        ):
            refreshed = self._knowledge_message_for(target)
            if refreshed is not None:
                return refreshed

        return self._knowledge_followup_replay(kind, recorded)

    def _knowledge_followup_replay(
        self, kind: str, recorded: dict
    ) -> Message | None:
        """The unchanged (Improvement 1) replay of a retained knowledge answer."""
        query = str(recorded.get("query") or "")
        status = str(recorded.get("status") or "")
        content = str(recorded.get("content") or "")

        if kind == "find":
            return Message(
                role="assistant",
                content=(
                    f"Most recent knowledge result "
                    f"(query '{query}', status {status}):\n\n{content}"
                ),
                metadata={
                    "knowledge_followup": {
                        "kind": "find",
                        "query": query,
                        "status": status,
                    }
                },
            )

        if kind == "source":
            sources = tuple(
                line.strip()
                for line in content.splitlines()
                if line.strip().lower().startswith("- source:")
            )
            if sources:
                body = (
                    "Sources attached to the most recent knowledge result:\n"
                    + "\n".join(sources)
                )
            else:
                body = (
                    "The most recent knowledge result carries no authorized "
                    "source provenance; I will not invent one."
                )
            return Message(
                role="assistant",
                content=body,
                metadata={"knowledge_followup": {"kind": "source"}},
            )

        if kind == "continue":
            return Message(
                role="assistant",
                content=(
                    f"I resolved this against the most recent knowledge result "
                    f"('{query}'). I do not autonomously continue research; tell "
                    "me the next objective or source."
                ),
                metadata={
                    "knowledge_followup": {"kind": "continue", "query": query}
                },
            )
        return None

    def _build_conversation_context(self) -> ConversationContext:
        """Build the bounded, read-only context projection for this turn.

        Single authoritative construction point: it projects the existing
        ``Conversation`` history and ``ConversationState`` into an immutable
        snapshot. The builtin layer never receives the mutable sources, and the
        projection carries no authority.
        """
        state = self._state_manager.state if self._state_manager is not None else None
        return build_conversation_context(self._conversation.messages, state)

    @staticmethod
    def _build_turn_meaning(spec: TaskSpec, text: str) -> TurnMeaning:
        """Build the L1 typed turn-meaning contract for the cognition boundary.

        Shared construction point for ``send`` and ``stream``: an immutable,
        role-typed, JSON-safe projection of existing turn meaning. It is
        behaviour-neutral and is not consumed semantically in L1.
        """
        return build_turn_meaning(spec, text)

    def _builtin_after_failure(
        self,
        text: str,
        spec: TaskSpec | None,
    ) -> Message | None:
        """Serve a built-in response after a provider failure.

        Same claim rules as the pre-AI builtin path (casual turns only,
        never needs-clarification). Legacy intake-less turns (spec None)
        are classified text-only: the AI has already failed, so any
        confident builtin answer beats propagating the error. The
        resulting message carries ``fallback_after_provider_failure``
        metadata so callers can tell a post-failure builtin answer apart
        from a direct one.
        """
        if self._builtin_response is None:
            return None
        if spec is None:
            # Legacy intake-less turn: the AI already failed, so classify
            # text-only rather than propagating the error.
            message = self._builtin_response.respond(
                text,
                spec=None,
                message_count=len(self._conversation.messages),
                context=self._build_conversation_context(),
            )
        else:
            message = self._maybe_handle_builtin_response(spec, text)
        if message is None:
            return None
        message.metadata["fallback_after_provider_failure"] = True
        return message

    def _deterministic_fallback(
        self,
        text: str,
        spec: TaskSpec | None,
        session_context: SessionContext | None,
        error_context: str,
    ) -> Message:
        """The existing deterministic fallback chain, in its existing order.

        Phase 4 order preserved verbatim: the built-in deterministic response
        first (``_builtin_after_failure``), then the legacy deterministic
        fallback resolver, then the bounded degraded notice. L8 reuses this for
        a delegated turn whose pipeline answer is unusable — the terminal
        deterministic floor must stay reachable without a second AI call.
        """
        message = self._builtin_after_failure(text, spec)
        if message is None and self._fallback_resolver is not None:
            message = self._fallback_resolver.resolve(
                text=text,
                spec=spec,
                session_context=session_context,
                error_context=error_context,
            )
        if message is None:
            message = Message(
                role="assistant",
                content=(
                    "External AI inference is currently unavailable and no deterministic "
                    "fallback resolver is configured."
                ),
                metadata={
                    "degraded": True,
                    "model_available": False,
                    "error": error_context,
                },
            )
        return message

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
        """Send a user message through Atlas.

        Stage 2 — the public entry point records the bounded dialogue turn AFTER
        the existing cascade completes. Every turn funnels through here, so the
        recording is route-independent (which handler ran never decides whether
        dialogue state is recorded). Recording is representation-only and
        fail-soft; it changes no routing.
        """
        self._last_meaning = None
        self._pre_turn_operation_id = self._discourse_latest_operation_id()
        pre_turn_projection = self._authoritative_projection()
        message = self._send_turn(text, session_context)
        if self._authoritative_projection() != pre_turn_projection:
            self._record_dialogue_turn()
        self._record_thread_turn(text)
        return message

    #: The conversational snapshots added by Stages 2/3/5 — METADATA, not
    #: authoritative state (see :meth:`_authoritative_projection`).
    _CONVERSATIONAL_SNAPSHOTS: tuple[str, ...] = (
        "dialogue_state",
        "discourse_state",
        "thread_state",
    )

    def _authoritative_projection(self) -> str:
        """The state WITHOUT the conversational snapshots (Stage 1–10 audit).

        Stages 2/3/5 add ``dialogue_state`` / ``discourse_state`` / ``thread_state``
        to :class:`ConversationState` as conversational METADATA. They are persisted
        together with a turn that changed authoritative state, but a turn that
        changed nothing else is not a state mutation: pure no-op turns
        (acknowledgement / recall / refused repeat) keep the existing state object,
        exactly as they did before these stages.
        """
        if self._state_manager is None:
            return ""
        data = self._state_manager.state.to_dict()
        for key in self._CONVERSATIONAL_SNAPSHOTS:
            data.pop(key, None)
        return json.dumps(data, sort_keys=True, default=str)

    def _send_turn(
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

        # NLU-4 — capture explicitly named conversational entities for
        # reference resolution on later turns.
        self._capture_conversational_entities(text)

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
        # Step 9 — resolve an outstanding clarification BEFORE any other surface
        # can reinterpret the follow-up. A candidate-selection reply resumes the
        # correct route; a genuine new request clears the clarification and
        # continues unchanged; nothing is guessed or executed.
        clarification_resolution = self._maybe_resolve_clarification(text, spec)
        if clarification_resolution is not None:
            self._conversation.add_message(clarification_resolution)
            return clarification_resolution
        # C7 GAP-C31-02 — bounded deterministic reference/context exposure.
        # Applied only to recognized multi-word reference phrases, before the
        # single existing routing cascade. AMBIGUOUS reuses the existing
        # clarification mechanism; UNRESOLVED and non-reference turns are
        # byte-for-byte unchanged.
        if spec is not None:
            # L4 — bounded deterministic entity identification. Known entity
            # names the user explicitly wrote are recorded as evidence and, when
            # exactly one is named, become the bounded conversation subject;
            # routing is untouched and nothing is guessed.
            spec = self._apply_entity_identification(spec, text)
            spec, reference_response = self._apply_reference_resolution(spec, text)
            if reference_response is not None:
                self._conversation.add_message(reference_response)
                return reference_response
        # Repeat/re-check of the most recent governed operation (bounded,
        # whole-turn). The RETAINED operation kind decides the response — never
        # the phrase's verb; only read-only handlers are re-entered and
        # governed/mutating operations are refused. Unrecognized forms and the
        # no-retained-operation case fall through unchanged.
        repeat_response = self._maybe_handle_repeat_request(text, spec)
        if repeat_response is not None:
            self._conversation.add_message(repeat_response)
            return repeat_response
        # C4.1 — explicit capability-detail precedence. An "explain <name>"
        # request that names a REGISTERED capability/tool must reach the
        # deterministic capability-detail surface even when the name itself
        # contains an investigation/research cue token ("analysis", "trace",
        # "research"), which would otherwise preempt it via intake
        # classification. Narrow and authoritative: only a registered name is
        # claimed and nothing is fabricated. Ordinary investigation/research
        # requests do not start with an explicit detail verb, so they are never
        # captured here.
        capability_detail = self._maybe_handle_capability_detail_request(text)
        if capability_detail is not None:
            self._conversation.add_message(capability_detail)
            return capability_detail
        # Step 13 — a bounded capability-STATE question ("is investigation
        # available?", "why can't you research?", "which capabilities are
        # unavailable?") is answered from the SAME unified capability model the
        # kernel exposes, BEFORE an operational route can misinterpret it as a
        # request to run. An unresolvable name declines (fail-closed).
        capability_state = self._maybe_handle_capability_state_question(text)
        if capability_state is not None:
            self._conversation.add_message(capability_state)
            return capability_state
        # Step 14 — a bounded architecture self-understanding question
        # ("which component owns X?", "what is the responsibility of the X
        # component?", "what are your governance boundaries?", "what
        # architecture information do you not know?") is answered from the SAME
        # architecture/capability models BEFORE an operational route can
        # misinterpret it. Unresolvable targets decline (fail-closed).
        architecture_question = self._maybe_handle_architecture_question(text)
        if architecture_question is not None:
            self._conversation.add_message(architecture_question)
            return architecture_question
        # Temporary Roadmap Step 1 — a bounded question about the CURRENT state
        # of the knowledge Atlas itself retains ("is your knowledge about X still
        # current?", "how fresh is the X information you hold?") is answered from
        # the EXISTING temporal seam BEFORE the generic knowledge/research routes
        # can reinterpret it as a request for external information. Internal-state
        # ownership outranks generic knowledge; an unwired seam declines
        # (fail-closed) so the existing route is unchanged.
        knowledge_state = self._maybe_handle_knowledge_state_question(text)
        if knowledge_state is not None:
            self._conversation.add_message(knowledge_state)
            return knowledge_state
        # Temporary Roadmap Step 1 — a request to AUTHORIZE a research source (or
        # to change the host allowlist) is answered by a bounded EXPLANATION of
        # the existing deny-by-default policy, never by performing it. Claimed
        # only when the turn names a source/host object, so a development
        # approval ("authorize this proposal") keeps its own route.
        source_authorization = self._maybe_handle_source_authorization_request(text)
        if source_authorization is not None:
            self._conversation.add_message(source_authorization)
            return source_authorization
        # Temporary Roadmap Step 4 — a bounded GOVERNED external-research turn
        # (an explicit URL/GitHub target in a research request) is carried through
        # the EXISTING acquisition/provenance/retention mechanisms by the injected
        # kernel bridge BEFORE the generic knowledge route can reinterpret the URL
        # as a knowledge query. It runs AFTER the source-authorization owner, so a
        # request to CHANGE authorization is never claimed here, and it declines
        # when no target is named or the bridge is unwired/raising.
        external_research = self._maybe_handle_external_research(text)
        if external_research is not None:
            self._conversation.add_message(external_research)
            return external_research
        # Evidence-driven improvement 1 — Atlas-informational self-knowledge
        # topics and external-knowledge requests are claimed deterministically
        # BEFORE the development/execution handlers, so an informational
        # question cannot be answered as a development action.
        evidence_self_knowledge = self._maybe_handle_evidence_self_knowledge(text)
        if evidence_self_knowledge is not None:
            self._conversation.add_message(evidence_self_knowledge)
            return evidence_self_knowledge
        # Checkpoint 4 — a bound reference is ANSWERED from the retained
        # conversation fact by the existing reference surface, BEFORE any
        # research/knowledge/orchestration route can reinterpret the turn as a
        # new operation ("what did you find?" must not run a fresh search or
        # demand a target). Narrow by construction: only a pure
        # reference/follow-up turn carrying a resolved reference and no
        # operation of its own; it never falls through to a provider.
        reference_answer = self._maybe_answer_resolved_reference(text, spec)
        if reference_answer is not None:
            self._conversation.add_message(reference_answer)
            return reference_answer
        # Step 8 — returning to a topic the conversation already covered. Claims
        # ONLY a bounded return form naming a matching PRIOR topic in the world
        # state; it reactivates that topic (never executes, never invents one)
        # and fails closed otherwise, so every existing route is unchanged.
        topic_return = self._maybe_handle_topic_return(text)
        if topic_return is not None:
            self._conversation.add_message(topic_return)
            return topic_return
        # Evidence gap analysis — a bounded request to analyze the retained
        # investigation findings reaches the EXISTING deterministic
        # EvidenceGapAnalyzer over the retained InvestigationReport. Read-only,
        # model-free and state-preserving: it never re-investigates, never
        # overwrites the retained investigation/result, and never authorizes,
        # approves, or executes anything.
        gap_analysis = self._maybe_handle_evidence_gap_analysis(text)
        if gap_analysis is not None:
            self._conversation.add_message(gap_analysis)
            return gap_analysis
        # Step 2 — Goal-Centered Orchestration. Narrowly guarded: a bounded
        # multi-stage goal (the existing decomposition composes >=2 steps)
        # sequences through the EXISTING kernel-owned OrchestrationExecutor, and
        # an EXACT bounded status form with an active plan is answered from the
        # retained plan. Anything else returns None and keeps its existing route.
        goal_response = self._maybe_handle_goal_request(text)
        if goal_response is not None:
            self._conversation.add_message(goal_response)
            return goal_response
        # Step 2 — resume the retained UNFINISHED plan (only a bounded
        # continuation turn with an incomplete plan is claimed).
        goal_resume = self._maybe_handle_goal_resume(text)
        if goal_resume is not None:
            self._conversation.add_message(goal_resume)
            return goal_resume
        goal_followup = self._maybe_handle_goal_followup(text)
        if goal_followup is not None:
            self._conversation.add_message(goal_followup)
            return goal_followup
        external_knowledge = self._maybe_handle_external_knowledge(text)
        if external_knowledge is not None:
            self._conversation.add_message(external_knowledge)
            return external_knowledge
        # Evidence-Driven Improvement 3 — an explicit research/knowledge request
        # is a request for INFORMATION, so it enters the existing local-first
        # knowledge path (D3 → governed D2) instead of the generic work flow.
        compound = self._maybe_handle_compound_request(text)
        if compound is not None:
            self._conversation.add_message(compound)
            return compound
        # Step 10 — a genuinely multi-intent/multi-step OPERATIONAL request that
        # the existing routes did not own (research-led compound shapes keep the
        # compound route above) is understood — ordered steps, explicit
        # dependencies — and its runnable read-only steps run through the
        # EXISTING orchestration bridge; every other step is reported truthfully.
        multi_step = self._maybe_handle_multi_step(text)
        if multi_step is not None:
            self._conversation.add_message(multi_step)
            return multi_step
        knowledge_request = self._maybe_handle_knowledge_request(text, spec)
        if knowledge_request is not None:
            self._conversation.add_message(knowledge_request)
            return knowledge_request
        # Evidence-driven improvement 1 — bare knowledge follow-ups resolve
        # against the immediately preceding knowledge answer (read-only).
        knowledge_followup = self._maybe_handle_knowledge_followup(text)
        if knowledge_followup is not None:
            self._conversation.add_message(knowledge_followup)
            return knowledge_followup
        # G1 — a frame-determined ambiguous request asks for its subject.
        clarification = self._maybe_handle_frame_clarification(text)
        if clarification is not None:
            self._conversation.add_message(clarification)
            return clarification
        # Step 6 — a request with more than one bounded intent answers every
        # understood part and reports any unhandled part instead of silently
        # reducing the turn to its first clause.
        multi_intent = self._maybe_handle_multi_intent(text)
        if multi_intent is not None:
            self._conversation.add_message(multi_intent)
            return multi_intent
        # Step 7 — an earlier-item reference the existing surfaces could not
        # resolve is represented honestly instead of guessing.
        ordinal_reference = self._maybe_handle_ordinal_reference(text)
        if ordinal_reference is not None:
            self._conversation.add_message(ordinal_reference)
            return ordinal_reference
        # Stage 4 — communicative-function-aware routing. A QUERY about prior
        # output ("what did you find?", "can you explain the result of the
        # investigation you just completed?", "why did you investigate that?") is
        # answered from the retained result, so a TOPIC word such as
        # "investigation" cannot by itself start a new investigation. It runs
        # AFTER every builtin/reference/knowledge surface (they keep precedence)
        # and BEFORE the operation handlers.
        result_query = self._maybe_handle_result_query(text, spec)
        if result_query is not None:
            self._conversation.add_message(result_query)
            return result_query
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
        # C4.2 — bounded repository impact-analysis exposure. Read-only and
        # deterministic; reuses the existing RepositoryMap capability.
        if spec is not None and spec.task_type is TaskType.REPOSITORY_IMPACT_REQUEST:
            impact_response = self._maybe_handle_repository_impact_request(
                spec, original_text=text
            )
            if impact_response is not None:
                self._conversation.add_message(impact_response)
                return impact_response
        # Autonomy semantics — explicit request to proceed autonomously
        # with an already-approved development plan. L1 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.AUTONOMY_REQUEST:
            autonomy_response = self._maybe_handle_autonomy_request(spec)
            if autonomy_response is not None:
                self._conversation.add_message(autonomy_response)
                return autonomy_response
        # L2 Autonomy semantics — explicit request to chain workflows or
        # make bounded plan adjustments. L2 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.L2_AUTONOMY_REQUEST:
            l2_response = self._maybe_handle_l2_autonomy_request(spec)
            if l2_response is not None:
                self._conversation.add_message(l2_response)
                return l2_response
        # L3 Autonomy semantics — explicit request to execute recovery,
        # generate sub-plans, or handle HIGH risk. L3 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.L3_AUTONOMY_REQUEST:
            l3_response = self._maybe_handle_l3_autonomy_request(spec)
            if l3_response is not None:
                self._conversation.add_message(l3_response)
                return l3_response
        # L4 Autonomy semantics — explicit request to acquire capabilities,
        # modify memory/knowledge, or handle CRITICAL risk. L4 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.L4_AUTONOMY_REQUEST:
            l4_response = self._maybe_handle_l4_autonomy_request(spec)
            if l4_response is not None:
                self._conversation.add_message(l4_response)
                return l4_response
        # L5 Autonomy semantics — explicit request to coordinate across objectives,
        # prioritize work, or manage dependencies. L5 controlled autonomy (FINAL LEVEL).
        if spec is not None and spec.task_type is TaskType.L5_AUTONOMY_REQUEST:
            l5_response = self._maybe_handle_l5_autonomy_request(spec)
            if l5_response is not None:
                self._conversation.add_message(l5_response)
                return l5_response
        # Development semantics win — run it first and never reroute development
        # through orchestration.
        development_response = self._development_request_route(spec, text)
        if development_response is not None:
            self._conversation.add_message(development_response)
            return development_response

        # P7.4 — route a pending confirmation reply through the local
        # coordinator (conversation-owned; never reaches F9 directly).
        coordinated = self._maybe_handle_development_need_confirmation(text, active_session)
        if coordinated is not None:
            self._conversation.add_message(coordinated)
            return coordinated

        # Model-independent conversational path (Phase 1): casual turns are
        # answered deterministically without any AI provider. Governed turns
        # fall through to the existing pipeline unchanged.
        builtin_response = self._maybe_handle_builtin_response(spec, text)
        cognition_delegated = False
        if builtin_response is not None:
            # L8-c — the existing L7 eligibility signal, produced by this very
            # floor reply, is the only thing that permits delegation to
            # cognition. It is honoured only when the cognition boundary is
            # actually wired: with no pipeline to consult there is nothing to
            # delegate to, so the floor stays terminal exactly as before.
            if self._cognition_api is not None and _delegated_by_eligibility(
                builtin_response
            ):
                cognition_delegated = True
            else:
                self._conversation.add_message(builtin_response)
                return builtin_response

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
            # L1 — typed turn-meaning contract at the cognition boundary. It
            # rides a dedicated parameter; the legacy metadata payload above is
            # untouched and stays backward-compatible.
            cognition_kwargs: dict[str, Any] = {}
            if spec is not None:
                cognition_kwargs["turn_meaning"] = self._build_turn_meaning(spec, text)
            decision = self._cognition_api.process(
                user_input=text,
                goal=spec.goal_string() if spec is not None else text,
                metadata=cognition_metadata,
                **cognition_kwargs,
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

            # L8-b-ii — deterministic response precedence, applied ONLY to a
            # turn the eligibility signal actually delegated. A trustworthy
            # non-local pipeline answer is owned by the conversation layer as
            # the single user-facing response, so the redundant
            # conversation-level AI call is not made. Otherwise the pipeline
            # produced nothing surfaceable (empty, L6-blocked, or the local
            # no-network tier), and the terminal deterministic fallback chain
            # applies — again with no second AI invocation. Turns that reached
            # cognition any other way keep today's behaviour exactly.
            if cognition_delegated:
                pipeline_answer = _usable_pipeline_response(decision.data)
                if pipeline_answer is not None:
                    assistant_message = Message(
                        role="assistant",
                        content=pipeline_answer,
                        metadata=_pipeline_response_metadata(decision.data),
                    )
                    self._conversation.add_message(assistant_message)
                    return assistant_message
                assistant_message = self._deterministic_fallback(
                    text,
                    spec,
                    active_session,
                    "pipeline produced no trustworthy answer",
                )
                self._conversation.add_message(assistant_message)
                return assistant_message
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
                metadata=_model_response_metadata(response),
            )
        except Exception as exc:
            # Phase 4 — an opted-in external provider failed (or the AI path
            # was reached without opt-in): serve the built-in deterministic
            # response first so ordinary conversation stays useful, then the
            # legacy deterministic fallback, then the bounded notice.
            assistant_message = self._deterministic_fallback(
                text, spec, active_session, str(exc)
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
        """Stream a response through Atlas.

        Stage 2 — matches :meth:`send`: the bounded dialogue turn is recorded
        AFTER the existing cascade completes, through the same single seam, so the
        recording is route-independent and send/stream stay equivalent.
        """
        self._last_meaning = None
        self._pre_turn_operation_id = self._discourse_latest_operation_id()
        pre_turn_projection = self._authoritative_projection()
        yield from self._stream_turn(text, session_context)
        if self._authoritative_projection() != pre_turn_projection:
            self._record_dialogue_turn()
        self._record_thread_turn(text)

    def _stream_turn(
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

        # NLU-4 — capture explicitly named conversational entities for
        # reference resolution on later turns.
        self._capture_conversational_entities(text)

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
        # Step 9 — mirror of send(): resolve an outstanding clarification before
        # any other surface can reinterpret the follow-up.
        clarification_resolution = self._maybe_resolve_clarification(text, spec)
        if clarification_resolution is not None:
            self._conversation.add_message(clarification_resolution)
            yield clarification_resolution.content
            return
        # C7 GAP-C31-02 (+ Phase 4) — bounded reference/context exposure on the
        # streaming path, mirroring send(): same method, same ordering, same
        # semantics. RESOLVED attaches structured evidence and routing
        # continues; AMBIGUOUS yields the existing bounded clarification and
        # stops; UNRESOLVED / non-reference turns are byte-for-byte unchanged.
        if spec is not None:
            # L4 — bounded deterministic entity identification, mirroring
            # send(): same method, same ordering, same semantics.
            spec = self._apply_entity_identification(spec, text)
            spec, reference_response = self._apply_reference_resolution(spec, text)
            if reference_response is not None:
                self._conversation.add_message(reference_response)
                yield reference_response.content
                return
        # Repeat/re-check of the most recent governed operation — mirror of
        # send(): same method, same placement, same semantics.
        repeat_response = self._maybe_handle_repeat_request(text, spec)
        if repeat_response is not None:
            self._conversation.add_message(repeat_response)
            yield repeat_response.content
            return
        # C4.1 — explicit capability-detail precedence. Mirror of send(): same
        # handler, same placement, same semantics. Registered names containing
        # an investigation/research cue token reach the capability-detail
        # surface instead of being preempted by intake classification.
        capability_detail = self._maybe_handle_capability_detail_request(text)
        if capability_detail is not None:
            self._conversation.add_message(capability_detail)
            yield capability_detail.content
            return
        # Step 13 — mirror of send(): a bounded capability-STATE question is
        # answered from the SAME unified capability model before an operational
        # route can misinterpret it.
        capability_state = self._maybe_handle_capability_state_question(text)
        if capability_state is not None:
            self._conversation.add_message(capability_state)
            yield capability_state.content
            return
        # Step 14 — mirror of send(): a bounded architecture self-understanding
        # question is answered from the SAME architecture/capability models.
        architecture_question = self._maybe_handle_architecture_question(text)
        if architecture_question is not None:
            self._conversation.add_message(architecture_question)
            yield architecture_question.content
            return
        # Temporary Roadmap Step 1 (mirror of send()): internal-state ownership
        # outranks generic knowledge — the state of Atlas's OWN retained
        # knowledge is answered from the EXISTING temporal seam, and a request to
        # authorize a research source is answered by an explanation of the
        # existing deny-by-default policy rather than by performing it.
        knowledge_state = self._maybe_handle_knowledge_state_question(text)
        if knowledge_state is not None:
            self._conversation.add_message(knowledge_state)
            yield knowledge_state.content
            return
        source_authorization = self._maybe_handle_source_authorization_request(text)
        if source_authorization is not None:
            self._conversation.add_message(source_authorization)
            yield source_authorization.content
            return
        # Temporary Roadmap Step 4 — the send() mirror of the governed
        # external-research route (same owner, same fail-closed rule).
        external_research = self._maybe_handle_external_research(text)
        if external_research is not None:
            self._conversation.add_message(external_research)
            yield external_research.content
            return
        # Evidence-driven improvement 1 — Atlas-informational self-knowledge
        # topics and external-knowledge requests (mirror of send()).
        evidence_self_knowledge = self._maybe_handle_evidence_self_knowledge(text)
        if evidence_self_knowledge is not None:
            self._conversation.add_message(evidence_self_knowledge)
            yield evidence_self_knowledge.content
            return
        # Checkpoint 4 (mirror of send()) — a bound reference is ANSWERED from the
        # retained conversation fact by the existing reference surface, BEFORE any
        # research/knowledge/operation route can reinterpret the turn as a new
        # operation. This mirror removes a pre-existing send/stream asymmetry.
        reference_answer = self._maybe_answer_resolved_reference(text, spec)
        if reference_answer is not None:
            self._conversation.add_message(reference_answer)
            yield reference_answer.content
            return
        # Step 8 — returning to a prior topic (mirror of send(): same handler,
        # same placement, same semantics). Reactivates a matching prior topic;
        # never executes and fails closed.
        topic_return = self._maybe_handle_topic_return(text)
        if topic_return is not None:
            self._conversation.add_message(topic_return)
            yield topic_return.content
            return
        # Evidence gap analysis (mirror of send(): same handler, same
        # placement, same semantics). Read-only and state-preserving.
        gap_analysis = self._maybe_handle_evidence_gap_analysis(text)
        if gap_analysis is not None:
            self._conversation.add_message(gap_analysis)
            yield gap_analysis.content
            return
        # Step 2 — Goal-Centered Orchestration (mirror of send()).
        goal_response = self._maybe_handle_goal_request(text)
        if goal_response is not None:
            self._conversation.add_message(goal_response)
            yield goal_response.content
            return
        goal_resume = self._maybe_handle_goal_resume(text)
        if goal_resume is not None:
            self._conversation.add_message(goal_resume)
            yield goal_resume.content
            return
        goal_followup = self._maybe_handle_goal_followup(text)
        if goal_followup is not None:
            self._conversation.add_message(goal_followup)
            yield goal_followup.content
            return
        external_knowledge = self._maybe_handle_external_knowledge(text)
        if external_knowledge is not None:
            self._conversation.add_message(external_knowledge)
            yield external_knowledge.content
            return
        # Evidence-Driven Improvement 3 — research/knowledge requests (mirror of
        # send(): same handler, same placement, same semantics).
        compound = self._maybe_handle_compound_request(text)
        if compound is not None:
            self._conversation.add_message(compound)
            yield compound.content
            return
        # Step 10 — mirror of send(): understand a multi-intent/multi-step
        # operational request and route its runnable read-only steps through the
        # EXISTING orchestration bridge.
        multi_step = self._maybe_handle_multi_step(text)
        if multi_step is not None:
            self._conversation.add_message(multi_step)
            yield multi_step.content
            return
        knowledge_request = self._maybe_handle_knowledge_request(text, spec)
        if knowledge_request is not None:
            self._conversation.add_message(knowledge_request)
            yield knowledge_request.content
            return
        # Evidence-driven improvement 1 — bare knowledge follow-ups (mirror of
        # send(): same handler, same placement, same semantics).
        knowledge_followup = self._maybe_handle_knowledge_followup(text)
        if knowledge_followup is not None:
            self._conversation.add_message(knowledge_followup)
            yield knowledge_followup.content
            return
        # G1 — frame-determined ambiguity asks for its subject (mirror of send()).
        clarification = self._maybe_handle_frame_clarification(text)
        if clarification is not None:
            self._conversation.add_message(clarification)
            yield clarification.content
            return
        # Step 6 — mirror of send().
        multi_intent = self._maybe_handle_multi_intent(text)
        if multi_intent is not None:
            self._conversation.add_message(multi_intent)
            yield multi_intent.content
            return
        # Step 7 — mirror of send().
        ordinal_reference = self._maybe_handle_ordinal_reference(text)
        if ordinal_reference is not None:
            self._conversation.add_message(ordinal_reference)
            yield ordinal_reference.content
            return
        # Stage 4 — same communicative-function-aware result-query route as send().
        result_query = self._maybe_handle_result_query(text, spec)
        if result_query is not None:
            self._conversation.add_message(result_query)
            yield result_query.content
            return
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
        # C4.2 — bounded repository impact-analysis exposure. Read-only and
        # deterministic; reuses the existing RepositoryMap capability.
        # Mirrors send(): same handler, same arguments, same position — without
        # it this turn falls through the whole governed cascade to the provider.
        if spec is not None and spec.task_type is TaskType.REPOSITORY_IMPACT_REQUEST:
            impact_response = self._maybe_handle_repository_impact_request(
                spec, original_text=text
            )
            if impact_response is not None:
                self._conversation.add_message(impact_response)
                yield impact_response.content
                return
        # Autonomy semantics — explicit request to proceed autonomously
        # with an already-approved development plan. L1 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.AUTONOMY_REQUEST:
            autonomy_response = self._maybe_handle_autonomy_request(spec)
            if autonomy_response is not None:
                self._conversation.add_message(autonomy_response)
                yield autonomy_response.content
                return
        # L2 Autonomy semantics — explicit request to chain workflows or
        # make bounded plan adjustments. L2 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.L2_AUTONOMY_REQUEST:
            l2_response = self._maybe_handle_l2_autonomy_request(spec)
            if l2_response is not None:
                self._conversation.add_message(l2_response)
                yield l2_response.content
                return
        # L3 Autonomy semantics — explicit request to execute recovery,
        # generate sub-plans, or handle HIGH risk. L3 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.L3_AUTONOMY_REQUEST:
            l3_response = self._maybe_handle_l3_autonomy_request(spec)
            if l3_response is not None:
                self._conversation.add_message(l3_response)
                yield l3_response.content
                return
        # L4 Autonomy semantics — explicit request to acquire capabilities,
        # modify memory/knowledge, or handle CRITICAL risk. L4 controlled autonomy.
        if spec is not None and spec.task_type is TaskType.L4_AUTONOMY_REQUEST:
            l4_response = self._maybe_handle_l4_autonomy_request(spec)
            if l4_response is not None:
                self._conversation.add_message(l4_response)
                yield l4_response.content
                return
        # L5 Autonomy semantics — explicit request to coordinate across objectives,
        # prioritize work, or manage dependencies. L5 controlled autonomy (FINAL LEVEL).
        if spec is not None and spec.task_type is TaskType.L5_AUTONOMY_REQUEST:
            l5_response = self._maybe_handle_l5_autonomy_request(spec)
            if l5_response is not None:
                self._conversation.add_message(l5_response)
                yield l5_response.content
                return
        # Development semantics win — run it first and never reroute development
        # through orchestration.
        development_response = self._development_request_route(spec, text)
        if development_response is not None:
            self._conversation.add_message(development_response)
            yield development_response.content
            return

        # P7.4 — route a pending confirmation reply through the local
        # coordinator (conversation-owned; never reaches F9 directly).
        # Mirrors send(): without it a confirmation reply is never consumed on
        # the user-facing path and the pending confirmation stays unresolved.
        coordinated = self._maybe_handle_development_need_confirmation(text, active_session)
        if coordinated is not None:
            self._conversation.add_message(coordinated)
            yield coordinated.content
            return

        # Model-independent conversational path (Phase 1): same placement as
        # send() — after every governed handler, before orchestration/AI.
        builtin_response = self._maybe_handle_builtin_response(spec, text)
        cognition_delegated = False
        if builtin_response is not None:
            # L8-c — same bounded delegation rule as send(): only the existing
            # L7 eligibility signal, and only when cognition is wired.
            if self._cognition_api is not None and _delegated_by_eligibility(
                builtin_response
            ):
                cognition_delegated = True
            else:
                self._conversation.add_message(builtin_response)
                yield builtin_response.content
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
            # L1 — typed turn-meaning contract at the cognition boundary. It
            # rides a dedicated parameter; the legacy metadata payload above is
            # untouched and stays backward-compatible.
            cognition_kwargs: dict[str, Any] = {}
            if spec is not None:
                cognition_kwargs["turn_meaning"] = self._build_turn_meaning(spec, text)
            decision = self._cognition_api.process(
                user_input=text,
                goal=spec.goal_string() if spec is not None else text,
                metadata=cognition_metadata,
                **cognition_kwargs,
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

            # L8-b-ii — streaming parity with send(): identical deterministic
            # precedence, gated on the same delegated-turn condition, with no
            # second AI invocation.
            if cognition_delegated:
                pipeline_answer = _usable_pipeline_response(decision.data)
                if pipeline_answer is not None:
                    assistant_message = Message(
                        role="assistant",
                        content=pipeline_answer,
                        metadata={
                            "cognition": {"source": "pipeline_final_response"}
                        },
                    )
                    self._conversation.add_message(assistant_message)
                    yield pipeline_answer
                    return
                fallback_message = self._deterministic_fallback(
                    text,
                    spec,
                    active_session,
                    "pipeline produced no trustworthy answer",
                )
                self._conversation.add_message(fallback_message)
                yield fallback_message.content
                return
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
                # Phase 4 — pre-token stream failure: built-in response
                # first, then the deterministic fallback stream, then the
                # bounded notice.
                builtin_message = self._builtin_after_failure(text, spec)
                if builtin_message is not None:
                    assistant_text = builtin_message.content
                    yield builtin_message.content
                elif self._fallback_resolver is not None:
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

    #: Casual conversational task types are served by the built-in
    #: deterministic engine by default; they must not carry a complexity
    #: floor that selects an external provider.
    _BUILTIN_FIRST_TASK_TYPES: frozenset[str] = frozenset(
        {"conversation", "unknown", "question"}
    )

    def _build_routing_request(
        self,
        text: str,
        spec: TaskSpec | None = None,
    ) -> RoutingRequest:
        """Build a minimal deterministic RoutingRequest from the user input.

        Phase 20 Batch 6 — the direct conversation path (send/stream) can
        bypass the RuntimeCoordinator, so the existing ModelRouter would
        otherwise stay dormant for CLI chat.

        Phase 2 — casual conversational turns (conversation / unknown /
        question) are served by the built-in deterministic engine by
        default, so they carry the baseline 0.3 complexity (the Mock /
        no-network tier) instead of a floor that selects an external
        provider. Only non-casual turns escalate with input length.

        B2 — when a TaskSpec is available, its deterministic task type is
        reflected in the routing request (no behavioral change to the
        model router; the spec only supplies the existing task_type field).
        """
        task_type = "conversation"
        if spec is not None:
            task_type = spec.task_type.value

        length = max(1, len(text.strip()))
        if task_type in self._BUILTIN_FIRST_TASK_TYPES:
            complexity = 0.3
        elif length <= 40:
            complexity = 0.5
        elif length <= 120:
            complexity = 0.6
        else:
            complexity = 0.7

        metadata: dict[str, object] = {"source": "conversation_service"}
        if (
            self._provider_call_timeout_s is not None
            and self._provider_call_timeout_s > 0
        ):
            metadata["conversation_timeout_s"] = self._provider_call_timeout_s

        return RoutingRequest(
            complexity=complexity,
            latency_requirement="fast",
            task_type=task_type,
            context_size=length,
            metadata=metadata,
        )

    def _intake(self, text: str, history_length: int = 0) -> TaskSpec | None:
        """Run the optional task intake, preserving legacy behavior when None.

        D1 — interpretation now flows through the deterministic Conversation
        Engine: the existing intake result is unchanged, the bounded
        :class:`SemanticIntake` projection is attached to ``spec.context``, and
        the bounded conversational-state fields (objective/subtasks/corrections)
        are updated. The engine never routes, authorizes, or executes; every
        existing routing rule downstream is untouched.
        """
        if self._engine is not None:
            state = (
                self._state_manager.state if self._state_manager is not None else None
            )
            prior_objective = bool(state is not None and state.current_objective)
            interpretation = self._engine.interpret(
                text, history_length=history_length, state=state
            )
            spec = interpretation.spec
            if spec is None:
                return None
            if self._state_manager is not None:
                updates = self._engine.state_updates(interpretation, state)
                if updates:
                    self._state_manager.update(**updates)
            spec = self._engine.with_semantic(spec, interpretation.semantic)
            # Stage 1 — attach the bounded L1 meaning projection. Additive and
            # PROCEED-only: it changes no routing and is fail-soft.
            return self._attach_meaning(text, spec, interpretation, prior_objective)
        if self._task_intake is None:
            return None
        return self._task_intake.intake(text, history_length=history_length)

    def _attach_meaning(
        self,
        text: str,
        spec: TaskSpec,
        interpretation: Any,
        prior_objective: bool,
    ) -> TaskSpec:
        """Attach the bounded L1 meaning projection to ``spec`` (Stage 1).

        Representation only and PROCEED-only: it projects the EXISTING
        deterministic interpretation into an :class:`AtlasMeaning`, records it
        on ``spec.context`` (the same additive channel ``semantic_intake`` uses)
        and exposes it via :attr:`last_meaning`. It never routes, authorizes, or
        executes, and it is fail-soft — an empty result or any failure leaves
        ``spec`` unchanged so no turn can be broken. The legacy intake-less path
        never reaches here.
        """
        from dataclasses import replace as _replace

        self._last_meaning = None
        try:
            has_knowledge_context = False
            try:
                has_knowledge_context = bool(self._active_knowledge_subject())
            except Exception:  # fail-soft: context probe never breaks a turn
                has_knowledge_context = False
            meaning = build_atlas_meaning(
                text,
                spec=spec,
                semantic=getattr(interpretation, "semantic", None),
                turn_role=getattr(interpretation, "turn_role", None),
                has_prior_objective=bool(prior_objective),
                has_knowledge_context=has_knowledge_context,
            )
        except Exception:  # fail-soft: meaning construction is never fatal
            return spec
        self._last_meaning = meaning
        context = dict(spec.context) if isinstance(spec.context, dict) else {}
        context[ATLAS_MEANING_KEY] = meaning.to_dict()
        # Stage 8 — optional linguistic evidence (advisory, bounded, fail-safe).
        # It NEVER routes, authorizes, or overwrites meaning; it rides the context
        # as a separate evidence projection for later consumers (e.g. Stage 6).
        try:
            evidence = self._linguistic.analyse(text)
            semantic = getattr(meaning, "semantic_intake", None)
            illocution = getattr(semantic, "act", "") if semantic is not None else ""
            adjudication = self._linguistic.adjudicate(
                evidence, deterministic_illocution=illocution
            )
            self._last_linguistic_evidence = evidence
            self._last_linguistic_adjudication = adjudication.to_dict()
            context[LINGUISTIC_EVIDENCE_KEY] = {
                **evidence.to_dict(),
                "adjudication": adjudication.to_dict(),
            }
        except Exception:  # fail-soft: linguistic evidence never breaks a turn
            self._last_linguistic_evidence = LinguisticEvidence()
            self._last_linguistic_adjudication = None
        # Stage 9 — optional LOCAL learned reference proposals (OFF by default).
        # Advisory evidence only: they never route, resolve, or authorize, and
        # Atlas (Stage 6) decides. A failure here never breaks a turn.
        if self._learned_proposer is not None:
            try:
                discourse = (
                    self._state_manager.state.discourse_state
                    if self._state_manager is not None
                    else None
                )
                candidate_list = [
                    (referent.referent_id, referent.label)
                    for referent in (getattr(discourse, "referents", ()) or ())
                    if getattr(referent, "kind", "") in ("result", "operation")
                    and getattr(referent, "referent_id", "")
                ]
                proposal_result = self._learned_proposer.propose(
                    text, candidates=candidate_list
                )
                payload = proposal_result.to_dict()
                self._last_reference_proposals = payload
                context[REFERENCE_PROPOSALS_KEY] = payload
            except Exception:  # fail-soft: learned proposals never break a turn
                self._last_reference_proposals = None
        return _replace(spec, context=context)

    @property
    def last_meaning(self) -> AtlasMeaning | None:
        """The bounded L1 meaning of the most recent interpreted turn, or None."""
        return self._last_meaning

    @property
    def last_linguistic_evidence(self) -> LinguisticEvidence | None:
        """The optional provider's bounded evidence for the last turn, or None."""
        return self._last_linguistic_evidence

    def _record_dialogue_turn(self) -> None:
        """Record the bounded dialogue turn through the single state seam (Stage 2).

        Route-independent: invoked once per turn from the public ``send``/``stream``
        entry points AFTER the existing cascade completes, so whichever handler ran
        does not decide whether dialogue state is recorded. It consumes the EXISTING
        Stage 1 :class:`AtlasMeaning` (no re-parsing, no second interpretation path)
        plus the EXISTING state facts, and folds them into ``ConversationState`` via
        the manager's single ``apply_dialogue_turn`` seam. Representation only and
        fail-soft: it never routes, authorizes, or mutates governed state.
        """
        meaning = self._last_meaning
        if meaning is None or self._state_manager is None:
            return
        try:
            outcome = outcome_from(
                meaning,
                self._state_manager.state,
                turn_index=len(self._conversation.messages),
            )
            self._state_manager.apply_dialogue_turn(outcome)
        except Exception:  # fail-soft: dialogue recording never breaks a turn
            return

    def _discourse_latest_operation_id(self) -> str:
        """Return the latest discourse Operation referent id, or ``""``."""
        if self._state_manager is None:
            return ""
        discourse = self._state_manager.state.discourse_state
        return getattr(discourse, "latest_operation_id", "") or ""

    def _active_thread_result_label(self) -> str:
        """Return the ACTIVE Stage 5 thread's result label, or ``""`` (Stage 6).

        Used so a bound RESULT reference prefers the active conversation thread's
        result (strong contextual evidence) over the single most-recent result
        (weak recency evidence). Representation only; fail-soft.
        """
        if self._state_manager is None:
            return ""
        try:
            thread_state = self._state_manager.state.thread_state
            active = thread_state.active() if thread_state is not None else None
            if active is None:
                return ""
            result_id = getattr(active, "result_referent_id", "")
            if not result_id:
                return ""
            discourse = self._state_manager.state.discourse_state
            if discourse is None:
                return ""
            referent = discourse.find(result_id)
            return referent.label if referent is not None else ""
        except Exception:  # fail-soft: never breaks a turn
            return ""

    def _record_thread_turn(self, text: str) -> None:
        """Record the bounded QUD/thread transition through the single seam (Stage 5).

        Consumes already-derived evidence only — the Stage 4 communicative
        function (from :attr:`last_meaning`), the Stage 3 referents recorded for
        the turn, the Stage 4 routing target (when the result-query route ran) and
        the turn text — and folds them into ``ConversationState.thread_state`` via
        the manager's single ``apply_thread_turn`` seam. It never re-parses raw
        text, routes, authorizes or executes anything, and it is fail-soft.
        """
        meaning = self._last_meaning
        if meaning is None or self._state_manager is None:
            return
        try:
            state = self._state_manager.state
            discourse = state.discourse_state
            latest_operation = getattr(discourse, "latest_operation_id", "") or ""
            new_operation = (
                latest_operation
                if latest_operation and latest_operation != self._pre_turn_operation_id
                else ""
            )
            latest_result = getattr(discourse, "latest_result_id", "") or ""
            operation_label = ""
            if new_operation and discourse is not None:
                referent = discourse.find(new_operation)
                if referent is not None:
                    operation_label = referent.label
            decision = self._last_routing_decision
            outcome = thread_outcome_from(
                function=getattr(meaning, "communicative_function", ""),
                turn_index=len(self._conversation.messages),
                text=text,
                objective=operation_label or state.current_objective or "",
                operation_referent_id=new_operation,
                result_referent_id=(latest_result if new_operation else ""),
                target_referent_id=(
                    getattr(decision, "target_referent_id", "") if decision else ""
                ),
            )
            self._state_manager.apply_thread_turn(outcome)
        except Exception:  # fail-soft: thread recording never breaks a turn
            return

    def _contextual_query_defers_to_another_surface(
        self, text: str, spec: TaskSpec | None
    ) -> bool:
        """True when an EXISTING surface must keep ownership of this turn.

        Stage 1–10 audit — the contextual result-query route is ADDITIVE and must
        not become a universal pre-router. Two authoritative signals are used:

          * the deterministic ``TaskType``: a turn a dedicated governed operation
            handler owns (impact / development / planning / execution / recovery /
            verification / report / autonomy / action) is never claimed here;
          * the EXISTING knowledge/recall surface recognizers: a turn shaped like a
            memory-store recall, a validated-knowledge request, or a conversation
            recall ("what did we find?") keeps its own surface.

        Investigation is deliberately NOT in the operation set: its cue family is
        noisy (noun forms), so Stage 4 must adjudicate it — that is the Stage 4
        capability this route exists to provide.
        """
        if spec is not None and getattr(
            spec.task_type, "value", ""
        ) in _CONTEXTUAL_DEFERRED_TASK_TYPES:
            return True
        evidence = getattr(self._last_meaning, "communicative_function_evidence", {}) or {}
        function = getattr(self._last_meaning, "communicative_function", "")
        domain = evidence.get("frame_domain")
        # A question about ATLAS ITSELF (the frame's SELF_KNOWLEDGE domain) belongs
        # to the existing self-knowledge / architecture surfaces — EXCEPT when the
        # bounded reading is a retrospective CAUSE query, where this route's honest
        # "no recorded result" must not be replaced by an architectural guess.
        if domain == _SELF_KNOWLEDGE_DOMAIN and function != FUNCTION_QUERY_CAUSE:
            return True
        # A CAUSE question about a CASUAL/external topic ("why was it built?") is
        # not a question about prior OUTPUT at all: it keeps its open-ended path.
        if function == FUNCTION_QUERY_CAUSE and domain == _CASUAL_DOMAIN:
            return True
        # An IMPERATIVE whose bounded reading is a query is an OPERATION REQUEST
        # ("find out what module handles this capability"), not a retrieval: the
        # surface that owns the operation keeps it. The noisy investigation family
        # is exempt — the function layer must adjudicate those (Stage 4).
        if evidence.get("illocution") == "request" and (
            spec is None
            or getattr(spec.task_type, "value", "")
            != TaskType.INVESTIGATION_REQUEST.value
        ):
            return True
        if not isinstance(text, str) or not text.strip():
            return False
        try:
            if is_store_recall_shaped(text) or is_validated_knowledge_shaped(text):
                return True
        except Exception:  # fail-soft: an ownership probe never breaks a turn
            pass
        try:
            if detect_turn_role(text, has_prior_objective=True) is TurnRole.RECALL:
                return True
        except Exception:
            pass
        return False

    def _maybe_handle_result_query(self, text: str, spec: TaskSpec | None) -> Message | None:
        """Stage 4 — communicative-function-aware routing for result queries.

        Recognizes a turn whose COMMUNICATIVE FUNCTION is a query about prior
        output ("what did you find?", "can you explain the result of the
        investigation you just completed?", "why did you investigate that?") and
        answers it from the retained result/referent — so a TOPIC word such as
        "investigation" can no longer, by itself, start a NEW investigation.

        Deterministic and fail-closed: an explicit target that cannot be matched,
        or an ambiguous one, asks for clarification; a clear query with no
        retained result is refused honestly (never a fabricated result and never a
        new investigation). Representation only: nothing is executed or
        authorized. Returns ``None`` for every other turn, so the existing
        cascade is unchanged.
        """
        meaning = self._last_meaning
        if meaning is None or self._builtin_response is None:
            return None
        function = getattr(meaning, "communicative_function", "")
        if function not in QUERY_FUNCTIONS:
            return None
        # Stage 1–10 audit — OWNERSHIP BOUNDARY: this route is additive. When an
        # EXISTING governed operation surface or knowledge/recall surface owns the
        # turn, defer (fall through) so that established surface handles it. Only
        # a genuine contextual query about prior output is claimed here.
        if self._contextual_query_defers_to_another_surface(text, spec):
            return None
        state = self._state_manager.state if self._state_manager is not None else None
        discourse = getattr(state, "discourse_state", None)
        thread_state = getattr(state, "thread_state", None)
        decision = resolve_routing(text, function, discourse, thread_state)
        self._last_routing_decision = decision
        # Stage 6 — the bounded salience/ambiguity assessment behind the decision.
        self._last_salience_assessment = dict(decision.assessment or {}) or None
        if decision.route == "existing":
            # Stage 10 — a named-topic follow-up that matched no referent falls
            # through unchanged, so the existing cascade owns the turn (fail-closed).
            return None
        # Stage 7 — bounded, evidence-grounded response composition. The SAME
        # composition is used by send() and stream() (this handler is shared).
        plan = compose_from_decision(function, decision, discourse)
        self._last_response_plan = plan.to_dict()
        metadata: dict[str, Any] = {
            "communicative_function": decision.to_dict(),
            "response_plan": plan.to_dict(),
        }

        if plan.shape == SHAPE_CLARIFICATION:
            question = render_response(plan)
            self._record_pending_clarification(
                KIND_REFERENCE, question, plan.candidates, text
            )
            return Message(role="assistant", content=question, metadata=metadata)

        if plan.shape in (SHAPE_RESULT_SUMMARY, SHAPE_EXPLANATION, SHAPE_UNAVAILABLE):
            if plan.shape == SHAPE_RESULT_SUMMARY:
                # Preserve the existing reference metadata contract.
                metadata["builtin_intent"] = "reference"
                metadata["reference_field"] = "latest_result"
            return Message(
                role="assistant",
                content=render_response(plan),
                metadata=metadata,
            )
        return None

    @staticmethod
    def _attach_session_to_spec(spec: TaskSpec, session_context: SessionContext) -> TaskSpec:
        enriched = dict(spec.context) if isinstance(spec.context, dict) else {}
        enriched["session_id"] = session_context.session_id
        enriched["principal_id"] = session_context.principal_id
        enriched["authority"] = session_context.authority.value
        from dataclasses import replace as _replace

        return _replace(spec, context=enriched)

    def _capture_conversational_entities(self, text: str) -> None:
        """NLU-4 — capture explicitly named conversational entities.

        Conversation-scoped, bounded, provenance-carrying, and high-precision:
        only a strong proper-noun surface form is captured. A captured entity
        records only that the user referred to a name — it is never a verified
        fact and never authority. Capture never raises.
        """
        if self._state_manager is None or not isinstance(text, str) or not text.strip():
            return
        try:
            names = capture_named_entities(text)
        except Exception:  # noqa: BLE001 - capture must never break a turn
            return
        if not names:
            return
        turn_id = getattr(self._state_manager.state, "turn_id", "")
        entities = tuple(
            CapturedEntity(name=name, normalized=name.lower(), turn_id=turn_id)
            for name in names
        )
        self._state_manager.record_captured_entities(entities)

    def _apply_entity_identification(self, spec: TaskSpec, text: str) -> TaskSpec:
        """Bounded deterministic entity identification for the current turn (L4).

        Identifies the known entity names the user explicitly wrote in this
        turn, records them as bounded evidence on the existing
        ``TaskSpec.context`` channel, and — only when exactly one entity is
        named — populates the existing bounded ``current_subject`` slot so the
        already-shipped subject references ("this topic", "that issue", "the
        problem") become reachable.

        Zero or multiple entities change nothing: nothing is guessed, no
        reference is resolved here, and routing is untouched. Identification is
        understanding only — it never authorizes, executes, mutates a governed
        field, or bypasses approval. With no catalog configured this is a no-op
        (fail closed).
        """
        catalog = self._entity_catalog
        if catalog is None:
            return spec

        from atlas.conversation.entity_identification import (
            IDENTIFIED_ENTITIES_KEY,
            identify_entities,
        )

        identified = identify_entities(text, catalog)
        if not identified:
            return spec

        from dataclasses import replace as _replace

        enriched = dict(spec.context) if isinstance(spec.context, dict) else {}
        enriched[IDENTIFIED_ENTITIES_KEY] = [entity.to_dict() for entity in identified]
        spec = _replace(spec, context=enriched)

        if len(identified) == 1 and self._state_manager is not None:
            self._state_manager.update(current_subject=identified[0].name)
        return spec

    def _apply_reference_resolution(
        self,
        spec: TaskSpec,
        text: str,
    ) -> tuple[TaskSpec, Message | None]:
        """Bounded deterministic reference/context exposure (C7 GAP-C31-02).

        Read-only interpretation of a bounded, recognized multi-word reference
        phrase against the current :class:`ConversationState`:

          * RESOLVED  -> the referent is attached to the existing structured
            ``TaskSpec.context`` and routing continues unchanged (single pass).
          * AMBIGUOUS -> the existing clarification mechanism is reused; never
            guesses.
          * UNRESOLVED / no bounded reference -> the spec is returned unchanged
            (fail closed; byte-for-byte current behavior).

        Phase 4 adds a bounded *contextual* pass over the Phase 3
        ``ConversationContext``: when no explicit lexicon reference resolves, a
        unique context referent (``the <phrase>`` / bare ``it``/``that``/
        ``this``) is attached as evidence. AMBIGUOUS/UNRESOLVED contextual
        results leave routing byte-for-byte unchanged and never generate a
        clarification message.

        It never authorizes, mutates, rewrites the user's message, invokes a
        handler directly, or runs a second routing pass.
        """
        from atlas.conversation.reference_resolution import (
            ReferenceResolutionStatus,
            has_bounded_reference,
        )

        if has_bounded_reference(text):
            result = self._reference_resolver.resolve(text, self._state_manager.state)

            if result.status is ReferenceResolutionStatus.AMBIGUOUS:
                from dataclasses import replace as _replace

                # Step 9 — preserve the competing candidate VALUES (bounded) so
                # the follow-up can be resolved deterministically.
                values = tuple(
                    str(getattr(self._state_manager.state, field, "") or "")
                    for field in (result.candidates or ())
                )
                self._record_pending_clarification(
                    KIND_REFERENCE,
                    result.reason or "Which subject do you mean?",
                    values,
                    text,
                )
                clarified = _replace(
                    spec,
                    needs_clarification=True,
                    ambiguity=_replace(
                        spec.ambiguity,
                        clarification_questions=(result.reason,),
                    ),
                )
                return spec, self._orchestration_clarification_message(clarified)

            if result.status is ReferenceResolutionStatus.RESOLVED:
                field, value = result.resolved_field, result.resolved_value
                # Stage 6 — a bound reference to a RESULT prefers the ACTIVE
                # thread's result (the strongest contextual evidence) over the
                # single most-recent result. Recency is only a fallback.
                if field == "latest_result":
                    active_label = self._active_thread_result_label()
                    if active_label:
                        value = active_label
                return self._attach_resolved_reference(spec, field, value), None

            # UNRESOLVED -> fall through to the bounded contextual resolver.

        resolve_contextual = getattr(
            self._reference_resolver, "resolve_contextual", None
        )
        if resolve_contextual is not None:
            state = self._state_manager.state if self._state_manager is not None else None
            contextual = resolve_contextual(
                text, self._build_conversation_context(), state
            )
            if contextual.status is ReferenceResolutionStatus.RESOLVED:
                return self._attach_resolved_reference(
                    spec, contextual.resolved_field, contextual.resolved_value
                ), None
            # NLU-5 — a descriptive reference that matches MORE than one captured
            # entity is a genuine ambiguity: ask which one, rather than guessing
            # or silently proceeding. (Only the captured-entity layer raises
            # this; existing investigation/established ambiguities keep the
            # documented "leave routing unchanged" behavior.)
            if contextual.status is ReferenceResolutionStatus.AMBIGUOUS:
                candidates = tuple(contextual.candidates or ())
                if contextual.resolved_field == CAPTURED_ENTITY_FIELD:
                    from dataclasses import replace as _replace

                    question = "Which of the products you mentioned should I use?"
                    self._record_pending_clarification(
                        KIND_REFERENCE, question, candidates, text
                    )
                    clarified = _replace(
                        spec,
                        needs_clarification=True,
                        ambiguity=_replace(
                            spec.ambiguity,
                            clarification_questions=(question,),
                        ),
                    )
                    return spec, self._orchestration_clarification_message(clarified)
                # Step 9 — a GENERAL contextual ambiguity (e.g. two distinct
                # established facts, or two candidate subjects). It is surfaced
                # ONLY for a genuine reference/follow-up turn, so a new objective
                # is never preempted. The competing candidates are preserved and
                # listed; nothing is chosen and nothing is executed.
                from atlas.conversation import semantic_frame as _frame

                frame = _frame.interpret(
                    text,
                    has_prior_objective=bool(self._has_prior_objective()),
                )
                if (
                    frame.role
                    in (_frame.SemanticRole.REFERENCE, _frame.SemanticRole.FOLLOW_UP)
                    and candidates
                ):
                    question = build_question(
                        KIND_REFERENCE, candidates, "Which subject do you mean?"
                    )
                    self._record_pending_clarification(
                        KIND_REFERENCE, question, candidates, text
                    )
                    return spec, Message(
                        role="assistant",
                        content=question,
                        metadata={
                            "clarification": {
                                "kind": KIND_REFERENCE,
                                "candidates": list(candidates),
                            }
                        },
                    )

        # UNRESOLVED -> fail closed; current routing is unchanged.
        return spec, None

    @staticmethod
    def _attach_resolved_reference(
        spec: TaskSpec,
        field: str,
        value: Any,
    ) -> TaskSpec:
        """Return a copy of ``spec`` carrying the resolved reference evidence.

        B — integration seam. Attachment itself is unchanged. When the pipeline
        has genuinely bound the reference (``RESOLVED`` with a valid bounded
        field/value pair), the scorer's ``reference`` ambiguity reason is no
        longer a real ambiguity and is reconciled through the existing
        :func:`reconcile_resolved_reference_ambiguity`: only that component is
        cleared, every other reason and the global threshold are untouched. A
        reference that stayed UNRESOLVED or AMBIGUOUS never reaches this method,
        so its clarification behavior is byte-for-byte unchanged.
        """
        from dataclasses import replace as _replace

        enriched = dict(spec.context) if isinstance(spec.context, dict) else {}
        enriched["resolved_reference"] = {"field": field, "value": value}
        enriched_spec = _replace(spec, context=enriched)

        if not isinstance(field, str) or not field:
            return enriched_spec
        if not isinstance(value, str) or not value.strip():
            return enriched_spec

        from atlas.conversation.task_intake import (
            reconcile_resolved_reference_ambiguity,
        )

        return reconcile_resolved_reference_ambiguity(enriched_spec)

    @staticmethod
    def _resolved_development_antecedent(spec: TaskSpec) -> str | None:
        """Return the resolved DEVELOPMENT antecedent carried by ``spec``, or None.

        L5 — a development request whose target is a resolved reference
        ("Develop that capability.") must use the resolved antecedent as its
        operand rather than the unresolved surface phrase. Only a reference the
        existing L4 pipeline already bound to the ``development_intent`` slot
        qualifies; an explicit development target carries no such evidence, so
        this returns ``None`` and the caller behaves exactly as before.
        """
        context = getattr(spec, "context", None)
        if not isinstance(context, dict):
            return None
        payload = context.get("resolved_reference")
        if not isinstance(payload, dict):
            return None
        if payload.get("field") != "development_intent":
            return None
        value = payload.get("value")
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

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
        # NLU-2 — research-objective completeness. A research request whose
        # subject is materially underspecified (a generic "a phone"/"a product"
        # with no concrete entity, or an unspecified comparison set) must ask a
        # bounded clarification instead of researching a subject it never
        # established. Nothing is guessed and no entity is invented.
        if spec.task_type is TaskType.INFORMATION_REQUEST:
            context = getattr(spec, "context", None)
            reference_resolved = bool(
                isinstance(context, dict)
                and isinstance(context.get("resolved_reference"), dict)
            )
            gap = research_subject_gap(
                spec.intent or spec.goal or "",
                reference_resolved=reference_resolved,
            )
            if gap is not None:
                self._record_pending_question((gap,))
                return Message(
                    role="assistant",
                    content=(
                        "I need one more detail before I can research this:\n"
                        f"- {gap}"
                    ),
                    metadata={"research_clarification": {"reason": "missing_subject"}},
                )
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
            self._retain_orchestration_result(result)
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
                self._retain_orchestration_result(msg)
                return msg
        if isinstance(result, str):
            return Message(role="assistant", content=result.strip())
        # Never swallow a typed, non-clarification request silently.
        return self._orchestration_clarification_message(spec)

    def _retain_orchestration_result(self, message: Message) -> None:
        """L5 — retain a bounded orchestration result for later reference.

        The research/orchestration path produces a deterministic report but
        previously left ``ConversationState`` untouched, so the EXISTING findings
        reference pattern ("what did you find?" -> ``current_investigation |
        latest_result``) had nothing to resolve against. Only a COMPLETED
        orchestration result is retained, as a bounded single-line copy of the
        report this turn already produced. Nothing is invented or summarised, no
        report object or source corpus is stored, and the existing
        ``latest_result`` slot is reused (no new state field).
        """
        if self._state_manager is None:
            return
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        payload = metadata.get("orchestration")
        if not isinstance(payload, dict) or payload.get("status") != "completed":
            return
        content = message.content if isinstance(message.content, str) else ""
        text = " ".join(content.split())
        if not text:
            return
        if len(text) > _MAX_ORCHESTRATION_RESULT_CHARS:
            text = text[:_MAX_ORCHESTRATION_RESULT_CHARS].rstrip() + "..."
        self._state_manager.update(latest_result=text)

    def _record_pending_question(self, questions: tuple[str, ...]) -> None:
        """Record the clarification question Atlas is waiting on (L6).

        A deterministic clarification is Atlas surfacing uncertainty. The
        outstanding question is preserved in the existing
        ``ConversationState.pending_question`` field ("Question Atlas is
        currently waiting for an answer to") so that uncertainty does not
        vanish with the reply. The value is bounded and derived only from the
        questions actually asked; nothing is guessed, no answer is invented,
        and no authority is created.
        """
        if self._state_manager is None:
            return
        text = "; ".join(
            question.strip()
            for question in questions
            if isinstance(question, str) and question.strip()
        )
        if not text:
            return
        if len(text) > _MAX_PENDING_QUESTION_CHARS:
            text = text[:_MAX_PENDING_QUESTION_CHARS].rstrip() + "..."
        self._state_manager.update(pending_question=text)

    def _orchestration_clarification_message(self, spec: TaskSpec) -> Message:
        """Bounded clarification for orchestrated ACTION/INFORMATION requests."""
        lines = [
            "I need a bit more detail before I can run this.",
        ]
        questions = getattr(spec.ambiguity, "clarification_questions", ()) or ()
        asked = tuple(questions)[:8]
        if not asked:
            # Fall back to a deterministic bounded rephrase of the ambiguous
            # slot (the intent is bounded; ambiguity is bounded; together
            # this is still deterministic).
            asked = ("What outcome or detail would tell me this is done?",)
        for question in asked:
            lines.append(f"- {question}")
        self._record_pending_question(asked)
        return Message(role="assistant", content="\n".join(lines))

    def _development_request_route(
        self,
        spec: TaskSpec | None,
        text: str,
    ) -> Message | None:
        """Route a DEVELOPMENT_REQUEST through the governed paths.

        G2 — an EXPLANATORY question about Atlas's own mechanism ("how would you
        add a new capability?") is self-knowledge, not a development directive, so
        the self-knowledge surface owns it and no development route is invoked.

        G3 — every other DEVELOPMENT_REQUEST is offered to the EXISTING bounded
        DevelopmentDriver (see :meth:`_maybe_handle_development_request`), after
        the B3 clarification gate and after L5 antecedent resolution. An absent or
        raising driver seam preserves the legacy F9 route verbatim.
        """
        if (
            spec is not None
            and spec.task_type is TaskType.DEVELOPMENT_REQUEST
            and self._is_self_knowledge_explanation(text)
        ):
            return None
        return self._maybe_handle_development_request(spec)

    @staticmethod
    def _is_self_knowledge_explanation(text: str) -> bool:
        """True for an explanatory question about Atlas itself (G2).

        Delegates to the SHARED bound used by the builtin classifier, so the two
        seams can never disagree: the turn must lead with an interrogative and
        the shared SemanticFrame must record the SELF_KNOWLEDGE domain.
        """
        return is_explanatory_self_knowledge(text)

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

        if self._development_bridge is None and self._development_driver_bridge is None:
            return None

        # L5 — a reference-only development follow-up ("Develop that
        # capability.") carries an L4-resolved antecedent. Use the RESOLVED
        # antecedent as the concrete operand the bridge receives, so the request
        # itself carries the referent and the antecedent is not replaced by the
        # unresolved surface phrase. Explicit development requests carry no such
        # evidence and behave exactly as before.
        resolved_antecedent = self._resolved_development_antecedent(spec)
        if resolved_antecedent is not None:
            from dataclasses import replace as _replace

            spec = _replace(
                spec, intent=resolved_antecedent, goal=resolved_antecedent
            )
        # Temporary Roadmap Step 6 gap fix — the accepted-request operand is the
        # user's OWN text. The deterministic intake's ``goal`` carries the bounded
        # utterance prefix ("respond: ..."), and recording that form made a
        # REPEATED equivalent turn hand the prefixed text back through the
        # antecedent machinery, which changed the derived capability identity for
        # the same user text. Preferring the already-clean ``intent`` (falling back
        # to the goal) keeps the recorded request, the derivation and every
        # transport identical. No routing, authority or lifecycle rule changes.
        operand = spec.intent or spec.goal or None
        # G3 — the governed self-development route: offer the (antecedent-resolved)
        # request to the EXISTING bounded DevelopmentDriver, which owns gap
        # assessment, deterministic authoring, the envelope-authorized sandbox
        # phase, verification and promotion-request preparation. It never
        # approves or promotes; an absent/raising seam falls through to the
        # legacy F9 bridge verbatim, and the accepted-request bookkeeping the
        # legacy path performs is preserved for every handled outcome.
        driver_bridge = self._development_driver_bridge
        if driver_bridge is not None:
            try:
                driven = driver_bridge(spec)
            except Exception:
                driven = None
            if isinstance(driven, Message):
                self._accept_development_request(operand)
                return driven
            if isinstance(driven, str) and driven.strip():
                self._accept_development_request(operand)
                return Message(role="assistant", content=driven)
        if self._development_bridge is None:
            return None
        result = self._development_bridge(spec)
        if isinstance(result, Message):
            self._accept_development_request(operand)
            return result
        if isinstance(result, str):
            self._accept_development_request(operand)
            return Message(role="assistant", content=result)
        # P7.5 — the bridge returned an authoritative F9 result object rather
        # than a pre-rendered Message. Project it through the reporter so the
        # conversational surface sees a truthful, provenance-preserving report.
        if self._outcome_reporter is not None:
            provenance = self._provenance_from_spec(spec)
            message = self._outcome_reporter.report(
                snapshot_from_result(result, **provenance)
            )
            self._accept_development_request(operand)
            return message
        return Message(
            role="assistant",
            content="The development request could not be prepared.",
        )

    def _accept_development_request(self, operand: str | None) -> None:
        """Record an ACCEPTED development request (facts only).

        A — the single point at which a development request becomes a
        conversational antecedent, reached only after the injected
        ``_development_bridge`` has returned an accepted result. Never called
        from classification, and never for a request that was
        clarification-pending, rejected, or failed before the handler.

        Two records are made, both from the same already-bounded text (the
        existing development goal/intent operand, bounded by the intake to
        ``_MAX_GOAL_CHARS`` / ``_MAX_INTENT_CHARS``):

          * the retained ``last_operation`` fact (unchanged behavior);
          * the bounded :attr:`ConversationState.development_intent`
            antecedent, so a later turn can refer back to it ("develop that
            capability"). Single-value semantics: the newest accepted
            development request replaces the previous intent — no history.

        A blank or non-string operand still records the operation but leaves
        the antecedent unchanged (fail closed); no other state field is
        touched, so ``current_subject`` keeps its catalog-entity contract.
        """
        self._record_operation(TaskType.DEVELOPMENT_REQUEST, operand=operand)
        if self._state_manager is None or not isinstance(operand, str):
            return
        text = operand.strip()
        if not text:
            return
        self._state_manager.update(development_intent=text)

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

    def _clarification_message(self, spec: TaskSpec) -> Message:
        """Build a bounded clarification response from the TaskSpec."""
        lines = [
            "I need a bit more detail before I can prepare this as a governed "
            "development request."
        ]
        questions = getattr(spec.ambiguity, "clarification_questions", ()) or ()
        asked = tuple(questions)[:8]
        for question in asked:
            lines.append(f"- {question}")
        self._record_pending_question(asked)
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

    def _record_operation(
        self,
        kind: TaskType,
        operand: str | None = None,
        proposal_id: str | None = None,
    ) -> None:
        """Record the most recent governed operation (facts only).

        Invoked ONLY from a handler's completion point — never from
        classification — so a request that was rejected, is awaiting
        clarification/approval, or did not actually run is never recorded.

        Stage 3 — this single helper is also the one seam that mirrors the
        completed operation into the discourse referent lifecycle, so the
        recording is not duplicated per handler/route.
        """
        if self._state_manager is None:
            return
        self._state_manager.record_operation(
            kind.value if hasattr(kind, "value") else str(kind),
            operand=operand,
            proposal_id=proposal_id,
        )
        self._record_discourse_operation(kind, operand, proposal_id)

    def _record_discourse_operation(
        self,
        kind: TaskType,
        operand: str | None,
        proposal_id: str | None,
    ) -> None:
        """Record a completed operation into the discourse referent registry.

        Stage 3 — the single, centralized operation-lifecycle recording point
        (reached through :meth:`_record_operation`, the one helper every operation
        handler already funnels through). It reads EXISTING facts only — the
        operation kind/operand/proposal reference, the retained ``latest_result``,
        and (for a read-only investigation) the bounded findings/evidence of the
        retained report — and folds them into ``ConversationState.discourse_state``
        via the single ``apply_discourse_turn`` seam. Representation only and
        fail-soft: it never routes, authorizes, executes or mutates governed state.
        """
        try:
            from atlas.conversation.discourse_state import DiscourseTurnOutcome

            kind_value = kind.value if hasattr(kind, "value") else str(kind)
            state = self._state_manager.state
            result_label = state.latest_result or ""
            findings: tuple[str, ...] = ()
            evidence: tuple[str, ...] = ()
            if kind_value == TaskType.INVESTIGATION_REQUEST.value and isinstance(
                self._last_investigation_report, InvestigationReport
            ):
                report = self._last_investigation_report
                findings = tuple(
                    finding.description or finding.category
                    for finding in report.findings
                )
                evidence = tuple(
                    finding.evidence
                    for finding in report.findings
                    if finding.evidence
                )
            outcome = DiscourseTurnOutcome(
                turn_index=len(self._conversation.messages),
                operation_origin=kind_value,
                operation_label=str(operand or ""),
                operation_status="completed",
                result_label=result_label,
                findings=findings,
                evidence=evidence,
                proposal_ref=str(proposal_id or ""),
            )
            self._state_manager.apply_discourse_turn(outcome)
        except Exception:  # fail-soft: referent recording never breaks a turn
            return

    def _maybe_handle_repeat_request(
        self,
        text: str,
        spec: TaskSpec | None,
    ) -> Message | None:
        """Handle a bounded repeat/re-check of the most recent governed operation.

        Recognition is whole-turn and bounded (``is_repeat_request``). When a
        repeat form is recognized AND an operation is retained, the retained
        operation's KIND decides the response — never the verb in the phrase:

          * read-only operations are re-entered through the SAME existing
            handler with the retained operand;
          * every other (governed/mutating) operation is refused with a
            deterministic instruction to use its explicit command/approval
            path — nothing is executed or approved here.

        When no operation is retained the method returns ``None`` so the
        existing fail-closed behavior for the turn is unchanged.
        """
        if not is_repeat_request(text):
            return None
        state = (
            self._state_manager.state if self._state_manager is not None else None
        )
        operation = (
            getattr(state, "last_operation", None) if state is not None else None
        )
        if operation is None:
            return None

        operand = getattr(operation, "operand", None)
        if operation.kind in _REPEATABLE_READ_ONLY_KINDS:
            if not isinstance(operand, str) or not operand.strip():
                return self._repeat_refusal(operation, "no retained target")
            if operation.kind == TaskType.INVESTIGATION_REQUEST.value:
                if self._investigation_service is None:
                    return self._repeat_refusal(operation, "handler unavailable")
                return self._maybe_handle_investigation_request(
                    spec, original_text=operand
                )
            return self._maybe_handle_repository_impact_request(
                spec, original_text=operand
            )

        return self._repeat_refusal(operation, "governed operation")

    @staticmethod
    def _repeat_refusal(operation: Any, reason: str) -> Message:
        """Deterministic refusal to repeat a non-re-runnable governed operation."""
        kind = getattr(operation, "kind", "unknown")
        return Message(
            role="assistant",
            content=(
                f"I will not repeat that automatically ({reason}): the most "
                f"recent governed operation was '{kind}'. Governed operations "
                "must be re-requested through their explicit command and, where "
                "applicable, approval path. Nothing was executed."
            ),
            metadata={"repeat": {"status": "not_repeated", "kind": kind}},
        )

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
        # The shared semantic frame already records WHICH operation owns the
        # turn; its bounded OBJECT (the thing the operation applies to) is passed
        # through so the read-only investigation searches for the request's
        # subject instead of turning every sentence token into a search term.
        # Representation only: routing, governance and the retained target are
        # unchanged, and an empty objective keeps the previous behaviour.
        from atlas.conversation.semantic_frame import (
            is_reference_or_follow_up,
            operation_object,
        )

        objective = operation_object(original_text) if original_text else ""
        if not objective and original_text and is_reference_or_follow_up(original_text):
            # A bare-reference follow-up ("Investigate this further.") carries no
            # object of its own: the retained investigation subject IS the
            # referent, so the evidence search uses it instead of the literal
            # words. The retained target and the state contracts are unchanged.
            retained = (
                self._state_manager.state.current_investigation
                if self._state_manager is not None
                else None
            )
            objective = retained or ""
        report = self._investigation_service.investigate(target, objective=objective)

        # C3.3 — Retain the produced report (evidence only) so a later report
        # request can synthesize it deterministically without re-gathering.
        self._last_investigation_report = report

        # Record the investigation in conversation state
        if self._state_manager is not None:
            self._state_manager.update(
                current_investigation=report.target,
                latest_result=report.diagnosis,
            )
        # Step 8 — the investigation target becomes the ACTIVE world topic (a
        # topic switch demotes the previous active topic to bounded history, so a
        # prior topic stops competing as active context). Representation only.
        self._observe_world_topic(
            report.target, "investigation", result_ref=report.diagnosis
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
                "objective": report.objective,
                "modification_status": report.modification_status,
                "findings_count": len(report.findings),
                "affected_files": list(report.affected_files),
            },
        }
        if proposal_meta:
            metadata["proposal"] = proposal_meta

        # The read-only investigation completed; retain it as the most recent
        # governed operation (operand = the actual investigation target).
        self._record_operation(
            TaskType.INVESTIGATION_REQUEST,
            operand=report.target,
            proposal_id=proposal.proposal_id if proposal is not None else None,
        )

        return Message(
            role="assistant",
            content="\n".join(content_parts),
            metadata=metadata,
        )

    def _maybe_handle_repository_impact_request(
        self,
        spec: TaskSpec,
        original_text: str | None = None,
    ) -> Message | None:
        """Handle a bounded REPOSITORY_IMPACT_REQUEST (C4.2).

        Read-only, deterministic exposure of the EXISTING RepositoryMap
        dependency/impact capability (``dependencies_of``, ``dependents_of``,
        ``impact_set``). It never mutates the repository, never calls a model,
        and never authorizes or executes anything. Unknown or ambiguous
        targets fail closed; no impact information is invented.
        """
        from atlas.conversation.repository_impact import (
            RepositoryImpactAnalyzer,
        )

        query = original_text or spec.goal or spec.intent or ""
        result = RepositoryImpactAnalyzer().analyze(query)

        if self._state_manager is not None:
            self._state_manager.update(latest_result=result.message)

        # The read-only impact analysis completed; retain it as the most recent
        # governed operation (operand = the resolved target, else the query).
        self._record_operation(
            TaskType.REPOSITORY_IMPACT_REQUEST,
            operand=result.resolved_module or query,
        )

        return Message(
            role="assistant",
            content=result.to_markdown(),
            metadata={
                "repository_impact": {
                    "status": result.status.value,
                    "resolved_module": result.resolved_module,
                    "candidates": list(result.candidates),
                    "dependents": list(result.dependents),
                    "dependencies": list(result.dependencies),
                    "impact": list(result.impact),
                    "affected_files": list(result.affected_files),
                    "modification_status": result.modification_status,
                },
            },
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

        # Approval-facing disclosure: when a bounded workload was authored
        # pre-approval, disclose its presence, size, and provenance so the
        # approver knows an executable sandbox payload exists.
        authored_changes = ev_proposal.metadata.get("code_changes") or []
        authored_tests = ev_proposal.metadata.get("test_files") or {}
        authored_cycle = ev_proposal.metadata.get("development_cycle") or {}
        workload_summary = ""
        if authored_changes:
            workload_summary = (
                f"**Authored workload:** {len(authored_changes)} code "
                f"change(s), {len(authored_tests)} test file(s) "
                f"(origin '{authored_cycle.get('change_origin', 'unknown')}', "
                f"content_status "
                f"'{authored_cycle.get('content_status', 'unknown')}'; "
                f"sandbox-only execution).\n\n"
            )
        planning_metadata: dict[str, Any] = {
            "status": "prepared",
            "investigation_proposal_id": inv_proposal.proposal_id,
            "evolution_proposal_id": ev_proposal.proposal_id,
            "approval_request_id": approval_request.request_id,
            "proposal_status": ev_proposal.status.name,
            "approval_status": approval_request.decision.name,
        }
        if authored_changes:
            planning_metadata["authored_workload"] = {
                "code_changes": len(authored_changes),
                "test_files": len(authored_tests),
                "change_origin": authored_cycle.get("change_origin", "unknown"),
                "content_status": authored_cycle.get(
                    "content_status", "unknown"
                ),
            }

        # The planning operation completed (proposal prepared and submitted for
        # approval); retain it as the most recent governed operation. It is
        # governed, so a repeat request is refused rather than re-planned.
        self._record_operation(
            TaskType.PLANNING_REQUEST,
            operand=getattr(inv_proposal, "investigation_target", None),
            proposal_id=ev_proposal.proposal_id,
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
                f"{workload_summary}"
                f"No changes have been made. This proposal requires your "
                f"explicit approval before any work begins."
            ),
            metadata={"planning": planning_metadata},
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

        # The governed execution ran through the existing bridge; retain it as
        # the most recent governed operation (never re-run from a repeat).
        self._record_operation(
            TaskType.EXECUTION_REQUEST,
            proposal_id=proposal.proposal_id,
        )

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

        # The governed recovery execution ran through the existing bridge;
        # retain it as the most recent governed operation.
        self._record_operation(
            TaskType.EXECUTION_REQUEST,
            proposal_id=proposal.proposal_id,
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

        # The recovery assessment completed (a recovery decision was produced);
        # retain it as the most recent governed operation. It is governed, so a
        # repeat request is refused rather than re-assessed.
        self._record_operation(
            TaskType.RECOVERY_REQUEST,
            proposal_id=recovery_proposal_id,
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

        # The verification ran (read-only over an existing development result);
        # retain it as the most recent governed operation. It is not re-runnable
        # from a cue-less repeat.
        self._record_operation(
            TaskType.VERIFICATION_REQUEST,
            proposal_id=proposal.proposal_id,
        )

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
            # C3.3 — Investigation-level reporting. When no development
            # lifecycle exists, report on the most recent read-only
            # investigation synthesis instead of refusing. Deterministic and
            # read-only; the development-lifecycle path below is unchanged.
            if self._last_investigation_report is not None:
                return self._handle_investigation_report(
                    self._last_investigation_report
                )
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

    def _handle_investigation_report(
        self,
        investigation_report: InvestigationReport,
    ) -> Message:
        """Render a deterministic synthesis of a read-only investigation.

        C3.3 — consumes ONLY the retained :class:`InvestigationReport`
        evidence. It never gathers new evidence, mutates state, calls a model,
        authorizes, or executes anything. Strictly read-only.
        """
        from atlas.conversation.investigation_synthesis import (
            InvestigationSynthesizer,
        )

        synthesis = InvestigationSynthesizer().synthesize(investigation_report)
        return Message(
            role="assistant",
            content=synthesis.to_markdown(),
            metadata={
                "report": {
                    "status": "investigation",
                    "kind": "investigation",
                    "target": synthesis.target,
                    "finding_count": synthesis.finding_count,
                    "component_count": synthesis.component_count,
                    "recommended_focus": synthesis.recommended_focus,
                    "insufficient_evidence": synthesis.insufficient_evidence,
                    "evidence_basis": list(synthesis.evidence_basis),
                    "ranked_components": [
                        c.to_dict() for c in synthesis.ranked_components
                    ],
                    "modification_status": synthesis.modification_status,
                },
            },
        )

    def _maybe_handle_autonomy_request(
        self,
        spec: TaskSpec,
    ) -> Message | None:
        """Handle an AUTONOMY_REQUEST.

        Executes an already-approved development plan autonomously under L1
        controlled autonomy. All steps (IMPLEMENT → VERIFY → ACCEPT) run
        without per-step user approval. Failure handling (diagnose → recover →
        verify) is also autonomous within L1 boundaries.

        L1 autonomy CANNOT:
        - Bypass user approval for new proposals
        - Exceed approved scope
        - Expand its own capabilities
        - Approve its own restricted actions
        - Mutate outside approved boundary
        - Promote from sandbox to real workspace

        Args:
            spec: the classified AUTONOMY_REQUEST TaskSpec.

        Returns:
            A Message describing the autonomy result, or None if autonomy
            is not possible.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. Autonomy requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"autonomy": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "Autonomy requires OWNER authority. "
                    "This session is not authorized to run autonomous development."
                ),
                metadata={"autonomy": {"status": "unauthorized"}},
            )

        state = self._state_manager.state if self._state_manager else None
        if state is None or not state.evolution_proposal_id:
            return Message(
                role="assistant",
                content=(
                    "There is no approved development proposal to execute "
                    "autonomously. Please investigate an issue, plan it, and "
                    "approve it first."
                ),
                metadata={"autonomy": {"status": "no_proposal"}},
            )

        # 3. Resolve the approved proposal from the live registry.
        proposal = self._resolve_evolution_proposal(state.evolution_proposal_id)
        if proposal is None:
            return Message(
                role="assistant",
                content=(
                    "The approved proposal could not be resolved. "
                    "Please plan the proposal again."
                ),
                metadata={"autonomy": {"status": "proposal_not_found"}},
            )

        # 4. Resolve the approved approval request.
        request = self._resolve_approved_request(state.evolution_proposal_id)
        if request is None:
            return Message(
                role="assistant",
                content=(
                    "The approved request could not be resolved. "
                    "Please approve the proposal again."
                ),
                metadata={"autonomy": {"status": "request_not_found"}},
            )

        # 5. Cross-validate identity + fingerprint BEFORE autonomy.
        from atlas.evolution.models import ApprovalDecision, ProposalStatus

        if proposal.status != ProposalStatus.APPROVED:
            return Message(
                role="assistant",
                content=(
                    f"Proposal '{proposal.proposal_id}' is "
                    f"'{proposal.status.name}', not APPROVED. "
                    "Only approved proposals can be executed autonomously."
                ),
                metadata={"autonomy": {"status": "not_approved"}},
            )
        if request.decision != ApprovalDecision.APPROVED:
            return Message(
                role="assistant",
                content=(
                    "The approval request has not been approved. "
                    "Please approve the proposal before autonomous execution."
                ),
                metadata={"autonomy": {"status": "not_approved"}},
            )
        if request.proposal_id != proposal.proposal_id:
            return Message(
                role="assistant",
                content=(
                    "The approval request does not match the active proposal. "
                    "Autonomous execution refused."
                ),
                metadata={"autonomy": {"status": "identity_mismatch"}},
            )
        if not request.is_valid_for(proposal):
            return Message(
                role="assistant",
                content=(
                    "The proposal has changed since the approval request was "
                    "created. Autonomous execution refused. Please approve again."
                ),
                metadata={"autonomy": {"status": "fingerprint_mismatch"}},
            )

        # 6. Check L1 autonomy via the injected kernel boundary.
        # The conversation layer never constructs evolution autonomy machinery
        # directly; the kernel composition root owns that and injects it here.
        if self._autonomy_check is None:
            return Message(
                role="assistant",
                content=(
                    "Autonomy check is not available. "
                    "L1 autonomous execution cannot proceed without the "
                    "kernel autonomy boundary."
                ),
                metadata={"autonomy": {"status": "not_available"}},
            )

        autonomy_decision = self._autonomy_check(
            proposal, active_session, level=1,
        )

        if not autonomy_decision.can_proceed:
            lines = [
                "## L1 Autonomy: Denied",
                "",
                f"**Reason:** {autonomy_decision.reason}",
            ]
            if autonomy_decision.escalation_required:
                lines.append("")
                lines.append(
                    "This action requires explicit user approval. "
                    "Please approve the action manually."
                )
            return Message(
                role="assistant",
                content="\n".join(lines),
                metadata={
                    "autonomy": {
                        "status": "denied",
                        "reason": autonomy_decision.reason,
                        "escalation_required": autonomy_decision.escalation_required,
                        "evidence": autonomy_decision.evidence,
                    },
                },
            )

        # 7. Delegate to the existing governed development-execution bridge.
        try:
            message = self._development_execution_bridge(
                active_session, proposal, request
            )
        except Exception as exc:
            return Message(
                role="assistant",
                content=(
                    f"Autonomous execution could not proceed: {exc}. "
                    "No changes were made."
                ),
                metadata={"autonomy": {"status": "execution_failed", "error": str(exc)}},
            )

        # 8. Update conversation state with L1 autonomy tracking.
        if self._state_manager is not None:
            current_steps = state.autonomous_steps_executed or 0
            self._state_manager.update(
                autonomous_steps_executed=current_steps + 1,
                last_autonomy_decision=autonomy_decision.reason,
                latest_result=f"Autonomous execution: {autonomy_decision.reason}",
            )

        # 9. Return the result with autonomy metadata.
        return Message(
            role="assistant",
            content=(
                f"## L1 Autonomous Execution\n\n"
                f"{message.content}\n\n"
                f"**Autonomy decision:** {autonomy_decision.reason}\n"
                f"**Authorization mode:** {autonomy_decision.authorization_mode.value if autonomy_decision.authorization_mode else 'none'}"
            ),
            metadata={
                "autonomy": {
                    "status": "executed",
                    "reason": autonomy_decision.reason,
                    "authorization_mode": (
                        autonomy_decision.authorization_mode.value
                        if autonomy_decision.authorization_mode
                        else None
                    ),
                    "evidence": autonomy_decision.evidence,
                    "proposal_id": proposal.proposal_id,
                },
            },
        )

    def _maybe_handle_l2_autonomy_request(
        self,
        spec: TaskSpec,
    ) -> Message | None:
        """Handle an L2_AUTONOMY_REQUEST.

        L2 controlled autonomy: chain multiple approved workflows or make
        bounded plan adjustments within approved scope.

        L2 can:
        - Chain multiple pre-approved workflows
        - Make bounded plan adjustments (reorder, add verification, skip redundant)
        - Perform cross-workflow diagnosis
        - Handle MEDIUM risk operations

        L2 CANNOT:
        - Create new workflows without approval
        - Expand scope beyond approved
        - Change the user's objective
        - Handle HIGH/CRITICAL risk
        - Promote from sandbox to real workspace

        Args:
            spec: the classified L2_AUTONOMY_REQUEST TaskSpec.

        Returns:
            A Message describing the L2 autonomy result, or None if L2
            autonomy is not possible.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. L2 autonomy requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"l2_autonomy": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "L2 autonomy requires OWNER authority. "
                    "This session is not authorized to run L2 autonomous development."
                ),
                metadata={"l2_autonomy": {"status": "unauthorized"}},
            )

        # 3. Check L2 autonomy via the injected kernel boundary.
        # The conversation layer never constructs evolution autonomy machinery
        # directly; the kernel composition root owns that and injects it here.
        if self._autonomy_check is None:
            return Message(
                role="assistant",
                content=(
                    "Autonomy check is not available. "
                    "L2 autonomous operation cannot proceed without the "
                    "kernel autonomy boundary."
                ),
                metadata={"l2_autonomy": {"status": "not_available"}},
            )

        l2_decision = self._autonomy_check(
            None, active_session, level=2,
        )

        if not l2_decision.can_proceed:
            lines = [
                "## L2 Autonomy: Denied",
                "",
                f"**Reason:** {l2_decision.reason}",
            ]
            if l2_decision.escalation_required:
                lines.append("")
                lines.append(
                    "This action requires explicit user approval. "
                    "Please approve the action manually."
                )
            return Message(
                role="assistant",
                content="\n".join(lines),
                metadata={
                    "l2_autonomy": {
                        "status": "denied",
                        "reason": l2_decision.reason,
                        "escalation_required": l2_decision.escalation_required,
                        "evidence": l2_decision.evidence,
                    },
                },
            )

        # 4. Update conversation state with L2 tracking
        if self._state_manager is not None:
            self._state_manager.update(
                last_l2_decision=l2_decision.reason,
                latest_result=f"L2 autonomy: {l2_decision.reason}",
            )

        # 5. Return L2 autonomy acknowledgment
        return Message(
            role="assistant",
            content=(
                f"## L2 Autonomous Operation\n\n"
                f"**Decision:** {l2_decision.reason}\n"
                f"**Authorization mode:** {l2_decision.authorization_mode.value if l2_decision.authorization_mode else 'none'}\n\n"
                f"L2 autonomy permits chaining approved workflows and making "
                f"bounded plan adjustments within approved scope."
            ),
            metadata={
                "l2_autonomy": {
                    "status": "acknowledged",
                    "reason": l2_decision.reason,
                    "authorization_mode": (
                        l2_decision.authorization_mode.value
                        if l2_decision.authorization_mode
                        else None
                    ),
                    "evidence": l2_decision.evidence,
                },
            },
        )

    def _maybe_handle_l3_autonomy_request(
        self,
        spec: TaskSpec,
    ) -> Message | None:
        """Handle an L3_AUTONOMY_REQUEST.

        L3 controlled autonomy: execute recovery autonomously, generate
        bounded sub-plans, or handle HIGH risk operations.

        L3 can:
        - Execute recovery within approved scope
        - Generate bounded sub-plans within approved scope
        - Handle HIGH risk operations
        - Modify internal configuration within approved scope

        L3 CANNOT:
        - Create new top-level objectives
        - Expand scope beyond approved
        - Handle CRITICAL risk
        - Promote to L4

        Args:
            spec: the classified L3_AUTONOMY_REQUEST TaskSpec.

        Returns:
            A Message describing the L3 autonomy result, or None if L3
            autonomy is not possible.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. L3 autonomy requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"l3_autonomy": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "L3 autonomy requires OWNER authority. "
                    "This session is not authorized to run L3 autonomous development."
                ),
                metadata={"l3_autonomy": {"status": "unauthorized"}},
            )

        # 3. Check L3 autonomy via the injected kernel boundary.
        # The conversation layer never constructs evolution autonomy machinery
        # directly; the kernel composition root owns that and injects it here.
        if self._autonomy_check is None:
            return Message(
                role="assistant",
                content=(
                    "Autonomy check is not available. "
                    "L3 autonomous operation cannot proceed without the "
                    "kernel autonomy boundary."
                ),
                metadata={"l3_autonomy": {"status": "not_available"}},
            )

        l3_decision = self._autonomy_check(
            None, active_session, level=3,
        )

        if not l3_decision.can_proceed:
            lines = [
                "## L3 Autonomy: Denied",
                "",
                f"**Reason:** {l3_decision.reason}",
            ]
            if l3_decision.escalation_required:
                lines.append("")
                lines.append(
                    "This action requires explicit user approval. "
                    "Please approve the action manually."
                )
            return Message(
                role="assistant",
                content="\n".join(lines),
                metadata={
                    "l3_autonomy": {
                        "status": "denied",
                        "reason": l3_decision.reason,
                        "escalation_required": l3_decision.escalation_required,
                        "evidence": l3_decision.evidence,
                    },
                },
            )

        # 4. Update conversation state with L3 tracking
        if self._state_manager is not None:
            self._state_manager.update(
                last_l3_decision=l3_decision.reason,
                latest_result=f"L3 autonomy: {l3_decision.reason}",
            )

        # 5. Return L3 autonomy acknowledgment
        return Message(
            role="assistant",
            content=(
                f"## L3 Autonomous Operation\n\n"
                f"**Decision:** {l3_decision.reason}\n"
                f"**Authorization mode:** {l3_decision.authorization_mode.value if l3_decision.authorization_mode else 'none'}\n\n"
                f"L3 autonomy permits autonomous recovery execution, bounded "
                f"sub-plan generation, and HIGH risk operations within approved scope."
            ),
            metadata={
                "l3_autonomy": {
                    "status": "acknowledged",
                    "reason": l3_decision.reason,
                    "authorization_mode": (
                        l3_decision.authorization_mode.value
                        if l3_decision.authorization_mode
                        else None
                    ),
                    "evidence": l3_decision.evidence,
                },
            },
        )

    def _maybe_handle_l4_autonomy_request(
        self,
        spec: TaskSpec,
    ) -> Message | None:
        """Handle an L4_AUTONOMY_REQUEST.

        L4 controlled autonomy: acquire new capabilities, modify
        memory/knowledge, or handle CRITICAL risk operations.

        L4 can:
        - Acquire new capabilities within approved scope
        - Modify memory/knowledge within approved scope
        - Handle CRITICAL risk operations
        - Modify internal configuration within approved scope

        L4 CANNOT:
        - Create new top-level objectives
        - Expand scope beyond approved
        - Handle operations beyond CRITICAL risk
        - Promote to L5

        Args:
            spec: the classified L4_AUTONOMY_REQUEST TaskSpec.

        Returns:
            A Message describing the L4 autonomy result, or None if L4
            autonomy is not possible.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. L4 autonomy requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"l4_autonomy": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "L4 autonomy requires OWNER authority. "
                    "This session is not authorized to run L4 autonomous development."
                ),
                metadata={"l4_autonomy": {"status": "unauthorized"}},
            )

        # 3. Check L4 autonomy via the injected kernel boundary.
        # The conversation layer never constructs evolution autonomy machinery
        # directly; the kernel composition root owns that and injects it here.
        if self._autonomy_check is None:
            return Message(
                role="assistant",
                content=(
                    "Autonomy check is not available. "
                    "L4 autonomous operation cannot proceed without the "
                    "kernel autonomy boundary."
                ),
                metadata={"l4_autonomy": {"status": "not_available"}},
            )

        l4_decision = self._autonomy_check(
            None, active_session, level=4,
        )

        if not l4_decision.can_proceed:
            lines = [
                "## L4 Autonomy: Denied",
                "",
                f"**Reason:** {l4_decision.reason}",
            ]
            if l4_decision.escalation_required:
                lines.append("")
                lines.append(
                    "This action requires explicit user approval. "
                    "Please approve the action manually."
                )
            return Message(
                role="assistant",
                content="\n".join(lines),
                metadata={
                    "l4_autonomy": {
                        "status": "denied",
                        "reason": l4_decision.reason,
                        "escalation_required": l4_decision.escalation_required,
                        "evidence": l4_decision.evidence,
                    },
                },
            )

        # 4. Update conversation state with L4 tracking
        if self._state_manager is not None:
            self._state_manager.update(
                last_l4_decision=l4_decision.reason,
                latest_result=f"L4 autonomy: {l4_decision.reason}",
            )

        # 5. Return L4 autonomy acknowledgment
        return Message(
            role="assistant",
            content=(
                f"## L4 Autonomous Operation\n\n"
                f"**Decision:** {l4_decision.reason}\n"
                f"**Authorization mode:** {l4_decision.authorization_mode.value if l4_decision.authorization_mode else 'none'}\n\n"
                f"L4 autonomy permits capability acquisition, memory/knowledge "
                f"modification, and CRITICAL risk operations within approved scope."
            ),
            metadata={
                "l4_autonomy": {
                    "status": "acknowledged",
                    "reason": l4_decision.reason,
                    "authorization_mode": (
                        l4_decision.authorization_mode.value
                        if l4_decision.authorization_mode
                        else None
                    ),
                    "evidence": l4_decision.evidence,
                },
            },
        )

    def _maybe_handle_l5_autonomy_request(
        self,
        spec: TaskSpec,
    ) -> Message | None:
        """Handle an L5_AUTONOMY_REQUEST.

        L5 controlled autonomy (FINAL LEVEL): coordinate across objectives,
        prioritize work, or manage dependencies.

        L5 can:
        - Coordinate across multiple approved objectives
        - Prioritize work across objectives
        - Manage dependencies between objectives
        - Allocate resources across objectives
        - Escalate conflicts between objectives to humans

        L5 CANNOT:
        - Create new top-level objectives
        - Expand scope beyond approved
        - Handle operations beyond CRITICAL risk
        - Promote beyond L5 (it is the final level)
        - Modify governance rules

        Args:
            spec: the classified L5_AUTONOMY_REQUEST TaskSpec.

        Returns:
            A Message describing the L5 autonomy result, or None if L5
            autonomy is not possible.
        """
        # 1. An active session must exist (fail-closed without attribution).
        active_session = self._last_session_context
        if active_session is None:
            return Message(
                role="assistant",
                content=(
                    "No active session. L5 autonomy requires an authenticated "
                    "session. Please start a session first."
                ),
                metadata={"l5_autonomy": {"status": "no_session"}},
            )

        # 2. OWNER authority is required (fail-closed for non-owners).
        if not active_session.is_owner:
            return Message(
                role="assistant",
                content=(
                    "L5 autonomy requires OWNER authority. "
                    "This session is not authorized to run L5 autonomous development."
                ),
                metadata={"l5_autonomy": {"status": "unauthorized"}},
            )

        # 3. Check L5 autonomy via the injected kernel boundary.
        # The conversation layer never constructs evolution autonomy machinery
        # directly; the kernel composition root owns that and injects it here.
        if self._autonomy_check is None:
            return Message(
                role="assistant",
                content=(
                    "Autonomy check is not available. "
                    "L5 autonomous operation cannot proceed without the "
                    "kernel autonomy boundary."
                ),
                metadata={"l5_autonomy": {"status": "not_available"}},
            )

        l5_decision = self._autonomy_check(
            None, active_session, level=5,
        )

        if not l5_decision.can_proceed:
            lines = [
                "## L5 Autonomy: Denied",
                "",
                f"**Reason:** {l5_decision.reason}",
            ]
            if l5_decision.escalation_required:
                lines.append("")
                lines.append(
                    "This action requires explicit user approval. "
                    "Please approve the action manually."
                )
            return Message(
                role="assistant",
                content="\n".join(lines),
                metadata={
                    "l5_autonomy": {
                        "status": "denied",
                        "reason": l5_decision.reason,
                        "escalation_required": l5_decision.escalation_required,
                        "evidence": l5_decision.evidence,
                    },
                },
            )

        # 4. Update conversation state with L5 tracking
        if self._state_manager is not None:
            self._state_manager.update(
                last_l5_decision=l5_decision.reason,
                latest_result=f"L5 autonomy: {l5_decision.reason}",
            )

        # 5. Return L5 autonomy acknowledgment
        return Message(
            role="assistant",
            content=(
                f"## L5 Autonomous Operation (FINAL LEVEL)\n\n"
                f"**Decision:** {l5_decision.reason}\n"
                f"**Authorization mode:** {l5_decision.authorization_mode.value if l5_decision.authorization_mode else 'none'}\n\n"
                f"L5 autonomy permits cross-objective coordination, priority-based "
                f"scheduling, and dependency management within approved scope. "
                f"L5 is the final controlled autonomy level."
            ),
            metadata={
                "l5_autonomy": {
                    "status": "acknowledged",
                    "reason": l5_decision.reason,
                    "authorization_mode": (
                        l5_decision.authorization_mode.value
                        if l5_decision.authorization_mode
                        else None
                    ),
                    "evidence": l5_decision.evidence,
                    "final_level": True,
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
