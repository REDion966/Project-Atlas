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
from atlas.ai.routing.models import RoutingRequest
from atlas.evolution.runtime_observations import collect_runtime_observations
from atlas.cognition.models import (
    CognitionState,
    PipelineMetrics,
    PipelineResult,
    StageResult,
    StageStatus,
    StageType,
)
from atlas.reasoning.capabilities.models import Capability


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
        feedback_coordinator: Any = None,
        goal_intelligence_engine: Any = None,
        conversation_service: Any = None,
        event_bus: Any = None,
        improvement_planner: Any = None,
        proposal_generator: Any = None,
        approval_manager: Any = None,
        evolution_memory: Any = None,
        intelligence_engine: Any = None,
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
        self._feedback_coordinator = feedback_coordinator
        self._goal_intelligence_engine = goal_intelligence_engine
        self._experience_accumulator = None
        self._self_model_engine = None
        self._conversation_service = conversation_service
        self._event_bus = event_bus

        # --- Phase 10.0: Evolution Pipeline ---
        self._improvement_planner = improvement_planner
        self._proposal_generator = proposal_generator
        self._approval_manager = approval_manager
        self._evolution_memory = evolution_memory

        # --- Phase 13.3: Evolution Scheduler (optional) ---
        self._evolution_scheduler = None

        # --- Phase 12.2: Evolution Intelligence Engine ---
        self._intelligence_engine = intelligence_engine

        # --- Phase 10.0: Transient metrics reference for Stage 13 ---
        self._current_metrics: PipelineMetrics | None = None

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
            goal=goal or "",
            metadata=metadata or {},
        )

        metrics = PipelineMetrics(
            started_at=datetime.now(),
        )

        stages: list[StageResult] = []
        pipeline_path: list[str] = []

        # --- Phase 10.0: Make metrics accessible to Stage 13 during this run ---
        self._current_metrics = metrics

        stage_definitions = self._build_stage_definitions()

        try:
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

            # --- Phase 8.2: Cognitive Feedback Loop ---
            if self._feedback_coordinator is not None:
                self._feedback_coordinator.process_feedback(state, result)

            # --- Phase 9.0: Experience Accumulation & Self-Model Update ---
            if self._experience_accumulator is not None:
                self._experience_accumulator.record(state, result)
            if self._self_model_engine is not None:
                self._self_model_engine.update()

            # --- Phase 9.2a: Feed accumulated experiences into Understanding Engine ---
            if (
                self._experience_accumulator is not None
                and self._understanding_engine is not None
            ):
                repo = self._experience_accumulator.repository
                recent_experiences = repo.get_experiences(n=50)
                if recent_experiences:
                    self._understanding_engine.process_experiences(
                        experiences=recent_experiences,
                        source="runtime_coordinator",
                    )

            # --- Phase 10.0.1: Feed self-model snapshot trends into GoalIntelligence ---
            if (
                self._goal_intelligence_engine is not None
                and self._self_model_engine is not None
            ):
                snapshot = self._self_model_engine.get_snapshot()
                if snapshot is not None:
                    trends = {
                        "self_model_trends": {
                            "success_rate_trend": getattr(snapshot, "trend_summary", ""),
                            "persistent_challenges": getattr(snapshot, "persistent_challenges", []),
                        },
                        "identity_summary": {},
                        "world_model_summary": {},
                        "learning_insights": {},
                        "reflection_suggestions": [],
                        "capability_profiles": {},
                    }
                    self._goal_intelligence_engine.analyze(trends)

            # --- Phase 13.3: Evolution Scheduler tick (replaces inline analysis) ---
            if self._evolution_scheduler is not None:
                self._evolution_scheduler.tick()

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

        finally:
            # --- Phase 10.0: Clear transient metrics reference after pipeline completes ---
            self._current_metrics = None

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
            (StageType.GOAL_INTELLIGENCE, self._stage_goal_intelligence),
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

        # The explicit goal (when provided) becomes the decision's
        # reasoning, which ReasoningController.create_plan carries into
        # the plan goal ("respond: <goal>"). Without a goal the previous
        # default is preserved verbatim.
        reasoning_text = state.goal or f"Process: {state.user_input[:100]}"

        decision = CognitionDecision(
            action="respond",
            reasoning=reasoning_text,
            data={
                "input": state.user_input,
                "goal": state.goal,
                "understanding_insights": [
                    {"summary": i.summary, "confidence": i.confidence}
                    for i in state.understanding_insights[:10]
                ],
            },
        )

        plan = self._reasoning_controller.create_plan(decision)
        capabilities = self._capability_analyzer.analyze(plan)

        # Phase 20 Batch 3: capability dispatch no longer executes here.
        # Only candidate capabilities are recorded; the plan (handed to the
        # PLANNING stage via state.reasoning_plan) drives selection and
        # dispatch after PLANNING has executed.
        reasoning_data = {
            "goal": plan.goal,
            "capabilities": [
                {"name": c.name, "priority": c.priority, "reason": c.reason}
                for c in capabilities
            ],
            "routes": [],
            "results": [],
        }

        state.reasoning_result = reasoning_data
        state.reasoning_plan = plan

        return StageResult(
            stage=StageType.REASONING,
            status=StageStatus.SUCCESS,
            data=reasoning_data,
            confidence=0.8 if capabilities else 0.0,
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

        plan = state.reasoning_plan or ReasoningPlan(
            goal=state.reasoning_result.get("goal", "respond"),
            steps=[],
        )

        # Phase 20 Batch 3: PLANNING executes first, then capability
        # selection and dispatch are driven by the plan steps — NOT in
        # REASONING.
        planning_plan = self._planning_engine.decompose(plan)

        # Capability selection is derived from the decomposed plan's steps,
        # so PLANNING genuinely drives capability selection and dispatch.
        execution_capabilities = self._select_plan_capabilities(planning_plan)
        routes = self._capability_router.route(execution_capabilities)
        results = self._capability_dispatcher.dispatch(execution_capabilities)

        # Rebuild reasoning state with the execution results. A fresh dict
        # keeps the REASONING stage's StageResult.data (which shares the
        # original dict) free of execution results — dispatch only appears
        # in the PLANNING stage and later context.
        state.reasoning_result = {
            "goal": state.reasoning_result.get("goal", "respond"),
            "capabilities": [
                {"name": c.name, "priority": c.priority, "reason": c.reason}
                for c in execution_capabilities
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

        # Record the reasoning outcome now that dispatch has executed.
        if self._reasoning_recorder is not None:
            self._record_outcome("respond", state.reasoning_result, results)

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
            "dispatched_capabilities": [
                {"name": c.name, "priority": c.priority, "reason": c.reason}
                for c in execution_capabilities
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

        state.planning_result = planning_data

        return StageResult(
            stage=StageType.PLANNING,
            status=StageStatus.SUCCESS,
            data=planning_data,
            confidence=0.7 if results else 0.0,
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

        # Prefer the plan-derived goal (carried through reasoning), falling
        # back to the explicit processing goal, then the raw user input.
        goal = state.reasoning_result.get("goal") or state.goal or state.user_input
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
        # Phase 20 Batch 6: the existing ModelRouter is activated by
        # constructing a RoutingRequest from the plan state and passing it
        # through AIService.chat(routing_context=...). No routing context is
        # produced when planning never ran — the AI service then keeps its
        # existing default behavior.
        routing_request = self._build_routing_request(state)
        if routing_request is None:
            response = self._ai_service.chat(messages)
        else:
            response = self._ai_service.chat(
                messages,
                routing_context=routing_request,
            )

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
        suggestions = getattr(state, "reflection_suggestions", []) or []

        pipeline_data = {
            "user_input": state.user_input,
            "memories_count": len(state.memories),
            "knowledge_count": len(state.knowledge),
            "understanding_insights_count": len(state.understanding_insights),
            "has_reasoning": bool(state.reasoning_result),
            "has_planning": bool(state.planning_result),
            "has_tool_result": bool(state.tool_result),
            "has_reflection": bool(suggestions),
            # Phase 20 Batch 4: pass reflection output through so the
            # LearningEngine can turn suggestions into reusable learning
            # evidence. Suggestions are serialized so the learning engine
            # stays independent of the reasoning layer.
            "reflection_suggestions": [
                {
                    "pattern": getattr(s, "pattern", ""),
                    "description": getattr(s, "description", ""),
                    "suggestion": getattr(s, "suggestion", ""),
                    "confidence": getattr(s, "confidence", 0.0),
                    "target_area": getattr(s, "target_area", ""),
                    "affected_outcomes_count": getattr(
                        s, "affected_outcomes_count", 0
                    ),
                }
                for s in suggestions
            ],
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

        # Compute current pipeline elapsed time and failure count from
        # the transient metrics reference set at the start of process().
        elapsed_ms = 0.0
        error_count = 0
        if self._current_metrics is not None:
            elapsed = (datetime.now() - self._current_metrics.started_at).total_seconds()
            elapsed_ms = elapsed * 1000.0
            error_count = self._current_metrics.failed_count

        observations, skipped = collect_runtime_observations(
            engine=self._evolution_observation_engine,
            state=state,
            metrics=self._current_metrics,
            elapsed_ms=elapsed_ms,
        )

        state.evolution_observations = observations

        # Phase 13.5 decision-pipeline closure: mirror the collected
        # observations into EvolutionMemory so runtime history survives a
        # restart and remains actionable for weakness aggregation.
        # Memory-first best-effort: persist_observation already degrades
        # gracefully, and any unexpected failure here must never break the
        # pipeline stage.
        if self._evolution_memory is not None and observations:
            try:
                for observation in observations:
                    self._evolution_memory.persist_observation(observation)
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "Failed to persist evolution observations from pipeline"
                )

        return StageResult(
            stage=StageType.EVOLUTION_OBSERVATION,
            status=StageStatus.SUCCESS,
            data={
                "observations_count": len(observations),
                "skipped_categories": sorted(skipped),
            },
            confidence=0.7,
        )

    # ------------------------------------------------------------------
    # Stage 14: Goal Intelligence
    # ------------------------------------------------------------------

    def _stage_goal_intelligence(
        self,
        state: CognitionState,
    ) -> StageResult:
        """Analyze accumulated evidence and generate improvement recommendations."""
        if self._goal_intelligence_engine is None:
            return StageResult(
                stage=StageType.GOAL_INTELLIGENCE,
                status=StageStatus.SKIPPED,
            )

        # Build evidence payload from pipeline state
        evidence = {
            "learning_insights": getattr(state, "learning_engine_result", {}) or {},
            "reflection_suggestions": getattr(state, "reflection_suggestions", []) or [],
            "capability_profiles": {},
            "identity_summary": (
                self._identity_engine.summary() if self._identity_engine is not None else {}
            ),
            "world_model_summary": getattr(state, "world_model_state", {}) or {},
        }

        report = self._goal_intelligence_engine.analyze(evidence)
        state.goal_intelligence_report = report

        return StageResult(
            stage=StageType.GOAL_INTELLIGENCE,
            status=StageStatus.SUCCESS,
            data={
                "report_id": report.report_id,
                "total_recommendations": report.total_recommendations,
                "total_opportunities": report.total_opportunities,
            },
            confidence=0.6 if report.total_recommendations > 0 else 0.3,
        )

    # ------------------------------------------------------------------
    # Stage 15: Memory Storage
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

    def _select_plan_capabilities(self, plan) -> list[Capability]:
        """Derive execution capabilities from the plan's steps.

        Each step action is first mapped through the CapabilityAnalyzer.
        When the step action itself names a registered capability (e.g. a
        Track-level handler such as ``research.query`` or ``toolchain.*``),
        that capability is used directly so plans can reach registered
        Track capabilities. Capabilities whose handler is missing remain in
        the list and the dispatcher fails them soft.
        """
        capabilities: list[Capability] = []
        for step in getattr(plan, "steps", []) or []:
            cap = self._capability_analyzer.analyze_step(step)
            action = getattr(step, "action", "") or ""
            if action and self._capability_registry.has(action):
                cap = Capability(
                    name=action,
                    priority=max(cap.priority, 5),
                    reason=f"Plan step action: {action}",
                    metadata=dict(cap.metadata),
                )
            capabilities.append(cap)
        capabilities.sort(key=lambda c: c.priority, reverse=True)
        return capabilities

    def _build_routing_request(
        self,
        state: CognitionState,
    ) -> RoutingRequest | None:
        """Build a deterministic RoutingRequest from the pipeline's plan state.

        Phase 20 Batch 6 — activates the existing ModelRouter by translating
        Phase 20 planning output (plan steps and dispatched capabilities)
        into the existing RoutingRequest schema.

        Complexity derives from how much work the plan implies: a 1-step
        respond/query plan maps to the low end; deeper plans and tool use
        escalate. A floor of 0.5 keeps ordinary requests on the configured
        Ollama profile rather than the 0.3-complexity Mock stub. Returns
        None when no planning ran, preserving the pre-routing behavior of a
        request that bypasses the ModelRouter.
        """
        planning = state.planning_result or {}
        steps = planning.get("steps") or []
        results = planning.get("results") or []
        if not steps:
            return None

        # Deterministic complexity: base + plan breadth/depth + tool use,
        # bounded to the [0.0, 1.0] schema range.
        step_weight = max(1, len(steps))
        tool_weight = 1 if any(
            r.get("tool_name") or r.get("capability", "").startswith("toolchain.")
            for r in results
        ) else 0
        complexity = min(1.0, 0.5 + (step_weight - 1) * 0.1 + tool_weight * 0.1)

        latency_requirement = "fast" if step_weight <= 2 else "medium"
        task_type = planning.get("goal", "respond") or "respond"
        context_size = max(
            0,
            len(steps) + len(state.understanding_insights),
        )

        return RoutingRequest(
            complexity=round(complexity, 2),
            latency_requirement=latency_requirement,
            task_type=task_type,
            context_size=context_size,
            metadata={
                "source": "runtime_coordinator",
                "plan_step_count": len(steps),
                "dispatched_count": len(results),
                "has_tool_execution": bool(tool_weight),
            },
        )

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
        """
        Build structured cognitive context for the AI provider.

        Phase 8.1 — Assembles a comprehensive system prompt from all
        cognitive subsystems. The LLM is the final reasoning assistant —
        it receives pre-computed identity, reasoning, planning, tool
        results, understanding, world model state, and learning insights.

        Atlas's intelligence is in the pipeline. The LLM is the voice.
        """
        return [
            {"role": "system", "content": self._build_cognitive_context(state)},
            {"role": "user", "content": state.user_input},
        ]

    def _build_cognitive_context(self, state: CognitionState) -> str:
        """
        Assemble a structured cognitive context from all subsystems.

        Order preserves the cognition pipeline flow:
          Identity → Conversation → Memory → Knowledge → Understanding →
          World Model → Reasoning → Planning → Tool Results →
          Learning → Evolution
        Each section is only included if data is available.
        """
        sections: list[str] = []

        # --- 1. Identity (who Atlas is, permanent) ---
        identity_section = self._build_identity_section()
        if identity_section:
            sections.append(identity_section)

        # --- 1b. Self-Model Assessment (how Atlas is performing) ---
        self_model_section = self._build_self_model_section()
        if self_model_section:
            sections.append(self_model_section)

        # --- 2. Conversation Context ---
        conv_section = self._build_conversation_section(state)
        if conv_section:
            sections.append(conv_section)

        # --- 3. Retrieved Memory ---
        memory_section = self._build_memory_section(state)
        if memory_section:
            sections.append(memory_section)

        # --- 4. Retrieved Knowledge ---
        knowledge_section = self._build_knowledge_section(state)
        if knowledge_section:
            sections.append(knowledge_section)

        # --- 5. Understanding Insights (structured summaries) ---
        understanding_section = self._build_understanding_section(state)
        if understanding_section:
            sections.append(understanding_section)

        # --- 6. World Model State ---
        world_section = self._build_world_model_section(state)
        if world_section:
            sections.append(world_section)

        # --- 7. Reasoning Results ---
        reasoning_section = self._build_reasoning_section(state)
        if reasoning_section:
            sections.append(reasoning_section)

        # --- 8. Planning Decisions ---
        planning_section = self._build_planning_section(state)
        if planning_section:
            sections.append(planning_section)

        # --- 9. Tool Results ---
        tool_section = self._build_tool_section(state)
        if tool_section:
            sections.append(tool_section)

        # --- 10. Learning Insights ---
        learning_section = self._build_learning_section(state)
        if learning_section:
            sections.append(learning_section)

        # --- Role instruction (LLM as assistant, not primary intelligence) ---
        sections.append(self._build_role_instruction())

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Individual cognitive context sections
    # ------------------------------------------------------------------

    def _build_self_model_section(self) -> str:
        """Build the Self-Model section from SelfModelEngine snapshot.

        Appears after Identity and before Conversation context so the
        LLM knows Atlas's performance state before seeing the current
        input. If no snapshot is available the section is omitted silently.
        """
        if self._self_model_engine is None:
            return ""
        snapshot = self._self_model_engine.get_snapshot()
        if snapshot is None:
            return ""

        lines = ["## Self-Model Assessment"]
        lines.append(
            f"Recent performance: {snapshot.overall_success_rate:.0%} "
            f"success rate across {snapshot.total_experiences} pipeline executions."
        )

        if snapshot.capability_assessments:
            lines.append("\nCapability confidence:")
            for name, score in sorted(
                snapshot.capability_assessments.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]:
                lines.append(f"- {name}: {score:.0%}")

        if snapshot.recent_improvement_evidence:
            lines.append("\nRecent improvements:")
            for ev in snapshot.recent_improvement_evidence[:3]:
                lines.append(f"- {ev}")

        if snapshot.persistent_challenges:
            lines.append("\nChallenges:")
            for ch in snapshot.persistent_challenges[:3]:
                lines.append(f"- {ch}")

        if snapshot.trend_summary:
            lines.append(f"\nTrend summary: {snapshot.trend_summary}")

        return "\n".join(lines)

    def _build_identity_section(self) -> str:
        """Build the Identity section from IdentityEngine."""
        if self._identity_engine is None:
            return ""
        if not self._identity_engine.initialized:
            return ""

        snap = self._identity_engine.snapshot()

        lines = ["## Identity"]
        lines.append(f"You are {snap.name}. You are {snap.description[:200]}.")

        # Core principles (immutable guidance)
        active_principles = snap.principles[:5]
        if active_principles:
            lines.append("\nCore principles you follow:")
            for p in active_principles:
                lines.append(f"- {p.title}: {p.description}")

        # Core beliefs (how Atlas sees itself)
        active_beliefs = [
            b for b in snap.beliefs
            if getattr(b, "confidence", "tentative") not in ("retired", "weak")
        ][:5]
        if active_beliefs:
            lines.append("\nWhat you believe about yourself:")
            for b in active_beliefs:
                lines.append(f"- {b.statement}")

        # Decision style
        style = snap.decision_style
        if style:
            lines.append(f"\nDecision style: {getattr(style, 'preferred_reasoning_style', 'structured')}, "
                         f"{getattr(style, 'preferred_explanation_style', 'transparent')} explanations")

        # Engineering preferences (how Atlas prefers to work)
        prefs = snap.engineering_preferences[:3]
        if prefs:
            lines.append("\nEngineering preferences:")
            for p in prefs:
                lines.append(f"- {p.name}: {p.description}")

        return "\n".join(lines)

    def _build_conversation_section(self, state: CognitionState) -> str:
        """Build conversation context."""
        ctx = state.conversation_context
        if not ctx:
            return ""
        history_len = ctx.get("history_length", 0)
        if history_len:
            return f"## Conversation Context\nCurrent conversation has {history_len} previous messages."
        return ""

    def _build_memory_section(self, state: CognitionState) -> str:
        """Build memory retrieval results."""
        if not state.memories:
            return ""
        lines = ["## Retrieved Memories"]
        for m in state.memories[:5]:
            title = getattr(m, "title", "") or getattr(m, "content", "")[:80]
            if title:
                lines.append(f"- {title}")
        return "\n".join(lines)

    def _build_knowledge_section(self, state: CognitionState) -> str:
        """Build knowledge retrieval results."""
        if not state.knowledge:
            return ""
        lines = ["## Retrieved Knowledge"]
        for k in state.knowledge[:5]:
            title = getattr(k, "title", "") or str(k)[:80]
            if title:
                lines.append(f"- {title}")
        return "\n".join(lines)

    def _build_understanding_section(self, state: CognitionState) -> str:
        """
        Build structured understanding summaries.

        Understanding provides concept-level analysis, not raw text.
        This is what elevates Atlas above simple text matching.
        """
        if not state.understanding_insights:
            return ""

        lines = ["## Understanding"]

        # Concept-level insights
        for i in state.understanding_insights[:5]:
            summary = getattr(i, "summary", "")
            category = getattr(i, "category", None)
            if summary:
                cat_str = f" [{category.value if hasattr(category, 'value') else category}]" if category else ""
                lines.append(f"- {summary}{cat_str}")

        # Extracted concepts
        if state.concepts:
            concept_names = [
                getattr(c, "label", "") or getattr(c, "name", "") or str(c)
                for c in state.concepts[:8]
            ]
            if concept_names:
                lines.append(f"\nKey concepts detected: {', '.join(c for c in concept_names if c)}")

        # Detected patterns
        if state.patterns:
            pattern_summaries = [
                getattr(p, "description", "") or getattr(p, "name", "") or str(p)
                for p in state.patterns[:3]
            ]
            if pattern_summaries:
                lines.append("\nPatterns recognized:")
                for ps in pattern_summaries:
                    if ps:
                        lines.append(f"- {ps}")

        return "\n".join(lines)

    def _build_world_model_section(self, state: CognitionState) -> str:
        """Build world model state for planning/prediction context."""
        wm = state.world_model_state
        if not wm:
            return ""

        lines = ["## World Model State"]
        entities = wm.get("graph_entities", 0)
        relations = wm.get("graph_relations", 0)
        rules = wm.get("behavior_rules", 0)
        lines.append(f"Entities tracked: {entities}, relations: {relations}, behavior rules: {rules}")

        active_goals = wm.get("active_goals", [])
        if active_goals:
            lines.append("Active goals:")
            for g in active_goals[:3]:
                desc = getattr(g, "description", str(g))[:100]
                lines.append(f"- {desc}")

        return "\n".join(lines)

    def _build_reasoning_section(self, state: CognitionState) -> str:
        """Build reasoning results."""
        if not state.reasoning_result:
            return ""

        lines = ["## Reasoning Analysis"]
        goal = state.reasoning_result.get("goal", "")
        if goal:
            lines.append(f"Goal: {goal}")

        capabilities = state.reasoning_result.get("capabilities", [])
        if capabilities:
            lines.append("Capabilities identified:")
            for c in capabilities[:5]:
                name = c.get("name", "unknown")
                reason = c.get("reason", "")
                lines.append(f"- {name}" + (f": {reason}" if reason else ""))

        results = state.reasoning_result.get("results", [])
        if results:
            success_count = sum(1 for r in results if r.get("success"))
            lines.append(f"Capability execution: {success_count}/{len(results)} succeeded")

        return "\n".join(lines)

    def _build_planning_section(self, state: CognitionState) -> str:
        """Build planning decisions — influenced by world model and learning."""
        if not state.planning_result:
            return ""

        lines = ["## Plan"]
        goal = state.planning_result.get("goal", "")
        status = state.planning_result.get("status", "")
        if goal:
            lines.append(f"Goal: {goal} (status: {status})")

        sub_goals = state.planning_result.get("sub_goals", [])
        if sub_goals:
            lines.append(f"Sub-goals: {len(sub_goals)} defined")

        steps = state.planning_result.get("steps", [])
        if steps:
            lines.append("Steps:")
            for s in steps[:8]:
                desc = s.get("description", "")
                step_status = s.get("status", "")
                if desc:
                    lines.append(f"- {desc} [{step_status}]")

        errors = state.planning_result.get("validation_errors", [])
        if errors:
            lines.append(f"Validation warnings: {len(errors)}")

        return "\n".join(lines)

    def _build_tool_section(self, state: CognitionState) -> str:
        """Build tool execution results."""
        if not state.tool_result:
            return ""

        tool_name = state.tool_result.get("tool_name", "unknown")
        success = state.tool_result.get("success", False)
        output = state.tool_result.get("output", "")
        error = state.tool_result.get("error", "")

        lines = ["## Tool Execution"]
        lines.append(f"Tool: {tool_name} — {'succeeded' if success else 'failed'}")
        if output and success:
            lines.append(f"Output: {str(output)[:300]}")
        if error:
            lines.append(f"Error: {error}")

        return "\n".join(lines)

    def _build_learning_section(self, state: CognitionState) -> str:
        """Build learning insights for context."""
        insights: list[str] = []

        # Learning engine insights
        if state.learning_engine_result:
            summary = state.learning_engine_result.get("summary", {})
            pipelines = summary.get("pipelines_processed", 0)
            if pipelines:
                insights.append(f"Pipelines observed: {pipelines}")

            top = summary.get("top_insights", [])
            if top:
                insights.append("Recent learning insights:")
                for t in top[:3]:
                    title = t.get("title", "")
                    importance = t.get("importance", "")
                    if title:
                        insights.append(f"- {title} [{importance}]")

        # Reflection suggestions
        if state.reflection_suggestions:
            insights.append("Reflection observations:")
            for s in state.reflection_suggestions[:3]:
                pattern = getattr(s, "pattern", "")
                desc = getattr(s, "description", "")
                if pattern:
                    insights.append(f"- {pattern}: {desc}")

        if not insights:
            return ""

        return "## Learning & Reflection\n" + "\n".join(insights)

    def _build_role_instruction(self) -> str:
        """
        Define the LLM's role: it is the final reasoning assistant.

        Atlas's identity, reasoning, planning, and understanding are
        pre-computed by the cognitive pipeline. The LLM receives this
        structured context and produces the response.

        The LLM is the VOICE of Atlas — not the brain.
        """
        return (
            "## Role\n"
            "You are the voice of Atlas, an intelligent AI operating framework. "
            "The identity, reasoning, planning, understanding, memory retrieval, "
            "knowledge querying, tool execution, learning, and world modeling "
            "have already been performed by Atlas's cognitive pipeline. "
            "Your role is to:\n"
            "1. Synthesize the provided cognitive context into a coherent response.\n"
            "2. Be transparent about how you arrive at conclusions.\n"
            "3. Acknowledge uncertainty when the context is insufficient.\n"
            "4. Respect Atlas's identity, principles, and preferences.\n"
            "5. Do not hallucinate capabilities Atlas does not have.\n"
            "6. The context above represents Atlas's actual cognitive state — "
            "treat it as authoritative."
        )

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
    def evolution_scheduler(self):
        """Return the injected EvolutionScheduler, or None."""
        return self._evolution_scheduler

    def set_evolution_scheduler(self, scheduler: Any) -> None:
        """Inject an EvolutionScheduler after construction."""
        self._evolution_scheduler = scheduler

    @property
    def feedback_coordinator(self):
        return self._feedback_coordinator

    @property
    def experience_accumulator(self):
        return self._experience_accumulator

    @property
    def self_model_engine(self):
        return self._self_model_engine

    def set_experience_accumulator(self, accumulator: Any) -> None:
        """Inject an ExperienceAccumulator after construction."""
        self._experience_accumulator = accumulator

    def set_self_model_engine(self, engine: Any) -> None:
        """Inject a SelfModelEngine after construction."""
        self._self_model_engine = engine

    @property
    def conversation_service(self):
        return self._conversation_service

    @property
    def event_bus(self):
        return self._event_bus

    @property
    def engine(self):
        return self._engine

    @property
    def improvement_planner(self):
        return self._improvement_planner

    @property
    def proposal_generator(self):
        return self._proposal_generator

    @property
    def approval_manager(self):
        return self._approval_manager

    @property
    def evolution_memory(self):
        return self._evolution_memory

    @property
    def current_metrics(self):
        """Return the transient metrics reference for the current pipeline run, or None."""
        return self._current_metrics
