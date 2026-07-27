"""
Atlas ExperienceAccumulator — Phase 9.0

Converts a single cognitive pipeline execution (CognitionState +
PipelineResult) into a structured experience record and stores it.

Pure logic. No infrastructure. No RuntimeCoordinator dependency.
"""

from datetime import datetime
from typing import Any

from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.experience.experience_repository import ExperienceRepository


class ExperienceAccumulator:
    """
    Captures pipeline executions as structured experiences.

    This component is intentionally passive: it records what happened,
    but does not analyze or act on the data. Analysis is the responsibility
    of the SelfModelEngine.
    """

    def __init__(self, repository: ExperienceRepository | None = None):
        self._repository = repository or ExperienceRepository()
        self._experience_counter = 0

    def record(
        self,
        state: Any,
        result: Any,
    ) -> StructuredExperience | None:
        """
        Convert a pipeline execution into a StructuredExperience and store it.

        Args:
            state: A CognitionState instance (duck-typed to avoid circular deps).
            result: A PipelineResult instance.

        Returns:
            The recorded StructuredExperience, or None if inputs are invalid.
        """
        if state is None or result is None:
            return None

        self._experience_counter += 1
        experience_id = f"EXP-{self._experience_counter:08d}"

        timestamp = getattr(result, "metrics", None)
        timestamp = getattr(timestamp, "completed_at", None) or datetime.now()

        duration_ms = getattr(getattr(result, "metrics", None), "total_duration_ms", 0.0)
        pipeline_path = getattr(getattr(result, "metrics", None), "pipeline_path", [])

        outcome = self._derive_outcome(result)

        experience = StructuredExperience(
            experience_id=experience_id,
            timestamp=timestamp,
            duration_ms=duration_ms,
            pipeline_path=list(pipeline_path),
            outcome=outcome,

            user_input=getattr(state, "user_input", "")[:500],
            conversation_history_length=getattr(
                getattr(state, "conversation_context", None), "get", lambda k, d: d
            )("history_length", 0),

            understanding_insights_count=len(getattr(state, "understanding_insights", [])),
            concepts_extracted=self._extract_concept_labels(state),
            world_model_entities=getattr(getattr(state, "world_model_state", {}), "get", lambda k, d: d)("graph_entities", 0),
            world_model_relations=getattr(getattr(state, "world_model_state", {}), "get", lambda k, d: d)("graph_relations", 0),

            reasoning_goal=self._extract_reasoning_goal(state),
            reasoning_capabilities=self._extract_capability_names(state),
            reasoning_success_count=self._extract_reasoning_success_count(state),
            reasoning_total_count=self._extract_reasoning_total_count(state),

            planning_goal=self._extract_planning_goal(state),
            planning_step_count=self._extract_planning_step_count(state),
            planning_validation_errors=self._extract_planning_errors(state),

            tool_name=getattr(getattr(state, "tool_result", {}), "get", lambda k, d: d)("tool_name", ""),
            tool_success=getattr(getattr(state, "tool_result", {}), "get", lambda k, d: d)("tool_success", False),

            learning_insights_count=self._extract_learning_insights_count(state),
            reflection_suggestions_count=len(getattr(state, "reflection_suggestions", [])),
            goal_recommendations_count=self._extract_goal_recommendations_count(state),

            identity_version=0,
            identity_belief_count=0,
            identity_capability_count=0,
        )

        self._repository.store_experience(experience)
        return experience

    @property
    def repository(self) -> ExperienceRepository:
        return self._repository

    @property
    def recorded_count(self) -> int:
        return self._repository.experience_count

    def seed_counter(self, n: int) -> None:
        """
        Seed the experience counter from a restored state.

        Ensures that newly recorded experience IDs do not collide with
        experiences loaded from persistent storage on startup.
        """
        self._experience_counter = max(0, n)

    # ------------------------------------------------------------------
    # Extraction helpers (all defensive against missing attributes)
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_outcome(result: Any) -> ExperienceOutcome:
        stages = getattr(result, "stages", []) or []
        if not stages:
            return ExperienceOutcome.SKIPPED

        failed = sum(1 for s in stages if getattr(s, "status", None) and "FAILED" in str(s.status))
        total = len(stages)

        if failed == 0:
            return ExperienceOutcome.SUCCESS
        if failed == total:
            return ExperienceOutcome.FAILURE
        return ExperienceOutcome.PARTIAL

    @staticmethod
    def _extract_concept_labels(state: Any) -> list[str]:
        concepts = getattr(state, "concepts", []) or []
        labels: list[str] = []
        for c in concepts[:20]:
            label = getattr(c, "label", None) or getattr(c, "name", None) or str(c)
            labels.append(label)
        return labels

    @staticmethod
    def _extract_reasoning_goal(state: Any) -> str:
        reasoning = getattr(state, "reasoning_result", {}) or {}
        return reasoning.get("goal", "") if isinstance(reasoning, dict) else ""

    @staticmethod
    def _extract_capability_names(state: Any) -> list[str]:
        reasoning = getattr(state, "reasoning_result", {}) or {}
        if not isinstance(reasoning, dict):
            return []
        capabilities = reasoning.get("capabilities", []) or []
        return [c.get("name", "") for c in capabilities if isinstance(c, dict)]

    @staticmethod
    def _extract_reasoning_success_count(state: Any) -> int:
        reasoning = getattr(state, "reasoning_result", {}) or {}
        if not isinstance(reasoning, dict):
            return 0
        results = reasoning.get("results", []) or []
        return sum(1 for r in results if isinstance(r, dict) and r.get("success"))

    @staticmethod
    def _extract_reasoning_total_count(state: Any) -> int:
        reasoning = getattr(state, "reasoning_result", {}) or {}
        if not isinstance(reasoning, dict):
            return 0
        return len(reasoning.get("results", []) or [])

    @staticmethod
    def _extract_planning_goal(state: Any) -> str:
        planning = getattr(state, "planning_result", {}) or {}
        return planning.get("goal", "") if isinstance(planning, dict) else ""

    @staticmethod
    def _extract_planning_step_count(state: Any) -> int:
        planning = getattr(state, "planning_result", {}) or {}
        if not isinstance(planning, dict):
            return 0
        return len(planning.get("steps", []) or [])

    @staticmethod
    def _extract_planning_errors(state: Any) -> int:
        planning = getattr(state, "planning_result", {}) or {}
        if not isinstance(planning, dict):
            return 0
        return len(planning.get("validation_errors", []) or [])

    @staticmethod
    def _extract_learning_insights_count(state: Any) -> int:
        learning = getattr(state, "learning_engine_result", {}) or {}
        if not isinstance(learning, dict):
            return 0
        return learning.get("insights_count", 0)

    @staticmethod
    def _extract_goal_recommendations_count(state: Any) -> int:
        report = getattr(state, "goal_intelligence_report", None)
        if report is None:
            return 0
        return getattr(report, "total_recommendations", 0)
