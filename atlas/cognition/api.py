"""
Atlas Cognition API

Public API boundary for the Service-based Cognition system.
Delegates to CognitionService and returns CognitionDecision.
Contains no reasoning logic.
"""

from atlas.cognition.decision import CognitionDecision
from atlas.services.cognition_service import CognitionService


class CognitionAPI:
    """
    Public API for Service-based Cognition.

    Receives user cognition requests, delegates to
    CognitionService, and returns CognitionDecision.
    """

    def __init__(self, cognition_service: CognitionService):
        self._cognition_service = cognition_service

    def process(
        self,
        user_input: str,
        memory=None,
        metadata=None,
        goal: str | None = None,
    ) -> CognitionDecision:
        """
        Process user input through the cognition system.

        Delegates to CognitionService.process().
        Returns a CognitionDecision with no additional logic.
        """

        return self._cognition_service.process(
            user_input=user_input,
            memory=memory,
            metadata=metadata,
            goal=goal,
        )