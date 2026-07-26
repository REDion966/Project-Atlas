"""
Atlas FeedbackCoordinator — Phase 8.2 Cognitive Feedback Loop.

After each cognitive pipeline execution, the FeedbackCoordinator
closes the loop by distributing accumulated evidence back into
the cognitive subsystems. This allows Atlas to improve itself
through evidence — NEVER through autonomous code modification.

Architecture rules:
  - Pure logic — no AI, no infrastructure, no EventBus
  - All components receive data through method parameters
  - Identity NEVER modifies itself autonomously
  - Capabilities evolve gradually from repeated evidence
  - Beliefs change through accumulated evidence only — never single events
  - World Model updates from structured observations only
  - Learning insights feed Understanding and World Model as structured evidence
"""

from typing import Any


class FeedbackCoordinator:
    """
    Closes the cognitive feedback loop after each pipeline execution.

    Injected dependencies (all optional — skipped gracefully if None):
      - identity_engine: BeliefManager + CapabilityProfiler + DecisionStyleManager
      - world_model_engine: WorldModelEngine for outcome recording
      - understanding_engine: UnderstandingEngine for evidence feeding
      - learning_engine: LearningEngine for insight extraction

    The coordinator observes the complete pipeline state and distributes
    structured feedback without modifying any subsystem autonomously.
    """

    def __init__(
        self,
        identity_engine: Any = None,
        world_model_engine: Any = None,
        understanding_engine: Any = None,
        learning_engine: Any = None,
    ):
        self._identity_engine = identity_engine
        self._world_model_engine = world_model_engine
        self._understanding_engine = understanding_engine
        self._learning_engine = learning_engine

    # ------------------------------------------------------------------
    # Main entry point — called after pipeline execution
    # ------------------------------------------------------------------

    def process_feedback(self, state: Any, result: Any) -> dict[str, Any]:
        """
        Process feedback from a completed pipeline execution.

        Distributes evidence back into:
          1. CapabilityProfiler — update capability confidence/stability
          2. BeliefManager — strengthen/weaken beliefs from learning evidence
          3. WorldModelEngine — record observations and outcomes
          4. UnderstandingEngine — feed learning insights as structured evidence
          5. DecisionStyleManager — observe style effectiveness

        Args:
            state: The CognitionState after all pipeline stages.
            result: The PipelineResult with metrics and stage results.

        Returns:
            A summary dict of feedback actions taken.
        """
        feedback_summary: dict[str, Any] = {}

        # 1. Update capability profiles from execution outcomes
        cap_updates = self._update_capabilities(result)
        if cap_updates:
            feedback_summary["capabilities_updated"] = cap_updates

        # 2. Strengthen/weaken beliefs from learning evidence
        belief_changes = self._update_beliefs_from_evidence(state, result)
        if belief_changes:
            feedback_summary["beliefs_updated"] = belief_changes

        # 3. Feed learning insights into World Model
        wm_updates = self._update_world_model(state, result)
        if wm_updates:
            feedback_summary["world_model_updated"] = wm_updates

        # 4. Feed learning insights into Understanding Engine
        understanding_updates = self._feed_understanding(state)
        if understanding_updates:
            feedback_summary["understanding_updated"] = understanding_updates

        # 5. Observe decision style effectiveness
        style_update = self._observe_decision_style(state)
        if style_update:
            feedback_summary["decision_style_updated"] = style_update

        return feedback_summary

    # ------------------------------------------------------------------
    # 1. Capability updates
    # ------------------------------------------------------------------

    def _update_capabilities(self, result: Any) -> list[str]:
        """Update CapabilityProfiler from pipeline stage results."""
        if self._identity_engine is None:
            return []

        profiler = getattr(self._identity_engine, "capabilities", None)
        if profiler is None:
            return []

        updated: list[str] = []
        stages = getattr(result, "stages", []) or []

        # Map stage names to capability names
        stage_to_capability = {
            "MEMORY_RETRIEVAL": "memory_retrieval",
            "KNOWLEDGE_RETRIEVAL": "knowledge_retrieval",
            "UNDERSTANDING": "understanding",
            "REASONING": "reasoning",
            "PLANNING": "planning",
            "TOOL_DECISION": "tool_usage",
            "TOOL_EXECUTION": "tool_usage",
            "REFLECTION": "reflection",
            "LEARNING": "learning",
        }

        for stage in stages:
            stage_name = getattr(stage, "stage", None)
            if stage_name is None:
                continue

            # Get the string name of the stage
            name = getattr(stage_name, "name", str(stage_name))
            cap_name = stage_to_capability.get(name)
            if cap_name is None:
                continue

            status = getattr(stage, "status", None)
            if status is None:
                continue

            # Map StageStatus to success bool
            status_name = getattr(status, "name", str(status))
            success = status_name == "SUCCESS"

            # Update capability — only if it exists (seeded by IdentityEngine)
            existing = getattr(profiler, "_memory", None)
            if existing and hasattr(existing, "get_capability_by_name"):
                cap = existing.get_capability_by_name(cap_name)
                if cap is not None:
                    profiler.update_capability(cap_name, success=success)
                    updated.append(cap_name)

        return updated

    # ------------------------------------------------------------------
    # 2. Belief updates from learning evidence
    # ------------------------------------------------------------------

    def _update_beliefs_from_evidence(
        self,
        state: Any,
        result: Any,
    ) -> list[str]:
        """
        Strengthen or weaken beliefs based on accumulated evidence.

        Key rule: Beliefs change from REPEATED evidence, never single events.
        The LearningEngine's insight count and reflection patterns provide
        the evidence signal.
        """
        if self._identity_engine is None:
            return []

        beliefs = getattr(self._identity_engine, "beliefs", None)
        if beliefs is None:
            return []

        changed: list[str] = []

        # Evidence from learning engine results
        learning_result = getattr(state, "learning_engine_result", None) or {}
        insight_count = learning_result.get("insights_count", 0)

        # Evidence from reflection suggestions
        reflection_suggestions = getattr(state, "reflection_suggestions", None) or []
        reflection_count = len(reflection_suggestions)

        # Evidence from reasoning success
        reasoning = getattr(state, "reasoning_result", None) or {}
        reasoning_results = reasoning.get("results", [])
        reasoning_success_count = sum(1 for r in reasoning_results if r.get("success"))

        # Evidence from planning
        planning = getattr(state, "planning_result", None) or {}
        planning_errors = len(planning.get("validation_errors", []))

        # Strengthen beliefs about learning when we have insights
        if insight_count > 0:
            for belief in self._get_active_beliefs("self"):
                if "learning" in getattr(belief, "statement", "").lower():
                    updated = beliefs.strengthen_belief(getattr(belief, "belief_id", ""))
                    if updated:
                        changed.append(getattr(updated, "belief_id", ""))

        # Strengthen beliefs about reasoning when it succeeds
        if reasoning_success_count > 0:
            for belief in self._get_active_beliefs("self"):
                if "reasoning" in getattr(belief, "statement", "").lower():
                    updated = beliefs.strengthen_belief(getattr(belief, "belief_id", ""))
                    if updated:
                        changed.append(getattr(updated, "belief_id", ""))

        # Weaken beliefs when planning has validation errors
        if planning_errors > 2:
            for belief in self._get_active_beliefs("self"):
                if "architecture" in getattr(belief, "category", ""):
                    beliefs.weaken_belief(getattr(belief, "belief_id", ""))

        return changed

    def _get_active_beliefs(self, category: str | None = None) -> list[Any]:
        """Get active (non-retired) beliefs, optionally filtered by category."""
        if self._identity_engine is None:
            return []
        beliefs = getattr(self._identity_engine, "beliefs", None)
        if beliefs is None:
            return []
        active = beliefs.get_active_beliefs()
        if category:
            return [b for b in active if getattr(b, "category", "") == category]
        return active

    # ------------------------------------------------------------------
    # 3. World Model updates
    # ------------------------------------------------------------------

    def _update_world_model(self, state: Any, result: Any) -> dict[str, Any]:
        """
        Update World Model with execution outcomes.

        Records:
          - Successful and failed plans as events
          - Tool execution outcomes as observations
          - Learning insights as entities
        """
        if self._world_model_engine is None:
            return {}

        updates: dict[str, Any] = {}

        # Record pipeline success/failure as an event
        success = getattr(result, "success", False)
        stages_count = getattr(getattr(result, "metrics", None), "stage_count", 0)
        event = self._world_model_engine.record_event(
            event_type="COGNITIVE_PIPELINE",
            description=f"Pipeline: {stages_count} stages, {'success' if success else 'failure'}",
            source_entity_id="runtime_coordinator",
            data={"success": success, "stage_count": stages_count},
        )
        updates["event_recorded"] = getattr(event, "event_id", "unknown")

        # Record planning outcome
        planning = getattr(state, "planning_result", None) or {}
        if planning:
            plan_goal = planning.get("goal", "")
            plan_status = planning.get("status", "")
            if plan_goal:
                goal = self._world_model_engine.define_goal(
                    description=f"Pipeline goal: {plan_goal[:100]}",
                )
                if plan_status == "completed" or plan_status == "success":
                    self._world_model_engine.complete_goal(getattr(goal, "goal_id", ""))
                updates["goal_defined"] = getattr(goal, "goal_id", "unknown")

        # Record tool outcome as observation
        tool_result = getattr(state, "tool_result", None) or {}
        if tool_result:
            self._world_model_engine.record_observation(
                description=f"Tool '{tool_result.get('tool_name', 'unknown')}' "
                           f"— {'success' if tool_result.get('success') else 'failure'}",
                entity_id="tool_engine",
                source="feedback_coordinator",
            )
            updates["tool_observation_recorded"] = True

        return updates

    # ------------------------------------------------------------------
    # 4. Understanding Engine updates
    # ------------------------------------------------------------------

    def _feed_understanding(self, state: Any) -> dict[str, Any]:
        """
        Feed learning insights back into UnderstandingEngine
        as structured evidence for concept extraction and pattern analysis.
        """
        if self._understanding_engine is None:
            return {}

        updates: dict[str, Any] = {}

        # Feed reflection suggestions as understanding observations
        suggestions = getattr(state, "reflection_suggestions", None) or []
        for s in suggestions[:3]:
            pattern = getattr(s, "pattern", "")
            description = getattr(s, "description", "")
            if pattern:
                self._understanding_engine.process_text(
                    text=f"Reflection: {pattern} — {description}",
                    source="feedback_coordinator",
                )
                updates.setdefault("reflection_patterns_fed", 0)
                updates["reflection_patterns_fed"] += 1

        # Feed learning engine summary
        learning_result = getattr(state, "learning_engine_result", None) or {}
        summary = learning_result.get("summary", {})
        top_insights = summary.get("top_insights", [])
        for t in top_insights[:3]:
            title = t.get("title", "")
            if title:
                self._understanding_engine.process_text(
                    text=f"Learning insight: {title}",
                    source="feedback_coordinator",
                )
                updates.setdefault("learning_insights_fed", 0)
                updates["learning_insights_fed"] += 1

        return updates

    # ------------------------------------------------------------------
    # 5. Decision style observation
    # ------------------------------------------------------------------

    def _observe_decision_style(self, state: Any) -> dict[str, Any]:
        """Observe and update decision style based on pipeline outcomes."""
        if self._identity_engine is None:
            return {}

        style_manager = getattr(self._identity_engine, "decision_style", None)
        if style_manager is None:
            return {}

        updates: dict[str, Any] = {}

        # Observe reasoning style based on capability selection
        reasoning = getattr(state, "reasoning_result", None) or {}
        capabilities = reasoning.get("capabilities", [])
        if capabilities:
            # Structured analysis succeeded if capabilities were identified
            style_manager.observe_reasoning("structured_analysis", success=len(capabilities) > 0)
            updates["reasoning_style_observed"] = True

        # Observe planning style
        planning = getattr(state, "planning_result", None) or {}
        steps = planning.get("steps", [])
        if steps:
            style_manager.observe_planning("stepwise_decomposition", success=len(steps) > 0)
            updates["planning_style_observed"] = True

        # Observe tool usage
        tool_result = getattr(state, "tool_result", None) or {}
        if tool_result.get("tool_name"):
            style_manager.observe_tool_usage("selective", success=tool_result.get("success", False))
            updates["tool_style_observed"] = True

        return updates

    def summary(self) -> dict[str, bool]:
        """Return availability of all feedback targets."""
        return {
            "has_identity": self._identity_engine is not None,
            "has_world_model": self._world_model_engine is not None,
            "has_understanding": self._understanding_engine is not None,
            "has_learning": self._learning_engine is not None,
        }