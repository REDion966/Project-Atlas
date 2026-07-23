"""
Atlas Kernel

The root application object.
"""

from collections.abc import Iterator
from pathlib import Path

from atlas.ai.ai_manager import AIManager
from atlas.config.configuration import Configuration
from atlas.conversation.conversation_service import ConversationService
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


        self._ai_manager.initialize(
            provider,
            model,
            timeout,
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

        self._cognition_service = CognitionService()


        context_engine = ContextEngine(
            memory_service=self._memory_service,
        )


        self._conversation = ConversationService(
            self._ai_manager.service,
            context_engine=context_engine,
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