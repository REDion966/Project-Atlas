"""
Atlas Cognition Service

Service layer connecting Atlas applications
with the Cognition Engine.

Phase 6.5.1 — Optional reasoning pipeline integration.
When reasoning components are injected, the service runs
the full pipeline (controller → analyzer → router → dispatcher)
after each cognition decision.
"""

from typing import TYPE_CHECKING

from atlas.services.service import Service
from atlas.cognition.context import CognitionContext
from atlas.cognition.engine import CognitionEngine
from atlas.learning.learning_manager import LearningManager
from atlas.learning.knowledge_feedback import KnowledgeFeedback

if TYPE_CHECKING:
    from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
    from atlas.reasoning.capabilities.models import Capability
    from atlas.reasoning.controller import ReasoningController
    from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
    from atlas.reasoning.execution.models import ExecutionResult, ExecutionRoute
    from atlas.reasoning.execution.registry import CapabilityRegistry
    from atlas.reasoning.execution.routing import CapabilityRouter
    from atlas.reasoning.models import ReasoningPlan


class CognitionService(Service):
    """
    Provides cognition capabilities to Atlas.

    Phase 6.5.1 — Supports optional reasoning pipeline injection.
    When reasoning components are provided, the service
    orchestrates the full reasoning chain after each decision:
      ReasoningController → CapabilityAnalyzer →
      CapabilityRouter → CapabilityDispatcher.
    """

    def __init__(
        self,
        engine: CognitionEngine | None = None,
        memory_service=None,
        knowledge_manager=None,
        learning_manager: LearningManager | None = None,
        knowledge_feedback: KnowledgeFeedback | None = None,
        event_bus=None,
        reasoning_controller=None,
        capability_analyzer=None,
        capability_registry=None,
        capability_router=None,
        capability_dispatcher=None,
    ):
        super().__init__("cognition")

        self._engine = engine or CognitionEngine()
        self._memory_service = memory_service
        self._knowledge_manager = knowledge_manager
        self._learning_manager = learning_manager
        self._knowledge_feedback = knowledge_feedback
        self._event_bus = event_bus

        # --- Phase 6.5.1: Optional reasoning pipeline ---
        self._reasoning_controller = reasoning_controller
        self._capability_analyzer = capability_analyzer
        self._capability_registry = capability_registry
        self._capability_router = capability_router
        self._capability_dispatcher = capability_dispatcher

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

        # --- Phase 6.5.1: Optional reasoning pipeline ---
        self._run_reasoning_pipeline(decision)

        return decision

    # --- Phase 6.5.1: Reasoning pipeline orchestration ---

    def _has_all_reasoning_components(self) -> bool:
        """
        Check whether all reasoning pipeline components are injected.

        Returns:
            True if all five reasoning components are present,
            False otherwise (pipeline is skipped).
        """
        return (
            self._reasoning_controller is not None
            and self._capability_analyzer is not None
            and self._capability_registry is not None
            and self._capability_router is not None
            and self._capability_dispatcher is not None
        )

    def _run_reasoning_pipeline(self, decision) -> None:
        """
        Run the reasoning pipeline on a cognition decision.

        When all reasoning components are injected, this method
        runs the full chain:
          ReasoningController.create_plan(decision)
            → CapabilityAnalyzer.analyze(plan)
            → CapabilityRouter.route(capabilities)
            → CapabilityDispatcher.dispatch(capabilities)

        Results are attached to decision.data["reasoning"].

        If any component is missing, the pipeline is silently
        skipped — preserving backward compatibility.

        Args:
            decision: The CognitionDecision produced by the engine.
        """
        if not self._has_all_reasoning_components():
            return

        # Type narrowing — the guard above ensures these are injected
        assert self._reasoning_controller is not None
        assert self._capability_analyzer is not None
        assert self._capability_router is not None
        assert self._capability_dispatcher is not None

        plan = self._reasoning_controller.create_plan(decision)

        capabilities = self._capability_analyzer.analyze(plan)

        routes = self._capability_router.route(capabilities)

        results = self._capability_dispatcher.dispatch(capabilities)

        decision.data["reasoning"] = {
            "goal": plan.goal,
            "capabilities": [
                {
                    "name": c.name,
                    "priority": c.priority,
                    "reason": c.reason,
                }
                for c in capabilities
            ],
            "routes": [
                {
                    "capability": r.capability,
                    "handler_name": r.handler_name,
                    "strategy": r.strategy,
                }
                for r in routes
            ],
            "results": [
                {
                    "capability": r.capability,
                    "success": r.success,
                    "output": r.output,
                    "error": r.error,
                }
                for r in results
            ],
        }

    @property
    def reasoning_controller(self):
        """
        Return the reasoning controller dependency (Phase 6.5.1).

        Returns:
            The ReasoningController if injected, or None.
        """
        return self._reasoning_controller

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
