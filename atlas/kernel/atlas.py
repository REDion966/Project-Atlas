"""
Atlas Kernel

The root application object.
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

from atlas.services.cognition_service import CognitionService

from atlas.state.state_manager import StateManager
from atlas.task.task_manager import TaskManager


class Atlas:
    """
    Root object for the Atlas application.
    """

    def __init__(self):

        self._container = ServiceContainer()

        self._event_bus = EventBus()

        self._state_manager = StateManager(
            self._event_bus
        )

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

        self._reasoning_controller: ReasoningController | None = None

        self._model_profile_registry: ModelProfileRegistry | None = None

        self._model_router: ModelRouter | None = None

        self._capability_analyzer: CapabilityAnalyzer | None = None

        self._capability_registry: CapabilityRegistry | None = None

        self._capability_router: CapabilityRouter | None = None

        self._capability_dispatcher: CapabilityDispatcher | None = None

        self._reasoning_recorder: ReasoningRecorder | None = None

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
        """
        Return Atlas cognitive loop.
        """

        return self._cognitive_loop

    @property
    def cognition_api(self):
        """
        Return the public Cognition API.
        """

        return self._cognition_api


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

        provider = str(self._config.get(
            "ai",
            "provider",
        ))

        model = str(self._config.get(
            "ai",
            "model",
        ))

        timeout = int(self._config.get(
            "ai",
            "timeout",
        ))


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

        self._model_router = ModelRouter(
            self._model_profile_registry,
        )

        self._ai_manager.initialize(
            provider,
            model,
            timeout,
            model_router=self._model_router,
        )


        repository = MemoryRepository()

        ranking_engine = RankingEngine()

        search_engine = MemorySearchEngine(
            repository,
            ranking_engine,
        )


        self._memory_service = MemoryManagerService(
            repository=repository,
            ranking_engine=ranking_engine,
            search_engine=search_engine,
        )


        self._knowledge_manager = KnowledgeManager()


        self._cognitive_loop = CognitiveLoop(
            memory_service=self._memory_service,
            knowledge_manager=self._knowledge_manager,
        )

        self._cognitive_service = CognitiveService(
            cognitive_loop=self._cognitive_loop
        )

        self._learning_manager = LearningManager()
        self._knowledge_feedback = KnowledgeFeedback()

        self._capability_registry = CapabilityRegistry()

        for capability_name, handler in DEFAULT_HANDLERS.items():
            self._capability_registry.register(capability_name, handler)

        self._reasoning_controller = ReasoningController()
        self._capability_analyzer = CapabilityAnalyzer()
        self._capability_router = CapabilityRouter(self._capability_registry)
        self._capability_dispatcher = CapabilityDispatcher(self._capability_registry)
        self._reasoning_recorder = ReasoningRecorder()

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
        )

        self._cognition_api = CognitionAPI(
            cognition_service=self._cognition_service,
        )


        context_engine = ContextEngine(
            memory_service=self._memory_service,
        )


        self._conversation = ConversationService(
            self._ai_manager.service,
            context_engine=context_engine,
            cognition_api=self._cognition_api,
        )


        self._container.register(
            "ai",
            self._ai_manager.service,
        )

        self._container.register(
            "conversation",
            self._conversation,
        )

        self._container.register(
            "memory",
            self._memory_service,
        )

        self._container.register(
            "knowledge",
            self._knowledge_manager,
        )

        self._container.register(
            "cognition",
            self._cognitive_loop,
        )

        self._container.register(
            "cognitive",
            self._cognitive_service,
        )

        self._container.register(
            "cognition_service",
            self._cognition_service,
        )

        self._container.register(
            "cognition_api",
            self._cognition_api,
        )

        self._container.register(
            "tasks",
            self._task_manager,
        )


        self._container.start_all()

        self._started = True


        self._state_manager.update(
            {
                "status": "running",
                "health": "healthy",
            }
        )


        self._event_bus.publish(
            "atlas.started",
            {
                "status": "running",
            },
        )


    def tick(self):

        self._task_manager.tick()


    def chat(
        self,
        text: str,
    ):

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.send(text)


    def stream(
        self,
        text: str,
    ) -> Iterator[str]:

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        yield from self._conversation.stream(text)


    def save_conversation(self) -> Path:

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.save()


    def load_conversation(
        self,
        filepath: Path,
    ):

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.load(filepath)


    def saved_conversations(self):

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.saved_conversations()


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

        self._learning_manager = None

        self._knowledge_feedback = None

        self._reasoning_controller = None
        self._capability_analyzer = None
        self._capability_registry = None
        self._capability_router = None
        self._capability_dispatcher = None
        self._reasoning_recorder = None

        self._model_profile_registry = None
        self._model_router = None


        self._started = False


        self._state_manager.update(
            {
                "status": "stopped",
                "health": "offline",
            }
        )


        self._event_bus.publish(
            "atlas.shutdown",
            {
                "status": "stopped",
            },
        )