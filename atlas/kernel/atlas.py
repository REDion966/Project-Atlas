"""
Atlas Kernel

The root application object.
"""

from atlas.ai.ai_manager import AIManager
from atlas.conversation.conversation_service import ConversationService
from atlas.kernel.service_container import ServiceContainer


class Atlas:
    """
    Root object for the Atlas application.

    Responsible for assembling and managing
    every Atlas subsystem.
    """

    def __init__(self):
        self._container = ServiceContainer()

        self._ai_manager = AIManager()
        self._conversation: ConversationService | None = None

        self._started = False

    @property
    def container(self) -> ServiceContainer:
        """Return the application's service container."""
        return self._container

    @property
    def started(self) -> bool:
        """Return whether Atlas has been started."""
        return self._started

    def start(self):
        """
        Start Atlas.
        """

        if self._started:
            return

        # Initialize AI
        self._ai_manager.initialize()

        # Create conversation service
        self._conversation = ConversationService(
            self._ai_manager.service
        )

        # Register services
        self._container.register(
            "ai",
            self._ai_manager.service,
        )

        self._container.register(
            "conversation",
            self._conversation,
        )

        # Start registered services
        self._container.start_all()

        self._started = True

    def chat(self, text: str):
        """
        Send a message to Atlas.
        """

        if not self._started:
            raise RuntimeError(
                "Atlas has not been started."
            )

        return self._conversation.send(text)

    def shutdown(self):
        """
        Shutdown Atlas.
        """

        if not self._started:
            return

        self._container.stop_all()
        self._container.clear()

        self._conversation = None

        self._started = False