"""
Atlas Cognition API

Public API boundary for the Service-based Cognition system.
Delegates to CognitionService and returns CognitionDecision.
Contains no reasoning logic.
"""

from typing import Any

from atlas.cognition.decision import CognitionDecision
from atlas.conversation.turn_meaning import accept_turn_meaning
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
        turn_meaning: Any = None,
    ) -> CognitionDecision:
        """
        Process user input through the cognition system.

        Delegates to CognitionService.process().
        Returns a CognitionDecision with no additional logic.

        ``turn_meaning`` is the optional L1 typed turn-meaning contract. This
        boundary performs a fail-closed *shape* acceptance check only
        (:func:`accept_turn_meaning`): a well-formed contract is forwarded
        unchanged; malformed input is dropped deterministically so behaviour is
        unchanged. The contract's semantic content is never consumed here.
        """

        accepted = accept_turn_meaning(turn_meaning)
        if accepted is None:
            return self._cognition_service.process(
                user_input=user_input,
                memory=memory,
                metadata=metadata,
                goal=goal,
            )
        return self._cognition_service.process(
            user_input=user_input,
            memory=memory,
            metadata=metadata,
            goal=goal,
            turn_meaning=accepted,
        )