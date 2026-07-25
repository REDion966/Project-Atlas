"""
Atlas Cognition Service

Service layer connecting Atlas applications
with the Cognition Engine.

Phase 6.5.1 — Optional reasoning pipeline integration.
When reasoning components are injected, the service runs
the full pipeline (controller → analyzer → router → dispatcher)
after each cognition decision.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

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
    from atlas.reasoning.outcomes import ReasoningOutcome, ReasoningRecorder
    from atlas.reasoning.reflection import ReflectionEngine, ReflectionSuggestion


class CognitionService(Service):
    """
    Provides cognition capabilities to Atlas.

    Phase 6.5.1 — Supports optional reasoning pipeline injection.
    When reasoning components are provided, the service
    orchestrates the full reasoning chain after each decision:
      ReasoningController → CapabilityAnalyzer →
      CapabilityRouter → CapabilityDispatcher.

    Phase 6.5.2 — Supports optional reasoning outcome recording.
    When a ReasoningRecorder is injected alongside the reasoning
    pipeline, completed reasoning outcomes are recorded for future
    reflection and observability.

    Phase 6.7 — Supports optional reflection analysis.
    When a ReflectionEngine is injected and outcomes are available,
    the service runs reflection after recording to produce analysis
    suggestions.
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
        reasoning_recorder=None,
        reflection_engine=None,
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

        # --- Phase 6.5.2: Optional reasoning outcome recording ---
        self._reasoning_recorder = reasoning_recorder

        # --- Phase 6.7: Optional reflection analysis ---
        self._reflection_engine = reflection_engine

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

        # --- Phase 6.5.2: Optional reasoning outcome recording ---
        self._record_reasoning_outcome(decision)

        # --- Phase 6.7: Optional reflection analysis ---
        self._run_reflection(decision)

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

    def _record_reasoning_outcome(self, decision) -> None:
        """
        Record the reasoning pipeline outcome when available.

        If a ReasoningRecorder is injected and the reasoning pipeline
        produced results in decision.data["reasoning"], this method
        constructs a ReasoningOutcome and stores it in the recorder.

        If the recorder is missing or no reasoning results exist,
        this method does nothing — preserving backward compatibility.

        Args:
            decision: The CognitionDecision that may contain reasoning
                pipeline results.
        """
        if self._reasoning_recorder is None:
            return

        reasoning_data = decision.data.get("reasoning")
        if reasoning_data is None:
            return

        success = all(
            r.get("success", False)
            for r in reasoning_data.get("results", [])
        )

        outcome = self._build_reasoning_outcome(
            decision_action=decision.action,
            reasoning_data=reasoning_data,
            success=success,
        )

        self._reasoning_recorder.record(outcome)

    # --- Phase 6.7: Reflection analysis ---

    def _run_reflection(self, decision) -> None:
        """
        Run reflection analysis when a ReflectionEngine is available.

        Requires both a ReflectionEngine and a ReasoningRecorder with
        recorded outcomes to produce suggestions. Suggestions are stored
        in decision.data["reflection"] as serialized metadata only.

        If the engine or recorder is missing, or no outcomes have been
        recorded, this method does nothing — preserving backward
        compatibility.

        Args:
            decision: The CognitionDecision to attach reflection
                suggestions to.
        """
        if self._reflection_engine is None:
            return

        if self._reasoning_recorder is None:
            return

        if self._reasoning_recorder.count == 0:
            return

        # Use the last 20 outcomes as a sliding reflection window
        recent_outcomes = self._reasoning_recorder.recent(20)

        suggestions = self._reflection_engine.analyze(recent_outcomes)

        if not suggestions:
            return

        decision.data["reflection"] = [
            {
                "pattern": s.pattern,
                "description": s.description,
                "suggestion": s.suggestion,
                "confidence": s.confidence,
                "target_area": s.target_area,
                "timestamp": s.timestamp.isoformat(),
                "affected_outcomes_count": s.affected_outcomes_count,
            }
            for s in suggestions
        ]

    def _build_reasoning_outcome(
        self,
        decision_action: str,
        reasoning_data: dict[str, Any],
        success: bool,
    ) -> "ReasoningOutcome":
        """
        Build a ReasoningOutcome from serialized reasoning data.

        This helper avoids a runtime import of ReasoningOutcome by
        constructing it through importlib, preserving the TYPE_CHECKING
        pattern and keeping CognitionService loosely coupled to the
        reasoning outcome types.

        Args:
            decision_action: The CognitionDecision action.
            reasoning_data: The serialized reasoning data produced by
                the reasoning pipeline.
            success: Whether all execution results succeeded.

        Returns:
            A populated ReasoningOutcome instance.
        """
        import importlib

        outcomes_module = importlib.import_module("atlas.reasoning.outcomes")
        outcome_cls = getattr(outcomes_module, "ReasoningOutcome")

        return outcome_cls(
            timestamp=datetime.now(),
            goal=reasoning_data.get("goal", ""),
            decision_action=decision_action,
            capabilities=list(reasoning_data.get("capabilities", [])),
            routes=list(reasoning_data.get("routes", [])),
            results=list(reasoning_data.get("results", [])),
            success=success,
            metadata={"source": "cognition_service"},
        )

    @property
    def reasoning_controller(self):
        """
        Return the reasoning controller dependency (Phase 6.5.1).

        Returns:
            The ReasoningController if injected, or None.
        """
        return self._reasoning_controller

    @property
    def reasoning_recorder(self):
        """
        Return the reasoning recorder dependency (Phase 6.5.2).

        Returns:
            The ReasoningRecorder if injected, or None.
        """
        return self._reasoning_recorder

    @property
    def reflection_engine(self):
        """
        Return the reflection engine dependency (Phase 6.7).

        Returns:
            The ReflectionEngine if injected, or None.
        """
        return self._reflection_engine

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
            "has_reasoning": self._reasoning_controller is not None,
            "has_recorder": self._reasoning_recorder is not None,
            "has_reflection": self._reflection_engine is not None,
        }
