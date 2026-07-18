"""
Atlas Kernel

The root application object.
"""

from collections.abc import Iterator
from pathlib import Path

from atlas.ai.ai_manager import AIManager
from atlas.config.configuration import Configuration
from atlas.conversation.conversation_service import ConversationService
from atlas.kernel.service_container import ServiceContainer
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

        self._config = Configuration()

        self._ai_manager = AIManager()
        self._conversation: ConversationService | None = None
        self._memory_service: MemoryManagerService | None = None

        self._started = False

    @property
    def container(self) -> ServiceContainer:
        """Return the application's service container."""
        return self._container

    @property
    def started(self) -> bool:
        """Return whether Atlas has been started."""
        return self._started

    @property
    def provider(self):
        """Return the active AI provider."""
        return self._ai_manager.provider

    def models(self):
        """Return available AI models."""

        return self._ai_manager.service.models()

    def start(self):
        """Start Atlas."""

        if self._started:
            return

        self._config.load()

        provider = self._config.get("ai", "provider")
        model = self._config.get("ai", "model")
        timeout = self._config.get("ai", "timeout")

        self._ai_manager.initialize(
            provider,
            model,
            timeout,
        )

        self._conversation = ConversationService(
            self._ai_manager.service
        )

        self._container.register(
            "ai",
            self._ai_manager.service,
        )

        self._container.register(
            "conversation",
            self._conversation,
        )

        # Assemble MemoryService with dependency injection
        repository = MemoryRepository()
        ranking_engine = RankingEngine()
        search_engine = MemorySearchEngine(repository, ranking_engine)
        self._memory_service = MemoryManagerService(
            repository=repository,
            ranking_engine=ranking_engine,
            search_engine=search_engine,
        )

        self._container.register(
            "memory",
            self._memory_service,
        )

        self._container.start_all()

        self._started = True

    def chat(self, text: str):
        """Send a message to Atlas."""

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.send(text)

    def stream(
        self,
        text: str,
    ) -> Iterator[str]:
        """Stream a response from Atlas."""

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
        """Shutdown Atlas."""

        if not self._started:
            return

        self._container.stop_all()
        self._container.clear()

        self._conversation = None
        self._memory_service = None

        self._started = False
