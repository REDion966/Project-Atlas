"""
Atlas Cognition Pipeline

Connects cognition engine with conversation flow.
"""

from atlas.cognition.context import CognitionContext
from atlas.cognition.engine import CognitionEngine


class CognitionPipeline:
    """
    Runs Atlas thinking pipeline.
    """

    def __init__(
        self,
        engine: CognitionEngine | None = None,
    ):
        self._engine = engine or CognitionEngine()

    def process(
        self,
        user_input: str,
        memory=None,
        metadata=None,
    ):
        """
        Process user input through cognition.
        """

        context = CognitionContext(
            user_input=user_input,
            memory=memory,
            metadata=metadata,
        )

        return self._engine.process(
            context
        )