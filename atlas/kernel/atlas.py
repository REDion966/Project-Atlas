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
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.ai.routing.router import ModelRouter
from atlas.config.configuration import Configuration
from atlas.conversation.conversation_service import ConversationService
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
from atlas.learning_engine.learning_engine import LearningEngine
from atlas.identity.identity_engine import IdentityEngine
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
from atlas.evolution.autonomy.autonomy_request_adapter import (
    AutonomyRequestAdapter,
)
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

        self._learning_manager: LearningManager | None = None
        self._knowledge_feedback: KnowledgeFeedback | None = None
        self._started = False

        # --- Phase 13.2: Component Registry ---
        self._component_registry = ComponentRegistry()

        # --- Phase 13.3: Evolution Scheduler ---
        self._evolution_scheduler: EvolutionScheduler | None = None

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
        return self._acquisition_service.acquire(
            question=question,
            sources=sources,
            knowledge_refs=knowledge_refs,
            query_id=query_id,
        )

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
        """
        self._development_controller = DevelopmentCycleController(
            approval_manager=self._approval_manager,
            researcher=(
                self._acquisition_service.acquire
                if self._acquisition_service is not None
                else None
            ),
        )

    @property
    def development_controller(self):
        """Return the kernel-owned DevelopmentCycleController (Phase F9)."""
        return self._development_controller

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

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def container(self):
        return self._container

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
        return self._self_development_loop.run(proposal, max_iterations=max_iterations)

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
        self._model_router = ModelRouter(self._model_profile_registry)

        self._ai_manager = AIManager(
            model_profile_registry=self._model_profile_registry,
        )

        api_keys = self._config.get("ai", "api_keys")
        allow_fallback = bool(self._config.get("ai", "allow_fallback", default=False))
        self._ai_manager.initialize(
            provider, model, timeout,
            model_router=self._model_router,
            api_keys=api_keys,  # type: ignore[arg-type]
            allow_fallback=allow_fallback,
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
        self._decision_intelligence = DecisionIntelligenceEngine(
            knowledge_query=self._knowledge_query,
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

        # --- Phase 16: ApplicationEngine (kernel-private) ---
        # Constructed after all required services (memory, knowledge, config,
        # capability registry) and the shared autonomy storage exist. Uses the
        # Batch 9 production adapters: readers for all four state scopes,
        # writers for MEMORY/KNOWLEDGE only (the Batch 10 INFORMATION
        # boundary). Not registered in ServiceContainer. No execution path is
        # created by construction alone.
        self._application_engine = init_autonomy_application_engine(
            storage=self._autonomy_storage,
            knowledge_manager=self._knowledge_manager,
            memory_service=self._memory_service,
            configuration=self._config,
            capability_registry=self._capability_registry,
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
        self._development_planner = DevelopmentPlanner()
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

        self._conversation = ConversationService(
            self._ai_manager.service,
            context_engine=context_engine,
            cognition_api=self._cognition_api,
        )

        # Wire conversation into the runtime coordinator
        self._runtime_coordinator._conversation_service = self._conversation

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
        self._boot_activation = None
        self._boot_report = None

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
        self._model_profile_registry = None
        self._model_router = None

        self._started = False

        self._state_manager.update({"status": "stopped", "health": "offline"})
        self._event_bus.publish("atlas.shutdown", {"status": "stopped"})
