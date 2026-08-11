"""
Atlas Cognition Service

Service layer — delegates orchestration to RuntimeCoordinator.
CognitionService is a service component only. It does NOT own
pipeline execution. All orchestration is delegated to RuntimeCoordinator.

When RuntimeCoordinator is not available, a backward-compatible
inline pipeline runs (preserving all existing behavior).

Phase 7.5.1 — Architecture Consolidation.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from atlas.services.service import Service
from atlas.cognition.decision import CognitionDecision
from atlas.cognition.models import PipelineResult

if TYPE_CHECKING:
    from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
    from atlas.reasoning.controller import ReasoningController
    from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
    from atlas.reasoning.execution.registry import CapabilityRegistry
    from atlas.reasoning.execution.routing import CapabilityRouter
    from atlas.reasoning.outcomes import ReasoningOutcome, ReasoningRecorder
    from atlas.reasoning.planning import PlanningEngine
    from atlas.reasoning.reflection import ReflectionEngine
    from atlas.tools.engine import ToolEngine
    from atlas.runtime.runtime_coordinator import RuntimeCoordinator


class CognitionService(Service):
    """
    Service wrapper around the RuntimeCoordinator.

    All cognitive processing is delegated to RuntimeCoordinator.
    CognitionService adapts the PipelineResult back to a
    CognitionDecision for backward compatibility.

    When RuntimeCoordinator is not available, a backward-compatible
    inline pipeline runs (preserving all legacy test behavior).
    """

    def __init__(
        self,
        engine: Any = None,
        memory_service: Any = None,
        knowledge_manager: Any = None,
        learning_manager: Any = None,
        knowledge_feedback: Any = None,
        event_bus: Any = None,
        reasoning_controller: Any = None,
        capability_analyzer: Any = None,
        capability_registry: Any = None,
        capability_router: Any = None,
        capability_dispatcher: Any = None,
        reasoning_recorder: Any = None,
        reflection_engine: Any = None,
        planning_engine: Any = None,
        tool_engine: Any = None,
        runtime_coordinator: "RuntimeCoordinator | None" = None,
    ):
        super().__init__("cognition")

        self._engine = engine
        self._memory_service = memory_service
        self._knowledge_manager = knowledge_manager
        self._learning_manager = learning_manager
        self._knowledge_feedback = knowledge_feedback
        self._event_bus = event_bus

        self._reasoning_controller = reasoning_controller
        self._capability_analyzer = capability_analyzer
        self._capability_registry = capability_registry
        self._capability_router = capability_router
        self._capability_dispatcher = capability_dispatcher
        self._reasoning_recorder = reasoning_recorder
        self._reflection_engine = reflection_engine
        self._planning_engine = planning_engine
        self._tool_engine = tool_engine

        # --- Phase 7.5.1: RuntimeCoordinator is the primary orchestrator ---
        self._runtime_coordinator = runtime_coordinator

    def start(self):
        self.mark_running()

    def stop(self):
        super().stop()

    def process(
        self,
        user_input: str,
        memory: Any = None,
        metadata: Any = None,
        goal: str | None = None,
    ) -> CognitionDecision:
        """
        Process user input through the cognitive runtime.

        When a RuntimeCoordinator is injected, ALL cognitive processing
        is delegated to it. The PipelineResult is mapped back to a
        CognitionDecision for backward compatibility.

        When no RuntimeCoordinator is available but reasoning components
        are injected, the legacy inline pipeline runs (preserving all
        existing test behavior).

        When neither is available, returns a minimal decision.
        """
        if not self.running:
            raise RuntimeError("Cognition service is not running.")

        # --- Phase 7.5.1: Primary path via RuntimeCoordinator ---
        if self._runtime_coordinator is not None:
            return self._process_via_runtime_coordinator(user_input, memory, metadata, goal)

        # --- Legacy fallback: inline pipeline (backward compatible) ---
        return self._process_legacy(user_input, memory, metadata, goal)

    # ------------------------------------------------------------------
    # Primary path: RuntimeCoordinator
    # ------------------------------------------------------------------

    def _process_via_runtime_coordinator(
        self,
        user_input: str,
        memory: Any,
        metadata: Any,
        goal: str | None,
    ) -> CognitionDecision:
        """Delegate full processing to RuntimeCoordinator, adapt result."""
        assert self._runtime_coordinator is not None

        result: PipelineResult = self._runtime_coordinator.process(
            user_input=user_input,
            memory=memory,
            metadata=metadata or {},
            goal=goal,
        )

        intermediate = result.intermediate_data
        reasoning_data: dict[str, Any] = {}
        planning_data: dict[str, Any] = {}
        tool_data: dict[str, Any] = {}

        # Extract structured data from pipeline stages
        for stage in result.stages:
            if not stage.data or stage.status.value <= 0:
                continue
            stage_name = stage.stage.name if hasattr(stage.stage, "name") else str(stage.stage)
            if "REASONING" in stage_name:
                reasoning_data = stage.data
            elif "PLANNING" in stage_name:
                planning_data = stage.data
            elif "TOOL_EXECUTION" in stage_name:
                tool_data = stage.data

        data_payload: dict[str, Any] = {
            "input": user_input,
            "memory_count": intermediate.get("memories_count", 0),
            "knowledge_count": intermediate.get("knowledge_count", 0),
            "understanding_insights_count": intermediate.get("understanding_insights_count", 0),
        }

        # Phase 20 corrective fix: capability dispatch moved from the
        # REASONING stage into PLANNING. The REASONING stage's route/result
        # lists are therefore structurally empty, while the executed results
        # live in the PLANNING stage. The public decision payload must keep
        # exposing the executed results under the "reasoning" key (the
        # pre-Phase-20 CognitionAPI contract). This overlay is read-only and
        # copies the lists, leaving the internal stage data untouched.
        if reasoning_data:
            public_reasoning = dict(reasoning_data)
            if planning_data:
                public_reasoning["capabilities"] = list(
                    planning_data.get(
                        "dispatched_capabilities",
                        public_reasoning.get("capabilities", []),
                    )
                )
                public_reasoning["routes"] = list(
                    planning_data.get(
                        "routes",
                        public_reasoning.get("routes", []),
                    )
                )
                public_reasoning["results"] = list(
                    planning_data.get(
                        "results",
                        public_reasoning.get("results", []),
                    )
                )
            data_payload["reasoning"] = public_reasoning
        if planning_data:
            data_payload["planning"] = planning_data
        if tool_data:
            data_payload["tool_results"] = tool_data

        if self._event_bus is not None:
            self._event_bus.publish(
                "cognition.decision.made",
                {
                    "action": "respond",
                    "reasoning": f"Pipeline: {user_input[:100]}",
                    "data": data_payload,
                },
            )

        return CognitionDecision(
            action="respond",
            reasoning=f"Processed through unified runtime: {result.metrics.stage_count} stages, "
                      f"{result.metrics.success_count} succeeded",
            data=data_payload,
        )

    # ------------------------------------------------------------------
    # Legacy fallback: inline pipeline (preserves all existing tests)
    # ------------------------------------------------------------------

    def _process_legacy(
        self,
        user_input: str,
        memory: Any,
        metadata: Any,
        goal: str | None,
    ) -> CognitionDecision:
        """Legacy inline pipeline — backward compatible with all tests."""
        from atlas.cognition.context import CognitionContext
        from atlas.cognition.engine import CognitionEngine

        engine = self._engine or CognitionEngine()

        memory_results = None
        knowledge_results = None

        if self._memory_service is not None and user_input:
            memory_results = self._memory_service.search(keyword=user_input)

        if self._knowledge_manager is not None and user_input:
            knowledge_results = self._knowledge_manager.query(user_input)

        context = CognitionContext(
            user_input=user_input,
            memory=memory_results or memory,
            metadata=metadata,
            goal=goal,
            knowledge=knowledge_results,
            memory_results=memory_results,
            knowledge_results=knowledge_results,
        )

        decision = engine.process(context)

        # --- Event: decision.made ---
        if self._event_bus is not None:
            self._event_bus.publish(
                "cognition.decision.made",
                {"action": decision.action, "reasoning": decision.reasoning, "data": decision.data},
            )

        # --- Learning feedback loop (Phase 5.3) ---
        learning_result = None
        if self._learning_manager is not None:
            experience = f"Action: {decision.action} | Reasoning: {decision.reasoning}"
            learning_result = self._learning_manager.learn(experience)

            if self._knowledge_feedback is not None and learning_result:
                self._knowledge_feedback.remember(learning_result.knowledge)

            if self._knowledge_manager is not None and learning_result:
                self._knowledge_manager.remember(
                    title=f"cognition:{decision.action}",
                    content=learning_result.knowledge,
                    source="cognition_service",
                )

        if self._event_bus is not None and learning_result is not None:
            self._event_bus.publish(
                "cognition.learning.completed",
                {"action": decision.action, "knowledge": learning_result.knowledge},
            )

        # --- Reasoning pipeline (Phase 6.5.1) ---
        self._run_reasoning_pipeline(decision)

        # --- Tool pipeline (Phase 6.9) ---
        self._run_tool_pipeline(decision)

        # --- Outcome recording (Phase 6.5.2) ---
        self._record_reasoning_outcome(decision)

        # --- Reflection (Phase 6.7) ---
        self._run_reflection(decision)

        return decision

    # ------------------------------------------------------------------
    # Legacy pipeline helper methods (preserved from Phase 6.x)
    # ------------------------------------------------------------------

    def _has_all_reasoning_components(self) -> bool:
        return (
            self._reasoning_controller is not None
            and self._capability_analyzer is not None
            and self._capability_registry is not None
            and self._capability_router is not None
            and self._capability_dispatcher is not None
        )

    def _run_reasoning_pipeline(self, decision) -> None:
        if not self._has_all_reasoning_components():
            return

        assert self._reasoning_controller is not None
        assert self._capability_analyzer is not None
        assert self._capability_router is not None
        assert self._capability_dispatcher is not None

        plan = self._reasoning_controller.create_plan(decision)

        if self._planning_engine is not None:
            planning_plan = self._planning_engine.decompose(plan)
            decision.data["planning"] = {
                "goal": planning_plan.goal,
                "sub_goals": list(planning_plan.sub_goals),
                "steps": [
                    {"id": s.id, "description": s.description, "action": s.action,
                     "depends_on": list(s.depends_on), "status": s.status}
                    for s in planning_plan.steps
                ],
                "status": planning_plan.status,
                "validation_errors": list(planning_plan.validation_errors),
            }

        capabilities = self._capability_analyzer.analyze(plan)
        routes = self._capability_router.route(capabilities)
        results = self._capability_dispatcher.dispatch(capabilities)

        decision.data["reasoning"] = {
            "goal": plan.goal,
            "capabilities": [
                {"name": c.name, "priority": c.priority, "reason": c.reason}
                for c in capabilities
            ],
            "routes": [
                {"capability": r.capability, "handler_name": r.handler_name, "strategy": r.strategy}
                for r in routes
            ],
            "results": [
                {"capability": r.capability, "success": r.success, "output": r.output, "error": r.error}
                for r in results
            ],
        }

    def _run_tool_pipeline(self, decision) -> None:
        if self._tool_engine is None:
            return

        reasoning_data = decision.data.get("reasoning")
        if reasoning_data is None:
            return

        import importlib
        tools_models = importlib.import_module("atlas.tools.models")
        tr_cls = getattr(tools_models, "ToolRequest")

        goal = reasoning_data.get("goal", decision.action)
        tool_request = tr_cls(
            goal=goal,
            context={
                "action": decision.action,
                "reasoning_data": reasoning_data,
                "planning_data": decision.data.get("planning"),
            },
        )

        result = self._tool_engine.fulfill(tool_request)
        decision.data["tool_results"] = {
            "tool_name": result.tool_name,
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        }

    def _record_reasoning_outcome(self, decision) -> None:
        if self._reasoning_recorder is None:
            return

        reasoning_data = decision.data.get("reasoning")
        if reasoning_data is None:
            return

        success = all(
            r.get("success", False) for r in reasoning_data.get("results", [])
        )

        import importlib
        outcomes_module = importlib.import_module("atlas.reasoning.outcomes")
        outcome_cls = getattr(outcomes_module, "ReasoningOutcome")

        outcome = outcome_cls(
            timestamp=datetime.now(),
            goal=reasoning_data.get("goal", ""),
            decision_action=decision.action,
            capabilities=list(reasoning_data.get("capabilities", [])),
            routes=list(reasoning_data.get("routes", [])),
            results=list(reasoning_data.get("results", [])),
            success=success,
            metadata={"source": "cognition_service"},
        )
        self._reasoning_recorder.record(outcome)

    def _run_reflection(self, decision) -> None:
        if self._reflection_engine is None:
            return
        if self._reasoning_recorder is None:
            return
        if self._reasoning_recorder.count == 0:
            return

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

    # ------------------------------------------------------------------
    # Properties (preserved for backward compatibility)
    # ------------------------------------------------------------------

    @property
    def engine(self):
        """Return cognition engine (legacy, may be None if using RuntimeCoordinator)."""
        return self._engine

    @property
    def reasoning_controller(self):
        return self._reasoning_controller

    @property
    def reasoning_recorder(self):
        return self._reasoning_recorder

    @property
    def reflection_engine(self):
        return self._reflection_engine

    @property
    def planning_engine(self):
        return self._planning_engine

    @property
    def tool_engine(self):
        return self._tool_engine

    @property
    def memory_service(self):
        return self._memory_service

    @property
    def knowledge_manager(self):
        return self._knowledge_manager

    @property
    def runtime_coordinator(self):
        """Return the RuntimeCoordinator (Phase 7.5.1)."""
        return self._runtime_coordinator

    @property
    def status(self):
        return {
            "running": self.running,
            "has_memory": self._memory_service is not None,
            "has_knowledge": self._knowledge_manager is not None,
            "has_learning": self._learning_manager is not None,
            "has_reasoning": self._reasoning_controller is not None,
            "has_recorder": self._reasoning_recorder is not None,
            "has_reflection": self._reflection_engine is not None,
            "has_planning": self._planning_engine is not None,
            "has_tools": self._tool_engine is not None,
            "has_runtime_coordinator": self._runtime_coordinator is not None,
        }
