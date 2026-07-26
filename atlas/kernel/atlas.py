"""
Atlas Kernel

The root application object.
Phase 7.5 — Wires RuntimeCoordinator and all cognitive subsystems.
"""

from collections.abc import Iterator
from pathlib import Path

from atlas.ai.ai_manager import AIManager
from atlas.ai.routing.models import ModelProfile
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
from atlas.learning_engine.learning_engine import LearningEngine
from atlas.identity.identity_engine import IdentityEngine
from atlas.goals.goal_intelligence_engine import GoalIntelligenceEngine
from atlas.goals.goal_repository import GoalRepository


class Atlas:
    """
    Root object for the Atlas application.

    Phase 7.5 — Wires all cognitive subsystems through the
    RuntimeCoordinator, the single permanent orchestrator.
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
    def started(self):
        return self._started

    @property
    def provider(self):
        return self._ai_manager.provider

    def models(self):
        return self._ai_manager.service.models()

    def start(self):
        if self._started:
            return

        self._config.load()

        provider = str(self._config.get("ai", "provider"))
        model = str(self._config.get("ai", "model"))
        timeout = int(self._config.get("ai", "timeout"))  # type: ignore[arg-type]

        # --- Model routing ---
        self._model_profile_registry = ModelProfileRegistry()
        self._model_profile_registry.register(
            ModelProfile(
                provider_name="Mock Provider",
                model_name="atlas-mock-v1",
                complexity_score=0.3,
                latency_class="fast",
                cost_tier=0.1,
                supported_tasks=["conversation"],
                priority=10,
            )
        )
        self._model_profile_registry.register(
            ModelProfile(
                provider_name="Ollama",
                model_name=model,
                complexity_score=0.8,
                latency_class="medium",
                cost_tier=0.2,
                supported_tasks=["conversation", "analysis", "code"],
                priority=20,
            )
        )
        self._model_router = ModelRouter(self._model_profile_registry)

        api_keys = self._config.get("ai", "api_keys")
        self._ai_manager.initialize(
            provider, model, timeout,
            model_router=self._model_router,
            api_keys=api_keys,  # type: ignore[arg-type]
        )

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

        # --- Reasoning pipeline ---
        self._capability_registry = CapabilityRegistry()
        for capability_name, handler in DEFAULT_HANDLERS.items():
            self._capability_registry.register(capability_name, handler)

        self._reasoning_controller = ReasoningController()
        self._capability_analyzer = CapabilityAnalyzer()
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

        # --- Phase 7.5: Wire all cognitive subsystems ---
        self._understanding_engine = UnderstandingEngine()
        self._world_model_engine = WorldModelEngine()
        self._self_observation_engine = SelfObservationEngine()
        self._learning_engine = LearningEngine()
        self._identity_engine = IdentityEngine()
        self._identity_engine.initialize()

        # --- Phase 8.3: Goal Intelligence Engine ---
        self._goal_repository = GoalRepository()
        self._goal_intelligence_engine = GoalIntelligenceEngine(
            repository=self._goal_repository,
        )

        # --- Phase 8.2: Create FeedbackCoordinator ---
        self._feedback_coordinator = FeedbackCoordinator(
            identity_engine=self._identity_engine,
            world_model_engine=self._world_model_engine,
            understanding_engine=self._understanding_engine,
            learning_engine=self._learning_engine,
        )

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
            event_bus=self._event_bus,
        )

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

        # --- Service container registration ---
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

        self._container.start_all()
        self._started = True

        self._state_manager.update({"status": "running", "health": "healthy"})
        self._event_bus.publish("atlas.started", {"status": "running"})

    def tick(self):
        self._task_manager.tick()

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

    def shutdown(self):
        if not self._started:
            return

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