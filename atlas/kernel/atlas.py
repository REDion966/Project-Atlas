"""
Atlas Kernel

The root application object.
"""

from collections.abc import Iterator
from pathlib import Path

from atlas.state.state_manager import StateManager
from atlas.events.event_bus import EventBus
from atlas.ai.ai_manager import AIManager
from atlas.config.configuration import Configuration
from atlas.conversation.conversation_service import ConversationService
from atlas.kernel.service_container import ServiceContainer
from atlas.memory.context.context_engine import ContextEngine
from atlas.memory.ranking.ranking_engine import RankingEngine
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.search.search_engine import MemorySearchEngine
from atlas.memory.service.memory_manager_service import MemoryManagerService


class Atlas:
    """
    Root object for the Atlas application.

    Responsible for assembling and managing
    every Atlas subsystem.
    """

    def __init__(self):

        self._container = ServiceContainer()

        # Central communication system
        self._event_bus = EventBus()

        # Reactive state system
        self._state_manager = StateManager(
            self._event_bus
        )

        self._config = Configuration()

        self._ai_manager = AIManager()

        self._conversation: ConversationService | None = None
        self._memory_service: MemoryManagerService | None = None

        self._started = False


    @property
    def container(self) -> ServiceContainer:
        """
        Return the application's service container.
        """

        return self._container


    @property
    def events(self) -> EventBus:
        """
        Return Atlas event bus.
        """

        return self._event_bus


    @property
    def state(self) -> StateManager:
        """
        Return Atlas state manager.
        """

        return self._state_manager


    @property
    def started(self) -> bool:
        """
        Return whether Atlas has been started.
        """

        return self._started


    @property
    def provider(self):
        """
        Return the active AI provider.
        """

        return self._ai_manager.provider


    def models(self):
        """
        Return available AI models.
        """

        return self._ai_manager.service.models()


    def start(self):
        """
        Start Atlas.
        """

        if self._started:
            return


        self._config.load()


        provider = self._config.get(
            "ai",
            "provider",
        )

        model = self._config.get(
            "ai",
            "model",
        )

        timeout = self._config.get(
            "ai",
            "timeout",
        )


        self._ai_manager.initialize(
            provider,
            model,
            timeout,
        )


        # --------------------------------------------------
        # Memory subsystem
        # --------------------------------------------------

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


        # --------------------------------------------------
        # Memory-aware context system
        # --------------------------------------------------

        context_engine = ContextEngine(
            memory_service=self._memory_service,
        )


        # --------------------------------------------------
        # Conversation subsystem
        # --------------------------------------------------

        self._conversation = ConversationService(
            self._ai_manager.service,
            context_engine=context_engine,
        )


        # --------------------------------------------------
        # Register services
        # --------------------------------------------------

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
                "status": "running"
            }
        )


    def chat(self, text: str):
        """
        Send a message to Atlas.
        """

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.send(text)


    def stream(
        self,
        text: str,
    ) -> Iterator[str]:
        """
        Stream a response from Atlas.
        """

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        yield from self._conversation.stream(text)


    def save_conversation(self) -> Path:
        """
        Save the active conversation.
        """

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.save()


    def load_conversation(
        self,
        filepath: Path,
    ):
        """
        Load a saved conversation.
        """

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.load(
            filepath
        )


    def saved_conversations(self):
        """
        Return saved conversations.
        """

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.saved_conversations()


    def shutdown(self):
        """
        Shutdown Atlas.
        """

        if not self._started:
            return


        self._container.stop_all()

        self._container.clear()


        self._conversation = None

        self._memory_service = None


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
                "status": "stopped"
            }
        )