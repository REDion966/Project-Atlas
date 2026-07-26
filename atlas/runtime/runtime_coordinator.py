"""
Atlas RuntimeCoordinator — Phase 7.5 Unified Cognitive Runtime.

The RuntimeCoordinator is the SINGLE permanent orchestrator for all
cognitive processing. Nothing else orchestrates cognition.

Execution order (invariant):
  Conversation Context → Memory Retrieval → Knowledge Retrieval →
  Understanding Engine → World Model Update → Reasoning Engine →
  Planning Engine → Tool Decision → Tool Execution →
  AI Response Generation → Learning Engine → Evolution Observation →
  Memory Storage

Every stage exchanges structured CognitionState objects.
No raw string passing between stages.

Architecture rules:
  - Pure logic NEVER imports infrastructure.
  - Infrastructure NEVER owns reasoning.
  - Providers NEVER own cognition.
  - Understanding stays between Knowledge and Reasoning.
  - Learning NEVER edits code.
  - Evolution NEVER edits code.
"""

import time
from datetime import datetime
from typing import Any, Callable

from atlas.cognition.context import CognitionContext
from atlas.cognition.decision import CognitionDecision
from atlas.cognition.engine import CognitionEngine
from atlas.cognition.models import (
    CognitionState,
    PipelineMetrics,
    PipelineResult,
    StageResult,
    StageStatus,
    StageType,
)


class RuntimeCoordinator:
    """
    Permanent unified cognitive runtime coordinator.

    This is the ONLY orchestrator for cognition. All processing
    flows through this single coordinator. No other component
    may orchestrate cognitive stages independently.

    Dependencies are all optional via injection. Missing dependencies
    cause stages to be skipped gracefully, preserving backward
    compatibility with all existing code paths.
    """

    def __init__(
        self,
        engine: CognitionEngine | None = None,
        memory_service: Any = None,
        knowledge_manager: Any = None,
        understanding_engine: Any = None,
        world_model_engine: Any = None,
        reasoning_controller: Any = None,
        capability_analyzer: Any = None,
        capability_registry: Any = None,
        capability_router: Any = None,
        capability_dispatcher: Any = None,
        planning_engine: Any = None,
        tool_engine: Any = None,
        ai_service: Any = None,
        reflection_engine: Any = None,
        reasoning_recorder: Any = None,
        learning_manager: Any = None,
        knowledge_feedback: Any = None,
        learning_engine: Any = None,
        evolution_observation_engine: Any = None,
        identity_engine: Any = None,
        conversation_service: Any = None,
        event_bus: Any = None,
    ):
        self._engine = engine or CognitionEngine()

        # Stage dependencies (all optional — skipped gracefully if None)
        self._memory_service = memory_service
        self._knowledge_manager = knowledge_manager
        self._understanding_engine = understanding_engine
        self._world_model_engine = world_model_engine
        self._reasoning_controller = reasoning_controller
        self._capability_analyzer = capability_analyzer
        self._capability_registry = capability_registry
        self._capability_router = capability_router
        self._capability_dispatcher = capability_dispatcher
        self._planning_engine = planning_engine
        self._tool_engine = tool_engine
        self._ai_service = ai_service
        self._reflection_engine = reflection_engine
        self._reasoning_recorder = reasoning_recorder
        self._learning_manager = learning_manager
        self._knowledge_feedback = knowledge_feedback
        self._learning_engine = learning_engine
        self._evolution_observation_engine = evolution_observation_engine
        self._identity_engine = identity_engine
        self._conversation_service = conversation_service
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Public API — the single entry point for all cognitive processing
    # ------------------------------------------------------------------

    def process(
        self,
        user_input: str,
        memory: Any = None,
        metadata: dict[str, Any] | None = None,
        goal: str | None = None,
    ) -> PipelineResult:
        """
        Process user input through the full unified cognitive pipeline.

        This is the single, permanent entry point for ALL cognitive
        processing. Every stage is executed in its defined order.

        Args:
            user_input: The user's input text.
            memory: Optional pre-retrieved memory data.
            metadata: Optional metadata context.
            goal: Optional processing goal.

        Returns:
            A PipelineResult containing all stage results, metrics,
            and the final response.
        """
        state = CognitionState(
            user_input=user_input,
            metadata=metadata or {},
        )

        metrics = PipelineMetrics(
            started_at=datetime.now(),
        )

        stages: list[StageResult] = []
        pipeline_path: list[str] = []

        stage_definitions = self._build_stage_definitions()

        for stage_type, stage_fn in stage_definitions:
            stage_start = time.perf_counter()
            stage_path_name = stage_type.name.lower()

            try:
                result = stage_fn(state)
                duration = (time.perf_counter() - stage_start) * 1000

                if result.status == StageStatus.SUCCESS:
                    metrics.success_count += 1
                    pipeline_path.append(stage_path_name)
                elif result.status == StageStatus.FAILED:
                    metrics.failed_count += 1
                    pipeline_path.append(f"{stage_path_name}:failed")
                else:
                    metrics.skipped_count += 1
                    pipeline_path.append(f"{stage_path_name}:skipped")

                result.duration_ms = round(duration, 2)
                stages.append(result)

            except Exception as exc:
                duration = (time.perf_counter() - stage_start) * 1000
                stages.append(StageResult(
                    stage=stage_type,
                    status=StageStatus.FAILED,
                    duration_ms=round(duration, 2),
                    error=str(exc),
                ))
                metrics.failed_count += 1
                pipeline_path.append(f"{stage_path_name}:error")
                break

        # Finalize metrics
        metrics.stage_count = len(stages)
        metrics.pipeline_path = pipeline_path
        metrics.completed_at = datetime.now()
        metrics.total_duration_ms = round(
            (metrics.completed_at - metrics.started_at).total_seconds() * 1000, 2
        )

        # Collect tool usage
        if state.tool_result and state.tool_result.get("tool_name"):
            metrics.tool_usage.append(state.tool_result["tool_name"])

        metrics.understanding_insights = len(state.understanding_insights)

        # Build intermediate data
        intermediate = {
            "user_input": state.user_input,
            "memories_count": len(state.memories),
            "knowledge_count": len(state.knowledge),
            "understanding_insights_count": len(state.understanding_insights),
            "concepts_count": len(state.concepts),
            "patterns_count": len(state.patterns),
            "has_world_model_state": bool(state.world_model_state),
            "has_reasoning": bool(state.reasoning_result),
            "has_planning": bool(state.planning_result),
            "has_tool_result": bool(state.tool_result),
            "has_reflection": bool(state.reflection_suggestions),
            "has_learning": bool(state.learning_result),
            "has_learning_engine": bool(state.learning_engine_result),
            "evolution_observations_count": len(state.evolution_observations),
        }

        overall_success = all(
            s.status != StageStatus.FAILED for s in stages
        )

        result = PipelineResult(
            success=overall_success,
            final_response=state.ai_response,
            stages=stages,
            metrics=metrics,
            intermediate_data=intermediate,
        )

        # Publish pipeline completion event
        if self._event_bus is not None:
            self._event_bus.publish(
                "runtime.pipeline.completed",
                {
                    "success": overall_success,
                    "stages_executed": metrics.stage_count,
                    "total_duration_ms": metrics.total_duration_ms,
                    "pipeline_path": pipeline_path,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Stage definitions — the invariant execution order
    # ------------------------------------------------------------------

    def _build_stage_definitions(
        self,
    ) -> list[tuple[StageType, Callable[[CognitionState], StageResult]]]:
        """Build the ordered list of stage definitions."""
        return [
            (StageType.CONVERSATION_CONTEXT, self._stage_conversation_context),
            (StageType.MEMORY_RETRIEVAL, self._stage_memory_retrieval),
            (StageType.KNOWLEDGE_RETRIEVAL, self._stage_knowledge_retrieval),
            (StageType.UNDERSTANDING, self._stage_understanding),
            (StageType.WORLD_MODEL, self._stage_world_model),
            (StageType.REASONING, self._stage_reasoning),
            (StageType.PLANNING, self._stage_planning),
            (StageType.TOOL_DECISION, self._stage_tool_decision),
            (StageType.TOOL_EXECUTION, self._stage_tool_execution),
            (StageType.AI_RESPONSE, self._stage_ai_response),
            (StageType.REFLECTION, self._stage_reflection),
            (StageType.LEARNING, self._stage_learning),
            (StageType.EVOLUTION_OBSERVATION, self._stage_evolution_observation),
            (StageType.MEMORY_STORAGE, self._stage_memory_storage),
        ]

    # ------------------------------------------------------------------
    # Stage 1: Conversation Context
    # ------------------------------------------------------------------

    def _stage_conversation_context(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._conversation_service is None:
            return StageResult(
                stage=StageType.CONVERSATION_CONTEXT,
                status=StageStatus.SKIPPED,
            )

        context = {
            "user_input": state.user_input,
            "has_history": hasattr(self._conversation_service, "history"),
        }

        if hasattr(self._conversation_service, "history"):
            try:
                history = self._conversation_service.history
                context["history_length"] = len(history) if history else 0
            except Exception:
                context["history_length"] = 0

        state.conversation_context = context

        return StageResult(
            stage=StageType.CONVERSATION_CONTEXT,
            status=StageStatus.SUCCESS,
            data=context,
            confidence=1.0,
        )

    # ------------------------------------------------------------------
    # Stage 2: Memory Retrieval
    # ------------------------------------------------------------------

    def _stage_memory_retrieval(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._memory_service is None:
            return StageResult(
                stage=StageType.MEMORY_RETRIEVAL,
                status=StageStatus.SKIPPED,
            )

        results = self._memory_service.search(keyword=state.user_input)
        memories = results if results else []
        state.memories = memories

        return StageResult(
            stage=StageType.MEMORY_RETRIEVAL,
            status=StageStatus.SUCCESS,
            data={"memories_count": len(memories)},
            confidence=0.8 if memories else 0.0,
        )

    # ------------------------------------------------------------------
    # Stage 3: Knowledge Retrieval
    # ------------------------------------------------------------------

    def _stage_knowledge_retrieval(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._knowledge_manager is None:
            return StageResult(
                stage=StageType.KNOWLEDGE_RETRIEVAL,
                status=StageStatus.SKIPPED,
            )

        results = self._knowledge_manager.query(state.user_input)
        knowledge = results if results else []
        state.knowledge = knowledge

        return StageResult(
            stage=StageType.KNOWLEDGE_RETRIEVAL,
            status=StageStatus.SUCCESS,
            data={"knowledge_count": len(knowledge)},
            confidence=0.8 if knowledge else 0.0,
        )

    # ------------------------------------------------------------------
    # Stage 4: Understanding Engine
    # ------------------------------------------------------------------

    def _stage_understanding(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._understanding_engine is None:
            return StageResult(
                stage=StageType.UNDERSTANDING,
                status=StageStatus.SKIPPED,
            )

        insights = self._understanding_engine.process_text(
            text=state.user_input,
            source="runtime_coordinator",
        )

        state.understanding_insights = insights
        state.concepts = self._understanding_engine.graph.get_all_concepts()
        state.patterns = self._understanding_engine.memory.get_patterns(10)

        return StageResult(
            stage=StageType.UNDERSTANDING,
            status=StageStatus.SUCCESS,
            data={
                "insights_count": len(insights),
                "concepts_count": len(state.concepts),
                "patterns_count": len(state.patterns),
            },
            confidence=0.7 if insights else 0.0,
        )

    # ------------------------------------------------------------------
    # Stage 5: World Model Update
    # ------------------------------------------------------------------

    def _stage_world_model(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._world_model_engine is None:
            return StageResult(
                stage=StageType.WORLD_MODEL,
                status=StageStatus.SKIPPED,
            )

        # Record the current input as an observation in the world model
        observation = self._world_model_engine.record_observation(
            description=f"User input: {state.user_input[:100]}",
            source="runtime_coordinator",
        )

        # Get current world summary
        world_summary = self._world_model_engine.get_world_summary()

        state.world_model_state = world_summary

        return StageResult(
            stage=StageType.WORLD_MODEL,
            status=StageStatus.SUCCESS,
            data={
                "observation_id": observation.observation_id,
                "entities_count": world_summary.get("graph_entities", 0),
                "active_goals_count": len(world_summary.get("active_goals", [])),
            },
            confidence=0.7,
        )

    # ------------------------------------------------------------------
    # Stage 6: Reasoning Engine
    # ------------------------------------------------------------------

    def _stage_reasoning(
        self,
        state: CognitionState,
    ) -> StageResult:
        if not self._has_reasoning_components():
            return StageResult(
                stage=StageType.REASONING,
                status=StageStatus.SKIPPED,
            )

        decision = CognitionDecision(
            action="respond",
            reasoning=f"Process: {state.user_input[:100]}",
            data={
                "input": state.user_input,
                "understanding_insights": [
                    {"summary": i.summary, "confidence": i.confidence}
                    for i in state.understanding_insights[:10]
                ],
            },
        )

        plan = self._reasoning_controller.create_plan(decision)
        capabilities = self._capability_analyzer.analyze(plan)
        routes = self._capability_router.route(capabilities)
        results = self._capability_dispatcher.dispatch(capabilities)

        reasoning_data = {
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

        state.reasoning_result = reasoning_data

        # Record reasoning outcome if recorder available
        if self._reasoning_recorder is not None:
            self._record_outcome(decision.action, reasoning_data, results)

        return StageResult(
            stage=StageType.REASONING,
            status=StageStatus.SUCCESS,
            data=reasoning_data,
            confidence=0.8 if results else 0.0,
        )

    # ------------------------------------------------------------------
    # Stage 7: Planning Engine
    # ------------------------------------------------------------------

    def _stage_planning(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._planning_engine is None:
            return StageResult(
                stage=StageType.PLANNING,
                status=StageStatus.SKIPPED,
            )

        if not state.reasoning_result:
            return StageResult(
                stage=StageType.PLANNING,
                status=StageStatus.SKIPPED,
                data={"reason": "No reasoning result to plan from"},
            )

        from atlas.reasoning.models import ReasoningPlan

        plan = ReasoningPlan(
            goal=state.reasoning_result.get("goal", "respond"),
            steps=[],
        )

        planning_plan = self._planning_engine.decompose(plan)

        planning_data = {
            "goal": planning_plan.goal,
            "sub_goals": list(planning_plan.sub_goals),
            "steps": [
                {
                    "id": s.id,
                    "description": s.description,
                    "action": s.action,
                    "depends_on": list(s.depends_on),
                    "status": s.status,
                }
                for s in planning_plan.steps
            ],
            "status": planning_plan.status,
            "validation_errors": list(planning_plan.validation_errors),
        }

        state.planning_result = planning_data

        return StageResult(
            stage=StageType.PLANNING,
            status=StageStatus.SUCCESS,
            data=planning_data,
            confidence=0.7,
        )

    # ------------------------------------------------------------------
    # Stage 8: Tool Decision
    # ------------------------------------------------------------------

    def _stage_tool_decision(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._tool_engine is None:
            return StageResult(
                stage=StageType.TOOL_DECISION,
                status=StageStatus.SKIPPED,
            )

        if not state.reasoning_result:
            return StageResult(
                stage=StageType.TOOL_DECISION,
                status=StageStatus.SKIPPED,
                data={"reason": "No reasoning result"},
            )

        from atlas.tools.models import ToolRequest

        goal = state.reasoning_result.get("goal", state.user_input)
        tool_request = ToolRequest(
            goal=goal,
            context={
                "user_input": state.user_input,
                "reasoning_data": state.reasoning_result,
                "planning_data": state.planning_result,
            },
        )

        state.tool_request = tool_request

        return StageResult(
            stage=StageType.TOOL_DECISION,
            status=StageStatus.SUCCESS,
            data={"goal": goal, "has_request": True},
            confidence=0.7,
        )

    # ------------------------------------------------------------------
    # Stage 9: Tool Execution
    # ------------------------------------------------------------------

    def _stage_tool_execution(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._tool_engine is None:
            return StageResult(
                stage=StageType.TOOL_EXECUTION,
                status=StageStatus.SKIPPED,
            )

        if state.tool_request is None:
            return StageResult(
                stage=StageType.TOOL_EXECUTION,
                status=StageStatus.SKIPPED,
                data={"reason": "No tool request"},
            )

        result = self._tool_engine.fulfill(state.tool_request)

        tool_data = {
            "tool_name": result.tool_name,
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        }

        state.tool_result = tool_data

        return StageResult(
            stage=StageType.TOOL_EXECUTION,
            status=StageStatus.SUCCESS if result.success else StageStatus.FAILED,
            data=tool_data,
            confidence=0.8 if result.success else 0.0,
        )

    # ------------------------------------------------------------------
    # Stage 10: AI Response Generation
    # ------------------------------------------------------------------

    def _stage_ai_response(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._ai_service is None:
            return StageResult(
                stage=StageType.AI_RESPONSE,
                status=StageStatus.SKIPPED,
            )

        messages = self._build_messages(state)
        response = self._ai_service.chat(messages)

        state.ai_response = response.text if hasattr(response, "text") else str(response)

        return StageResult(
            stage=StageType.AI_RESPONSE,
            status=StageStatus.SUCCESS,
            data={"response_length": len(state.ai_response)},
            confidence=0.9,
        )

    # ------------------------------------------------------------------
    # Stage 11: Reflection
    # ------------------------------------------------------------------

    def _stage_reflection(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._reflection_engine is None or self._reasoning_recorder is None:
            return StageResult(
                stage=StageType.REFLECTION,
                status=StageStatus.SKIPPED,
            )

        if self._reasoning_recorder.count == 0:
            return StageResult(
                stage=StageType.REFLECTION,
                status=StageStatus.SKIPPED,
                data={"reason": "No outcomes recorded"},
            )

        recent_outcomes = self._reasoning_recorder.recent(20)
        suggestions = self._reflection_engine.analyze(recent_outcomes)

        state.reflection_suggestions = suggestions

        return StageResult(
            stage=StageType.REFLECTION,
            status=StageStatus.SUCCESS,
            data={"suggestions_count": len(suggestions)},
            confidence=0.6 if suggestions else 0.0,
        )

    # ------------------------------------------------------------------
    # Stage 12: Learning Engine
    # ------------------------------------------------------------------

    def _stage_learning(
        self,
        state: CognitionState,
    ) -> StageResult:
        # Use LearningEngine if available (Phase 7.3), fall back to legacy LearningManager
        if self._learning_engine is not None:
            return self._stage_learning_engine(state)

        if self._learning_manager is not None:
            return self._stage_learning_legacy(state)

        return StageResult(
            stage=StageType.LEARNING,
            status=StageStatus.SKIPPED,
        )

    def _stage_learning_engine(
        self,
        state: CognitionState,
    ) -> StageResult:
        pipeline_data = {
            "user_input": state.user_input,
            "memories_count": len(state.memories),
            "knowledge_count": len(state.knowledge),
            "understanding_insights_count": len(state.understanding_insights),
            "has_reasoning": bool(state.reasoning_result),
            "has_planning": bool(state.planning_result),
            "has_tool_result": bool(state.tool_result),
            "has_reflection": bool(state.reflection_suggestions),
        }

        insights = self._learning_engine.learn_from_pipeline(pipeline_data)

        learning_data = {
            "insights_count": len(insights),
            "summary": self._learning_engine.get_learning_summary(),
        }

        state.learning_engine_result = learning_data

        return StageResult(
            stage=StageType.LEARNING,
            status=StageStatus.SUCCESS,
            data=learning_data,
            confidence=0.6 if insights else 0.3,
        )

    def _stage_learning_legacy(
        self,
        state: CognitionState,
    ) -> StageResult:
        experience = (
            f"Input: {state.user_input[:100]} | "
            f"Reasoning: {state.reasoning_result.get('goal', 'none') if state.reasoning_result else 'none'} | "
            f"Tool: {state.tool_result.get('tool_name', 'none') if state.tool_result else 'none'}"
        )

        learning_result = self._learning_manager.learn(experience)

        learning_data = {
            "experience": experience[:100],
            "knowledge": learning_result.knowledge if hasattr(learning_result, "knowledge") else "",
        }

        if self._knowledge_feedback is not None and hasattr(learning_result, "knowledge"):
            self._knowledge_feedback.remember(learning_result.knowledge)

        if self._knowledge_manager is not None and hasattr(learning_result, "knowledge"):
            self._knowledge_manager.remember(
                title=f"pipeline:{state.user_input[:50]}",
                content=learning_result.knowledge,
                source="runtime_coordinator",
            )

        state.learning_result = learning_data

        return StageResult(
            stage=StageType.LEARNING,
            status=StageStatus.SUCCESS,
            data=learning_data,
            confidence=0.5,
        )

    # ------------------------------------------------------------------
    # Stage 13: Evolution Observation
    # ------------------------------------------------------------------

    def _stage_evolution_observation(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._evolution_observation_engine is None:
            return StageResult(
                stage=StageType.EVOLUTION_OBSERVATION,
                status=StageStatus.SKIPPED,
            )

        obs = self._evolution_observation_engine.observe_runtime_metrics(
            avg_response_time_ms=0.0,
            request_count=1,
            error_count=0,
            source="runtime_coordinator",
        )

        state.evolution_observations = [obs]

        return StageResult(
            stage=StageType.EVOLUTION_OBSERVATION,
            status=StageStatus.SUCCESS,
            data={"observations_count": 1},
            confidence=0.7,
        )

    # ------------------------------------------------------------------
    # Stage 14: Memory Storage
    # ------------------------------------------------------------------

    def _stage_memory_storage(
        self,
        state: CognitionState,
    ) -> StageResult:
        if self._memory_service is None:
            return StageResult(
                stage=StageType.MEMORY_STORAGE,
                status=StageStatus.SKIPPED,
            )

        try:
            self._memory_service.store(
                content=state.ai_response or state.user_input,
                source="runtime_coordinator",
            )
            stored = True
        except Exception:
            stored = False

        return StageResult(
            stage=StageType.MEMORY_STORAGE,
            status=StageStatus.SUCCESS if stored else StageStatus.FAILED,
            data={"stored": stored},
            confidence=0.8 if stored else 0.0,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _has_reasoning_components(self) -> bool:
        return all([
            self._reasoning_controller is not None,
            self._capability_analyzer is not None,
            self._capability_router is not None,
            self._capability_dispatcher is not None,
        ])

    def _record_outcome(
        self,
        decision_action: str,
        reasoning_data: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Record a reasoning outcome using the recorder."""
        import importlib

        outcomes_module = importlib.import_module("atlas.reasoning.outcomes")
        outcome_cls = getattr(outcomes_module, "ReasoningOutcome")

        success = all(
            r.success for r in results
        ) if results else False

        outcome = outcome_cls(
            timestamp=datetime.now(),
            goal=reasoning_data.get("goal", ""),
            decision_action=decision_action,
            capabilities=list(reasoning_data.get("capabilities", [])),
            routes=list(reasoning_data.get("routes", [])),
            results=[
                {"capability": r.capability, "success": r.success, "output": r.output, "error": r.error}
                for r in results
            ],
            success=success,
            metadata={"source": "runtime_coordinator"},
        )

        self._reasoning_recorder.record(outcome)

    def _build_messages(
        self,
        state: CognitionState,
    ) -> list[dict[str, str]]:
        """Build chat messages from the accumulated pipeline state."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "You are Atlas, an intelligent AI operating framework."},
        ]

        if state.memories:
            memory_summary = f"Relevant memories: {len(state.memories)} items found."
            messages.append({"role": "system", "content": memory_summary})

        if state.knowledge:
            knowledge_summary = f"Relevant knowledge: {len(state.knowledge)} items found."
            messages.append({"role": "system", "content": knowledge_summary})

        if state.understanding_insights:
            insight_summary = "Understanding insights:\n"
            for i in state.understanding_insights[:5]:
                insight_summary += f"- {i.summary}\n"
            messages.append({"role": "system", "content": insight_summary})

        if state.tool_result:
            tool_summary = (
                f"Tool '{state.tool_result.get('tool_name', 'unknown')}' "
                f"{'succeeded' if state.tool_result.get('success') else 'failed'}: "
                f"{state.tool_result.get('output', '')}"
            )
            messages.append({"role": "system", "content": tool_summary})

        messages.append({"role": "user", "content": state.user_input})

        return messages

    # ------------------------------------------------------------------
    # Properties (for introspection and testing)
    # ------------------------------------------------------------------

    @property
    def memory_service(self):
        return self._memory_service

    @property
    def knowledge_manager(self):
        return self._knowledge_manager

    @property
    def understanding_engine(self):
        return self._understanding_engine

    @property
    def world_model_engine(self):
        return self._world_model_engine

    @property
    def reasoning_controller(self):
        return self._reasoning_controller

    @property
    def planning_engine(self):
        return self._planning_engine

    @property
    def tool_engine(self):
        return self._tool_engine

    @property
    def ai_service(self):
        return self._ai_service

    @property
    def reflection_engine(self):
        return self._reflection_engine

    @property
    def reasoning_recorder(self):
        return self._reasoning_recorder

    @property
    def learning_manager(self):
        return self._learning_manager

    @property
    def learning_engine(self):
        return self._learning_engine

    @property
    def evolution_observation_engine(self):
        return self._evolution_observation_engine

    @property
    def identity_engine(self):
        return self._identity_engine

    @property
    def conversation_service(self):
        return self._conversation_service

    @property
    def event_bus(self):
        return self._event_bus

    @property
    def engine(self):
        return self._engine