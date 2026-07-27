"""
Atlas SelfModelEngine — Phase 9.0

Orchestrates the analysis of accumulated experiences and produces
a SelfModelSnapshot. Provides evidence-based proposals for identity
evolution, capability reassessment, and improvement planning.

This engine NEVER directly rewrites identity. It only feeds evidence
into IdentityEngine's existing evidence-based update methods. All
identity changes remain approval-safe and gradual.

Pure logic. No AI. No infrastructure. No autonomous modification.
"""

from datetime import datetime
from typing import Any

from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    SelfModelSnapshot,
    StructuredExperience,
    TrendAnalysis,
    TrackedGoal,
)
from atlas.experience import serialization
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.trend_analyzer import TrendAnalyzer
from atlas.experience.outcome_tracker import OutcomeTracker


class SelfModelEngine:
    """
    Produces and maintains Atlas's self-model from accumulated experience.

    The engine is the bridge between transient pipeline executions and
    long-term adaptive identity. It:
      - Reads experiences from ExperienceRepository
      - Runs TrendAnalyzer to detect directional changes
      - Feeds evidence into IdentityEngine (beliefs, capabilities, decision style)
      - Feeds self-observations into UnderstandingEngine
      - Tracks goal outcomes via OutcomeTracker
      - Produces a SelfModelSnapshot

    All injected dependencies are optional. Missing dependencies cause
    that subsystem's update to be skipped gracefully.
    """

    DEFAULT_WINDOW_SIZE = 20
    DEFAULT_UPDATE_INTERVAL = 5

    def __init__(
        self,
        repository: ExperienceRepository | None = None,
        trend_analyzer: TrendAnalyzer | None = None,
        outcome_tracker: OutcomeTracker | None = None,
        identity_engine: Any = None,
        understanding_engine: Any = None,
        goal_intelligence_engine: Any = None,
        window_size: int = DEFAULT_WINDOW_SIZE,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ):
        self._repository = repository or ExperienceRepository()
        self._trend_analyzer = trend_analyzer or TrendAnalyzer()
        self._outcome_tracker = outcome_tracker or OutcomeTracker(repository=self._repository)
        self._identity_engine = identity_engine
        self._understanding_engine = understanding_engine
        self._goal_intelligence_engine = goal_intelligence_engine
        self._window_size = max(2, window_size)
        self._update_interval = max(1, update_interval)
        self._update_counter = 0
        self._snapshot_counter = 0
        self._latest_snapshot: SelfModelSnapshot | None = None

    def update(self) -> SelfModelSnapshot | None:
        """
        Analyze accumulated experiences and update the self-model.

        Runs every update_interval calls. On each run:
          1. Reads recent experience window
          2. Produces trend analysis
          3. Evaluates tracked goal outcomes
          4. Feeds evidence to identity, understanding, and goals
          5. Produces SelfModelSnapshot

        Returns:
            The latest SelfModelSnapshot, or None if not enough data.
        """
        self._update_counter += 1
        if self._update_counter % self._update_interval != 0:
            return self._latest_snapshot

        experiences = self._repository.get_window(self._window_size)
        if not experiences:
            return self._latest_snapshot

        analysis = self._trend_analyzer.analyze(experiences)
        self._repository.store_analysis(analysis)

        # Evaluate goal outcomes
        self._outcome_tracker.evaluate_outcomes()

        # Compute persistent challenges for downstream consumers
        persistent_challenges = self._identify_persistent_challenges(analysis, experiences)

        # Feed evidence to subsystems
        self._update_identity(analysis, experiences)
        self._feed_self_understanding(analysis, experiences, persistent_challenges)
        self._feed_goal_intelligence(analysis, experiences, persistent_challenges)

        snapshot = self._build_snapshot(analysis, experiences, persistent_challenges)
        self._latest_snapshot = snapshot

        # Persist snapshot through repository. Best-effort; storage failures
        # are swallowed so the pipeline is never blocked by persistence.
        try:
            self._repository.persist_snapshot(serialization.snapshot_to_dict(snapshot))
        except Exception:
            pass

        return snapshot

    def get_snapshot(self) -> SelfModelSnapshot | None:
        """Return the most recent self-model snapshot."""
        return self._latest_snapshot

    @property
    def repository(self) -> ExperienceRepository:
        return self._repository

    @property
    def update_count(self) -> int:
        return self._update_counter

    def seed_snapshot_counter(self, n: int) -> None:
        """
        Seed the snapshot counter from a restored state.

        Prevents newly generated snapshot IDs from colliding with snapshots
        loaded from persistent storage on startup.
        """
        self._snapshot_counter = max(0, n)

    def restore_snapshot(self, snapshot_dict: dict) -> SelfModelSnapshot | None:
        """
        Restore the latest self-model snapshot from a dictionary.

        Sets _latest_snapshot and synchronizes _snapshot_counter with the
        restored snapshot_id so subsequent snapshots continue the sequence.
        """
        snapshot = serialization.dict_to_snapshot(snapshot_dict)
        self._latest_snapshot = snapshot
        sid = snapshot.snapshot_id
        if isinstance(sid, str) and sid.startswith("SELF-") and sid[5:].isdigit():
            # _build_snapshot pre-increments the counter before using it, so
            # seed to the restored numeric ID; the next build will produce ID+1.
            self._snapshot_counter = int(sid[5:])
        return self._latest_snapshot

    # ------------------------------------------------------------------
    # Evidence feeding (approval-safe, never directly mutates identity)
    # ------------------------------------------------------------------

    def _update_identity(
        self,
        analysis: TrendAnalysis,
        experiences: list[StructuredExperience],
    ) -> None:
        """Feed trend evidence into IdentityEngine via its evidence methods."""
        if self._identity_engine is None:
            return

        # Strengthen or weaken core beliefs based on overall success trend
        belief_manager = getattr(self._identity_engine, "belief_manager", None)
        if belief_manager is not None:
            if analysis.success_rate_trend == "improving":
                self._strengthen_belief(
                    belief_manager,
                    "I am continuously improving through experience.",
                    min(0.9, analysis.overall_success_rate),
                )
            elif analysis.success_rate_trend == "declining":
                self._weaken_belief(
                    belief_manager,
                    "I am continuously improving through experience.",
                    0.1,
                )

            if analysis.reasoning_trend == "improving":
                self._strengthen_belief(
                    belief_manager,
                    "My reasoning pipeline produces reliable outcomes.",
                    min(0.9, analysis.avg_reasoning_success),
                )
            elif analysis.reasoning_trend == "declining":
                self._weaken_belief(
                    belief_manager,
                    "My reasoning pipeline produces reliable outcomes.",
                    0.1,
                )

        # Update capability profiles from capability trends
        profiler = getattr(self._identity_engine, "capability_profiler", None)
        if profiler is not None and analysis.capability_trends:
            for capability_name, trend in analysis.capability_trends.items():
                if trend == "improving":
                    self._update_capability(profiler, capability_name, success=True)
                elif trend == "declining":
                    self._update_capability(profiler, capability_name, success=False)

        # Observe decision style from recent outcomes
        style_manager = getattr(self._identity_engine, "decision_style_manager", None)
        if style_manager is not None and experiences:
            latest = experiences[-1]
            observe = getattr(style_manager, "observe_outcome", None)
            if observe is not None:
                observe(
                    success=latest.outcome == ExperienceOutcome.SUCCESS,
                    confidence=self._estimate_confidence(latest),
                )

    @staticmethod
    def _strengthen_belief(belief_manager: Any, statement: str, amount: float) -> None:
        strengthen = getattr(belief_manager, "strengthen_belief", None)
        if strengthen is not None:
            strengthen(statement, evidence_strength=round(amount, 4))

    @staticmethod
    def _weaken_belief(belief_manager: Any, statement: str, amount: float) -> None:
        weaken = getattr(belief_manager, "weaken_belief", None)
        if weaken is not None:
            weaken(statement, evidence_strength=round(amount, 4))

    @staticmethod
    def _update_capability(profiler: Any, capability_name: str, success: bool) -> None:
        update = getattr(profiler, "update_capability", None)
        if update is not None:
            update(capability_name, success=success)
        else:
            record = getattr(profiler, "record_outcome", None)
            if record is not None:
                record(capability_name, success=success)

    @staticmethod
    def _estimate_confidence(experience: StructuredExperience) -> float:
        if experience.outcome == ExperienceOutcome.SUCCESS:
            return 0.8
        if experience.outcome == ExperienceOutcome.PARTIAL:
            return 0.5
        return 0.2

    # ------------------------------------------------------------------
    # Self-understanding feed
    # ------------------------------------------------------------------

    def _feed_self_understanding(
        self,
        analysis: TrendAnalysis,
        experiences: list[StructuredExperience],
        persistent_challenges: list[str] | None = None,
    ) -> None:
        """Feed a structured self-observation into UnderstandingEngine."""
        if self._understanding_engine is None:
            return

        observation = self._build_self_observation(analysis, experiences, persistent_challenges or [])
        process = getattr(self._understanding_engine, "process_text", None)
        if process is not None:
            process(text=observation, source="self_model_engine")

    @staticmethod
    def _build_self_observation(
        analysis: TrendAnalysis,
        experiences: list[StructuredExperience],
        persistent_challenges: list[str],
    ) -> str:
        recent = experiences[-1] if experiences else None
        parts = [
            f"Self-observation: Atlas has {len(experiences)} recent experiences. "
            f"Overall success rate is {analysis.overall_success_rate:.0%} and trending {analysis.success_rate_trend}. "
            f"Reasoning success is {analysis.avg_reasoning_success:.0%} and trending {analysis.reasoning_trend}. "
            f"Understanding insight rate is {analysis.avg_understanding_insights:.2f} and trending {analysis.understanding_trend}. "
            f"Planning error rate is {analysis.avg_planning_errors:.2f} and trending {analysis.planning_trend}. "
            f"Tool success rate is {analysis.tool_success_rate:.0%} and trending {analysis.tool_trend}. "
            f"Learning insight rate is {analysis.learning_insight_rate:.2f} and trending {analysis.learning_trend}.",
        ]
        if recent:
            parts.append(
                f"Latest experience {recent.experience_id} had outcome {recent.outcome.name} "
                f"with goal '{recent.reasoning_goal or recent.planning_goal}'.",
            )
        if persistent_challenges:
            parts.append("Persistent challenges: " + ", ".join(persistent_challenges[:5]))
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Goal intelligence feed
    # ------------------------------------------------------------------

    def _feed_goal_intelligence(
        self,
        analysis: TrendAnalysis,
        experiences: list[StructuredExperience],
        persistent_challenges: list[str] | None = None,
    ) -> None:
        """Feed trend evidence into GoalIntelligenceEngine."""
        if self._goal_intelligence_engine is None:
            return

        evidence = {
            "self_model_trends": {
                "success_rate_trend": analysis.success_rate_trend,
                "reasoning_trend": analysis.reasoning_trend,
                "understanding_trend": analysis.understanding_trend,
                "planning_trend": analysis.planning_trend,
                "tool_trend": analysis.tool_trend,
                "learning_trend": analysis.learning_trend,
            },
            "persistent_challenges": persistent_challenges or [],
            "outcome_summary": self._outcome_tracker.get_outcome_summary(),
        }

        analyze = getattr(self._goal_intelligence_engine, "analyze", None)
        if analyze is not None:
            analyze(evidence)

    # ------------------------------------------------------------------
    # Snapshot construction
    # ------------------------------------------------------------------

    def _build_snapshot(
        self,
        analysis: TrendAnalysis,
        experiences: list[StructuredExperience],
        persistent_challenges: list[str] | None = None,
    ) -> SelfModelSnapshot:
        self._snapshot_counter += 1
        snapshot_id = f"SELF-{self._snapshot_counter:06d}"

        all_experiences = self._repository.experience_count
        overall_success = self._trend_analyzer._success_rate(
            self._repository.get_experiences(n=all_experiences)
        )

        capability_assessments = self._build_capability_assessments(analysis, experiences)
        belief_evidence = self._build_belief_evidence()

        improvement_evidence = self._collect_improvement_evidence(analysis)
        challenges = persistent_challenges or self._identify_persistent_challenges(analysis, experiences)

        return SelfModelSnapshot(
            snapshot_id=snapshot_id,
            timestamp=datetime.now(),
            total_experiences=all_experiences,
            overall_success_rate=round(overall_success, 4),
            capability_assessments=capability_assessments,
            belief_evidence=belief_evidence,
            trend_summary=self._build_trend_summary(analysis),
            identity_version=self._get_identity_version(),
            last_trend_analysis=analysis.timestamp,
            recent_improvement_evidence=improvement_evidence,
            persistent_challenges=challenges,
        )

    def _build_capability_assessments(
        self,
        analysis: TrendAnalysis,
        experiences: list[StructuredExperience],
    ) -> dict[str, float]:
        """Map capability trends to 0.0-1.0 confidence scores."""
        assessments: dict[str, float] = {}

        for cap, trend in analysis.capability_trends.items():
            if trend == "improving":
                assessments[cap] = 0.75
            elif trend == "stable":
                assessments[cap] = 0.55
            else:
                assessments[cap] = 0.35

        # Fallback for observed capabilities without enough data
        for exp in experiences:
            for cap in exp.reasoning_capabilities:
                if cap and cap not in assessments:
                    if exp.outcome == ExperienceOutcome.SUCCESS:
                        assessments[cap] = 0.60
                    elif exp.outcome == ExperienceOutcome.PARTIAL:
                        assessments[cap] = 0.45
                    else:
                        assessments[cap] = 0.30

        return assessments

    def _build_belief_evidence(self) -> dict[str, float]:
        """Extract current belief confidence from IdentityEngine if available."""
        if self._identity_engine is None:
            return {}

        belief_manager = getattr(self._identity_engine, "belief_manager", None)
        if belief_manager is None:
            return {}

        beliefs = getattr(belief_manager, "beliefs", {})
        if not isinstance(beliefs, dict):
            return {}

        return {
            statement: getattr(belief, "confidence", 0.5)
            for statement, belief in beliefs.items()
            if hasattr(belief, "confidence")
        }

    def _collect_improvement_evidence(self, analysis: TrendAnalysis) -> list[str]:
        """Collect evidence of recent improvement for the snapshot."""
        evidence: list[str] = []
        if analysis.success_rate_trend == "improving":
            evidence.append(f"Overall success rate improving to {analysis.overall_success_rate:.0%}")
        if analysis.reasoning_trend == "improving":
            evidence.append(f"Reasoning success improving to {analysis.avg_reasoning_success:.0%}")
        if analysis.understanding_trend == "improving":
            evidence.append(f"Understanding depth improving ({analysis.avg_understanding_insights:.2f} insights/run)")
        if analysis.learning_trend == "improving":
            evidence.append(f"Learning insight rate improving ({analysis.learning_insight_rate:.2f}/run)")
        return evidence

    def _identify_persistent_challenges(
        self,
        analysis: TrendAnalysis,
        experiences: list[StructuredExperience],
    ) -> list[str]:
        """Identify persistent challenges from declining trends."""
        challenges: list[str] = []
        if analysis.reasoning_trend == "declining":
            challenges.append("Reasoning success is declining")
        if analysis.planning_trend == "declining":
            challenges.append("Planning errors are increasing")
        if analysis.tool_trend == "declining":
            challenges.append("Tool success rate is declining")
        if analysis.understanding_trend == "declining":
            challenges.append("Understanding insight generation is declining")

        # Identify most common failure capability
        failure_caps: dict[str, int] = {}
        for exp in experiences:
            if exp.outcome != ExperienceOutcome.SUCCESS:
                for cap in exp.reasoning_capabilities:
                    if cap:
                        failure_caps[cap] = failure_caps.get(cap, 0) + 1
        if failure_caps:
            weakest = max(failure_caps, key=lambda k: failure_caps[k])
            challenges.append(f"Capability '{weakest}' appears in failed outcomes")

        return challenges

    @staticmethod
    def _build_trend_summary(analysis: TrendAnalysis) -> str:
        parts = [
            f"Success: {analysis.success_rate_trend} ({analysis.overall_success_rate:.0%})",
            f"Reasoning: {analysis.reasoning_trend} ({analysis.avg_reasoning_success:.0%})",
            f"Understanding: {analysis.understanding_trend} ({analysis.avg_understanding_insights:.2f})",
            f"Planning: {analysis.planning_trend} ({analysis.avg_planning_errors:.2f} errors)",
            f"Tools: {analysis.tool_trend} ({analysis.tool_success_rate:.0%})",
            f"Learning: {analysis.learning_trend} ({analysis.learning_insight_rate:.2f})",
        ]
        return " | ".join(parts)

    def _get_identity_version(self) -> int:
        if self._identity_engine is None:
            return 0
        return getattr(self._identity_engine, "version", 0)
