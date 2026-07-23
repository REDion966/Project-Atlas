"""
Atlas Cognition Service

Service layer connecting Atlas applications
with the Cognition Engine.
"""

from atlas.services.service import Service
from atlas.cognition.context import CognitionContext
from atlas.cognition.engine import CognitionEngine


class CognitionService(Service):
    """
    Provides cognition capabilities to Atlas.
    """

    def __init__(
        self,
        engine: CognitionEngine | None = None,
        memory_service=None,
        knowledge_manager=None,
    ):
        super().__init__("cognition")

        self._engine = engine or CognitionEngine()
        self._memory_service = memory_service
        self._knowledge_manager = knowledge_manager

    def start(self):
        """
        Start cognition service.
        """

        self.mark_running()

    def stop(self):
        """
        Stop cognition service.
        """

        super().stop()

    def process(
        self,
        user_input: str,
        memory=None,
        metadata=None,
        goal: str | None = None,
    ):
        """
        Process user input through cognition engine.

        Retrieves relevant memories and knowledge if available,
        builds a complete CognitionContext, and passes it to
        the CognitionEngine.
        """

        if not self.running:
            raise RuntimeError(
                "Cognition service is not running."
            )

        memory_results = None
        knowledge_results = None

        if self._memory_service is not None and user_input:
            memory_results = self._memory_service.search(
                keyword=user_input,
            )

        if self._knowledge_manager is not None and user_input:
            knowledge_results = self._knowledge_manager.query(
                user_input,
            )

        context = CognitionContext(
            user_input=user_input,
            memory=memory_results or memory,
            metadata=metadata,
            goal=goal,
            knowledge=knowledge_results,
            memory_results=memory_results,
            knowledge_results=knowledge_results,
        )

        return self._engine.process(context)

    @property
    def engine(self):
        """
        Return cognition engine.
        """

        return self._engine

    @property
    def memory_service(self):
        """Return memory service dependency."""

        return self._memory_service

    @property
    def knowledge_manager(self):
        """Return knowledge manager dependency."""

        return self._knowledge_manager