"""
Atlas Cognition Service

Service layer connecting Atlas applications
with the Cognition Engine.
"""

from atlas.services.service import Service
from atlas.cognition.context import CognitionContext
from atlas.cognition.engine import CognitionEngine
from atlas.learning.learning_manager import LearningManager
from atlas.learning.knowledge_feedback import KnowledgeFeedback


class CognitionService(Service):
    """
    Provides cognition capabilities to Atlas.
    """

    def __init__(
        self,
        engine: CognitionEngine | None = None,
        memory_service=None,
        knowledge_manager=None,
        learning_manager: LearningManager | None = None,
        knowledge_feedback: KnowledgeFeedback | None = None,
        event_bus=None,
    ):
        super().__init__("cognition")

        self._engine = engine or CognitionEngine()
        self._memory_service = memory_service
        self._knowledge_manager = knowledge_manager
        self._learning_manager = learning_manager
        self._knowledge_feedback = knowledge_feedback
        self._event_bus = event_bus

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

        decision = self._engine.process(context)

        # --- Cognition Event: decision.made ---
        if self._event_bus is not None:
            self._event_bus.publish(
                "cognition.decision.made",
                {
                    "action": decision.action,
                    "reasoning": decision.reasoning,
                    "data": decision.data,
                },
            )

        # --- Cognition Feedback Loop (Phase 5.3) ---
        learning_result = None
        if self._learning_manager is not None:
            experience = (
                f"Action: {decision.action} | "
                f"Reasoning: {decision.reasoning}"
            )
            learning_result = self._learning_manager.learn(experience)

            if self._knowledge_feedback is not None:
                self._knowledge_feedback.remember(
                    learning_result.knowledge
                )

            if self._knowledge_manager is not None:
                self._knowledge_manager.remember(
                    title=f"cognition:{decision.action}",
                    content=learning_result.knowledge,
                    source="cognition_service",
                )

        # --- Cognition Event: learning.completed ---
        if self._event_bus is not None and learning_result is not None:
            self._event_bus.publish(
                "cognition.learning.completed",
                {
                    "action": decision.action,
                    "knowledge": learning_result.knowledge,
                },
            )

        return decision

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

    @property
    def status(self):
        """
        Return cognition service status summary.

        Returns a dict with running state and dependency availability.
        """

        return {
            "running": self.running,
            "has_memory": self._memory_service is not None,
            "has_knowledge": self._knowledge_manager is not None,
            "has_learning": self._learning_manager is not None,
        }
