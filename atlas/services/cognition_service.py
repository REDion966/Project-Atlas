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
    ):
        super().__init__("cognition")

        self._engine = engine or CognitionEngine()

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
    ):
        """
        Process user input through cognition engine.
        """

        if not self.running:
            raise RuntimeError(
                "Cognition service is not running."
            )

        context = CognitionContext(
            user_input=user_input,
            memory=memory,
            metadata=metadata,
        )

        return self._engine.process(
            context
        )

    @property
    def engine(self):
        """
        Return cognition engine.
        """

        return self._engine