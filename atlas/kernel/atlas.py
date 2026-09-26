"""
Atlas Kernel

The root application object and sole composition root.
All subsystem wiring occurs here via private helper methods called
from ``start()`` in dependency order.  No component is instantiated
internally — everything is constructor-injected from this root.

v0.20.0 — Atlas Core complete.  Numbered phases are finished.
"""

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from atlas.ai.ai_manager import AIManager
from atlas.ai.routing.profile_loader import load_model_profiles
from atlas.ai.routing.models import RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.ai.routing.router import ModelRouter
from atlas.config.configuration import Configuration
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_intake import task_spec_to_development_need
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.development_need_detector import AdvisorySignal
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.message import Message
from atlas.cognition.api import CognitionAPI
from atlas.events.event_bus import EventBus
from atlas.kernel.service_container import ServiceContainer
from atlas.intelligence.cognitive_loop import CognitiveLoop
from atlas.intelligence.cognitive_service import CognitiveService

from atlas.memory.context.context_engine import ContextEngine
from atlas.memory.ranking.ranking_engine import RankingEngine
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.search.search_engine import MemorySearchEngine
from atlas.memory.service.memory_manager_service import MemoryManagerService

from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.knowledge.capability_handlers import KnowledgeRetrievalHandlerFactory

from atlas.learning.learning_manager import LearningManager
from atlas.learning.knowledge_feedback import KnowledgeFeedback

from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.handlers import DEFAULT_HANDLERS
from atlas.reasoning.outcomes import ReasoningRecorder
from atlas.reasoning.planning import PlanningEngine
from atlas.reasoning.reflection import ReflectionEngine

from atlas.tools.builtins import BUILTIN_TOOLS
from atlas.tools.engine import ToolEngine
from atlas.tools.executor import ToolExecutor
from atlas.tools.registry import ToolRegistry
from atlas.tools.selector import ToolSelector

from atlas.services.cognition_service import CognitionService

from atlas.state.state_manager import StateManager
from atlas.task.task_manager import TaskManager

# --- Phase 7.5: Unified Cognitive Runtime ---
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.runtime.feedback_coordinator import FeedbackCoordinator

# --- Previously-unwired subsystems ---
from atlas.understanding.understanding_engine import UnderstandingEngine
from atlas.world_model.world_model_engine import WorldModelEngine
from atlas.evolution.self_observation import SelfObservationEngine
from atlas.evolution.development_planner import DevelopmentPlanner
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.evolution.autonomy.sandbox_tools import register_sandbox_tools
from atlas.evolution.environment import EnvironmentObserver
from atlas.evolution.environment.providers import (
    ProviderHealthObserver,
    default_providers,
)
from atlas.ai.availability import ProviderAvailabilityTracker
from atlas.evolution.lifecycle import CapabilityLifecycleAssessor
from atlas.evolution.lifecycle.targets import targets_from_registries
from atlas.evolution.adaptation import AdaptationDecisionEngine
from atlas.evolution.adaptation.evaluator import AdaptationEvaluator
from atlas.evolution.adaptation.orchestrator import AdaptationOrchestrator
from atlas.evolution.operation import OperationController
from atlas.evolution.development_cycle import DevelopmentCycleController
from atlas.evolution.model_assisted_supplier import ModelAssistedChangeSupplier
from atlas.learning_engine.learning_engine import LearningEngine
from atlas.identity.identity_engine import IdentityEngine
from atlas.authority.service import AuthorityService
from atlas.session.manager import SessionManager
from atlas.session.context import SessionContext
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.goals.goal_intelligence_engine import GoalIntelligenceEngine
from atlas.goals.goal_repository import GoalRepository

# --- Phase 9.0: Experience & Self-Model ---
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.experience_accumulator import ExperienceAccumulator
from atlas.experience.self_model_engine import SelfModelEngine
from atlas.experience.outcome_tracker import OutcomeTracker
from atlas.experience.serialization import snapshot_to_dict
from atlas.storage.experience_storage import SQLiteExperienceStorage
from atlas.storage.understanding_storage import SQLiteUnderstandingStorage

# --- Phase 10.0: Evolution Pipeline ---
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.models import ProposalStatus
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory

# --- Phase 11.0: Evolution Execution Engine ---
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.execution_gateway import EvolutionExecutionGateway

# --- Phase 11.3: Evolution Persistence ---
from atlas.storage.evolution_storage import SQLiteEvolutionStorage

# --- Phase 12.1 / 12.2: Evolution Intelligence ---
from atlas.evolution.insight_scorer import InsightScorer
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine

# --- Phase 13.1: Governance ---
from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.evolution.governance.rule_engine import RuleEngine

# --- Phase 13.3: Evolution Scheduler ---
from atlas.evolution.scheduler import EvolutionScheduler

# --- Phase 13.5: Persistent Evolution Knowledge ---
from atlas.evolution.knowledge.consolidator import EvolutionKnowledgeConsolidator
from atlas.evolution.knowledge.repository import EvolutionKnowledgeRepository
from atlas.evolution.knowledge.query import EvolutionKnowledgeQuery

# --- Phase 13.6: Automatic Evolution Knowledge Consolidation Pipeline ---
from atlas.evolution.knowledge.pipeline import EvolutionKnowledgePipeline

# --- Phase 14.2 / 14.4: Decision Intelligence ---
from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine

# --- Phase 15.0: Goal Execution ---
from atlas.goals.goal_execution_engine import GoalExecutionEngine
from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
from atlas.tools.execution_action_binder import ToolExecutionActionBinder

# --- Phase 13.2: Component Registry ---
from atlas.lifecycle import (
    ComponentMetadata,
    ComponentRegistry,
    ComponentStatus,
    CORE_COMPONENTS,
)

# --- Track A: Research & Knowledge (Phase 17 integration) ---
from atlas.research.capability_handlers import ResearchCapabilityFactory
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.research.acquisition import InformationAcquisitionService
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
    PromotionRequest,
    build_change_manifest,
)
from atlas.evolution.freshness.assessor import KnowledgeFreshnessAssessor
from atlas.research.evolution_integration import (
    ResearchIngestBridge,
    register_gov_008,
)
from atlas.research.wiring import register_research_component
from atlas.storage.research_storage import ResearchSQLiteStorage

# --- Track B: Tool Ecosystem (Phase 18 integration) ---
from atlas.storage.toolchain_storage import ToolchainSQLiteStorage
from atlas.toolchain.capability_handlers import ToolchainCapabilityFactory
from atlas.toolchain.evolution_integration import register_gov_009
from atlas.toolchain.wiring import (
    register_toolchain_component,
    register_toolchain_evolution_component,
)

# --- Track C: Long-Term Learning (Phase 19 integration) ---
from atlas.longterm.capability_handlers import LongTermCapabilityFactory
from atlas.longterm.consolidator import Consolidator
from atlas.longterm.episode_recorder import EpisodicRecorder
from atlas.longterm.episode_repository import EpisodicRepository
from atlas.longterm.evolution_integration import (
    LongTermIngestBridge,
    register_gov_010,
)
from atlas.longterm.procedure_extractor import ProcedureExtractor
from atlas.longterm.procedure_repository import ProceduralRepository
from atlas.longterm.wiring import (
    register_longterm_component,
    register_longterm_evolution_component,
)
from atlas.storage.longterm_storage import LongTermSQLiteStorage

# --- Track D: Advanced Reasoning (Track D integration) ---
from atlas.advanced_reasoning.capability_handlers import (
    AdvancedReasoningCapabilityFactory,
)
from atlas.advanced_reasoning.causal import CausalReasoner
from atlas.advanced_reasoning.evolution_integration import (
    ReasoningIngestBridge,
    register_gov_011,
)
from atlas.advanced_reasoning.models import CausalPath
from atlas.advanced_reasoning.multi_step import MultiStepReasoner
from atlas.advanced_reasoning.service import AdvancedReasoningService
from atlas.advanced_reasoning.trace_recorder import ReasoningTraceRecorder
from atlas.advanced_reasoning.trace_repository import ReasoningTraceRepository
from atlas.advanced_reasoning.wiring import (
    register_advanced_reasoning_component,
    register_advanced_reasoning_evolution_component,
)
from atlas.storage.advanced_reasoning_storage import AdvancedReasoningSQLiteStorage

# --- Phase 16: Autonomy persistence wiring ---
from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
from atlas.evolution.autonomy.autonomy_controller import AutonomyController
from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
from atlas.evolution.autonomy.autonomy_request_adapter import (
    AutonomyRequestAdapter,
)
from atlas.evolution.autonomy.models import AutonomyPolicy, RiskLevel
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.kernel.autonomy_wiring import (
    init_autonomy_application_engine,
    init_autonomy_dispatcher,
    init_autonomy_persistence,
    init_boot_activation,
    init_governed_ingest_sink,
    shutdown_autonomy_persistence,
)
from atlas.evolution.self_management import SelfManagementReview


class KnowledgeEvidenceProvider:
    """Kernel-boundary ``EvidenceProvider`` backed by ``KnowledgeManager.query``.

    Read-only: converts each ``KnowledgeEntry`` into a stable
    ``"source:title"`` reference string.  Pure Track D modules never import
    the knowledge service (TRACK_D section 3.4).
    """

    def __init__(self, knowledge_manager: KnowledgeManager) -> None:
        self._knowledge_manager = knowledge_manager

    def query(self, query_text: str, limit: int = 10) -> list[str]:
        """Return up to ``limit`` stable knowledge reference strings."""
        try:
            entries = self._knowledge_manager.query(query_text)
        except Exception:
            return []
        references = sorted(
            f"{entry.source}:{entry.title}" if entry.source else entry.title
            for entry in entries
            if getattr(entry, "title", "")
        )
        return references[:limit]


class WorldModelCausalGraphProvider:
    """Kernel-boundary ``CausalGraphProvider`` backed by ``WorldModelEngine``.

    Read-only: causal chains come from ``world_model.get_causal_chain``;
    ``related_entities`` is the deterministic union of direct causes and
    effects.  The provider never mutates the world model.
    """

    def __init__(self, world_model: WorldModelEngine) -> None:
        self._world_model = world_model

    def causal_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 5,
    ) -> tuple[CausalPath, ...]:
        """Return causal paths from ``source`` to ``target``."""
        try:
            chains = self._world_model.get_causal_chain(source, target)
        except Exception:
            return ()
        paths: list[CausalPath] = []
        for chain_index, chain in enumerate(chains):
            bounded = list(chain)[: max(1, max_depth)]
            if not bounded:
                continue
            entity_ids = (source,) + tuple(
                relation.target_id for relation in bounded
            )
            relation_types = tuple(
                relation.relation_type.name for relation in bounded
            )
            confidence = round(
                sum(relation.confidence for relation in bounded) / len(bounded),
                4,
            )
            path_id = (
                f"cpath:{hashlib.sha256(source.encode()).hexdigest()[:16]}:"
                f"{hashlib.sha256(target.encode()).hexdigest()[:16]}:{chain_index:04d}"
            )
            paths.append(
                CausalPath(
                    path_id=path_id,
                    source=source,
                    target=target,
                    entity_ids=entity_ids,
                    relation_types=relation_types,
                    confidence=confidence,
                    metadata={"source": "world_model"},
                )
            )
        return tuple(
            sorted(
                paths,
                key=lambda p: (round(p.confidence, 6), p.path_id),
                reverse=True,
            )
        )

    def related_entities(
        self,
        entity_id: str,
        max_depth: int = 5,
    ) -> tuple[str, ...]:
        """Return entity IDs causally related to ``entity_id``."""
        try:
            causes = self._world_model.get_entity_causes(entity_id)
            effects = self._world_model.get_entity_effects(entity_id)
        except Exception:
            return ()
        related = {
            relation.source_id for relation in causes if relation.source_id
        }
        related.update(
            relation.target_id for relation in effects if relation.target_id
        )
        related.discard(entity_id)
        return tuple(sorted(related))[: max(1, max_depth) * 10]


class Atlas:
    """Root application object and sole composition root.

    All subsystem wiring occurs in ``start()`` via private helper methods
    called in strict dependency order.  No component instantiates other
    components internally — everything is constructor-injected from here.

    v0.20.0 — Atlas Core complete.  Numbered phases are finished.
    """

    def __init__(self):

        self._container = ServiceContainer()
        self._event_bus = EventBus()
        self._state_manager = StateManager(self._event_bus)
        self._config = Configuration()
        self._ai_manager = AIManager()
        self._task_manager = TaskManager()

        self._conversation: ConversationService | None = None
        self._proposal_change_supplier = None
        self._memory_service: MemoryManagerService | None = None
        self._knowledge_manager: KnowledgeManager | None = None
        self._cognitive_loop: CognitiveLoop | None = None
        self._cognitive_service: CognitiveService | None = None
        self._cognition_service: CognitionService | None = None
        self._cognition_api: CognitionAPI | None = None

        # --- Runtime Coordinator (Phase 7.5) ---
        self._runtime_coordinator: RuntimeCoordinator | None = None
        self._understanding_engine: UnderstandingEngine | None = None
        self._world_model_engine: WorldModelEngine | None = None
        self._self_observation_engine: SelfObservationEngine | None = None
        self._learning_engine: LearningEngine | None = None
        self._identity_engine: IdentityEngine | None = None
        self._authority_service: AuthorityService | None = None
        self._session_manager: SessionManager | None = None
        self._session_context: SessionContext | None = None
        self._orchestration_executor: OrchestrationExecutor | None = None

        # --- Phase 8.3: Goal Intelligence ---
        self._goal_repository: GoalRepository | None = None
        self._goal_intelligence_engine: GoalIntelligenceEngine | None = None

        # --- Phase 9.0: Experience & Self-Model ---
        self._experience_repository: ExperienceRepository | None = None
        self._experience_accumulator: ExperienceAccumulator | None = None
        self._self_model_engine: SelfModelEngine | None = None

        # --- Phase 10.0: Evolution Pipeline ---
        self._improvement_planner: ImprovementPlanner | None = None
        self._proposal_generator: ProposalGenerator | None = None
        self._approval_manager: ApprovalManager | None = None
        self._evolution_memory: EvolutionMemory | None = None

        # --- Stage H: Promotion gate (kernel-owned read-only view + bridge) ---
        # One PromotionGate composed over the kernel-owned EvolutionMemory.
        # Used by ``pending_promotion_reviews()`` and the manual
        # ``submit_development_for_promotion_review()`` bridge. Never
        # mutates the repository; never auto-runs.
        self._promotion_gate: PromotionGate | None = None

        # --- Phase 11.0: Evolution Execution Engine ---
        self._outcome_tracker: OutcomeTracker | None = None
        self._execution_engine: EvolutionExecutionEngine | None = None
        self._execution_gateway: EvolutionExecutionGateway | None = None

        # --- Phase 13.1: Governance ---
        self._constraint_registry: ConstraintRegistry | None = None
        self._rule_engine: Any | None = None

        # --- Phase 11.3: Evolution Persistence ---
        self._evolution_storage: SQLiteEvolutionStorage | None = None

        # --- Phase 12.1 / 12.2: Evolution Intelligence ---
        self._insight_scorer: InsightScorer | None = None
        self._intelligence_engine: EvolutionIntelligenceEngine | None = None

        # --- Reasoning pipeline ---
        self._reasoning_controller: ReasoningController | None = None
        self._capability_analyzer: CapabilityAnalyzer | None = None
        self._capability_registry: CapabilityRegistry | None = None
        self._capability_router: CapabilityRouter | None = None
        self._capability_dispatcher: CapabilityDispatcher | None = None
        self._reasoning_recorder: ReasoningRecorder | None = None
        self._reflection_engine: ReflectionEngine | None = None
        self._planning_engine: PlanningEngine | None = None

        # --- Tool intelligence ---
        self._tool_registry: ToolRegistry | None = None
        self._tool_selector: ToolSelector | None = None
        self._tool_executor: ToolExecutor | None = None
        self._tool_engine: ToolEngine | None = None

        # --- Model routing ---
        self._model_profile_registry: ModelProfileRegistry | None = None
        self._model_router: ModelRouter | None = None

        # --- Phase 6.1: Deterministic Fallback Resolver ---
        self._deterministic_fallback: Any | None = None

        # --- Phase 1: Built-In Conversational Response Service ---
        self._builtin_response: Any | None = None

        self._learning_manager: LearningManager | None = None
        self._knowledge_feedback: KnowledgeFeedback | None = None
        self._started = False

        # --- Phase 13.2: Component Registry ---
        self._component_registry = ComponentRegistry()

        # --- Phase 13.3: Evolution Scheduler ---
        self._evolution_scheduler: EvolutionScheduler | None = None

        # --- Stage A1: Repository self-knowledge (read-only, lazy build) ---
        try:
            self._repository_map_builder = RepositoryMapBuilder(
                Path(__file__).resolve().parents[2]
            )
        except Exception:
            self._repository_map_builder = None
        self._repository_map: Any | None = None

        # --- Stage F: latest bounded research evidence (cache-only) ---
        self._last_research_evidence: dict | None = None

        # --- D2: controlled external-knowledge acquisition (lazy; deny-by-default) ---
        self._external_acquirer: Any | None = None

        # --- D3: conversation <-> knowledge integration (lazy) ---
        self._knowledge_decision: Any | None = None

        # --- D4: self-directed work orchestration (lazy) ---
        self._work_orchestrator: Any | None = None

        # --- D5: development independence orchestration (lazy) ---
        self._development_run_orchestrator: Any | None = None

        # --- Phase 13.5: Persistent Evolution Knowledge ---
        self._knowledge_consolidator: EvolutionKnowledgeConsolidator | None = None
        self._knowledge_repository: EvolutionKnowledgeRepository | None = None
        self._knowledge_query: EvolutionKnowledgeQuery | None = None

        # --- Phase 13.6: Automatic Evolution Knowledge Consolidation Pipeline ---
        self._knowledge_pipeline: EvolutionKnowledgePipeline | None = None

        # --- Phase 14.4: Decision Intelligence ---
        self._decision_intelligence: DecisionIntelligenceEngine | None = None

        # --- Phase 15.0: Goal Execution ---
        self._goal_executor: GoalExecutionEngine | None = None
        self._binder_registry: ExecutionActionBinderRegistry | None = None

        # --- Track A: Research & Knowledge ---
        self._research_storage: ResearchSQLiteStorage | None = None
        self._research_factory: ResearchCapabilityFactory | None = None
        self._research_coordinator: ConcreteResearchCoordinator | None = None
        self._research_ingest_bridge: ResearchIngestBridge | None = None
        self._acquisition_service: InformationAcquisitionService | None = None

        # --- Phase 5.2: Direct Atlas Evolution (bounded; opt-in) ---
        self._development_envelope: Any | None = None
        self._development_authority: Any | None = None
        self._development_driver: Any | None = None
        self._promotion_executor: Any | None = None
        self._development_authorizations: dict[str, Any] = {}
        self._promotion_artifacts: dict[str, Any] = {}
        self._development_envelope_usage: int = 0

        # --- Track B: Tool Ecosystem ---
        self._toolchain_storage: ToolchainSQLiteStorage | None = None
        self._toolchain_factory: ToolchainCapabilityFactory | None = None

        # --- Track C: Long-Term Learning ---
        self._longterm_storage: LongTermSQLiteStorage | None = None
        self._episodic_repository: EpisodicRepository | None = None
        self._procedural_repository: ProceduralRepository | None = None
        self._longterm_recorder: EpisodicRecorder | None = None
        self._procedure_extractor: ProcedureExtractor | None = None
        self._longterm_consolidator: Consolidator | None = None
        self._longterm_factory: LongTermCapabilityFactory | None = None
        self._longterm_ingest_bridge: LongTermIngestBridge | None = None

        # --- Track D: Advanced Reasoning ---
        self._advanced_reasoning_storage: AdvancedReasoningSQLiteStorage | None = None
        self._advanced_reasoning_repository: Any | None = None
        self._advanced_reasoning_service: AdvancedReasoningService | None = None
        self._advanced_reasoning_factory: AdvancedReasoningCapabilityFactory | None = None
        self._advanced_reasoning_recorder: ReasoningTraceRecorder | None = None
        self._advanced_reasoning_ingest_bridge: ReasoningIngestBridge | None = None
        self._advanced_reasoning_evidence_provider: Any | None = None
        self._advanced_reasoning_causal_provider: Any | None = None

        # --- Phase 16: Autonomy persistence ---
        self._autonomy_storage: Any | None = None
        self._schedule_store: Any | None = None
        self._application_engine: Any | None = None
        self._governed_ingest_sink: Any | None = None
        self._autonomy_request_adapter: Any | None = None
        self._autonomy_dispatcher: Any | None = None

        # --- Phase 16.7 / F11 (post-Core): Boot activation & SAFE_MODE ---
        # One boot-time staged-config activation pass over the EXISTING
        # Phase 16.7 service. Runs once during startup; integrity failure
        # => SAFE_MODE (base config, dispatcher suppressed). Never retried;
        # no background recovery; never runs from tick().
        self._boot_activation: Any | None = None
        self._boot_report: Any | None = None
        self._config_overlay: dict[str, Any] = {}

        # --- Phase E6: Governed self-development loop ---
        # One DevelopmentPlanner + one SelfDevelopmentLoop reuse the existing
        # kernel-owned LearningMemory and ToolRegistry. No parallel registries or
        # stores are created. Development runs are bounded and never touch the
        # real repository.
        self._development_planner: DevelopmentPlanner | None = None
        self._self_development_loop: SelfDevelopmentLoop | None = None

        # --- Phase F1 (post-Core): Environment observation foundation ---
        # One EnvironmentObserver reusing the EXISTING model-profile / tool /
        # capability registries, the EXISTING EventBus, and the EXISTING
        # SelfObservationEngine. Purely observational; nothing auto-runs.
        self._environment_observer: EnvironmentObserver | None = None

        # --- Phase F10 (post-Core): AI provider availability (observation) ---
        # One bounded, deterministic outcome tracker exposed through the
        # EXISTING F1 environment-observation cycle. On demand only; never
        # records by itself; never runs from tick(); no daemon.
        self._ai_availability: ProviderAvailabilityTracker | None = None

        # --- Phase F3 (post-Core): Lifecycle assessment foundation ---
        # One pure CapabilityLifecycleAssessor reusing the EXISTING registries
        # as read-only snapshot inputs. Never auto-runs; never mutates.
        self._lifecycle_assessor: CapabilityLifecycleAssessor | None = None

        # --- Phase F4 (post-Core): Governed adaptation decision foundation ---
        # One pure AdaptationDecisionEngine producing DRAFT proposal candidates
        # only. Never auto-runs; never approves; never executes.
        self._adaptation_engine: AdaptationDecisionEngine | None = None

        # --- Phase F5 (post-Core): Adaptation evaluation & feedback ---
        # One pure AdaptationEvaluator closing the governed loop. Observes and
        # records outcomes only; never executes, never approves.
        self._adaptation_evaluator: AdaptationEvaluator | None = None

        # --- Phase F6 (post-Core): Full adaptation cycle orchestrator ---
        # One pure orchestrator composing F1-F5 into bounded, manually-triggered
        # adaptation cycles. Never auto-runs; never approves; never executes.
        self._adaptation_orchestrator: AdaptationOrchestrator | None = None

        # --- Phase F7 (post-Core): Autonomous Operation Controller ---
        # One bounded, manually-invoked operational controller around F6.
        # Never a daemon; never approves/executes; never runs from tick();
        # an external host drives ``run_operation_cycle()`` explicitly.
        self._operation_controller: OperationController | None = None

        # --- Phase F9 (post-Core): Governed Development Cycle Controller ---
        # One bounded, single-shot preparation controller. Never approves;
        # never authorizes; never executes; never runs from tick(); an
        # external host drives ``run_development_cycle()`` explicitly.
        self._development_controller: DevelopmentCycleController | None = None

        # --- Phase F11 (post-Core): Long-Term Self-Management Review ---
        # One bounded, read-only, single-shot evidence review. Never
        # approves/authorizes/executes; never persists; never runs from
        # tick(); an external host calls ``run_self_management_review()``.
        self._self_management_review: SelfManagementReview | None = None

        # --- P5: Proactive Advisory (advisory-only, never autonomous) ---
        # Composes the EXISTING F1/F10/F11/B3.x/P4 signals into one bounded
        # user-facing advisory report. Never invokes a tool, capability,
        # orchestration, development, governance, approval, or promotion
        # path directly; the report's ``suggested_action`` is a bounded hint
        # for the operator. Never runs from tick(); an external host calls
        # ``run_proactive_advisory()``.
        self._proactive_advisor: Any | None = None

    # ------------------------------------------------------------------
    # Public entry / on-demand observation cycle
    # ------------------------------------------------------------------

    def observe_environment(self):
        """Run one bounded environment observation cycle.

        Returns an ``EnvironmentObservationResult``. Raises ``RuntimeError``
        if Atlas has not started (observer not wired).
        """
        if self._environment_observer is None:
            raise RuntimeError(
                "Environment observer is not wired; Atlas.start() must run first."
            )
        return self._environment_observer.observe_cycle()

    # ------------------------------------------------------------------
    # Phase F1: Environment observer (wired; never auto-started)
    # ------------------------------------------------------------------

    def _init_environment_observer(self) -> None:
        """Phase F1 (post-Core): additively wire the environment observer.

        Reuses the existing registries/EventBus/SelfObservationEngine.
        Nothing runs automatically; ``observe_environment()`` drives it on demand.
        """
        providers = default_providers(
            model_registry=self._model_profile_registry,
            tool_registry=self._tool_registry,
            capability_registry=self._capability_registry,
        )
        # --- Phase F10 (post-Core): AI provider availability ---
        # Bounded, deterministic outcome tracker exposed as one additional
        # PROVIDER-domain observation. Purely observational; outcomes are
        # recorded only when a caller reports them; nothing auto-runs.
        self._ai_availability = ProviderAvailabilityTracker()
        providers.append(ProviderHealthObserver(self._ai_availability))
        self._environment_observer = EnvironmentObserver(
            providers=providers,
            event_bus=self._event_bus,
            observation_engine=self._self_observation_engine,
        )

    # ------------------------------------------------------------------
    # Phase F3: Lifecycle assessor (wired; read-only, never auto-runs)
    # ------------------------------------------------------------------

    def _init_lifecycle_assessor(self) -> None:
        """Phase F3 (post-Core): additively wire the lifecycle assessor.

        Reuses the existing model/tool/capability/skill registries as
        read-only snapshot inputs. No mutation, no automatic execution.
        """
        self._lifecycle_assessor = CapabilityLifecycleAssessor()

    def assess_capability_lifecycle(self, changes=None, freshness=None, targets=None):
        """Run a read-only lifecycle assessment over existing registries.

        Args:
            changes: Optional iterable of F1 ``EnvironmentChange`` records.
            freshness: Optional iterable of F2 ``KnowledgeFreshnessAssessment``
                records.
            targets: Optional explicit ``LifecycleTarget`` descriptors. When
                ``None``, targets are snapshotted from the kernel's existing
                model-profile / tool / capability registries.

        Returns:
            A ``LifecycleAssessmentResult``. Never mutates any registry and
            never executes anything.
        """
        if self._lifecycle_assessor is None:
            raise RuntimeError(
                "Lifecycle assessor is not wired; Atlas.start() must run first."
            )
        if targets is None:
            targets = targets_from_registries(
                model_registry=self._model_profile_registry,
                tool_registry=self._tool_registry,
                capability_registry=self._capability_registry,
            )
        return self._lifecycle_assessor.assess_many(
            targets,
            changes=changes or (),
            freshness=freshness or (),
        )

    # ------------------------------------------------------------------
    # Phase F4: Governed adaptation decision (candidate-producing only)
    # ------------------------------------------------------------------

    def _init_adaptation_engine(self) -> None:
        """Phase F4 (post-Core): additively wire the adaptation decision engine.

        Produces DRAFT proposal candidates only. No approval, no execution,
        no persistence. Nothing auto-runs.
        """
        self._adaptation_engine = AdaptationDecisionEngine()

    def generate_adaptation_proposals(self, changes=None, freshness=None, targets=None):
        """Run F1/F2/F3 -> F4 and return DRAFT-only adaptation proposals.

        Args:
            changes: Optional iterable of F1 ``EnvironmentChange`` records.
            freshness: Optional iterable of F2 ``KnowledgeFreshnessAssessment``
                records.
            targets: Optional explicit ``LifecycleTarget`` descriptors. When
                ``None``, targets are snapshotted from the kernel's existing
                registries.

        Returns:
            A tuple of ``EvolutionProposal`` in ``DRAFT`` status (never
            ``APPROVED``). Nothing is executed or approved here.
        """
        if self._adaptation_engine is None or self._lifecycle_assessor is None:
            raise RuntimeError(
                "Adaptation engine is not wired; Atlas.start() must run first."
            )
        assessment_result = self.assess_capability_lifecycle(
            changes=changes, freshness=freshness, targets=targets
        )
        return self._adaptation_engine.generate(assessment_result.assessments)

    # ------------------------------------------------------------------
    # Phase F5: Adaptation evaluation & feedback (observer only)
    # ------------------------------------------------------------------

    def _init_adaptation_evaluator(self) -> None:
        """Phase F5 (post-Core): additively wire the adaptation evaluator.

        Closes the governed loop with pure evaluation + feedback. It never
        executes, never approves, never auto-runs.
        """
        self._adaptation_evaluator = AdaptationEvaluator()

    def evaluate_adaptation(self, proposal, outcome=None):
        """Evaluate one adaptation proposal (optionally with its outcome).

        Args:
            proposal: An ``EvolutionProposal`` (any lifecycle status).
            outcome: Optional Phase E ``DevelopmentOutcome`` / run result.

        Returns:
            An ``AdaptationEvaluation`` plus its ``AdaptationFeedback`` as a
            tuple. Nothing is executed, approved, or persisted here.
        """
        if self._adaptation_evaluator is None:
            raise RuntimeError(
                "Adaptation evaluator is not wired; Atlas.start() must run first."
            )
        evaluation = (
            self._adaptation_evaluator.evaluate_outcome(proposal, outcome)
            if outcome is not None
            else self._adaptation_evaluator.evaluate_proposal(proposal)
        )
        return (evaluation, self._adaptation_evaluator.feedback_for(evaluation))

    # ------------------------------------------------------------------
    # Phase F6: Full adaptation cycle (manually triggered; bounded)
    # ------------------------------------------------------------------

    def _init_adaptation_orchestrator(self) -> None:
        """Phase F6 (post-Core): additively wire the adaptation orchestrator.

        Composes the kernel's existing F1/F3/F4/F5 instances plus a fresh F2
        assessor into one bounded adaptation cycle. Never runs automatically;
        ``run_adaptation_cycle()`` drives it explicitly.
        """
        self._adaptation_orchestrator = AdaptationOrchestrator(
            environment_observer=self._environment_observer,
            lifecycle_assessor=self._lifecycle_assessor,
            decision_engine=self._adaptation_engine,
            evaluator=self._adaptation_evaluator,
        )

    def run_adaptation_cycle(
        self,
        knowledge_refs=(),
        lifecycle_targets=(),
        supplied_changes=(),
        evaluate_pairs=(),
        max_candidates=5,
    ):
        """Manually trigger one bounded F1-F5 adaptation cycle.

        Produces DRAFT ``EvolutionProposal`` candidates ONLY and returns a
        bounded ``AdaptationCycleResult``. It never approves, never executes,
        never auto-runs from ``tick()``, and never starts a daemon.

        Args:
            knowledge_refs: F2 ``KnowledgeRef`` descriptors.
            lifecycle_targets: F3 ``LifecycleTarget`` descriptors (defaults to
                a read-only snapshot of the kernel's existing registries when
                omitted).
            supplied_changes: Optional explicit F1 ``EnvironmentChange`` list.
            evaluate_pairs: Optional ``(proposal, outcome)`` pairs for F5
                evaluation (existing/governance-held data only).
            max_candidates: Bound on generated candidates/proposals.

        Returns:
            An ``AdaptationCycleResult``.
        """
        if self._adaptation_orchestrator is None:
            raise RuntimeError(
                "Adaptation orchestrator is not wired; Atlas.start() must run first."
            )
        if lifecycle_targets is None or not lifecycle_targets:
            lifecycle_targets = targets_from_registries(
                model_registry=self._model_profile_registry,
                tool_registry=self._tool_registry,
                capability_registry=self._capability_registry,
            )
        return self._adaptation_orchestrator.run_cycle(
            knowledge_refs=knowledge_refs,
            lifecycle_targets=lifecycle_targets,
            supplied_changes=supplied_changes,
            evaluate_pairs=evaluate_pairs,
            max_candidates=max_candidates,
        )

    # ------------------------------------------------------------------
    # Phase F7: Autonomous Operation Controller (manually invoked; bounded)
    # ------------------------------------------------------------------

    def _init_operation_controller(self) -> None:
        """Phase F7 (post-Core): additively wire the operation controller.

        Wraps the kernel's existing ``run_adaptation_cycle`` (F6) in a bounded,
        manually-invoked controller with the default policy. It never runs from
        ``tick()`` and never starts a daemon; an external host process calls
        ``run_operation_cycle()``.
        """
        self._operation_controller = OperationController(
            cycle_runner=self.run_adaptation_cycle,
        )

    @property
    def operation_controller(self):
        """Return the kernel-owned OperationController (Phase F7).

        Bounded, manually-invoked wrapper around F6. Never auto-runs, never
        approves, never executes.
        """
        return self._operation_controller

    def run_operation_cycle(
        self,
        knowledge_refs=(),
        lifecycle_targets=(),
        supplied_changes=(),
        evaluate_pairs=(),
        max_cycles=None,
    ):
        """Manually trigger ONE bounded autonomous-operation invocation.

        Delegates to the kernel's F7 ``OperationController``, which wraps the
        existing F6 adaptation cycle inside a bounded cooldown / budget /
        failure policy. Returns an ``OperationResult``. Nothing is approved,
        executed, or auto-run here.
        """
        if self._operation_controller is None:
            raise RuntimeError(
                "Operation controller is not wired; Atlas.start() must run first."
            )
        return self._operation_controller.run_operation(
            knowledge_refs=knowledge_refs,
            lifecycle_targets=lifecycle_targets,
            supplied_changes=supplied_changes,
            evaluate_pairs=evaluate_pairs,
            max_cycles=max_cycles,
        )

    # ------------------------------------------------------------------
    # Phase F8: Information Acquisition (manually invoked; bounded)
    # ------------------------------------------------------------------

    def _select_research_sources(self, question: str):
        """Phase 3.2 — deterministic, authorized local source selection.

        Chooses repository (CODEBASE) sources for a research question using the
        existing cached repository map. It only SELECTS among sources the
        existing architecture already recognizes; it grants no authorization and
        never selects web (the web adapter remains deny-by-default). Fail-closed:
        an unavailable map or any error yields an empty selection.
        """
        from atlas.research.source_selection import select_repository_sources

        try:
            return select_repository_sources(
                question, repository_map=self.repository_map
            )
        except Exception:
            return ()

    def _init_information_acquisition(self) -> None:
        """Phase F8 (post-Core): additively wire the acquisition service.

        Wraps the kernel's existing F2 ``KnowledgeFreshnessAssessor`` and the
        research coordinator in a thin, deterministic, model-optional
        information-acquisition layer. It never runs from ``tick()``, never
        starts a daemon, and never bypasses the GOV-008 governed ingest path.
        """
        self._acquisition_service = InformationAcquisitionService(
            coordinator=self._research_coordinator,
            planner=self._research_factory.planner,
            freshness_assessor=KnowledgeFreshnessAssessor(),
        )

    @property
    def acquisition_service(self):
        """Return the kernel-owned InformationAcquisitionService (Phase F8)."""
        return self._acquisition_service

    @property
    def external_acquisition(self):
        """Return the kernel-owned ExternalKnowledgeAcquirer (D2).

        Controlled external-knowledge acquisition built over the EXISTING
        acquisition service and validated-knowledge retriever. Its host policy
        is derived from the EXISTING ``research.web_allowed_hosts`` config, so
        it is deny-by-default: with no allowlist entry, no host is fetchable.
        Read-only with respect to governance: it never approves, authorizes,
        executes, promotes, or self-modifies anything.
        """
        if self._external_acquirer is None:
            from atlas.research.external_acquisition import ExternalKnowledgeAcquirer
            from atlas.research.sources.web import web_host_policy_from_hosts
            from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever

            hosts = self._config.get("research", "web_allowed_hosts", default=())
            self._external_acquirer = ExternalKnowledgeAcquirer(
                acquisition_service=self._acquisition_service,
                validated_retriever=ValidatedKnowledgeRetriever(self._research_storage),
                host_policy=web_host_policy_from_hosts(tuple(hosts or ())),
            )
        return self._external_acquirer

    def acquire_external_knowledge(
        self,
        objective: str,
        candidate_urls=(),
        knowledge_query: str = "",
    ):
        """Run ONE controlled external-knowledge acquisition (D2).

        Returns an ``ExternalAcquisitionResult``. Deny-by-default: candidate
        hosts must be explicitly allowlisted in ``research.web_allowed_hosts``.
        Never approves, authorizes, executes, or promotes anything.
        """
        return self.external_acquisition.acquire(
            objective,
            candidate_urls=tuple(candidate_urls or ()),
            knowledge_query=knowledge_query,
        )

    @property
    def knowledge_decision(self):
        """Return the kernel-owned KnowledgeDecisionService (D3).

        Integrates the existing validated-knowledge retrieval with the D2
        acquisition boundary. Read-only with respect to governance: it never
        approves, authorizes, executes, promotes, or self-modifies anything.
        """
        if self._knowledge_decision is None:
            from atlas.research.knowledge_decision import KnowledgeDecisionService
            from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever

            self._knowledge_decision = KnowledgeDecisionService(
                validated_retriever=ValidatedKnowledgeRetriever(self._research_storage),
                external_acquirer=self.external_acquisition,
            )
        return self._knowledge_decision

    def _external_source_urls(self):
        """Authorized external candidate URLs from optional config (default none).

        Empty by default: no candidate source, so D2 stays deny-by-default and
        the conversational knowledge path performs no network access.
        """
        try:
            urls = self._config.get("research", "external_source_urls", default=())
        except Exception:
            return ()
        if not isinstance(urls, (list, tuple)):
            return ()
        return tuple(u for u in urls if isinstance(u, str) and u.strip())

    def _knowledge_decision_enrich(self, query: str):
        """D3 local-first enrichment for the conversational knowledge surface.

        Returns validated knowledge (existing first, else via governed D2
        acquisition) or ``None``. Fail-soft: any error leaves behavior unchanged.
        """
        try:
            return self.knowledge_decision.retrieve_with_acquisition(
                query, candidate_urls=self._external_source_urls()
            )
        except Exception:
            return None

    def _knowledge_status(self, query: str):
        """G2 — structured D3 sufficiency decision for the conversational report.

        Delegates to the EXISTING ``knowledge_decision`` service: the same
        decision ``answer_knowledge_question`` returns. The conversation layer
        uses it only to REPORT sufficiency and the governed-acquisition outcome
        for a question the local store could not answer. Deterministic,
        read-only in effect for the conversation, and fail-soft: any error leaves
        the existing (C6.1) rendering unchanged.
        """
        try:
            return self.knowledge_decision.decide(query)
        except Exception:
            return None

    def answer_knowledge_question(
        self,
        objective: str,
        candidate_urls=(),
        knowledge_query: str = "",
    ):
        """Structured D3 knowledge decision (API seam; never fabricates).

        Returns a ``KnowledgeAnswer`` describing sufficiency and, where
        applicable, the governed acquisition outcome. Pure decision + retrieval:
        it never approves, authorizes, executes, or promotes anything.
        """
        return self.knowledge_decision.decide(
            objective,
            knowledge_query=knowledge_query,
            candidate_urls=tuple(candidate_urls or ()),
        )

    @property
    def work_orchestrator(self):
        """Return the kernel-owned WorkOrchestrator (D4).

        Bounded orchestration over the EXISTING knowledge decision, capability
        registry/dispatcher, and session/authority boundary. It never creates
        authority and never executes governed development.
        """
        if self._work_orchestrator is None:
            from atlas.orchestration.work_orchestrator import WorkOrchestrator

            self._work_orchestrator = WorkOrchestrator(
                knowledge_decision=self.knowledge_decision,
                capability_registry=self._capability_registry,
                dispatcher=self._capability_dispatcher,
                authorization_check=self._orchestration_authorization_check,
            )
        return self._work_orchestrator

    @staticmethod
    def _orchestration_authorization_check(session_context) -> bool:
        """Consult the EXISTING authority boundary (read-only).

        True only for a session context the existing authority layer already
        established as OWNER. It never creates authority and never infers it
        from language, a proposal, or external content.
        """
        return bool(
            session_context is not None
            and getattr(session_context, "is_owner", False)
        )

    def run_work_objective(
        self,
        objective: str,
        semantic=None,
        candidate_urls=(),
        require_authorization: bool = False,
        session_context=None,
    ):
        """Run ONE bounded D4 orchestration lifecycle (API seam).

        Returns an ``OrchestrationRun``. Never approves, authorizes, executes
        governed development, or promotes anything.
        """
        return self.work_orchestrator.run(
            objective,
            semantic=semantic,
            session_context=session_context,
            candidate_urls=tuple(candidate_urls or ()),
            require_authorization=require_authorization,
        )

    @property
    def development_orchestrator(self):
        """Return the kernel-owned DevelopmentOrchestrator (D5).

        Bounded coordinator over the EXISTING governed development lifecycle:
        proposal preparation, OWNER approval (read-only), sandbox execution,
        verification, promotion review/executor, and self-knowledge refresh.
        It never approves, authorizes, executes without an approved proposal,
        or promotes itself.
        """
        if self._development_run_orchestrator is None:
            from atlas.orchestration.development_orchestrator import (
                DevelopmentOrchestrator,
            )

            self._development_run_orchestrator = DevelopmentOrchestrator(
                driver=lambda objective, metadata: self.run_development_driver(
                    objective, metadata=metadata
                ),
                approval_checker=self._development_proposal_approved,
                execution_runner=lambda session, proposal_id: (
                    self.run_development_execution(session, proposal_id)
                ),
                promotion_reviewer=lambda session, run_result, proposal_id: (
                    self.submit_development_for_promotion_review(
                        session, run_result, proposal_id=proposal_id
                    )
                ),
                promotion_executor=lambda session, request_id: (
                    self.promote_validated_change(session, request_id)
                ),
                self_knowledge_refresher=self._development_self_knowledge_snapshot,
            )
        return self._development_run_orchestrator

    def _development_proposal_approved(self, proposal_id: str) -> bool:
        """READ-ONLY check of the EXISTING persisted approval state.

        True only when the existing EvolutionMemory holds the proposal in
        ``APPROVED`` status. It never creates or infers approval.
        """
        try:
            proposal = self._evolution_memory.get_proposal(proposal_id)
        except Exception:
            return False
        if proposal is None:
            return False
        return getattr(getattr(proposal, "status", None), "name", "") == "APPROVED"

    def _development_self_knowledge_snapshot(self) -> dict:
        """Read-only self-knowledge snapshot (existing capability model)."""
        try:
            model = self.capability_model()
            return {
                "capabilities": int(getattr(model, "capability_count", 0) or 0),
                "components": int(getattr(model, "component_count", 0) or 0),
                "tools": int(getattr(model, "tool_count", 0) or 0),
            }
        except Exception:
            return {}

    def run_development_objective(
        self,
        objective: str,
        session_context=None,
        metadata=None,
    ):
        """Run ONE bounded governed development lifecycle (D5 API seam).

        Returns a ``DevelopmentRun``. The orchestrator never approves,
        authorizes, or promotes itself; it stops at ``AWAITING_OWNER`` without
        approval and executes only through the existing governed paths.
        """
        return self.development_orchestrator.run(
            objective,
            session_context=session_context,
            metadata=dict(metadata or {}),
        )

    def run_information_acquisition(
        self,
        question="",
        sources=(),
        knowledge_refs=(),
        query_id="",
    ):
        """Manually trigger ONE bounded information-acquisition invocation.

        Delegates to the kernel's F8 ``InformationAcquisitionService``, which
        composes the existing F2 freshness gate and research pipeline. Returns
        an ``AcquisitionResult``. Read-only with respect to runtime execution:
        nothing is approved, executed, or auto-run here.
        """
        if self._acquisition_service is None:
            raise RuntimeError(
                "Information acquisition is not wired; Atlas.start() must run first."
            )
        result = self._acquisition_service.acquire(
            question=question,
            sources=sources,
            knowledge_refs=knowledge_refs,
            query_id=query_id,
        )

        # Stage F: cache a bounded, JSON-safe summary of the latest
        # acquisition so planning context and proposals can carry research
        # evidence. Cache-only — never triggers another acquisition.
        try:
            from atlas.research.evidence_summary import summarize_acquisition

            self._last_research_evidence = summarize_acquisition(result)
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Phase F9: Governed Development Cycle (manually invoked; bounded)
    # ------------------------------------------------------------------

    def _init_development_cycle(self) -> None:
        """Phase F9 (post-Core): additively wire the development-cycle
        controller.

        Composes the EXISTING ``ApprovalManager`` and, when wired, the F8
        acquisition service as an optional researcher. The controller only
        PREPARES a bounded DRAFT ``EvolutionProposal`` and submits it to the
        existing approval workflow. It never runs from ``tick()``, never
        starts a daemon, and never authorizes, executes, or promotes.

        B4 (governed model-assisted authoring) — OPT-IN ONLY: when the
        ``[development] model_assisted_authoring`` config flag is explicitly
        ``true``, the optional :class:`ModelAssistedChangeSupplier` is
        constructed and injected through the existing ``change_supplier``
        seam. When false (the default), ``change_supplier`` stays ``None``
        and the controller uses the existing ``DeterministicChangeSupplier``
        — no model is required, no model-assisted authoring occurs.
        """
        from atlas.evolution.development_cycle import DeterministicChangeSupplier
        from atlas.evolution.development_scaffold_supplier import (
            CompositeChangeSupplier,
            ScaffoldChangeSupplier,
        )

        model_supplier = None
        if bool(
            self._config.get("development", "model_assisted_authoring", default=False)
        ):
            model_supplier = ModelAssistedChangeSupplier(
                authoring_model=self._model_assisted_authoring_model,
            )

        # Phase 5.2 — deterministic-first authoring over the EXISTING
        # ChangeSupplier seam: explicitly supplied content, then the bounded
        # scaffold author, then (opt-in only) the non-authoritative model
        # supplier. No new synthesis surface is introduced.
        change_supplier = CompositeChangeSupplier(
            [
                DeterministicChangeSupplier(),
                ScaffoldChangeSupplier(),
                model_supplier,
            ]
        )

        # Task 2 — the SAME authoritative composition is exposed to both
        # consumers: the F9 development controller above and the conversational
        # P17 authoring seam. No second, competing supplier is constructed, and
        # the deterministic-first ordering is unchanged.
        self._proposal_change_supplier = change_supplier

        self._development_controller = DevelopmentCycleController(
            approval_manager=self._approval_manager,
            change_supplier=change_supplier,
            researcher=(
                self._acquisition_service.acquire
                if self._acquisition_service is not None
                else None
            ),
            proposal_store=self._evolution_memory,
            approval_request_store=self._evolution_memory,
        )

        # Phase 5.2 — bounded Development Envelope (disabled by default).
        from atlas.evolution.development_envelope import (
            DevelopmentAuthority,
            DevelopmentEnvelope,
        )

        envelope_data: Any = None
        try:
            envelope_data = self._config.get(
                "development", "envelope", default=None
            )
        except Exception:
            envelope_data = None
        self._development_envelope = DevelopmentEnvelope.from_mapping(envelope_data)
        self._development_authority = DevelopmentAuthority(
            self._development_envelope,
            usage_provider=lambda: self._development_envelope_usage,
        )

    def _model_assisted_authoring_model(self, prompt: str):
        """Duck-typed authoring model backed by the EXISTING ``AIService``.

        Wired by the kernel composition root; the supplier itself never
        imports ``atlas.ai``. Uses the existing ``AIService.chat`` routing
        convention and returns the ``AIResponse.text`` string.
        """
        response = self._ai_manager.service.chat(
            [{"role": "user", "content": prompt}],
            routing_context=RoutingRequest(
                complexity=0.8,
                latency_requirement="any",
                task_type="development",
                context_size=len(prompt),
                metadata={"source": "development_cycle"},
            ),
        )
        return response.text

    def _intent_assist_model(self, prompt: str):
        """Duck-typed model callable for the OPTIONAL language-understanding seam.

        Backed by the EXISTING ``AIService`` (no new integration); used only by
        :class:`~atlas.conversation.model_intent_parser.ModelIntentParser`, which
        is itself wired only when external providers are explicitly enabled and
        only consulted for turns the deterministic intake cannot type. The
        result is untrusted text; it can never approve, execute, or promote.
        """
        response = self._ai_manager.service.chat(
            [{"role": "user", "content": prompt}],
            routing_context=RoutingRequest(
                complexity=0.4,
                latency_requirement="fast",
                task_type="conversation",
                context_size=len(prompt),
                metadata={"source": "language_understanding"},
            ),
        )
        return response.text

    def _build_task_intake(self):
        """Build the kernel-owned conversational intake.

        Deterministic by default. When external providers are explicitly enabled
        (``[ai].external_providers = true``), the EXISTING optional model-assisted
        parsing seam is wired in — bounded to turns the deterministic intake
        cannot type and to the closed, non-governed task-type vocabulary. Any
        wiring failure falls back to the deterministic intake (fail-closed).
        """
        from atlas.conversation.task_intake import TaskIntake

        try:
            if not bool(getattr(self._ai_manager, "external_providers", False)):
                return TaskIntake()
            from atlas.conversation.model_intent_parser import ModelIntentParser

            return TaskIntake(parser=ModelIntentParser(model=self._intent_assist_model))
        except Exception:
            return TaskIntake()

    @property
    def development_controller(self):
        """Return the kernel-owned DevelopmentCycleController (Phase F9)."""
        return self._development_controller

    @property
    def deterministic_fallback(self):
        """Return the kernel-owned DeterministicFallbackResolver (Phase 6.1)."""
        return self._deterministic_fallback

    @property
    def builtin_response(self):
        """Return the kernel-owned BuiltinResponseService (Phase 1)."""
        return self._builtin_response

    def run_development_cycle(
        self,
        need,
        force_research=False,
    ):
        """Manually trigger ONE bounded development-cycle preparation.

        Delegates to the kernel's F9 ``DevelopmentCycleController``, which
        formulates a bounded DRAFT ``EvolutionProposal`` and submits it to
        the existing ``ApprovalManager``, STOPPING at the human approval
        boundary. Returns a ``DevelopmentCycleResult``. Nothing is approved,
        authorized, scheduled, executed, or promoted here.
        """
        if self._development_controller is None:
            raise RuntimeError(
                "Development cycle controller is not wired; Atlas.start() "
                "must run first."
            )
        return self._development_controller.run_development_cycle(
            need,
            force_research=force_research,
        )

    # ------------------------------------------------------------------
    # B3 — Conversational development bridge
    # ------------------------------------------------------------------

    def _orchestration_bridge(self, spec, session_context=None) -> Message:
        """Convert a B2 ACTION/INFORMATION TaskSpec into an orchestration result."""
        from atlas.orchestration.execution_models import ExecutionRequest
        from atlas.orchestration.reporting import orchestration_result_to_message
        from atlas.orchestration.target_resolution import task_spec_to_execution_steps

        # The per-request session (forwarded by ConversationService) is
        # authoritative; only fall back to the kernel-bound session when none
        # was provided (backward compatibility for kernel-driven calls).
        request_session = session_context
        if request_session is None:
            request_session = getattr(self, "_session_context", None)

        steps = task_spec_to_execution_steps(
            spec,
            tool_targets=self._registered_tool_targets(),
        )
        if steps is None:
            return None  # type: ignore[return-value]

        executor = getattr(self, "_orchestration_executor", None)

        # Reuse the bounded per-request SessionContext; the bridge never
        # derives authority from user text and never trusts ``spec.context``.
        result = executor.execute(
            ExecutionRequest(
                steps=tuple(steps),
                session_context=request_session,
            )
        )
        # P2/B2.4 — Additive experience capture. Record the completed
        # orchestration run as a StructuredExperience through the kernel-owned
        # ExperienceAccumulator (SQLite dual-write, best-effort). Failures are
        # swallowed so reporting is never blocked. No schema change, no
        # RuntimeCoordinator change, no authority/context bypass.
        try:
            acc = getattr(self, "_experience_accumulator", None)
            if acc is not None and hasattr(acc, "record_orchestration"):
                acc.record_orchestration(
                    user_input=spec.goal if hasattr(spec, "goal") else "",
                    task_spec=spec,
                    result=result,
                    conversation_history_length=0,
                )
        except Exception:
            pass
        return orchestration_result_to_message(result, intent=spec.intent)

    def _registered_tool_targets(self) -> set[str]:
        """Return the set of registered tool names (bounded, deterministic)."""
        registry = getattr(self, "_tool_registry", None)
        if registry is None:
            return set()
        try:
            return {tool.name for tool in registry.list()}
        except Exception:
            return set()

    def _development_bridge(self, spec) -> Message:
        """Convert a B2 TaskSpec into a bounded governed-development report.

        Maps ``spec`` through the pure ``task_spec_to_development_need``
        adapter, then delegates to the EXISTING ``run_development_cycle``
        bridge (F9). The result is a short conversational ``Message``; it
        never approves, authorizes, executes, or promotes anything.
        """
        need = task_spec_to_development_need(spec)
        if need is None:
            return Message(
                role="assistant",
                content=(
                    "I could not prepare this as a governed development "
                    "request. Please clarify the objective and success criteria."
                ),
            )

        result = self.run_development_cycle(need)

        lines: list[str] = []
        if result.ok:
            lines.append("Development request accepted for governed preparation.")
            if result.proposal_id:
                lines.append(f"Proposal ID: {result.proposal_id}")
            if result.approval_request_id:
                lines.append(f"Approval Request: {result.approval_request_id}")
            lines.append(f"Status: {result.proposal_status}")
            if result.researched:
                lines.append("Evidence: direct-source research performed.")
            lines.append(
                "Stopped at the human approval boundary (PENDING_APPROVAL). "
                "Nothing is approved, executed, or promoted."
            )
        else:
            lines.append("Development preparation FAILED (fail-closed).")
            for stage, message in result.failures[:5]:
                lines.append(f"- {stage}: {message}")

        return Message(role="assistant", content="\n".join(lines))

    def _development_execution_bridge(
        self,
        session_context,
        proposal: "atlas.evolution.models.EvolutionProposal",
        request: "atlas.evolution.models.ApprovalRequest",
    ) -> Message:
        """Bridge an already-approved conversational proposal into governed execution.

        Persists the live EvolutionProposal and its decided ApprovalRequest into
        the EXISTING EvolutionMemory stores, then delegates to the EXISTING
        ``run_development_execution`` (OWNER-gated, DevelopmentPlanner,
        SelfDevelopmentLoop: sandboxed implementation, pytest verification,
        snapshot/rollback, DevelopmentOutcome).

        This is the single sanctioned seam: the conversation layer resolves and
        validates the real objects; this method owns persistence + execution.
        It never authorizes, never applies directly, and never promotes.
        """
        if proposal is None or request is None:
            raise RuntimeError("Execution requires a proposal and approval request.")

        memory = self._evolution_memory
        if memory is None:
            raise RuntimeError(
                "Evolution memory is not wired; Atlas.start() must run first."
            )

        # Persist the live objects so run_development_execution can resolve them
        # by proposal_id exactly as the F9 track does.
        memory.store_proposal(proposal)
        memory.store_approval_request(request)

        # Delegate to the existing governed development execution path. This
        # re-runs the OWNER authority gate and requires APPROVED status.
        result = self.run_development_execution(session_context, proposal.proposal_id)

        # Preserve the execution evidence on the proposal so the read-only
        # conversational surfaces (recovery, verification, lifecycle report)
        # reconstruct WHAT actually happened instead of a default FAILED
        # stand-in. Metadata is excluded from the proposal fingerprint, so this
        # changes no status, scope, or approval binding.
        self._persist_development_evidence(proposal, result)
        memory.store_proposal(proposal)

        return self._development_execution_message(result)

    @staticmethod
    def _persist_development_evidence(proposal: Any, result: Any) -> None:
        """Record bounded execution evidence on the proposal metadata.

        Fulfills the documented kernel-bridge contract consumed by
        ``ConversationService._RecoveryResultStandin`` and the lifecycle report
        builder: after a governed run the proposal carries the terminal result
        status and the last outcome's evidence, so recovery/verification can
        classify the real failure rather than reconstructing a default FAILED
        stand-in. Evidence only — never mutates the repository, status, scope,
        or approval, and metadata is excluded from the proposal fingerprint.
        """
        metadata = getattr(proposal, "metadata", None)
        if not isinstance(metadata, dict):
            return

        status = getattr(result, "status", None)
        status_name = (
            getattr(status, "name", str(status)) if status is not None else "FAILED"
        )
        outcomes = list(getattr(result, "outcomes", None) or [])
        last = outcomes[-1] if outcomes else None

        last_outcome = {
            "verification_passed": bool(
                getattr(last, "verification_passed", False)
            ),
            "rollback_occurred": bool(getattr(last, "rollback_occurred", False)),
            "test_outcome": str(getattr(last, "test_outcome", "") or ""),
            "message": str(getattr(last, "message", "") or "")[:500],
        }
        metadata["execution"] = {
            "status": (
                "succeeded" if status_name == "SUCCESS" else status_name.lower()
            ),
            "result_status": status_name,
            "iterations_used": int(getattr(result, "iterations_used", 0) or 0),
            "outcomes_count": len(outcomes),
            "message": str(getattr(result, "message", "") or "")[:500],
            # Nested copy for the lifecycle-report reader; the recovery reader
            # (``_RecoveryResultStandin``) reads the top-level key below.
            "last_outcome": dict(last_outcome),
        }
        metadata["last_outcome"] = dict(last_outcome)

        # Phase 4.2 — persist the read-only verification verdict and the
        # diagnosis/recovery evidence so the conversational surfaces can
        # reconstruct WHAT happened, objectively, without a model and without
        # re-running. Metadata only; never mutates the repository, status,
        # scope, or approval.
        verification = getattr(result, "verification", None)
        if verification is not None:
            metadata["verification"] = {
                "status": getattr(
                    getattr(verification, "status", None), "value", ""
                ),
                "iterations_examined": int(
                    getattr(verification, "iterations_examined", 0) or 0
                ),
                "all_tests_passed": getattr(
                    verification, "all_tests_passed", None
                ),
                "any_rollback": bool(
                    getattr(verification, "any_rollback", False)
                ),
                "message": str(getattr(verification, "message", ""))[:500],
            }
        diagnostic = getattr(result, "diagnosis", None)
        if diagnostic is not None:
            metadata["diagnosis"] = {
                "failure_class": getattr(
                    getattr(diagnostic, "failure_class", None), "value", ""
                ),
                "confidence": getattr(
                    getattr(diagnostic, "confidence", None), "value", ""
                ),
                "recoverable": getattr(diagnostic, "recoverable", None),
                "cause": str(getattr(diagnostic, "cause", ""))[:500],
            }
        recovery = getattr(result, "recovery", None)
        if recovery is not None:
            metadata["recovery"] = {
                "recoverable": bool(getattr(recovery, "recoverable", False)),
                "strategy": getattr(
                    getattr(recovery, "strategy", None), "value", ""
                ),
                "rationale": str(getattr(recovery, "rationale", ""))[:500],
            }
        usefulness = getattr(result, "usefulness", None)
        if usefulness is not None:
            to_dict = getattr(usefulness, "to_dict", None)
            if callable(to_dict):
                try:
                    metadata["usefulness"] = dict(to_dict())
                except Exception:
                    pass

    @staticmethod
    def _development_execution_message(result: Any) -> Message:
        """Convert a DevelopmentRunResult into a conversational Message.

        On failure, attaches a structured DiagnosticResult produced by the
        read-only DevelopmentDiagnostic and a RecoveryDecision produced by the
        read-only DevelopmentRecovery, so the conversation layer can surface
        WHY the development failed and whether recovery is appropriate —
        without inventing a root cause or a recovery strategy.
        """
        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
        from atlas.evolution.development_recovery import DevelopmentRecovery

        status = getattr(result, "status", None)
        status_name = getattr(status, "name", str(status)) if status is not None else "unknown"
        iterations = getattr(result, "iterations_used", 0)
        outcomes = getattr(result, "outcomes", None) or []
        message_text = getattr(result, "message", "") or ""

        lines = [f"## Development Execution: {status_name}"]
        if message_text:
            lines.append("")
            lines.append(message_text)
        lines.append("")
        lines.append(f"**Iterations used:** {iterations}")
        lines.append(f"**Outcomes recorded:** {len(outcomes)}")

        # Phase 4.2 — surface the objective verification verdict (read-only).
        verification = getattr(result, "verification", None)
        verification_meta: dict | None = None
        if verification is not None:
            v_status = getattr(getattr(verification, "status", None), "value", "")
            lines.append(f"**Verification:** {v_status}")
            verification_meta = {
                "status": v_status,
                "iterations_examined": int(
                    getattr(verification, "iterations_examined", 0) or 0
                ),
                "all_tests_passed": getattr(
                    verification, "all_tests_passed", None
                ),
                "any_rollback": bool(
                    getattr(verification, "any_rollback", False)
                ),
                "message": str(getattr(verification, "message", ""))[:500],
            }

        exec_status = "succeeded" if status_name == "SUCCESS" else status_name.lower()

        # On failure, attach a structured, evidence-backed diagnosis and a
        # recovery decision. Both are read-only and fail-closed.
        diagnostic_meta: dict | None = None
        recovery_meta: dict | None = None
        if status_name != "SUCCESS":
            diagnostic = DevelopmentDiagnostic().diagnose(result)
            recovery = DevelopmentRecovery().decide(result, diagnostic)

            lines.append("")
            lines.append(f"**Diagnosis:** {diagnostic.failure_class.value}")
            lines.append(f"**Confidence:** {diagnostic.confidence.value}")
            lines.append(f"**Cause:** {diagnostic.cause}")
            if diagnostic.evidence:
                lines.append(f"**Evidence:** {diagnostic.evidence}")

            lines.append("")
            lines.append(f"**Recoverable:** {'yes' if recovery.recoverable else 'no'}")
            lines.append(f"**Recovery strategy:** {recovery.strategy.value}")
            lines.append(f"**Rationale:** {recovery.rationale}")

            diagnostic_meta = {
                "failure_class": diagnostic.failure_class.value,
                "confidence": diagnostic.confidence.value,
                "cause": diagnostic.cause,
                "evidence": diagnostic.evidence,
                "recoverable": diagnostic.recoverable,
            }
            recovery_meta = {
                "recoverable": recovery.recoverable,
                "strategy": recovery.strategy.value,
                "rationale": recovery.rationale,
                "evidence": recovery.evidence,
            }

        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={
                "execution": {
                    "status": exec_status,
                    "result_status": status_name,
                    "iterations_used": iterations,
                    "outcomes_count": len(outcomes),
                },
                "diagnostic": diagnostic_meta,
                "verification": verification_meta,
            },
        )

    # ------------------------------------------------------------------
    # Conversational autonomy boundary (conversation -> kernel -> evolution)
    # ------------------------------------------------------------------

    # Level -> (max risk, execution level). Identical to the parameters the
    # conversation handlers previously built inline.
    _AUTONOMY_POLICY_BY_LEVEL: dict[int, tuple[Any, Any]] = {
        1: (RiskLevel.LOW, ExecutionLevel.SANDBOXED),
        2: (RiskLevel.MEDIUM, ExecutionLevel.CODE_ARTIFACT),
        3: (RiskLevel.HIGH, ExecutionLevel.SELF_CONFIG),
        4: (RiskLevel.CRITICAL, ExecutionLevel.INFORMATION),
        5: (RiskLevel.CRITICAL, ExecutionLevel.AUTONOMOUS),
    }

    @staticmethod
    def _approved_placeholder() -> Any:
        """Build the placeholder object the L2-L5 autonomy checks require.

        Mirrors the inline placeholder the conversation handlers previously
        constructed: an object whose ``status.name`` is ``APPROVED``.
        """
        return type("_P", (), {"status": type("S", (), {"name": "APPROVED"})()})()

    def _autonomy_check(
        self,
        proposal: Any,
        session_context: Any,
        *,
        level: int,
    ) -> Any:
        """Perform an L1-L5 autonomy check on behalf of the conversation layer.

        This is the kernel-owned boundary. The conversation layer never
        constructs evolution autonomy machinery directly; it asks the kernel
        for a decision, preserving the dependency direction:

            conversation -> injected boundary -> kernel -> evolution

        Policy parameters per level are identical to those the conversation
        handlers previously constructed inline (L1 LOW/SANDBOXED,
        L2 MEDIUM/CODE_ARTIFACT, L3 HIGH/SELF_CONFIG, L4 CRITICAL/INFORMATION,
        L5 CRITICAL/AUTONOMOUS). For L1 the real ``proposal`` is checked;
        L2-L5 reproduce the handlers' placeholder inputs exactly.
        """
        try:
            risk_level, execution_level = self._AUTONOMY_POLICY_BY_LEVEL[level]
        except KeyError:
            raise ValueError(f"Unknown autonomy level: {level}")

        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CODE],
            max_risk_level=risk_level,
            effective_execution_level=execution_level,
            requires_user_approval_scopes=[],
            max_requests_per_window=10,
            authorization_ttl_minutes=60,
        )
        policy_engine = AutonomyPolicyEngine(policy=policy)
        auth_manager = AuthorizationManager(policy=policy)
        controller = AutonomyController(
            authorization_manager=auth_manager,
            policy_engine=policy_engine,
        )

        if level == 1:
            return controller.check_execution_autonomy(
                proposal=proposal,
                session_context=session_context,
            )
        if level == 2:
            return controller.check_medium_risk_autonomy(
                proposal=self._approved_placeholder(),
                session_context=session_context,
            )
        if level == 3:
            return controller.check_high_risk_autonomy(
                proposal=self._approved_placeholder(),
                session_context=session_context,
            )
        if level == 4:
            return controller.check_critical_risk_autonomy(
                proposal=self._approved_placeholder(),
                session_context=session_context,
            )
        if level == 5:
            objectives = [self._approved_placeholder() for _ in range(2)]
            return controller.check_cross_objective_coordination_autonomy(
                objectives=objectives,
                session_context=session_context,
            )
        raise ValueError(f"Unknown autonomy level: {level}")

    # ------------------------------------------------------------------
    # Phase F11: Long-Term Self-Management Review (manually invoked)
    # ------------------------------------------------------------------

    def _init_self_management_review(self) -> None:
        """Phase F11 (post-Core): additively wire the self-management review.

        Composes the EXISTING EvolutionMemory, LearningMemory, ScheduleStore,
        and F10 availability tracker as read-only evidence sources. The review
        never runs from ``tick()``, never persists anything, and never
        approves, authorizes, executes, or promotes.
        """
        learning_memory = getattr(self._learning_engine, "memory", None)
        self._self_management_review = SelfManagementReview(
            evolution_memory=self._evolution_memory,
            learning_memory=learning_memory,
            schedule_store=self._schedule_store,
            availability=self._ai_availability,
        )

    def _init_proactive_advisor(self) -> None:
        """P5: additively wire the proactive advisor.

        Composes the EXISTING F1/F10/F11 signals and the B3.x/P4 seams into
        one bounded, principal-scoped advisory report. Each dependency is
        optional; missing seams degrade to a report with no items from that
        source. Never auto-runs; never invokes a tool, capability,
        orchestration, development, governance, approval, or promotion path
        directly. Kernel-private (not registered in the ServiceContainer
        because the container key-set is exact-set-tested).
        """
        try:
            from atlas.advisory.advisor import ProactiveAdvisor

            self._proactive_advisor = ProactiveAdvisor(
                environment_observer=self._environment_observer,
                availability=self._ai_availability,
                self_management_review=self._self_management_review,
                interaction_bridge=getattr(
                    self, "_interaction_learning_bridge", None
                ),
                collective_governance=getattr(self, "_collective_governance", None),
            )
        except Exception:
            self._proactive_advisor = None

    def _require_development_authority(
        self, session_context, action: str, *, allow_envelope: bool = False
    ) -> None:
        """Fail-closed OWNER authorization for a development action.

        Resolves the acting identity through the EXISTING authoritative
        session model (SessionManager + SessionContext), never through a
        caller-supplied principal id. The SessionManager only contains
        sessions created through AuthorityService, so a fabricated, missing,
        or conflicting identity is rejected before any OWNER check:

          * missing/unknown session context -> fail closed
          * unknown session id in SessionManager -> fail closed
          * principal/session mismatch -> fail closed
          * principal resolved by AuthorityService -> assert OWNER

        Raises (fail-closed) on missing/mismatched identity or insufficient
        authority.

        Phase 5.2: when ``allow_envelope`` is True and the action is the
        sandbox-only ``execution`` action, a valid bounded Development Envelope
        may authorize it instead of an OWNER session. Promotion and every other
        action remain OWNER-only — the envelope can NEVER authorize them.
        """
        if allow_envelope and action == "execution":
            authority = getattr(self, "_development_authority", None)
            if authority is not None:
                decision = authority.check("sandbox_development")
                if decision.allowed:
                    return
        if session_context is None:
            raise RuntimeError(
                "Development action requires an active session context "
                "(fail-closed)."
            )
        manager = getattr(self, "_session_manager", None)
        authority = getattr(self, "_authority_service", None)
        if manager is None or authority is None:
            raise RuntimeError(
                "Session/authority services are not wired; Atlas.start() must "
                "run first."
            )
        session_id = getattr(session_context, "session_id", "")
        if not isinstance(session_id, str) or not session_id.strip():
            raise RuntimeError(
                "Development action requires an active session (fail-closed)."
            )
        session = manager.get(session_id)
        if session is None:
            raise RuntimeError(
                f"Unknown session '{session_id}' for development {action} "
                "(fail-closed)."
            )
        # The session is immutable and was created by SessionManager from a
        # resolved Principal. Re-resolve through AuthorityService and reject
        # any mismatch between the caller's context and the authoritative
        # session so a conflicting identity claim can never be honored.
        principal_id = session.principal_id
        if getattr(session_context, "principal_id", "") != principal_id:
            raise RuntimeError(
                f"Mismatched session/principal for development {action} "
                "(fail-closed)."
            )
        if authority.resolve(principal_id) is None:
            raise RuntimeError(
                f"Unknown principal '{principal_id}' for development {action} "
                "(fail-closed)."
            )
        decision = authority.assert_owner(principal_id, action=action)
        if decision.denied:
            raise RuntimeError(
                f"Development {action} denied for principal '{principal_id}': "
                f"{decision.reason or 'owner authority required'}"
            )

    def confirm_development_approval(
        self, session_context, proposal_id: str, comment: str = ""
    ):
        """Explicit human confirmation of a persisted development proposal.

        Operational Maturity track — the cross-process human gate for F9
        proposals. Composes EXISTING machinery only:

          * AUTHORIZES the acting identity resolved from ``session_context``
            through the EXISTING SessionManager + AuthorityService
            (OWNER-only), BEFORE any status transition,
          * loads the persisted PENDING_APPROVAL proposal from
            EvolutionMemory (restored from EvolutionSQLiteStorage),
          * locates its pending ApprovalRequest,
          * records the explicit decision via the EXISTING ApprovalManager
            two-step contract (``approve`` +
            ``update_proposal_from_decision``),
          * persists APPROVED via ``update_proposal_status``.

        Never executes, schedules, or promotes anything; sandbox execution of
        the approved proposal happens separately via
        ``run_development_execution()``. Fail-closed on authorization failure,
        missing proposals, wrong states, or missing pending requests.
        """
        # P7.6 — authorization boundary BEFORE the PENDING_APPROVAL status
        # transition. Only the Owner may approve; the check trusts the
        # authoritative session-resolved principal, never a caller-supplied id.
        self._require_development_authority(session_context, action="approval")

        memory = self._evolution_memory
        manager = self._approval_manager
        if memory is None or manager is None:
            raise RuntimeError(
                "Evolution approval surfaces are not wired; Atlas.start() "
                "must run first."
            )

        proposal = memory.get_proposal(proposal_id)
        if proposal is None:
            raise RuntimeError(
                f"Proposal '{proposal_id}' not found."
            )
        status_name = getattr(proposal.status, "name", "")
        if status_name != "PENDING_APPROVAL":
            raise RuntimeError(
                f"Proposal '{proposal_id}' is {status_name}, not "
                "PENDING_APPROVAL — refusing to confirm."
            )

        pending = [
            req
            for req in memory.get_all_approval_requests()
            if req.proposal_id == proposal_id
            and getattr(req.decision, "name", "") == "PENDING"
        ]
        if not pending:
            raise RuntimeError(
                f"Proposal '{proposal_id}' has no pending approval request."
            )

        manager.approve(pending[0], comment=comment)
        manager.update_proposal_from_decision(proposal, pending[0])
        memory.update_proposal_status(proposal_id, ProposalStatus.APPROVED)
        return proposal

    def run_development_execution(
        self, session_context, proposal_id: str, *, allow_envelope: bool = False
    ):
        """Execute an APPROVED, persisted development proposal.

        P7.6 — AUTHORIZES the acting identity resolved from
        ``session_context`` through the EXISTING SessionManager +
        AuthorityService (OWNER-only) BEFORE loading or executing anything.

        Loads the proposal from EvolutionMemory, requires APPROVED state,
        then runs the EXISTING DevelopmentPlanner + SelfDevelopmentLoop path
        (disposable CodeSandbox, pytest verification, DevelopmentOutcome,
        LearningMemory evidence). Read-only with respect to the real
        repository; never approves/authorizes/promotes anything.
        """
        # P7.6 — authorization boundary BEFORE any execution. Phase 5.2 adds the
        # bounded Development Envelope as an ALTERNATIVE authority for the
        # sandbox-only execution action only (never for promotion).
        self._require_development_authority(
            session_context, action="execution", allow_envelope=allow_envelope
        )

        memory = self._evolution_memory
        planner = self._development_planner
        loop = self._self_development_loop
        if memory is None or planner is None or loop is None:
            raise RuntimeError(
                "Development execution surfaces are not wired; Atlas.start() "
                "must run first."
            )

        proposal = memory.get_proposal(proposal_id)
        if proposal is None:
            raise RuntimeError(f"Proposal '{proposal_id}' not found.")
        status_name = getattr(proposal.status, "name", "")
        if status_name not in ("APPROVED", "SANDBOX_AUTHORIZED"):
            raise RuntimeError(
                f"Proposal '{proposal_id}' is {status_name}, not APPROVED — "
                "only explicitly approved proposals may be executed."
            )
        if status_name == "SANDBOX_AUTHORIZED":
            # The bounded envelope path must present a valid, fingerprint-bound
            # authorization; the OWNER APPROVED path does not.
            authorization = self._development_authorizations.get(proposal_id)
            if authorization is None or not authorization.is_valid_for(proposal):
                raise RuntimeError(
                    f"Proposal '{proposal_id}' has no valid sandbox authorization."
                )

        plan = planner.plan(proposal)
        result = loop.run(proposal)

        # Phase 4.2 — objective verification of the run. The read-only
        # DevelopmentVerification report is attached to the result so the
        # governed execution path (and every caller) carries an explicit,
        # evidence-backed verification verdict. Fail-soft: verification never
        # changes the run outcome, never mutates the repository, and never
        # requires a model.
        try:
            from atlas.evolution.development_verification import (
                DevelopmentVerification,
            )

            result.verification = DevelopmentVerification().verify(result)
        except Exception:
            pass

        # Phase 5.2 — deterministic, EVIDENCE-BASED usefulness assessment
        # (objective + capability improvement + regression + verification).
        # Attached to the result so the governed path carries a structured
        # judgment rather than a bare numeric proxy. Fail-soft; model-free.
        try:
            from atlas.evolution.development_usefulness import assess_usefulness

            v_status = getattr(
                getattr(result.verification, "status", None), "value", ""
            )
            run_status = getattr(getattr(result, "status", None), "name", "")
            result.usefulness = assess_usefulness(
                proposal_id=proposal_id,
                objective=str(getattr(proposal, "expected_benefit", "") or ""),
                verification_status=v_status,
                capability_present_before=None,
                capability_present_after=(v_status == "verified"),
                regression_detected=(run_status not in ("", "SUCCESS")),
                evidence_count=len(getattr(result, "outcomes", ()) or ()),
            )
        except Exception:
            pass

        # Phase 4.3 — persist the lifecycle evidence (verification/diagnosis/
        # recovery) on the proposal from THIS entry point too, so the CLI and
        # conversation paths produce coherent, inspectable outcomes. The
        # conversational bridge persists as well; the write is idempotent
        # metadata-only and never mutates the repository, status, or approval.
        try:
            self._persist_development_evidence(proposal, result)
            memory.store_proposal(proposal)
        except Exception:
            pass

        # Phase 5.2 (G-B) — retention → reuse. Persist a bounded "development"
        # EvolutionRecord ONLY for VERIFIED successes (never failed/unverified
        # work), carrying the authoritative usefulness summary, so the existing
        # ``_evolution_context_snapshot`` → DecisionIntelligenceEngine/planning
        # path can retrieve and use the retained development experience. Reuses
        # the existing memory + record builder; no new subsystem. Fail-soft.
        try:
            verified = (
                getattr(
                    getattr(getattr(result, "verification", None), "status", None),
                    "value",
                    "",
                )
                == "verified"
            )
            succeeded = (
                getattr(getattr(result, "status", None), "name", "") == "SUCCESS"
            )
            if verified and succeeded and memory is not None:
                record = self._build_development_record(proposal, result)
                if record is not None:
                    usefulness = getattr(result, "usefulness", None)
                    to_dict = getattr(usefulness, "to_dict", None)
                    if callable(to_dict):
                        try:
                            record.metadata["usefulness"] = dict(to_dict())
                        except Exception:
                            pass
                    memory.store_record(record)
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # Phase 5.2 — Direct Atlas Evolution (bounded; opt-in)
    # ------------------------------------------------------------------

    @property
    def development_envelope(self):
        """Return the bounded Development Envelope policy (read-only)."""
        return self._development_envelope

    @property
    def development_authority(self):
        """Return the kernel-owned DevelopmentAuthority (read-only)."""
        return self._development_authority

    def authorize_development_execution(self, proposal_id: str):
        """Authorize SANDBOX execution via the bounded Development Envelope.

        Sets ``ProposalStatus.SANDBOX_AUTHORIZED`` (NOT ``APPROVED``) and
        records a fingerprint-bound ``DevelopmentAuthorization(mode=ENVELOPE)``.
        It NEVER authorizes promotion and never touches the live repository.
        """
        authority = self._development_authority
        if authority is None:
            raise RuntimeError(
                "Development authority is not wired; Atlas.start() must run first."
            )
        memory = self._evolution_memory
        proposal = memory.get_proposal(proposal_id) if memory is not None else None
        if proposal is None:
            raise RuntimeError(f"Proposal '{proposal_id}' not found.")
        status_name = getattr(proposal.status, "name", "")
        if status_name not in ("DRAFT", "PENDING_APPROVAL"):
            raise RuntimeError(
                f"Proposal '{proposal_id}' is {status_name}; only DRAFT/"
                "PENDING_APPROVAL proposals may receive a sandbox authorization."
            )
        decision = authority.check("sandbox_development")
        if not decision.allowed:
            raise RuntimeError(f"Development envelope denied: {decision.reason}")
        authorization = authority.authorize(proposal)
        if authorization is None:
            raise RuntimeError("Development envelope declined to authorize.")

        self._development_envelope_usage += 1
        self._development_authorizations[proposal_id] = authorization
        proposal.status = ProposalStatus.SANDBOX_AUTHORIZED
        try:
            memory.store_proposal(proposal)
        except Exception:
            pass
        self._record_development_authorization_audit(proposal, authorization)
        return authorization

    def _record_development_authorization_audit(self, proposal, authorization) -> None:
        """Best-effort audit of a granted development authorization."""
        try:
            memory = self._evolution_memory
            if memory is None:
                return
            from atlas.evolution.models import EvolutionRecord

            memory.store_record(
                EvolutionRecord(
                    record_id=f"devauth:{authorization.authorization_id}",
                    event_type="development.authorization",
                    description=(
                        f"{authorization.mode.value} development authorization "
                        f"for {getattr(proposal, 'proposal_id', '')}"
                    ),
                    related_ids=[getattr(proposal, "proposal_id", "")],
                    metadata=authorization.to_dict(),
                )
            )
        except Exception:
            pass

    @staticmethod
    def _promotion_repo_root():
        """The live repository root a promotion would target."""
        from pathlib import Path

        return Path(__file__).resolve().parents[2]

    def _registered_capability_names(self) -> tuple[str, ...]:
        """Names registered on the EXISTING capability registry (bounded, read-only)."""
        names: list[str] = []
        try:
            registry = getattr(self, "_capability_registry", None)
            names.extend(list(getattr(registry, "registered_names", ()) or ()))
        except Exception:
            pass
        return tuple(name for name in names if name)

    def _pending_approval_request_id(self, proposal_id: str) -> str:
        """The EXISTING ApprovalManager's pending request id for ``proposal_id``.

        Read-only lookup over the existing pending requests; returns ``""`` when there is
        none. Never creates, approves, or mutates anything.
        """
        if not proposal_id:
            return ""
        try:
            requests = self._evolution_memory.get_pending_approval_requests()
        except Exception:
            return ""
        for request in tuple(requests or ()):
            if str(getattr(request, "proposal_id", "") or "") == str(proposal_id):
                return str(getattr(request, "request_id", "") or "")
        return ""

    def _development_driver_bridge(self, spec) -> Message:
        """G3 — route a conversational development request through the EXISTING driver.

        The bounded ``DevelopmentDriver`` is the governed self-development orchestrator
        (gap assessment -> bounded research -> need -> authoring -> cycle ->
        envelope-authorized sandbox execution -> verification -> usefulness ->
        promotion-request preparation). This seam is the conversational entry point the
        documented gap calls for; the kernel API and ``atlas postcore drive`` are unchanged.

        Authoring content is derived DETERMINISTICALLY from the request's own words through
        the existing scaffold specification contract; when the request names no capability
        nothing is invented and the driver's own honest terminal is reported. The report
        states only what the driver actually did: it never claims an approval, an execution
        outside the bounded Development Envelope, or a promotion.
        """
        from atlas.evolution.development_request_scaffold import (
            scaffold_spec_for_request,
        )

        need = task_spec_to_development_need(spec)
        if need is None:
            return Message(
                role="assistant",
                content=(
                    "I could not prepare this as a governed development "
                    "request. Please clarify the objective and success criteria."
                ),
            )

        request = str(
            getattr(spec, "intent", "") or getattr(spec, "goal", "") or need.title
        ).strip()
        metadata: dict[str, Any] = {}
        scaffold = scaffold_spec_for_request(
            request, registered_names=self._registered_capability_names()
        )
        if scaffold is not None:
            metadata["scaffold"] = scaffold

        result = self.run_development_driver(request, metadata=metadata or None)

        lines = [
            "Governed self-development request routed through the existing "
            "DevelopmentDriver (deterministic; no external AI model used):",
            f"- Outcome: {result.terminal.value}",
        ]
        if result.detail:
            lines.append(f"- Detail: {result.detail}")
        status = ""
        if result.proposal_id:
            lines.append(f"- Proposal ID: {result.proposal_id}")
            try:
                proposal = self._evolution_memory.get_proposal(result.proposal_id)
                raw_status = getattr(proposal, "status", None)
                status = str(
                    getattr(raw_status, "name", "")
                    or getattr(raw_status, "value", "")
                    or ""
                )
            except Exception:
                status = ""
            if status:
                lines.append(f"- Status: {status}")
            approval_request_id = self._pending_approval_request_id(result.proposal_id)
            if approval_request_id:
                lines.append(f"- Approval Request: {approval_request_id}")
        if result.authorization_id:
            lines.append(f"- Sandbox authorization: {result.authorization_id}")
        if result.execution_status:
            lines.append(f"- Execution: {result.execution_status}")
        if result.verification_status:
            lines.append(f"- Verification: {result.verification_status}")
        outcome = getattr(getattr(result, "usefulness", None), "outcome", "")
        if outcome:
            lines.append(f"- Usefulness: {outcome}")
        if result.promotion_request_id:
            lines.append(f"- Promotion Request: {result.promotion_request_id}")
        for stage, failure in tuple(result.failures)[:5]:
            lines.append(f"- {stage}: {failure}")
        lines.append(
            "Nothing is approved, executed, or promoted; promotion requires "
            "explicit OWNER authorization."
        )
        return Message(
            role="assistant",
            content="\n".join(lines),
            metadata={"development_driver": result.to_dict()},
        )

    def _ensure_development_driver(self):
        """Build (once) the bounded DevelopmentDriver from kernel surfaces."""
        if self._development_driver is not None:
            return self._development_driver
        controller = self._development_controller
        if controller is None:
            return None
        from atlas.evolution.development_driver import DevelopmentDriver
        from atlas.evolution.development_gap import assess_development_gap
        from atlas.evolution.development_usefulness import assess_usefulness

        kernel = self

        def _capability_names() -> tuple[str, ...]:
            return kernel._registered_capability_names()

        def _knowledge_retriever():
            try:
                from atlas.research.validated_retrieval import (
                    ValidatedKnowledgeRetriever,
                )

                return ValidatedKnowledgeRetriever(kernel._research_storage)
            except Exception:
                return None

        def _gap(request: str):
            return assess_development_gap(
                request,
                capability_names=_capability_names(),
                knowledge_retriever=_knowledge_retriever(),
            )

        def _executor(proposal):
            # Register the bounded envelope authorization (SANDBOX_AUTHORIZED)
            # then execute sandbox-only development under it.
            kernel.authorize_development_execution(proposal.proposal_id)
            return kernel.run_development_execution(
                None, proposal.proposal_id, allow_envelope=True
            )

        def _promotion_preparer(proposal, run_result):
            return kernel._prepare_promotion_request(proposal, run_result)

        driver = DevelopmentDriver(
            gap_assessor=_gap,
            cycle_runner=controller.run_development_cycle,
            executor=_executor,
            authority=self._development_authority,
            researcher=(
                self._acquisition_service.acquire
                if self._acquisition_service is not None
                else None
            ),
            usefulness_fn=assess_usefulness,
            promotion_preparer=_promotion_preparer,
        )
        self._development_driver = driver
        return driver

    def run_development_driver(self, request: str, metadata=None):
        """Drive ONE bounded direct-evolution invocation for ``request``.

        Orchestration only; never runs from ``tick()``; never promotes.
        """
        driver = self._ensure_development_driver()
        if driver is None:
            raise RuntimeError(
                "Development driver is not wired; Atlas.start() must run first."
            )
        return driver.drive(request, metadata=metadata)

    def _ensure_promotion_executor(self):
        """Build (once) the OWNER-only transactional PromotionExecutor."""
        if self._promotion_executor is not None:
            return self._promotion_executor
        from atlas.evolution.promotion_executor import PromotionExecutor

        self._promotion_executor = PromotionExecutor(
            self._promotion_repo_root(),
            version_recorder=self._record_promotion_version,
            audit_recorder=self._record_promotion_audit,
            activator=self._activate_promoted_capability,
        )
        return self._promotion_executor

    def _activate_promoted_capability(self, artifact):
        """Bounded capability activation after an OWNER-authorized promotion.

        Runs only inside ``promote_validated_change`` (OWNER-gated); the
        Development Envelope can never reach this path. Raises on any
        malformed/invalid declared capability so the executor fails closed.

        Step 2 — after a successful activation the EXISTING self-knowledge
        inputs are refreshed so the promoted capability is not left as a bare,
        unattributed registry name (see
        :meth:`_refresh_self_knowledge_after_activation`).
        """
        from atlas.evolution.capability_activation import CapabilityActivator

        activator = CapabilityActivator(
            self._promotion_repo_root(),
            self._capability_registry,
            audit_recorder=self._record_activation_audit,
        )
        activation = activator.activate(artifact)
        self._refresh_self_knowledge_after_activation(artifact, activation)
        return activation

    def _refresh_self_knowledge_after_activation(self, artifact, activation) -> dict:
        """Project an activated capability into the EXISTING self-knowledge inputs.

        Reuses the existing ``project_evolved_capability`` projection: the
        promoting module is registered as the HEALTHY provider component so the
        capability model reports it honestly (deterministic dependency,
        availability) instead of an unattributed ``UNKNOWN`` name. The cached
        repository map is then refreshed so the new module becomes visible to the
        architecture model. Never grants authority, never promotes, and is
        fail-soft (activation has already succeeded, so a projection problem must
        not fail an OWNER-approved promotion closed on a cosmetic step).
        """
        summary: dict[str, Any] = {
            "projected": [],
            "repository_map_refreshed": False,
        }
        try:
            if not getattr(activation, "activated", False):
                return summary
            capabilities = tuple(getattr(activation, "capabilities", ()) or ())
            if not capabilities:
                return summary
            from atlas.evolution.self_evolution import project_evolved_capability

            modules = self._activation_code_modules(artifact)
            for capability in capabilities:
                module = self._activation_module_for_capability(artifact, modules, capability)
                if module is None:
                    continue
                if project_evolved_capability(
                    self._component_registry,
                    module_path=module,
                    capability_name=capability,
                ) is not None:
                    summary["projected"].append(capability)
            try:
                if self._repository_map is not None:
                    self.refresh_repository_map()
                    summary["repository_map_refreshed"] = True
            except Exception:
                pass
            self._record_self_knowledge_refresh(summary)
        except Exception:
            pass
        return summary

    @staticmethod
    def _activation_code_modules(artifact) -> tuple[str, ...]:
        """Repository-relative non-test ``.py`` paths carried by an artifact."""
        paths: list[str] = []
        for entry in tuple(getattr(artifact, "files", ()) or ()):
            path = str(getattr(entry, "path", "") or "").replace("\\", "/")
            if path.endswith(".py") and not path.startswith("tests/"):
                paths.append(path)
        return tuple(paths)

    @staticmethod
    def _activation_module_for_capability(artifact, modules, capability) -> str | None:
        """The artifact module that declares ``capability`` (bounded; else first)."""
        for entry in tuple(getattr(artifact, "files", ()) or ()):
            path = str(getattr(entry, "path", "") or "").replace("\\", "/")
            if path not in modules:
                continue
            content = str(getattr(entry, "post_content", "") or "")
            if "CAPABILITY_NAME" in content and capability in content:
                return path
        return modules[0] if modules else None

    def _record_self_knowledge_refresh(self, summary: dict) -> None:
        """Best-effort audit record for a post-activation self-knowledge refresh."""
        try:
            projected = tuple(summary.get("projected") or ())
            if not projected:
                return
            memory = self._evolution_memory
            if memory is None:
                return
            from atlas.evolution.models import EvolutionRecord

            memory.store_record(
                EvolutionRecord(
                    record_id="capselfknow:" + "--".join(projected)[:80],
                    event_type="capability_self_knowledge_refresh",
                    description=(
                        "Projected activated capabilities into the self-knowledge "
                        "inputs: " + ", ".join(projected)
                    ),
                    related_ids=list(projected),
                    metadata=dict(summary),
                )
            )
        except Exception:
            pass

    def _record_activation_audit(self, activation) -> str:
        """Best-effort activation audit record (existing memory architecture)."""
        try:
            memory = self._evolution_memory
            if memory is None:
                return ""
            from atlas.evolution.models import EvolutionRecord

            capabilities = tuple(getattr(activation, "capabilities", ()) or ())
            record_id = "capactivation:" + "--".join(capabilities)[:80]
            memory.store_record(
                EvolutionRecord(
                    record_id=record_id,
                    event_type="capability_activation",
                    description=(
                        "Activated promoted capability: "
                        + (", ".join(capabilities) or "(none)")
                    ),
                    related_ids=list(capabilities),
                    metadata=getattr(activation, "to_dict", lambda: {})(),
                )
            )
            return record_id
        except Exception:
            return ""

    @property
    def capability_registry(self):
        """Return the kernel-owned CapabilityRegistry (runtime, read-only)."""
        return self._capability_registry

    @property
    def capability_dispatcher(self):
        """Return the kernel-owned CapabilityDispatcher (normal invocation path)."""
        return self._capability_dispatcher

    def _record_promotion_audit(self, artifact) -> str:
        """Best-effort audit record for a promoted changeset."""
        try:
            memory = self._evolution_memory
            if memory is None:
                return ""
            from atlas.evolution.models import EvolutionRecord

            record_id = f"promoaudit:{getattr(artifact, 'artifact_id', '')}"
            memory.store_record(
                EvolutionRecord(
                    record_id=record_id,
                    event_type="development_promotion",
                    description=(
                        f"Promoted changeset for proposal "
                        f"{getattr(artifact, 'proposal_id', '')}"
                    ),
                    related_ids=[getattr(artifact, "proposal_id", "")],
                    metadata=getattr(artifact, "to_dict", lambda: {})(),
                )
            )
            return record_id
        except Exception:
            return ""

    def _record_promotion_version(self, artifact) -> str:
        """Record a real CODE version for a promoted changeset.

        Reuses the EXISTING ``VersionManager`` (no parallel versioning
        subsystem): it builds a CODE-scoped ``EvolutionRequest`` +
        ``ChangeReceipt`` from the promoted changeset and calls
        ``record_version``, returning the resulting manifest id. Raises on any
        failure so the executor fails the promotion closed rather than
        reporting a false success.
        """
        storage = self._autonomy_storage
        if storage is None:
            raise RuntimeError(
                "autonomy storage is unavailable; cannot record a CODE version"
            )
        from atlas.evolution.autonomy.models import (
            ChangeReceipt,
            EvolutionRequest,
        )
        from atlas.evolution.autonomy.version_manager import VersionManager
        from atlas.evolution.governance.models import ScopeType

        files = tuple(getattr(artifact, "files", ()) or ())
        if not files:
            raise RuntimeError("promotion artifact carries no files to version")
        request_id = f"promo:{getattr(artifact, 'artifact_id', '')}"
        request = EvolutionRequest(
            request_id=request_id,
            source=f"promotion:{getattr(artifact, 'proposal_id', '')}",
            target_scope=ScopeType.CODE,
            change_payload={
                "code_changes": [
                    {"path": entry.path, "content": entry.post_content}
                    for entry in files
                ]
            },
            metadata={"kind": "development_promotion"},
        )
        receipt = ChangeReceipt(
            request_id=request_id,
            changed_keys=[entry.path for entry in files],
            before_refs={
                entry.path: (
                    entry.pre_hash if entry.pre_state is not None else "ABSENT"
                )
                for entry in files
            },
            after_refs={entry.path: entry.post_hash for entry in files},
            version_delta="+0.0.1",
            target_tags=["code", "promotion"],
        )
        version = VersionManager(storage=storage).record_version(request, receipt)
        return str(getattr(version, "manifest_id", "") or "")

    def _prepare_promotion_request(self, proposal, run_result):
        """Capture the artifact and open a promotion review (no mutation)."""
        gate = self._promotion_gate
        if gate is None:
            raise RuntimeError("Promotion gate is not wired.")
        from atlas.evolution.promotion_artifact import capture_promotion_artifact
        from atlas.evolution.promotion_gate import build_change_manifest

        metadata = getattr(proposal, "metadata", None) or {}
        changes = metadata.get("code_changes", [])
        if not changes:
            # The driver may pass a lightweight proposal stand-in; resolve the
            # persisted proposal (which carries the authored changes).
            memory = self._evolution_memory
            if memory is not None:
                try:
                    persisted = memory.get_proposal(
                        getattr(proposal, "proposal_id", "")
                    )
                except Exception:
                    persisted = None
                if persisted is not None:
                    proposal = persisted
                    metadata = getattr(proposal, "metadata", None) or {}
                    changes = metadata.get("code_changes", [])
        if not changes:
            raise RuntimeError("proposal carries no code changes to promote")
        artifact = capture_promotion_artifact(
            changes,
            proposal_id=getattr(proposal, "proposal_id", ""),
            repo_root=self._promotion_repo_root(),
        )
        assessment = gate.assess(
            run_result,
            proposal_id=getattr(proposal, "proposal_id", ""),
            change_manifest=build_change_manifest(changes),
        )
        request = gate.request_review(assessment)
        self._promotion_artifacts[request.request_id] = {
            "artifact": artifact,
            "request": request,
            "assessment": assessment,
            "proposal_id": getattr(proposal, "proposal_id", ""),
        }
        return request.request_id

    def approve_promotion_review(
        self, session_context, request_id: str, comment: str = ""
    ):
        """OWNER-only approval of a pending promotion review (no mutation)."""
        self._require_development_authority(session_context, action="promotion_approval")
        entry = self._promotion_artifacts.get(request_id)
        if entry is None:
            raise RuntimeError(f"Promotion review '{request_id}' not found.")
        request = entry["request"]
        return self._promotion_gate.approve(request, comment=comment)

    def promote_validated_change(self, session_context, request_id: str):
        """OWNER-only, transactional promotion of a validated changeset."""
        self._require_development_authority(session_context, action="promotion")
        entry = self._promotion_artifacts.get(request_id)
        if entry is None:
            raise RuntimeError(f"Promotion review '{request_id}' not found.")
        request = entry["request"]
        status = getattr(getattr(request, "status", None), "value", "")
        if status != "approved":
            raise RuntimeError(
                f"Promotion review '{request_id}' is {status or 'unknown'}, "
                "not approved — refusing to promote."
            )
        executor = self._ensure_promotion_executor()
        result = executor.promote(entry["artifact"], authorized=True)
        if result.ok:
            try:
                from atlas.evolution.promotion_gate import PromotionStatus

                request.status = PromotionStatus.PROMOTED
            except Exception:
                pass
        return result

    @property
    def self_management_review(self):
        """Return the kernel-owned SelfManagementReview (Phase F11)."""
        return self._self_management_review

    def run_self_management_review(self):
        """Manually trigger ONE bounded long-term self-management review.

        Aggregates durable evidence (evolution records, learning signals,
        request queues, provider availability) into a bounded, deterministic,
        JSON-safe report. Read-only: nothing is approved, authorized,
        executed, promoted, or persisted here. Flagged maintenance needs are
        inert evidence for the EXISTING F6/F9 governance flows.
        """
        if self._self_management_review is None:
            raise RuntimeError(
                "Self-management review is not wired; Atlas.start() must "
                "run first."
            )
        return self._self_management_review.run_review()

    @property
    def proactive_advisor(self):
        """Return the kernel-owned ProactiveAdvisor (P5)."""
        return self._proactive_advisor

    def run_proactive_advisory(self, principal_id: str = ""):
        """Manually trigger ONE bounded proactive advisory report (P5).

        Composes the EXISTING F1/F10/F11 signals and the B3.x/P4 seams into
        a bounded, principal-scoped, JSON-safe advisory report. Each
        ``AdvisoryItem`` is INERT — the report's ``suggested_action`` is a
        bounded hint naming an existing governed path; the advisor never
        invokes a tool, capability, orchestration, development, governance,
        approval, or promotion boundary directly.

        Owner / User authority is preserved: the report carries the
        ``requires_owner`` flag per item; a USER never receives an item whose
        suggested action names an OWNER-only governed path (the bridge
        filters these out at the CLI surface; the underlying seam is
        preserved for Owner-only presentation).

        Args:
            principal_id: The principal to scope the report to. Required for
                principal-scoped sources (B3.x interaction bridge).

        Returns:
            An :class:`atlas.advisory.models.AdvisoryReport`.
        """
        if self._proactive_advisor is None:
            raise RuntimeError(
                "Proactive advisor is not wired; Atlas.start() must run first."
            )
        return self._proactive_advisor.run_advisory(principal_id=principal_id or "")

    # ------------------------------------------------------------------
    # P7.7 — Advisory-input integration (composition boundary)
    # ------------------------------------------------------------------

    @staticmethod
    def project_advisory(item: Any) -> AdvisorySignal | None:
        """Project one P5 ``AdvisoryItem`` into a conversation-owned
        :class:`AdvisorySignal` (P7.7).

        This is the ONLY place that maps advisory runtime data into the P7
        conversation input shape. Conversation never imports ``atlas.advisory``;
        the kernel performs the projection at the composition boundary and
        injects the immutable signal into the conversation layer.

        Returns ``None`` when the item lacks the minimal fields the detector
        needs (no summary and no suggested action), so non-improvement items
        never reach P7.
        """
        if item is None:
            return None
        summary = str(getattr(item, "summary", "") or "").strip()
        suggested_action = str(getattr(item, "suggested_action", "") or "").strip()
        if not summary and not suggested_action:
            return None
        evidence_ids = getattr(item, "evidence_ids", ()) or ()
        try:
            evidence_ids = tuple(str(e)[:128] for e in evidence_ids if e)[:8]
        except TypeError:
            evidence_ids = ()
        # NOTE: authority is intentionally NOT projected. AdvisoryItem carries
        # no authority, only requires_owner. The authoritative session context
        # (not advisory content) binds the pending confirmation and governs the
        # development action (P7.6); inventing authority here would misattribute
        # provenance and must never elevate a USER to OWNER.
        return AdvisorySignal(
            kind=str(getattr(item, "kind", "") or ""),
            summary=summary[:400],
            suggested_action=suggested_action[:200],
            evidence_ids=evidence_ids,
            principal_id=str(getattr(item, "principal_id", "") or "")[:128],
            authority="",
        )

    def feed_advisory(self, report: Any, session_context: Any = None) -> list[Message]:
        """Feed a P5 :class:`AdvisoryReport` into the P7 conversational path
        (P7.7).

        Each item is projected (via :meth:`project_advisory`) into a bounded
        :class:`AdvisorySignal` and handed to the conversation service, which
        runs P7.2 detection + P7.3 explanation. Advisory alone NEVER invokes
        the development bridge; only explicit human confirmation can.

        Multiple opportunities are handled deterministically: each signal is
        fed in report order, and the conversation layer's single pending-
        confirmation slot bounds state. Unrelated/non-improvement items project
        to ``None`` and are skipped silently.

        Returns the list of explanation :class:`Message`s produced (one per
        detected opportunity). An empty list means no opportunity was detected.
        """
        if report is None:
            return []
        items = getattr(report, "items", ()) or ()
        session = session_context if session_context is not None else self._session_context
        messages: list[Message] = []
        for item in items:
            signal = self.project_advisory(item)
            if signal is None:
                continue
            message = self._conversation.handle_advisory(signal, session)
            if message is not None:
                messages.append(message)
        return messages

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def container(self):
        return self._container

    @property
    def authority_service(self) -> AuthorityService | None:
        """Return the kernel-owned AuthorityService (P1/B1.1)."""
        return self._authority_service

    @property
    def session_manager(self) -> SessionManager | None:
        """Return the kernel-owned SessionManager (P1/B1.2)."""
        return self._session_manager

    @property
    def session_context(self) -> SessionContext | None:
        """Return the current Owner SessionContext (P1/B1.2)."""
        return self._session_context

    @property
    def orchestration_executor(self) -> OrchestrationExecutor | None:
        """Return the kernel-owned OrchestrationExecutor (P2/B2.2)."""
        return self._orchestration_executor

    def start_user_session(self, principal_id: str) -> SessionContext:
        """Create a USER session for ``principal_id`` (fail-closed).

        Validates the principal through AuthorityService; an unknown principal
        raises ``PermissionError`` and no session is created.
        """
        if self._session_manager is None or self._authority_service is None:
            raise RuntimeError("Session surfaces are not wired; Atlas.start() must run first.")
        session = self._session_manager.create_session(principal_id)
        ctx = SessionContext.from_session(session, action="user_session")
        return ctx

    def set_session_context(self, session_context: SessionContext | None) -> None:
        """Set the active session context for subsequent conversations."""
        self._session_context = session_context
        if self._conversation is not None:
            self._conversation.set_session_context(session_context)

    @property
    def events(self):
        return self._event_bus

    @property
    def state(self):
        return self._state_manager

    @property
    def tasks(self):
        return self._task_manager

    @property
    def cognitive(self):
        return self._cognitive_loop

    @property
    def cognition_api(self):
        return self._cognition_api

    @property
    def runtime_coordinator(self):
        """Return the unified RuntimeCoordinator (Phase 7.5)."""
        return self._runtime_coordinator

    @property
    def execution_engine(self):
        """Return the EvolutionExecutionEngine (Phase 11.0)."""
        return self._execution_engine

    @property
    def execution_gateway(self):
        """Return the EvolutionExecutionGateway (Phase 13.4)."""
        return self._execution_gateway

    @property
    def development_planner(self):
        """Return the kernel-owned DevelopmentPlanner (Phase E3/E6)."""
        return self._development_planner

    @property
    def self_development_loop(self):
        """Return the kernel-owned governed SelfDevelopmentLoop (Phase E5/E6)."""
        return self._self_development_loop

    @property
    def lifecycle_assessor(self):
        """Return the kernel-owned CapabilityLifecycleAssessor (Phase F3).

        Reuses the existing registries as read-only snapshot inputs. Never
        mutates and never auto-runs.
        """
        return self._lifecycle_assessor

    @property
    def adaptation_engine(self):
        """Return the kernel-owned AdaptationDecisionEngine (Phase F4).

        Produces DRAFT proposal candidates ONLY. Never approves, never
        executes, never auto-runs.
        """
        return self._adaptation_engine

    @property
    def adaptation_evaluator(self):
        """Return the kernel-owned AdaptationEvaluator (Phase F5).

        Observes + evaluates outcomes only. Never executes, never approves,
        never auto-runs.
        """
        return self._adaptation_evaluator

    @property
    def adaptation_orchestrator(self):
        """Return the kernel-owned AdaptationOrchestrator (Phase F6).

        Composes F1-F5 into bounded, manually-triggered adaptation cycles.
        Never auto-runs, never approves, never executes.
        """
        return self._adaptation_orchestrator

    @property
    def environment_observer(self):
        """Return the kernel-owned EnvironmentObserver (Phase F1).

        Reuses the existing model/tool/capability registries, EventBus, and
        SelfObservationEngine. Purely observational — nothing auto-runs.
        """
        return self._environment_observer

    @property
    def ai_availability(self):
        """Return the kernel-owned ProviderAvailabilityTracker (Phase F10).

        Bounded, deterministic, observation-only AI-provider availability.
        Callers may record outcomes explicitly; status/snapshot are computed
        on demand. Never records by itself; never auto-runs; never blocks
        any non-AI path.
        """
        return self._ai_availability

    @property
    def boot_safe_mode(self) -> bool:
        """True when F11 boot recovery reported SAFE_MODE.

        SAFE_MODE only narrows capabilities: base config is used, the config
        overlay is preserved, and autonomous lifecycle advancement stays
        disabled for the session (the governed dispatcher is not wired).
        """
        return bool(self._boot_report is not None and self._boot_report.safe_mode)

    @property
    def boot_report(self):
        """Return the F11 boot activation report (read-only), or None."""
        return self._boot_report

    @property
    def boot_activation(self):
        """Return the kernel-owned BootActivationService (F11), or None."""
        return self._boot_activation

    @property
    def rule_engine(self):
        """Return the governance RuleEngine (Phase 13.1)."""
        return self._rule_engine

    @property
    def intelligence_engine(self):
        """Return the EvolutionIntelligenceEngine (Phase 12.2)."""
        return self._intelligence_engine

    @property
    def evolution_knowledge(self):
        """
        Return the EvolutionKnowledgeQuery (Phase 13.5).

        The query is the read-only surface for the persistent evolution
        knowledge layer.
        """
        return self._knowledge_query

    @property
    def decision_intelligence(self):
        """
        Return the DecisionIntelligenceEngine (Phase 14.2).

        The engine is the read-only adaptive planning layer that consumes
        consolidated evolution knowledge and produces PlanningContexts.
        """
        return self._decision_intelligence

    @property
    def outcome_tracker(self):
        """Return the shared OutcomeTracker (Phase 11.0)."""
        return self._outcome_tracker

    @property
    def goal_executor(self):
        """Return the GoalExecutionEngine (Phase 15.0)."""
        return self._goal_executor

    @property
    def research_coordinator(self):
        """Return the kernel-owned ConcreteResearchCoordinator (Phase 21)."""
        return self._research_coordinator

    @property
    def schedule_store(self):
        """Return the Phase 16 ScheduleStore, or None if not wired."""
        return self._schedule_store

    @property
    def application_engine(self):
        """Return the kernel-owned Phase 16 ApplicationEngine (kernel-private).

        The engine is NOT registered in the ServiceContainer (track-private
        precedent). Constructing it creates no execution path — ``apply()``
        is only reachable through the governed pipeline.
        """
        return self._application_engine

    @property
    def started(self):
        return self._started

    @property
    def repository_map(self):
        """Read-only repository self-knowledge map (built once, cached).

        Returns ``None`` when the builder is unavailable or a build attempt
        failed — callers must treat the result as advisory context.
        """
        if self._repository_map is None and self._repository_map_builder is not None:
            try:
                self._repository_map = self._repository_map_builder.build()
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "Repository map build failed; returning no map"
                )
        return self._repository_map

    def refresh_repository_map(self):
        """Explicitly rebuild the cached repository map (read-only).

        Returns the fresh snapshot, or ``None`` when unavailable/failed.
        Never raises; never triggered automatically.
        """
        if self._repository_map_builder is None:
            return None
        self._repository_map = None
        return self.repository_map

    @property
    def provider(self):
        return self._ai_manager.provider

    def models(self):
        return self._ai_manager.service.models()

    # ------------------------------------------------------------------
    # Phase E6 — Governed self-development entry point
    # ------------------------------------------------------------------

    def run_self_development(self, proposal, max_iterations=None):
        """Run the bounded, governed self-development loop for an approved proposal.

        This is the smallest real runtime bridge from an APPROVED
        ``EvolutionProposal`` to the kernel-owned E5 ``SelfDevelopmentLoop``
        (which delegates planning to the E3 ``DevelopmentPlanner`` and executes
        the E2 sandbox / E4 pytest path). It reuses the existing governance
        approval contract and never touches the real repository.

        Phase 13.5 development-history closure: after the loop returns, one
        ``event_type="development"`` EvolutionRecord is stored best-effort in
        EvolutionMemory (and the knowledge pipeline is consolidated) so the
        evolution history and F7 insight feedback see development runs. The
        returned ``DevelopmentRunResult`` is never affected by persistence.

        Args:
            proposal: An already-approved ``EvolutionProposal`` carrying the
                development workload in its metadata.
            max_iterations: Optional bounded iteration budget.

        Returns:
            A ``DevelopmentRunResult``. Unapproved / malformed proposals fail
            closed with no sandbox work performed.
        """
        if self._self_development_loop is None:
            raise RuntimeError(
                "Self-development loop is not wired; Atlas.start() must run first."
            )
        result = self._self_development_loop.run(
            proposal, max_iterations=max_iterations
        )
        # --- Development Outcome → Evolution History bridge (Phase 13.5) ---
        # Best-effort on every step: a missing memory skips persistence,
        # storage failures are swallowed, and consolidation failures never
        # propagate. The DevelopmentRunResult is always returned unchanged.
        try:
            record = self._build_development_record(proposal, result)
            if self._evolution_memory is not None and record is not None:
                self._evolution_memory.store_record(record)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Failed to store development history record for proposal %s",
                getattr(proposal, "proposal_id", "?"),
            )

        # --- Stage E: promotion-review foundation ---
        # Assess every finished run; verified successes automatically open a
        # PENDING_REVIEW promotion request (audit + human boundary prep).
        # Stage H: a bounded change manifest (from the proposal's own
        # persisted workload) is attached so an approving operator can see
        # what actually changed. Fail-soft throughout.
        try:
            gate = PromotionGate(evolution_memory=self._evolution_memory)
            change_manifest = build_change_manifest(
                (getattr(proposal, "metadata", {}) or {}).get(
                    "code_changes", []
                )
            )
            assessment = gate.assess(
                result,
                proposal_id=getattr(proposal, "proposal_id", ""),
                change_manifest=change_manifest,
            )
            if (
                assessment.recommendation
                is PromotionRecommendation.READY_FOR_PROMOTION
            ):
                gate.request_review(assessment)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Failed promotion-review assessment for proposal %s",
                getattr(proposal, "proposal_id", "?"),
            )

        if self._knowledge_pipeline is not None:
            try:
                self._knowledge_pipeline.consolidate()
            except Exception:
                pass

        return result

    def _build_development_record(self, proposal, result):
        """Construct the ``development`` EvolutionRecord for an SDL run.

        Pure construction from the already-available ``DevelopmentRunResult``
        evidence. Returns None only when no evidence can be derived.
        """
        from atlas.evolution.models import EvolutionRecord
        from atlas.evolution.development_models import DevelopmentOutcomeStatus

        from datetime import datetime

        last_outcome = result.outcomes[-1] if result.outcomes else None
        success = result.status == DevelopmentOutcomeStatus.SUCCESS

        related_ids = [proposal.proposal_id]
        if result.plan is not None and getattr(result.plan, "plan_id", ""):
            related_ids.append(result.plan.plan_id)

        evidence: dict = {
            "terminal_status": result.status.name,
            "iterations_used": result.iterations_used,
            "success": success,
            "message": result.message,
        }
        if last_outcome is not None:
            evidence.update(
                {
                    "verification_passed": bool(last_outcome.verification_passed),
                    "rollback_occurred": bool(last_outcome.rollback_occurred),
                    "test_outcome": last_outcome.test_outcome,
                    "changed_files": list(last_outcome.changed_files),
                    "final_iteration": last_outcome.iteration,
                }
            )
            learning_ref = last_outcome.metadata.get("learning_insight_id", "")
            if learning_ref:
                evidence["learning_evidence"] = learning_ref
            outcome_id = (
                getattr(last_outcome, "outcome_id", "")
                or last_outcome.metadata.get("outcome_id", "")
            )
            if outcome_id:
                related_ids.append(str(outcome_id))

        counter = getattr(self, "_development_record_counter", 0)
        counter += 1
        self._development_record_counter = counter
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        return EvolutionRecord(
            record_id=f"DEV-{timestamp}-{counter:04d}",
            event_type="development",
            description=(
                f"Self-development run for proposal "
                f"'{proposal.proposal_id}': {result.status.name}. "
                f"{result.message[:150]}"
            ),
            related_ids=related_ids,
            metadata=evidence,
        )

    def _evolution_context_snapshot(self, limit: int = 10) -> dict:
        """
        Build a bounded, JSON-safe evolution-history snapshot (Stage D).

        Aggregates the most recent development runs, execution attempts,
        and insights from EvolutionMemory into the advisory structure
        consumed by DecisionIntelligenceEngine / DevelopmentPlanner::

            {"history": {"previous_attempts": [...],
                         "successful_patterns": [...],
                         "failed_patterns": [...]},
             "development": {"recent_runs": [...],
                             "common_failures": [...]}}

        Fail-soft: returns {} when memory is unavailable or anything goes
        wrong. Bounded by ``limit`` per section — never dumps full history.
        """
        memory = self._evolution_memory
        if memory is None:
            return {}

        try:
            development_records = memory.get_records_by_type("development")[
                :limit
            ]
            execution_records = memory.get_records_by_type("execution")[:limit]
            insights = memory.get_insights(n=limit)

            recent_runs = [
                {
                    "record_id": record.record_id,
                    "proposal_id": (
                        record.related_ids[0]
                        if record.related_ids
                        else ""
                    ),
                    "terminal_status": str(
                        record.metadata.get("terminal_status", "")
                    ),
                    "success": bool(record.metadata.get("success", False)),
                    "iterations_used": record.metadata.get(
                        "iterations_used", 0
                    ),
                    # Phase 5.2 (G-B) — bounded usefulness evidence so planning
                    # can retrieve and use retained development experience.
                    "usefulness_outcome": str(
                        (record.metadata.get("usefulness") or {}).get("outcome", "")
                    ),
                    "capability_improvement": str(
                        (record.metadata.get("usefulness") or {}).get(
                            "capability_improvement", ""
                        )
                    ),
                }
                for record in development_records
            ]

            previous_attempts = [
                {
                    "proposal_id": insight.proposal_id,
                    "outcome": insight.outcome,
                    "record_id": insight.execution_record_id,
                }
                for insight in insights
            ]

            successful_patterns = [
                {
                    "proposal_id": insight.proposal_id,
                    "evidence_summary": insight.evidence_summary[:120],
                }
                for insight in insights
                if insight.outcome == "success"
            ]
            failed_patterns = [
                {
                    "proposal_id": insight.proposal_id,
                    "evidence_summary": insight.evidence_summary[:120],
                }
                for insight in insights
                if insight.outcome == "failure"
            ]

            # Most recent distinct failure signals across execution and
            # development records (bounded, deduplicated).
            common_failures: list[str] = []
            for record in list(execution_records) + list(development_records):
                if record.metadata.get("success", True):
                    continue
                signal = str(
                    record.metadata.get(
                        "error", record.metadata.get("test_outcome", "")
                    )
                )[:120]
                if signal and signal not in common_failures:
                    common_failures.append(signal)

            snapshot = {
                "history": {
                    "previous_attempts": previous_attempts,
                    "successful_patterns": successful_patterns,
                    "failed_patterns": failed_patterns,
                },
                "development": {
                    "recent_runs": recent_runs,
                    "common_failures": common_failures[:limit],
                },
            }

            # Stage F: attach the latest bounded research-evidence summary
            # (cache-only; acquisition itself is never triggered here).
            research_evidence = self._last_research_evidence
            if isinstance(research_evidence, dict) and research_evidence:
                snapshot["research"] = dict(research_evidence)

            return snapshot

        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Failed to build evolution context snapshot"
            )
            return {}

    def pending_promotion_reviews(self) -> list:
        """Stage H: read-only prioritized view of PENDING_REVIEW promotion
        requests (highest decision quality first). Delegates to the
        kernel-owned PromotionGate over the EvolutionMemory; never
        raises and never modifies anything."""
        gate = self._promotion_gate
        if gate is None:
            return []
        return gate.pending_reviews()

    def promotion_review_details(self, request_id: str) -> dict | None:
        """Stage H: read-only detail of ONE promotion review.

        Resolves a single existing ``promotion_review`` record by its
        ``request_id`` and returns the bounded, JSON-safe evidence the
        operator needs to review it (assessment, change manifest,
        recommendation, decision, etc.). NEVER approves, rejects, promotes,
        or executes anything. Fail-soft: returns ``None`` when the request
        is unknown or the gate is not wired.
        """
        gate = self._promotion_gate
        if gate is None or not request_id:
            return None
        return gate.promotion_review_details(request_id)

    @property
    def promotion_gate(self) -> PromotionGate:
        """Return the kernel-owned Stage H PromotionGate.

        Constructed once during ``start()`` over the kernel-owned
        EvolutionMemory. Read-only surface for review visibility; the
        companion ``submit_development_for_promotion_review()`` is the
        only entry point that opens new PENDING_REVIEW audit rows.
        """
        if self._promotion_gate is None:
            raise RuntimeError(
                "Promotion gate is not wired; Atlas.start() must run first."
            )
        return self._promotion_gate

    def submit_development_for_promotion_review(
        self,
        session_context,
        run_result: Any,
        proposal_id: str = "",
        change_manifest: dict[str, Any] | None = None,
        development_record_id: str = "",
    ) -> PromotionRequest:
        """Stage H: bridge a verified ``DevelopmentRunResult`` into a
        ``PENDING_REVIEW`` audit row carrying bounded change evidence.

        P7.6 — AUTHORIZES the acting identity resolved from
        ``session_context`` through the EXISTING SessionManager +
        AuthorityService (OWNER-only) BEFORE opening any review.

        Manual, additive, read-only with respect to the repository:

        * Calls ``PromotionGate.assess(...)`` (deterministic risk
          classification; manifest preserved on the assessment).
        * Calls ``PromotionGate.request_review(...)`` (opens a
          ``PENDING_REVIEW`` request and persists a
          ``event_type="promotion_review"`` record via the existing
          EvolutionMemory surface).
        * Returns the ``PromotionRequest`` to the caller.

        Hard safety contract:

        * Never calls ``approve()`` / ``reject()`` / anything that
          mutates the request's status away from ``PENDING_REVIEW``.
        * Never mutates the repository. No filesystem, no git, no
          subprocess. ``PROMOTED`` is reserved for out-of-scope
          operator tooling.
        * Never auto-runs. There is no daemon, no tick-loop wiring, and
          no SDL integration. The host invokes this method explicitly.
        """
        # P7.6 — authorization boundary BEFORE any review submission.
        self._require_development_authority(session_context, action="promotion_review")

        gate = self._promotion_gate
        if gate is None:
            raise RuntimeError(
                "Promotion gate is not wired; Atlas.start() must run first."
            )
        assessment = gate.assess(
            run_result,
            proposal_id=proposal_id,
            change_manifest=change_manifest,
        )
        return gate.request_review(
            assessment,
            development_record_id=development_record_id,
        )


    # ------------------------------------------------------------------
    # Composition root — public entry point
    # ------------------------------------------------------------------

    def start(self):
        """Start Atlas by wiring all subsystems in dependency order.

        The public entry point delegates to private helper methods that
        each initialise a coherent wiring domain.  Dependency ordering
        between helpers is explicit in the call sequence below.
        """
        if self._started:
            return

        self._config.load()

        # Domain 1 — AI provider, model routing, config
        self._init_ai_provider()

        # Domain 2 — Memory, knowledge, legacy intelligence, learning
        self._init_memory_knowledge()

        # Domain 3 — Reasoning pipeline, capability registry, tracks A/B
        #   factories, learning engine, tools
        self._init_reasoning_pipeline()

        # Domain 4 — Understanding, world model, identity, goals,
        #   experience, self-model, feedback
        self._init_cognitive_engines()

        # Domain 5 — Evolution storage, tracks A-D infrastructure
        self._init_tracks()

        # Domain 6 — Evolution intelligence, knowledge, governance, gateway
        self._init_evolution_pipeline()

        # Stage H: kernel-owned PromotionGate (read-only review view +
        # manual bridge). Wired after Domain 6 so EvolutionMemory exists.
        # No auto-run; nothing executes; nothing changes the repository.
        self._init_promotion_gate()

        # Domain 6b — Phase F1: environment observation foundation
        # Purely observational; wiring only, nothing auto-runs.
        self._init_environment_observer()

        # Domain 6c — Phase F3: lifecycle assessment foundation
        # Read-only assessment; wiring only, nothing auto-runs.
        self._init_lifecycle_assessor()

        # Domain 6d — Phase F4: governed adaptation decision foundation
        # Candidate-producing only; nothing auto-runs, nothing approves.
        self._init_adaptation_engine()

        # Domain 6e — Phase F5: adaptation evaluation & feedback foundation
        # Observer/evaluator only; nothing auto-runs, nothing executes.
        self._init_adaptation_evaluator()

        # Domain 6f — Phase F6: full adaptation cycle orchestrator
        # Manually-triggered composition only; nothing auto-runs.
        self._init_adaptation_orchestrator()

        # Domain 6g — Phase F7: autonomous operation controller
        # Bounded manual wrapper around F6; nothing auto-runs, no daemon.
        self._init_operation_controller()

        # Domain 6h — Phase F9: governed development-cycle preparation
        # Bounded single-shot proposal preparation; stops at the human
        # approval boundary. Nothing auto-runs, no daemon, no execution.
        self._init_development_cycle()

        # Domain 6i — Phase F11: long-term self-management review
        # Read-only aggregation of durable evidence; nothing auto-runs,
        # no daemon, no execution, no persistence of its own.
        self._init_self_management_review()

        # Domain 6j — P5: Proactive Advisory (advisory-only, no execution)
        # Composes the EXISTING F1/F10/F11 and B3.x/P4 seams into one bounded,
        # principal-scoped advisory report. Never invokes a tool, capability,
        # orchestration, development, governance, approval, or promotion path
        # directly. Kernel-private; never runs from tick().
        self._init_proactive_advisor()

        # Domain 7 — RuntimeCoordinator, scheduler, goal execution,
        #   cognition service, conversation, component registry, container
        self._init_runtime_services()

    # ------------------------------------------------------------------
    # Domain 1 — AI Provider
    # ------------------------------------------------------------------

    def _init_ai_provider(self) -> None:
        """Wire model routing, AI manager, and provider configuration."""
        provider = str(self._config.get("ai", "provider"))
        model = str(self._config.get("ai", "model"))
        timeout = int(self._config.get("ai", "timeout"))  # type: ignore[arg-type]

        # --- Model routing ---
        # Registry is recreated here so shutdown() → start() restarts work.
        # Profiles come from the optional [ai.profiles] config section;
        # when absent, safe defaults replicate the previous behavior.
        self._model_profile_registry = ModelProfileRegistry()
        profile_entries = self._config.get("ai", "profiles") or []
        for profile in load_model_profiles(profile_entries, model):
            self._model_profile_registry.register(profile)
        external_providers = bool(
            self._config.get("ai", "external_providers", default=False)
        )
        self._model_router = ModelRouter(
            self._model_profile_registry,
            external_providers=external_providers,
        )

        self._ai_manager = AIManager(
            model_profile_registry=self._model_profile_registry,
        )

        api_keys = self._config.get("ai", "api_keys")
        allow_fallback = bool(self._config.get("ai", "allow_fallback", default=False))
        conversation_timeout_s = self._config.get(
            "ai", "conversation_timeout_s", default=20.0
        )
        self._ai_manager.initialize(
            provider, model, timeout,
            model_router=self._model_router,
            api_keys=api_keys,  # type: ignore[arg-type]
            allow_fallback=allow_fallback,
            external_providers=external_providers,
        )

    # ------------------------------------------------------------------
    # Domain 2 — Memory, Knowledge, Legacy Intelligence, Learning
    # ------------------------------------------------------------------

    def _init_memory_knowledge(self) -> None:
        """Wire memory, knowledge, legacy cognitive loop, and learning."""
        # --- Memory ---
        repository = MemoryRepository()
        ranking_engine = RankingEngine()
        search_engine = MemorySearchEngine(repository, ranking_engine)
        self._memory_service = MemoryManagerService(
            repository=repository,
            ranking_engine=ranking_engine,
            search_engine=search_engine,
        )

        # --- Knowledge ---
        self._knowledge_manager = KnowledgeManager()

        # --- Legacy intelligence (preserved) ---
        self._cognitive_loop = CognitiveLoop(
            memory_service=self._memory_service,
            knowledge_manager=self._knowledge_manager,
        )
        self._cognitive_service = CognitiveService(
            cognitive_loop=self._cognitive_loop
        )

        # --- Learning ---
        self._learning_manager = LearningManager()
        self._knowledge_feedback = KnowledgeFeedback()

    # ------------------------------------------------------------------
    # Domain 3 — Reasoning Pipeline & Tools
    # ------------------------------------------------------------------

    def _init_reasoning_pipeline(self) -> None:
        """Wire the capability registry, reasoning engine, and tools.

        Creates the CapabilityRegistry and registers all default handlers
        plus Track A/B factories *before* the LearningEngine so that the
        CapabilityAnalyzer can reuse the same kernel-owned LearningMemory
        instance (Phase 20 Batch 4 ordering requirement).
        """
        self._capability_registry = CapabilityRegistry()
        for capability_name, handler in DEFAULT_HANDLERS.items():
            self._capability_registry.register(capability_name, handler)

        # --- Track A: Register research capability handlers (Phase 17.7) ---
        self._research_factory = ResearchCapabilityFactory(
            web_hosts=self._config.get("research", "web_allowed_hosts", default=()),
        )
        self._research_factory.register(self._capability_registry)

        # --- Track B: Register toolchain capability handlers (Phase 18.7) ---
        self._toolchain_factory = ToolchainCapabilityFactory()
        self._toolchain_factory.register(self._capability_registry)

        # --- Knowledge: Register knowledge retrieval capability handler ---
        self._knowledge_factory = KnowledgeRetrievalHandlerFactory(
            knowledge_manager=self._knowledge_manager,
        )
        self._knowledge_factory.register(self._capability_registry)

        self._reasoning_controller = ReasoningController()
        # --- Phase 20 Batch 4: create the LearningEngine before the
        #     CapabilityAnalyzer so reflection-derived strategy evidence
        #     (stored in the kernel-owned LearningMemory) can influence
        #     capability selection.  The exact same LearningMemory instance
        #     is reused — no second store is created.
        self._learning_engine = LearningEngine()
        self._capability_analyzer = CapabilityAnalyzer(
            learning_provider=self._learning_engine.memory,
        )
        self._capability_router = CapabilityRouter(self._capability_registry)
        self._capability_dispatcher = CapabilityDispatcher(self._capability_registry)
        self._reasoning_recorder = ReasoningRecorder()
        self._reflection_engine = ReflectionEngine()
        self._planning_engine = PlanningEngine()

        # --- Tool engine ---
        self._tool_registry = ToolRegistry()
        self._tool_selector = ToolSelector()
        self._tool_executor = ToolExecutor(self._tool_registry)
        self._tool_engine = ToolEngine(
            self._tool_registry, self._tool_selector, self._tool_executor,
        )
        for tool in BUILTIN_TOOLS:
            self._tool_registry.register(tool)

        # --- Phase E6: Register the E4 sandbox tools through the SAME
        #     kernel-owned ToolRegistry (pytest + read-only git inspection,
        #     confined to minted sandbox workspaces). No parallel registry.
        register_sandbox_tools(self._tool_registry)

    # ------------------------------------------------------------------
    # Domain 4 — Cognitive Engines
    # ------------------------------------------------------------------

    def _init_cognitive_engines(self) -> None:
        """Wire understanding, world model, identity, goals, experience,
        self-model, and feedback — all cognitive engines that the
        RuntimeCoordinator depends on.
        """
        # --- Phase 7.5: Understanding ---
        understanding_storage = SQLiteUnderstandingStorage()
        understanding_storage.initialize()

        self._understanding_engine = UnderstandingEngine(
            understanding_storage=understanding_storage,
        )
        understanding_restore_result = self._understanding_engine.restore()

        self._world_model_engine = WorldModelEngine()
        self._self_observation_engine = SelfObservationEngine()
        # self._learning_engine is created earlier (Phase 20 Batch 4) so
        # the CapabilityAnalyzer can reuse the same kernel-owned
        # LearningMemory instance.
        self._identity_engine = IdentityEngine()
        self._identity_engine.initialize()

        # --- Phase 8.3: Goal Intelligence Engine ---
        self._goal_repository = GoalRepository()
        self._goal_intelligence_engine = GoalIntelligenceEngine(
            repository=self._goal_repository,
        )

        # --- Phase 9.1: Experience & Self-Model with persistence ---
        storage = SQLiteExperienceStorage()
        storage.initialize()

        self._experience_repository = ExperienceRepository(storage=storage)
        restore_result = self._experience_repository.restore()

        self._experience_accumulator = ExperienceAccumulator(
            repository=self._experience_repository,
        )
        self._experience_accumulator.seed_counter(restore_result.max_experience_id or 0)

        # --- Phase 11.0: Create shared OutcomeTracker for SelfModelEngine
        #     and EvolutionExecutionEngine ---
        self._outcome_tracker = OutcomeTracker(
            repository=self._experience_repository,
        )

        self._self_model_engine = SelfModelEngine(
            repository=self._experience_repository,
            outcome_tracker=self._outcome_tracker,
            identity_engine=self._identity_engine,
            understanding_engine=self._understanding_engine,
            goal_intelligence_engine=self._goal_intelligence_engine,
            window_size=20,
            update_interval=5,
        )
        self._self_model_engine.seed_snapshot_counter(restore_result.max_snapshot_id or 0)
        if restore_result.latest_snapshot is not None:
            self._self_model_engine.restore_snapshot(restore_result.latest_snapshot)

        if storage.is_available():
            self._event_bus.publish(
                "experience.storage.initialized",
                {
                    "restored_experiences": restore_result.experience_count,
                    "db_path": str(storage.db_path),
                },
            )
        else:
            self._event_bus.publish(
                "experience.storage.unavailable",
                {"mode": "memory_only"},
            )

        if understanding_storage.is_available():
            self._event_bus.publish(
                "understanding.storage.initialized",
                {
                    "restored_concepts": understanding_restore_result.concept_count,
                    "db_path": str(understanding_storage.db_path),
                },
            )
        else:
            self._event_bus.publish(
                "understanding.storage.unavailable",
                {"mode": "memory_only"},
            )

        # --- Phase 8.2: Create FeedbackCoordinator ---
        self._feedback_coordinator = FeedbackCoordinator(
            identity_engine=self._identity_engine,
            world_model_engine=self._world_model_engine,
            understanding_engine=self._understanding_engine,
            learning_engine=self._learning_engine,
        )

    # ------------------------------------------------------------------
    # Domain 5 — Track Infrastructure
    # ------------------------------------------------------------------

    def _init_tracks(self) -> None:
        """Wire evolution storage and all four Track subsystems (A–D).

        Each track follows the same pattern: create storage, initialise,
        publish availability events, compose track-private components, and
        register capability handlers / governance rules.
        """
        # --- Phase 11.3: Create and initialize evolution storage ---
        self._evolution_storage = SQLiteEvolutionStorage()
        evolution_storage = self._evolution_storage
        evolution_storage.initialize()
        if evolution_storage.is_available():
            self._event_bus.publish(
                "evolution.storage.initialized",
                {"db_path": str(evolution_storage.db_path)},
            )
        else:
            self._event_bus.publish(
                "evolution.storage.unavailable",
                {"mode": "memory_only"},
            )

        # --- Persistent Learning: bind the kernel-owned evolution storage to
        #     the LearningEngine's memory and restore previously persisted
        #     reusable learning insights. Additive; no second store is created
        #     and storage failures leave the memory fully functional.
        if self._learning_engine is not None:
            learning_memory = getattr(self._learning_engine, "memory", None)
            if learning_memory is not None and hasattr(
                learning_memory, "bind_storage"
            ):
                learning_memory.bind_storage(evolution_storage)

        # --- Track A: Instantiate and initialize research storage (Phase 17.6) ---
        self._research_storage = ResearchSQLiteStorage()
        self._research_storage.initialize()
        if self._research_storage.is_available():
            self._event_bus.publish(
                "research.storage.initialized",
                {"db_path": str(self._research_storage.db_path)},
            )
        else:
            self._event_bus.publish(
                "research.storage.unavailable",
                {"mode": "memory_only"},
            )

        # --- Track A (Phase 21): Concrete Research Coordinator ---
        # Composed from the SAME Track A components owned by the factory
        # (planner/extractor/verifier + the factory's source resolver) — no
        # duplicate components.  Storage is the kernel-owned research adapter;
        # ingest is governed and fails closed (sink intentionally unwired
        # until the Phase 16 hand-off exists).  The coordinator is kernel-private
        # and NOT registered in the ServiceContainer (Track C/D precedent).
        self._research_ingest_bridge = ResearchIngestBridge()
        self._research_coordinator = ConcreteResearchCoordinator(
            planner=self._research_factory.planner,
            extractor=self._research_factory.extractor,
            verifier=self._research_factory.verifier,
            storage=self._research_storage,
            ingest=self._research_ingest_bridge,
            resolve_sources=self._research_factory._resolve_sources,
            select_sources=self._select_research_sources,
        )
        self._research_factory.register_coordinator(
            self._research_coordinator, self._capability_registry
        )

        # --- Track A (Phase F8): Information Acquisition Service ---
        # Thin manual bridge over the EXISTING F2 freshness + research
        # coordinator. Never runs from tick(); never a daemon; bounded and
        # model-optional. Wire after the coordinator exists so the single
        # coordinator/factory instances are reused (no duplicates).
        self._init_information_acquisition()

        # --- Track B: Instantiate and initialize toolchain storage (Phase 18.8) ---
        self._toolchain_storage = ToolchainSQLiteStorage()
        self._toolchain_storage.initialize()
        if self._toolchain_storage.is_available():
            self._event_bus.publish(
                "toolchain.storage.initialized",
                {"db_path": str(self._toolchain_storage.db_path)},
            )
        else:
            self._event_bus.publish(
                "toolchain.storage.unavailable",
                {"mode": "memory_only"},
            )

        # --- Track C: Instantiate and initialize long-term storage (Phase 19) ---
        self._longterm_storage = LongTermSQLiteStorage()
        self._longterm_storage.initialize()
        if self._longterm_storage.is_available():
            self._event_bus.publish(
                "longterm.storage.initialized",
                {"db_path": str(self._longterm_storage.db_path)},
            )
        else:
            self._event_bus.publish(
                "longterm.storage.unavailable",
                {"mode": "memory_only"},
            )

        # --- Track C: Long-term repositories with persistent storage ---
        self._episodic_repository = EpisodicRepository(
            storage=self._longterm_storage,
        )
        self._procedural_repository = ProceduralRepository(
            storage=self._longterm_storage,
        )
        self._episodic_repository.restore()
        self._procedural_repository.restore()

        # --- Track C: Episodic recorder + procedure extractor (additive
        #     consumers of the existing ExperienceAccumulator output) ---
        self._longterm_recorder = EpisodicRecorder()
        self._procedure_extractor = ProcedureExtractor()
        self._event_bus.subscribe(
            "runtime.pipeline.completed",
            self._record_longterm_from_pipeline,
        )

        # --- Track C: Consolidator + governed ingest bridge (fail-closed) ---
        self._longterm_consolidator = Consolidator()
        # The Phase 16 ingest sink is not yet kernel-wired (same as Tracks A
        # and B); the bridge therefore fails closed until a sink is provided.
        self._longterm_ingest_bridge = LongTermIngestBridge()

        # --- Track C: Register long-term capability handlers (Phase 19.4) ---
        self._longterm_factory = LongTermCapabilityFactory(
            episodes=self._episodic_repository,
            procedures=self._procedural_repository,
            consolidator=self._longterm_consolidator,
            evolve_bridge=self._longterm_ingest_bridge,
        )
        self._longterm_factory.register(self._capability_registry)

        # --- Track D: Instantiate and initialize advanced-reasoning storage ---
        self._advanced_reasoning_storage = AdvancedReasoningSQLiteStorage()
        self._advanced_reasoning_storage.initialize()
        if self._advanced_reasoning_storage.is_available():
            self._event_bus.publish(
                "reasoning.storage.initialized",
                {"db_path": str(self._advanced_reasoning_storage.db_path)},
            )
        else:
            self._event_bus.publish(
                "reasoning.storage.unavailable",
                {"mode": "memory_only"},
            )

        # --- Track D: Provider adapters (kernel-boundary, read-only) ---
        # EvidenceProvider wraps KnowledgeManager; CausalGraphProvider wraps
        # WorldModelEngine.  Neither adapter is registered in the container.
        self._advanced_reasoning_evidence_provider = KnowledgeEvidenceProvider(
            self._knowledge_manager
        )
        self._advanced_reasoning_causal_provider = WorldModelCausalGraphProvider(
            self._world_model_engine
        )

        # --- Track D: AdvancedReasoningService (private, kernel-owned) ---
        # Composed with injected engines, dual-write repository, and the
        # fail-closed ingest bridge.  The engine implementations receive the
        # kernel-built provider adapters (KnowledgeEvidenceProvider →
        # MultiStepReasoner; WorldModelCausalGraphProvider → CausalReasoner)
        # so traces are evidence-aware and causal analysis reads the world
        # model.  The service is NOT registered in the ServiceContainer
        # (Track C private-factory precedent).
        self._advanced_reasoning_ingest_bridge = ReasoningIngestBridge()
        self._advanced_reasoning_repository = ReasoningTraceRepository(
            storage=self._advanced_reasoning_storage
        )
        self._advanced_reasoning_service = AdvancedReasoningService(
            multi_step=MultiStepReasoner(
                evidence_provider=self._advanced_reasoning_evidence_provider
            ),
            causal=CausalReasoner(
                graph_provider=self._advanced_reasoning_causal_provider
            ),
            repository=self._advanced_reasoning_repository,
            ingest_bridge=self._advanced_reasoning_ingest_bridge,
        )
        self._advanced_reasoning_repository.restore()

        # --- Track D: Trace recorder as additive pipeline-consumer surface ---
        # The recorder is wired to the existing runtime.pipeline.completed
        # event (Track C precedent).  The subscription itself is kernel-owned.
        self._advanced_reasoning_recorder = ReasoningTraceRecorder()
        self._event_bus.subscribe(
            "runtime.pipeline.completed",
            self._record_reasoning_from_pipeline,
        )

        # --- Track D: Register reasoning capability handlers ---
        self._advanced_reasoning_factory = AdvancedReasoningCapabilityFactory(
            service=self._advanced_reasoning_service
        )
        self._advanced_reasoning_factory.register(self._capability_registry)

    # ------------------------------------------------------------------
    # Domain 6 — Evolution Pipeline
    # ------------------------------------------------------------------

    def _init_evolution_pipeline(self) -> None:
        """Wire the evolution intelligence, knowledge, governance, and
        execution gateway — the full governed self-improvement pipeline.
        """
        # --- Phase 10.0: Evolution Pipeline with Phase 11.3 persistence ---
        self._improvement_planner = ImprovementPlanner()
        self._proposal_generator = ProposalGenerator()
        self._approval_manager = ApprovalManager()
        self._evolution_memory = EvolutionMemory(storage=self._evolution_storage)
        self._evolution_memory.restore()

        # --- P1/B1.1: Owner/User authority foundation ---
        # Exactly one logical Owner, designated via [authority] owner_name.
        # Auditable through the kernel-owned EvolutionMemory (best-effort).
        owner_name = str(
            self._config.get("authority", "owner_name", default="Owner")
        )
        self._authority_service = AuthorityService(
            owner_name=owner_name,
            audit_store=self._evolution_memory,
        )

        # Phase 13.5 decision-pipeline closure: replay restored observations
        # into the scheduler's working set so pre-restart runtime history
        # remains actionable for weakness aggregation (oldest-first).
        restored_observations = self._evolution_memory.get_observations(n=1000)
        if restored_observations:
            self._self_observation_engine.seed(list(reversed(restored_observations)))

        # --- Phase 13.5: Create the Persistent Evolution Knowledge layer ---
        self._knowledge_repository = EvolutionKnowledgeRepository(
            storage=self._evolution_storage,
        )
        self._knowledge_repository.restore()
        self._knowledge_consolidator = EvolutionKnowledgeConsolidator()
        self._knowledge_query = EvolutionKnowledgeQuery(
            repository=self._knowledge_repository,
        )

        # --- Phase 13.6: Create the automatic knowledge consolidation pipeline ---
        # Created before the EvolutionIntelligenceEngine so that the engine
        # receives a fully-constructed pipeline (Phase 14 review finding).
        self._knowledge_pipeline = EvolutionKnowledgePipeline(
            consolidator=self._knowledge_consolidator,
            repository=self._knowledge_repository,
        )

        # --- Phase 12.1 / 12.2: Create the Evolution Intelligence Engine ---
        self._insight_scorer = InsightScorer()
        self._intelligence_engine = EvolutionIntelligenceEngine(
            evolution_memory=self._evolution_memory,
            experience_repository=self._experience_repository,
            insight_scorer=self._insight_scorer,
            storage=self._evolution_storage,
            knowledge_pipeline=self._knowledge_pipeline,
        )

        # --- Phase 14.4: Create the DecisionIntelligenceEngine ---
        # Read-only adaptive planning: EvolutionKnowledgeQuery → engine.
        # Stage A1: the engine also consumes the ALREADY-BUILT repository
        # map via a cache-only provider (never triggers a scan).
        self._decision_intelligence = DecisionIntelligenceEngine(
            knowledge_query=self._knowledge_query,
            repository_map_provider=lambda: self._repository_map,
            evolution_context_provider=self._evolution_context_snapshot,
        )

        # --- Phase 11.0: Create the EvolutionExecutionEngine ---
        self._execution_engine = EvolutionExecutionEngine(
            approval_manager=self._approval_manager,
            evolution_memory=self._evolution_memory,
            outcome_tracker=self._outcome_tracker,
            knowledge_pipeline=self._knowledge_pipeline,
        )

        # --- Phase 13.1: Governance (ConstraintRegistry → RuleEngine) ---
        self._constraint_registry = ConstraintRegistry()
        # --- Track A: Register GOV-008 (RESEARCH_INGEST) additively ---
        register_gov_008(self._constraint_registry)
        # --- Track B: Register GOV-009 (TOOLCHAIN_INGEST) additively ---
        register_gov_009(self._constraint_registry)
        # --- Track C: Register GOV-010 (LONGTERM_INGEST) additively ---
        register_gov_010(self._constraint_registry)
        # --- Track D: Register GOV-011 (REASONING_INGEST) additively ---
        register_gov_011(self._constraint_registry)
        self._rule_engine = RuleEngine(
            constraint_registry=self._constraint_registry,
        )

        # --- Phase 13.4: Create the EvolutionExecutionGateway ---
        # The gateway is the ONLY future entry point for self-modification.
        # It sits between approval and execution, validating every proposal
        # against governance rules.  Missing governance fails CLOSED.
        # Constructed after the Phase 16 application engine + request adapter
        # exist so it can expose the governed ``execute_request`` path.

        # --- Phase 16: Autonomy persistence foundation ---
        # Wired with a disabled AutonomyPolicy — no autonomous execution.
        # ScheduleStore is available for future request lifecycle management.
        self._autonomy_storage, self._schedule_store = (
            init_autonomy_persistence(self._event_bus)
        )

        # --- Phase 16: AuthorizationManager (kernel-private) ---
        # Enforces authority at the execution boundary. Uses the same
        # AutonomyPolicy as the ScheduleStore so authorization decisions are
        # consistent with the governed pipeline. Wired into the
        # ApplicationEngine so that ``apply`` refuses unauthorized requests
        # independently of any upstream caller.
        self._authorization_manager = AuthorizationManager(
            policy=(
                self._schedule_store.policy
                if self._schedule_store is not None
                else AutonomyPolicy()  # disabled by default — no autonomy
            ),
        )

        # --- Phase 16: ApplicationEngine (kernel-private) ---
        # Constructed after all required services (memory, knowledge, config,
        # capability registry) and the shared autonomy storage exist. Uses the
        # Batch 9 production adapters: readers for all four state scopes,
        # writers for MEMORY/KNOWLEDGE only (the Batch 10 INFORMATION
        # boundary). Not registered in ServiceContainer. No execution path is
        # created by construction alone. The authorization_manager enforces
        # authority at the execution boundary so the engine cannot be bypassed.
        self._application_engine = init_autonomy_application_engine(
            storage=self._autonomy_storage,
            knowledge_manager=self._knowledge_manager,
            memory_service=self._memory_service,
            configuration=self._config,
            capability_registry=self._capability_registry,
            authorization_manager=self._authorization_manager,
        )

        # --- Phase 16: AutonomyRequestAdapter (sole translator) ---
        # Translates an EvolutionRequest into the scope-pinned EvolutionProposal
        # the RuleEngine / gateway require (closed scope map, D2). Kernel-private.
        self._autonomy_request_adapter = AutonomyRequestAdapter()

        # --- Phase 13.4/16: Construct the gateway with the governed path ---
        # ``execute(proposal)`` semantics are unchanged; ``execute_request`` is
        # the sole applied-evolution path carrying the engine + adapter (D3/D15).
        self._execution_gateway = EvolutionExecutionGateway(
            execution_engine=self._execution_engine,
            rule_engine=self._rule_engine,
            evolution_memory=self._evolution_memory,
            application_engine=self._application_engine,
            autonomy_request_adapter=self._autonomy_request_adapter,
        )

        # --- Phase 16: Governed ingest sink (kernel-private, shared) ---
        # One sink instance persists bridge-produced EvolutionRequests as
        # DRAFTED records via the existing ScheduleStore.  Injected into the
        # three kernel-owned ingest bridges (Research, LongTerm, Reasoning).
        # ToolchainIngestBridge is created on-demand in CLI/skill-author
        # contexts (not kernel-owned) and uses its own fail-closed default.
        if self._schedule_store is not None:
            self._governed_ingest_sink = init_governed_ingest_sink(
                self._schedule_store
            )
            # Inject into the three kernel-owned bridges.
            if self._research_ingest_bridge is not None:
                self._research_ingest_bridge._sink = (  # noqa: SLF001
                    self._governed_ingest_sink
                )
            if self._longterm_ingest_bridge is not None:
                self._longterm_ingest_bridge._sink = (  # noqa: SLF001
                    self._governed_ingest_sink
                )
            if self._advanced_reasoning_ingest_bridge is not None:
                self._advanced_reasoning_ingest_bridge._sink = (  # noqa: SLF001
                    self._governed_ingest_sink
                )

        # --- Phase E6: Governed self-development loop ---
        # Construct one DevelopmentPlanner + one SelfDevelopmentLoop reusing the
        # existing kernel-owned LearningMemory and the governed approval gate.
        # The loop is bounded, never authorizes, and never writes to the real
        # repository. It is kernel-owned (not registered as a gateway service).
        # Stage C: the planner receives a CACHE-ONLY repository-map provider
        # (same pattern as DecisionIntelligence) for awareness-only target
        # validation — it never triggers a scan itself.
        self._development_planner = DevelopmentPlanner(
            repository_map_provider=lambda: self._repository_map,
            planning_context_provider=lambda: (
                self._decision_intelligence.get_planning_context()
                if self._decision_intelligence is not None
                else None
            ),
            # WS4: cache-only ArchitectureModel provider (same discipline as
            # the repository-map provider above). It yields the read-only
            # self-knowledge projection ONLY when the repository map is
            # already built — it never triggers a scan. Advisory development
            # evidence only; it can never authorize, execute, or promote.
            architecture_model_provider=lambda: (
                self.architecture_model()
                if self._repository_map is not None
                else None
            ),
        )
        learning_memory = getattr(self._learning_engine, "memory", None)
        self._self_development_loop = SelfDevelopmentLoop(
            planner=self._development_planner,
            learning_store=learning_memory,
        )

        # --- Phase 16.7 / F11: Boot activation & SAFE_MODE recovery ---
        # One pass of the EXISTING BootActivationService over the shared
        # autonomy storage: integrity check first; on a clean report, staged
        # config entries are activated and verified (requests transition to
        # COMPLETED/FAILED). An integrity failure => SAFE_MODE: base config,
        # overlay preserved, autonomous advancement suppressed for this
        # session (dispatcher not wired). Runs once per startup; never
        # retried; no background recovery; never runs from tick().
        if self._autonomy_storage is not None:
            self._boot_activation = init_boot_activation(
                storage=self._autonomy_storage,
                config_overlay=self._config_overlay,
            )
            integrity = self._boot_activation.check_integrity()
            if integrity.safe_mode:
                self._boot_report = integrity
            else:
                self._boot_report = (
                    self._boot_activation.activate_staged_configs()
                )

        # --- Phase 16 / Batch 13: Governed lifecycle dispatcher ---
        # Kernel-private consumer that advances DRAFTED requests to the
        # PENDING_AUTHORIZATION terminus and applies pre-authorized SCHEDULED
        # requests exclusively through gateway.execute_request(). It never
        # authorizes anything and is never registered in the ServiceContainer.
        # F11 SAFE_MODE: when boot recovery reported an integrity failure the
        # dispatcher is NOT wired — autonomous advancement stays disabled for
        # this session (tick()'s existing None-guard skips it).
        if (
            self._schedule_store is not None
            and not (self._boot_report is not None and self._boot_report.safe_mode)
        ):
            # Batch 15: wire the existing post-application lifecycle services
            # (VerificationService, RollbackManager, VersionManager) over the
            # shared AutonomySQLiteStorage + ApplicationEngine internals.
            self._autonomy_dispatcher = init_autonomy_dispatcher(
                schedule_store=self._schedule_store,
                execution_gateway=self._execution_gateway,
                application_engine=self._application_engine,
                storage=self._autonomy_storage,
            )

    # ------------------------------------------------------------------
    # Stage H — Promotion gate foundation (kernel-owned)
    # ------------------------------------------------------------------

    def _init_promotion_gate(self) -> None:
        """Stage H: wire the kernel-owned ``PromotionGate`` over the
        kernel-owned ``EvolutionMemory``.

        Composed once during ``start()`` after ``_init_evolution_pipeline()``
        so that ``self._evolution_memory`` exists. Pure wiring — no
        filesystem, git, or subprocess behavior; no auto-run; no
        integration with ``SelfDevelopmentLoop`` or the runtime
        coordinator. The gate is used by:

        * ``pending_promotion_reviews()`` — read-only view,
        * ``submit_development_for_promotion_review()`` — manual
          bridge that opens PENDING_REVIEW audit rows carrying
          bounded change evidence.
        """
        self._promotion_gate = PromotionGate(
            evolution_memory=self._evolution_memory,
        )

    # ------------------------------------------------------------------
    # Domain 7 — Runtime, Services & Container
    # ------------------------------------------------------------------

    def _init_runtime_services(self) -> None:
        """Wire the RuntimeCoordinator, scheduler, goal execution,
        cognition service, conversation, component registry, and
        service container — the final assembly of the running system.
        """
        # --- Phase 7.5: Create the RuntimeCoordinator (single orchestrator) ---
        self._runtime_coordinator = RuntimeCoordinator(
            memory_service=self._memory_service,
            knowledge_manager=self._knowledge_manager,
            understanding_engine=self._understanding_engine,
            world_model_engine=self._world_model_engine,
            reasoning_controller=self._reasoning_controller,
            capability_analyzer=self._capability_analyzer,
            capability_registry=self._capability_registry,
            capability_router=self._capability_router,
            capability_dispatcher=self._capability_dispatcher,
            planning_engine=self._planning_engine,
            tool_engine=self._tool_engine,
            ai_service=self._ai_manager.service,
            reflection_engine=self._reflection_engine,
            reasoning_recorder=self._reasoning_recorder,
            learning_manager=self._learning_manager,
            knowledge_feedback=self._knowledge_feedback,
            learning_engine=self._learning_engine,
            evolution_observation_engine=self._self_observation_engine,
            identity_engine=self._identity_engine,
            feedback_coordinator=self._feedback_coordinator,
            goal_intelligence_engine=self._goal_intelligence_engine,
            conversation_service=None,  # Wired below
            improvement_planner=self._improvement_planner,
            proposal_generator=self._proposal_generator,
            approval_manager=self._approval_manager,
            evolution_memory=self._evolution_memory,
            intelligence_engine=self._intelligence_engine,
        )

        # --- Phase 13.3: Create the EvolutionScheduler and inject into RuntimeCoordinator ---
        self._evolution_scheduler = EvolutionScheduler(
            observation_engine=self._self_observation_engine,
            improvement_planner=self._improvement_planner,
            proposal_generator=self._proposal_generator,
            approval_manager=self._approval_manager,
            evolution_memory=self._evolution_memory,
            intelligence_engine=self._intelligence_engine,
            knowledge_pipeline=self._knowledge_pipeline,
            decision_intelligence=self._decision_intelligence,
            tick_interval=10,
            min_observations=5,
            research_evidence_provider=lambda: self._last_research_evidence,
        )
        self._runtime_coordinator.set_evolution_scheduler(self._evolution_scheduler)

        # --- Phase 15.0: Goal Execution Engine ---
        # Create binder registry with the single Phase 15 binder
        self._binder_registry = ExecutionActionBinderRegistry()
        tool_binder = ToolExecutionActionBinder(tool_engine=self._tool_engine)
        self._binder_registry.register(tool_binder)

        self._goal_executor = GoalExecutionEngine(
            repository=self._goal_repository,
            execution_gateway=self._execution_gateway,
            binder_registry=self._binder_registry,
            outcome_tracker=self._outcome_tracker,
            evolution_memory=self._evolution_memory,
            decision_intelligence=self._decision_intelligence,
            event_bus=self._event_bus,
        )

        # Inject Phase 9.0 components after RuntimeCoordinator construction
        self._runtime_coordinator.set_experience_accumulator(self._experience_accumulator)
        self._runtime_coordinator.set_self_model_engine(self._self_model_engine)

        # Set event bus
        self._runtime_coordinator._event_bus = self._event_bus

        # --- Phase 7.5.1: CognitionService delegates to RuntimeCoordinator ---
        self._cognition_service = CognitionService(
            memory_service=self._memory_service,
            knowledge_manager=self._knowledge_manager,
            learning_manager=self._learning_manager,
            knowledge_feedback=self._knowledge_feedback,
            event_bus=self._event_bus,
            reasoning_controller=self._reasoning_controller,
            capability_analyzer=self._capability_analyzer,
            capability_registry=self._capability_registry,
            capability_router=self._capability_router,
            capability_dispatcher=self._capability_dispatcher,
            reasoning_recorder=self._reasoning_recorder,
            reflection_engine=self._reflection_engine,
            planning_engine=self._planning_engine,
            tool_engine=self._tool_engine,
            runtime_coordinator=self._runtime_coordinator,
        )

        self._cognition_api = CognitionAPI(
            cognition_service=self._cognition_service,
        )

        context_engine = ContextEngine(memory_service=self._memory_service)

        # --- P1/B1.2: Session-scoped context ---
        # In-memory session registry bound to the kernel-owned AuthorityService.
        # An Owner session is established for the current single-owner CLI flow;
        # User sessions are created on demand via start_user_session().
        self._session_manager = SessionManager(authority_service=self._authority_service)  # type: ignore[arg-type]
        try:
            _owner_session = self._session_manager.create_session(self._authority_service.owner.principal_id)  # type: ignore[union-attr]
            self._session_context = SessionContext.from_session(_owner_session, action="owner_session")
        except Exception:
            self._session_context = None

        # --- P3/B3.1+B3.2: Interaction capture + learning integration ---
        # One InteractionRecorder + InteractionRepository (B3.1) and one
        # InteractionLearningBridge (B3.2) composing the EXISTING
        # LearningMemory into a principal-scoped, advisory planning-context
        # provider. Kernel-private (not registered in the container; the
        # container key-set is exact-set-tested). Never auto-runs; never
        # executes anything; never touches tick()/RuntimeCoordinator.
        try:
            from atlas.interaction.learning_bridge import InteractionLearningBridge
            from atlas.interaction.recorder import InteractionRecorder
            from atlas.interaction.repository import InteractionRepository

            learning_memory = getattr(self._learning_engine, "memory", None)
            self._interaction_repository = InteractionRepository()
            self._interaction_recorder = InteractionRecorder(
                repository=self._interaction_repository,
            )
            self._interaction_learning_bridge = InteractionLearningBridge(
                repository=self._interaction_repository,
                learning_memory=learning_memory,
            )
            provider = self._interaction_learning_bridge.planning_context_provider(
                self._session_context.principal_id
                if self._session_context is not None
                else ""
            )
            if provider is not None:
                self._interaction_context_provider = provider
        except Exception:
            self._interaction_repository = None
            self._interaction_recorder = None
            self._interaction_learning_bridge = None
            self._interaction_context_provider = None

        # --- Phase 6.1: Deterministic Fallback Resolver ---
        try:
            from atlas.conversation.deterministic_fallback import DeterministicFallbackResolver

            self._deterministic_fallback = DeterministicFallbackResolver(
                knowledge_manager=self._knowledge_manager,
                tool_registry=self._tool_registry,
            )
        except Exception:
            self._deterministic_fallback = None

        # --- Phase 1 (+ Phase 3): Built-In Conversational Response Service ---
        # Model-independent deterministic responses for casual conversational
        # turns. Shares the kernel-owned registries/services read-only;
        # never calls a provider and never mutates anything.
        try:
            from atlas.conversation.builtin_response import BuiltinResponseService

            self._builtin_response = BuiltinResponseService(
                tool_registry=self._tool_registry,
                knowledge_manager=self._knowledge_manager,
                capability_registry=self._capability_registry,
                memory_service=self._memory_service,
                # Lazy provider: the service container is populated later in
                # this same startup sequence, so the status answer must
                # resolve the registration snapshot on demand rather than
                # capture it before any service is registered.
                service_names=self._container.names,
                # Built only during start(); only usable after start.
                started=True,
                # WS — bounded conversational self-knowledge. Cache-only: the
                # snapshot never triggers a repository scan, so asking a casual
                # architecture question cannot cause one. Read-only/advisory.
                architecture_model_provider=self._architecture_model_snapshot,
                # G2 — bounded RELATIONSHIP snapshot for an EXPLICIT named-target
                # dependency/impact question. This is the SAME
                # ``architecture_model()`` the CLI/API expose: it builds the
                # repository map at most once per process through the existing
                # builder and caches it on the kernel. It is consulted by the
                # conversational renderer only when the turn names an explicit
                # dotted target, so a casual architecture question still never
                # triggers a scan. Read-only/advisory; it can never authorize,
                # execute, or promote anything.
                architecture_relationship_provider=self.architecture_model,
                # G2 — structured sufficiency/acquisition reporting for a
                # knowledge question the local store could not answer. This is
                # the EXISTING knowledge-decision service used by
                # ``answer_knowledge_question``; the conversation layer only
                # REPORTS its decision (status + governed-acquisition outcome)
                # and never gains authority from it.
                knowledge_status_provider=self._knowledge_status,
                # D3 — knowledge-decision provider: local-first validated
                # knowledge, else governed D2 acquisition. Deny-by-default, so
                # with no authorized source configured the C6.1 outcome is
                # rendered unchanged and no network access occurs.
                knowledge_decision_provider=self._knowledge_decision_enrich,
                # C6.1 — bounded conversational access to EXISTING validated
                # knowledge. The kernel capability is passed through unchanged
                # (read-only, deterministic, no model): the conversation layer
                # never queries storage directly and never acquires anything.
                validated_knowledge_provider=self.validated_knowledge,
            )
        except Exception:
            self._builtin_response = None

        try:
            conversation_timeout_s = float(
                self._config.get("ai", "conversation_timeout_s", default=20.0)
            )
        except (TypeError, ValueError):
            conversation_timeout_s = 20.0

        # L4 — bounded known-entity catalog for deterministic entity
        # identification. Built from the registries AFTER they are populated
        # (registration happens earlier in startup), so the names are complete;
        # an unmatched name is simply not identified, so a stale catalog can
        # only lose evidence, never invent any.
        from atlas.conversation.entity_identification import EntityCatalog

        entity_catalog = EntityCatalog.from_names(
            {
                "capability": self._capability_registry.registered_names,
                "tool": [tool.name for tool in self._tool_registry.list()],
            }
        )

        self._conversation = ConversationService(
            self._ai_manager.service,
            context_engine=context_engine,
            cognition_api=self._cognition_api,
            # Step 1 — the kernel-owned intake. Deterministic by default; the
            # OPTIONAL model-assisted parsing seam is wired only when external
            # providers are explicitly enabled (see _build_task_intake).
            task_intake=self._build_task_intake(),
            development_bridge=self._development_bridge,
            # G3 — the governed self-development route: a conversational
            # development request reaches the EXISTING bounded DevelopmentDriver
            # (gap -> authoring -> envelope-authorized sandbox -> verification ->
            # promotion request). Duck-typed, kernel-owned: the conversation layer
            # never imports atlas.evolution, never approves, never promotes, and
            # tick() never invokes it.
            development_driver_bridge=self._development_driver_bridge,
            orchestration_resolver=self._orchestration_bridge,
            session_context=self._session_context,
            fallback_resolver=self._deterministic_fallback,
            builtin_response=self._builtin_response,
            provider_call_timeout_s=conversation_timeout_s,
            development_need_coordinator=DevelopmentNeedCoordinator(),
            investigation_service=InvestigationService(),
            approval_manager=self._approval_manager,
            development_execution_bridge=self._development_execution_bridge,
            proposal_change_supplier=self._proposal_change_supplier,
            autonomy_check=self._autonomy_check,
            entity_catalog=entity_catalog,
        )
        # P2/B2.4 — wire orchestration experience capture through the
        # existing ExperienceAccumulator (no schema/migration, no tick change).
        try:
            if hasattr(self._conversation, "set_experience_capture"):
                self._conversation.set_experience_capture(self._experience_accumulator)
        except Exception:
            pass

        # Wire conversation into the runtime coordinator
        self._runtime_coordinator._conversation_service = self._conversation

        # --- P4: Collective learning (candidate → governed approval → collective) ---
        # One kernel-owned CollectiveRepository + CollectiveGovernance, driven by
        # the EXISTING ApprovalManager + AuthorityService + EvolutionMemory.
        # Kernel-private (not registered in ServiceContainer — the container key-set
        # is exact-set-tested). Never auto-runs; never touches tick()/RuntimeCoordinator.
        try:
            from atlas.collective.governance import CollectiveGovernance
            from atlas.collective.repository import CollectiveRepository
            self._collective_repository = CollectiveRepository()
            self._collective_governance = CollectiveGovernance(
                repository=self._collective_repository,
                authority_service=self._authority_service,
                approval_manager=self._approval_manager,
                evolution_memory=self._evolution_memory,
            )
        except Exception:
            self._collective_repository = None
            self._collective_governance = None

        # --- P2/B2.2: Governed orchestration executor ---
        # Composes EXISTING execution seams only (ToolExecutor,
        # CapabilityDispatcher, InformationAcquisitionService, AuthorityService).
        # WorkspaceService is not kernel-owned, so the workspace seam fails
        # closed. Kernel-private (no container registration — the container
        # key-set is exact-set-tested); never touches tick().
        self._orchestration_executor = OrchestrationExecutor(
            capability_registry=self._capability_registry,
            capability_dispatcher=self._capability_dispatcher,
            tool_executor=self._tool_executor,
            workspace_service=None,
            research_service=self._acquisition_service,
            authority_service=self._authority_service,
        )

        # --- Phase 13.2: Register core components in the registry ---
        self._register_components()

        # --- Service container registration ---
        self._container.register("component_registry", self._component_registry)
        self._container.register("ai", self._ai_manager.service)
        self._container.register("conversation", self._conversation)
        self._container.register("memory", self._memory_service)
        self._container.register("knowledge", self._knowledge_manager)
        self._container.register("cognition", self._cognitive_loop)
        self._container.register("cognitive", self._cognitive_service)
        self._container.register("cognition_service", self._cognition_service)
        self._container.register("cognition_api", self._cognition_api)
        self._container.register("tasks", self._task_manager)
        # --- Phase 7.5: Register runtime coordinator ---
        self._container.register("runtime_coordinator", self._runtime_coordinator)
        self._container.register("understanding", self._understanding_engine)
        self._container.register("world_model", self._world_model_engine)
        self._container.register("evolution_observer", self._self_observation_engine)
        self._container.register("learning_engine", self._learning_engine)
        self._container.register("identity", self._identity_engine)
        self._container.register("authority", self._authority_service)
        self._container.register("feedback_coordinator", self._feedback_coordinator)
        self._container.register("goal_repository", self._goal_repository)
        self._container.register("goal_intelligence", self._goal_intelligence_engine)
        # --- Phase 9.0: Register experience & self-model services ---
        self._container.register("experience_repository", self._experience_repository)
        self._container.register("experience_accumulator", self._experience_accumulator)
        self._container.register("self_model_engine", self._self_model_engine)
        # --- Phase 12.2: Register evolution intelligence engine ---
        self._container.register("intelligence_engine", self._intelligence_engine)
        # --- Phase 13.4: Register evolution execution gateway ---
        self._container.register("execution_gateway", self._execution_gateway)
        # --- Phase 13.5: Register persistent evolution knowledge ---
        self._container.register("evolution_knowledge", self._knowledge_query)
        # --- Phase 15.0: Register goal execution engine ---
        self._container.register("goal_execution", self._goal_executor)

        self._container.start_all()
        self._started = True

        self._state_manager.update({"status": "running", "health": "healthy"})
        self._event_bus.publish("atlas.started", {"status": "running"})

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self):
        self._task_manager.tick()
        if self._evolution_scheduler is not None:
            self._evolution_scheduler.tick()
        if self._goal_executor is not None:
            self._goal_executor.settle()
        # Phase 16 / Batch 13 — governed lifecycle. One non-blocking settle.
        if self._autonomy_dispatcher is not None:
            self._autonomy_dispatcher.settle()

    # ------------------------------------------------------------------
    # Pipeline event consumers
    # ------------------------------------------------------------------

    def _record_longterm_from_pipeline(self, payload: Any) -> None:
        """Track C additive consumer: record the latest experience as an episode.

        Subscribed to ``runtime.pipeline.completed`` (published by the
        RuntimeCoordinator after experience accumulation).  This is an
        additive consumer — the 15-stage pipeline order is untouched.
        Failures are swallowed so the pipeline event never breaks.
        """
        if self._experience_accumulator is None or self._longterm_recorder is None:
            return
        if (
            self._episodic_repository is None
            or self._procedure_extractor is None
            or self._procedural_repository is None
        ):
            return
        try:
            experiences = self._experience_accumulator.repository.get_experiences(n=1)
            if not experiences:
                return
            episode = self._longterm_recorder.record(experiences[0])
            self._episodic_repository.store_episode(episode)
            procedures = self._procedure_extractor.extract(
                self._episodic_repository.get_episodes(n=500)
            )
            for procedure in procedures:
                self._procedural_repository.store_procedure(procedure)
        except Exception:
            self._event_bus.publish(
                "longterm.recording.failed",
                {"source": "runtime.pipeline.completed"},
            )

    def _record_reasoning_from_pipeline(self, payload: Any) -> None:
        """Track D additive consumer: record the latest experience as a trace.

        Subscribed to ``runtime.pipeline.completed`` (published by the
        RuntimeCoordinator after experience accumulation).  This is an
        additive consumer — the 15-stage pipeline order is untouched.
        Failures are swallowed so the pipeline event never breaks.
        """
        if self._advanced_reasoning_recorder is None:
            return
        try:
            if self._experience_accumulator is None:
                return
            experiences = self._experience_accumulator.repository.get_experiences(n=1)
            if not experiences:
                return
            experience = experiences[0]
            from atlas.advanced_reasoning.models import (
                ReasoningStrategy,
                ReasoningTrace,
                TraceStatus,
            )

            recorded = ReasoningTrace(
                trace_id=f"trace:pipeline:{experience.experience_id}",
                question=str(getattr(experience, "user_input", "") or "pipeline experience"),
                strategy=ReasoningStrategy.DECOMPOSE,
                status=TraceStatus.COMPLETED,
                conclusion="",
                confidence=0.0,
                metadata={
                    "source": "runtime.pipeline.completed",
                    "experience_id": experience.experience_id,
                },
            )
            self._advanced_reasoning_recorder.record(recorded)
        except Exception:
            self._event_bus.publish(
                "reasoning.recording.failed",
                {"source": "runtime.pipeline.completed"},
            )

    # ------------------------------------------------------------------
    # Conversation API
    # ------------------------------------------------------------------

    def chat(self, text: str):
        if not self._started:
            raise RuntimeError("Atlas has not been started.")
        return self._conversation.send(text)  # type: ignore[union-attr]

    def stream(self, text: str) -> Iterator[str]:
        if not self._started:
            raise RuntimeError("Atlas has not been started.")
        yield from self._conversation.stream(text)  # type: ignore[union-attr]

    def save_conversation(self) -> Path:
        if not self._started:
            raise RuntimeError("Atlas has not been started.")
        return self._conversation.save()  # type: ignore[union-attr]

    def load_conversation(self, filepath: Path):
        if not self._started:
            raise RuntimeError("Atlas has not been started.")
        return self._conversation.load(filepath)  # type: ignore[union-attr]

    def saved_conversations(self):
        if not self._started:
            raise RuntimeError("Atlas has not been started.")
        return self._conversation.saved_conversations()  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Phase 13.2: Component Registry
    # ------------------------------------------------------------------

    @property
    def component_registry(self) -> ComponentRegistry:
        """Return the ComponentRegistry for structural self-observation."""
        return self._component_registry

    def capability_model(self):
        """Return the canonical deterministic capability model (C5.1).

        READ-ONLY projection over the existing authoritative registries
        (ComponentRegistry, CapabilityRegistry, ToolRegistry). It never mutates
        registries, persists nothing, performs no network I/O, and does not
        call an external AI model.
        """
        from atlas.self_knowledge.capability_model import build_capability_model

        return build_capability_model(
            component_registry=self._component_registry,
            capability_registry=self._capability_registry,
            tool_registry=self._tool_registry,
        )

    def architecture_model(self):
        """Return the read-only architecture self-knowledge model (Phase 1.2).

        READ-ONLY projection over the existing authoritative structural sources
        (``ComponentRegistry``, the C5.1 ``CapabilityModel``, and the cached
        ``RepositoryMap``). It never mutates registries or the repository map,
        persists nothing, performs no network I/O, and does not call an external
        AI model. When the repository map is unavailable, module-level facts are
        omitted and reported honestly.
        """
        from atlas.self_knowledge.architecture_model import build_architecture_model

        return build_architecture_model(
            component_registry=self._component_registry,
            capability_model=self.capability_model(),
            repository_map=self.repository_map,
        )

    def _architecture_model_snapshot(self):
        """Cache-only ArchitectureModel snapshot for the conversational floor.

        READ-ONLY and deterministic. Built directly from the registries plus the
        ALREADY-CACHED repository map attribute — unlike ``architecture_model()``
        it never triggers a repository scan, so a casual architecture question
        cannot cause one. When the map has not been built, the model honestly
        omits module-level facts (the map is passed as None and the model's
        limitations state so).
        """
        from atlas.self_knowledge.architecture_model import build_architecture_model

        return build_architecture_model(
            component_registry=self._component_registry,
            capability_model=self.capability_model(),
            repository_map=self._repository_map,
        )

    def validated_knowledge(self, query: str):
        """Return validated (SUPPORTED) persisted research knowledge (C6.1).

        READ-ONLY, deterministic retrieval over the kernel-owned research
        storage (``research_claims``/``research_verifications``/
        ``research_citations``). It never mutates, persists nothing, performs
        no network I/O, and does not call an external model. Unavailable or
        errored storage fails closed and never falls back to unvalidated
        in-memory knowledge.
        """
        from atlas.research.validated_retrieval import (
            ValidatedKnowledgeRetriever,
        )

        return ValidatedKnowledgeRetriever(self._research_storage).retrieve(query)

    def _register_components(self) -> None:
        """Register all core components in the ComponentRegistry.

        Iterates over CORE_COMPONENTS definitions and registers each
        one.  This is purely observational — the registry never modifies,
        restarts, or repairs any component.
        """
        for metadata in CORE_COMPONENTS:
            try:
                self._component_registry.register(metadata)
            except ValueError:
                # Duplicate registration should not happen with the
                # predefined definitions, but is safely ignored if it does.
                pass

        # --- Track A: Register research component metadata (Phase 17.9) ---
        try:
            register_research_component(self._component_registry)
        except ValueError:
            pass

        # --- Track B: Register toolchain component metadata (Phase 18.10) ---
        try:
            register_toolchain_component(self._component_registry)
        except ValueError:
            pass
        try:
            register_toolchain_evolution_component(self._component_registry)
        except ValueError:
            pass

        # --- Track C: Register long-term component metadata (Phase 19.5) ---
        try:
            register_longterm_component(self._component_registry)
        except ValueError:
            pass
        try:
            register_longterm_evolution_component(self._component_registry)
        except ValueError:
            pass

        # --- Track D: Register advanced-reasoning component metadata ---
        try:
            register_advanced_reasoning_component(self._component_registry)
        except ValueError:
            pass
        try:
            register_advanced_reasoning_evolution_component(self._component_registry)
        except ValueError:
            pass

        # Mark all registered components as HEALTHY since they were
        # successfully created during startup.
        for component in self._component_registry.get_all():
            self._component_registry.update_status(
                component.name,
                ComponentStatus.HEALTHY,
            )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self):
        if not self._started:
            return

        # --- Phase 9.1: Persist pending self-model snapshot before cleanup ---
        if self._self_model_engine is not None and self._experience_repository is not None:
            snapshot = self._self_model_engine.get_snapshot()
            if snapshot is not None:
                self._experience_repository.persist_snapshot(snapshot_to_dict(snapshot))

            storage = getattr(self._experience_repository, "_storage", None)
            if storage is not None and hasattr(storage, "close"):
                try:
                    storage.close()
                    self._event_bus.publish("experience.storage.closed", {})
                except Exception:
                    pass

        if self._understanding_engine is not None:
            try:
                self._understanding_engine.close()
            except Exception:
                pass

        self._container.stop_all()
        self._container.clear()

        self._conversation = None
        self._memory_service = None
        self._knowledge_manager = None
        self._cognitive_loop = None
        self._cognitive_service = None
        self._cognition_service = None
        self._cognition_api = None

        # --- Phase 7.5: Cleanup ---
        self._runtime_coordinator = None
        self._understanding_engine = None
        self._world_model_engine = None
        self._self_observation_engine = None
        self._learning_engine = None
        self._identity_engine = None
        self._authority_service = None
        self._session_manager = None
        self._session_context = None
        self._orchestration_executor = None

        # --- P3/B3.1+B3.2: Interaction capture cleanup ---
        self._interaction_repository = None
        self._interaction_recorder = None
        self._interaction_learning_bridge = None
        self._interaction_context_provider = None

        # --- Phase 12.2: Cleanup ---
        self._intelligence_engine = None
        self._insight_scorer = None

        # --- Phase 13.3: Cleanup ---
        self._evolution_scheduler = None

        # --- Phase 13.4: Cleanup ---
        self._execution_gateway = None
        self._rule_engine = None
        self._development_planner = None
        self._self_development_loop = None
        self._environment_observer = None
        self._lifecycle_assessor = None
        self._adaptation_engine = None
        self._adaptation_evaluator = None
        self._adaptation_orchestrator = None
        self._operation_controller = None
        self._development_controller = None
        self._ai_availability = None
        self._self_management_review = None
        self._external_acquirer = None
        self._knowledge_decision = None
        self._work_orchestrator = None
        self._development_run_orchestrator = None
        self._boot_activation = None
        self._boot_report = None

        # --- P4: Collective learning cleanup ---
        self._collective_repository = None
        self._collective_governance = None

        # --- P5: Proactive Advisor cleanup ---
        self._proactive_advisor = None

        # --- Phase 15.0: Cleanup ---
        self._goal_executor = None
        self._binder_registry = None

        # --- Phase 14.4: Cleanup ---
        self._decision_intelligence = None

        # --- Phase 13.6: Cleanup ---
        self._knowledge_pipeline = None

        # --- Track A: Cleanup (storage close + kernel-private refs) ---
        if self._research_storage is not None:
            try:
                self._research_storage.close()
            except Exception:
                pass
        self._research_storage = None
        self._research_factory = None
        self._research_coordinator = None
        self._research_ingest_bridge = None
        self._acquisition_service = None

        # --- Track C: Cleanup ---
        if self._longterm_storage is not None:
            try:
                self._longterm_storage.close()
            except Exception:
                pass
        self._longterm_storage = None
        self._episodic_repository = None
        self._procedural_repository = None
        self._longterm_recorder = None
        self._procedure_extractor = None
        self._longterm_consolidator = None
        self._longterm_factory = None
        self._longterm_ingest_bridge = None

        # --- Phase 16: Autonomy persistence cleanup ---
        shutdown_autonomy_persistence(self._autonomy_storage)
        self._autonomy_storage = None
        self._schedule_store = None
        self._application_engine = None
        self._governed_ingest_sink = None
        self._autonomy_request_adapter = None
        self._autonomy_dispatcher = None

        # --- Track D: Cleanup ---
        if self._advanced_reasoning_storage is not None:
            try:
                self._advanced_reasoning_storage.close()
            except Exception:
                pass
        self._advanced_reasoning_storage = None
        self._advanced_reasoning_repository = None
        self._advanced_reasoning_service = None
        self._advanced_reasoning_factory = None
        self._advanced_reasoning_recorder = None
        self._advanced_reasoning_ingest_bridge = None
        self._advanced_reasoning_evidence_provider = None
        self._advanced_reasoning_causal_provider = None

        self._learning_manager = None
        self._knowledge_feedback = None
        self._reasoning_controller = None
        self._capability_analyzer = None
        self._capability_registry = None
        self._capability_router = None
        self._capability_dispatcher = None
        self._reasoning_recorder = None
        self._reflection_engine = None
        self._planning_engine = None
        self._tool_engine = None
        self._tool_executor = None
        self._tool_selector = None
        self._tool_registry = None
        self._deterministic_fallback = None
        self._builtin_response = None
        self._model_profile_registry = None
        self._model_router = None

        self._started = False

        self._state_manager.update({"status": "stopped", "health": "offline"})
        self._event_bus.publish("atlas.shutdown", {"status": "stopped"})
