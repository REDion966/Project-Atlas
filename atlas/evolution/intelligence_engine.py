"""
Atlas EvolutionIntelligenceEngine — Phase 12.2 / 12.3

Orchestration layer that connects executed evolution proposals with
InsightScorer and produces EvolutionInsight objects.

This is an analytical-only component. It reads, scores, and reports.
It NEVER:
  - executes proposals
  - approves proposals
  - modifies proposals
  - calls AI providers
  - generates code
  - modifies Atlas behavior

All dependencies are optional via constructor injection. Missing
dependencies cause operations to be skipped gracefully, preserving
backward compatibility and enabling incremental testing.

Phase 12.3 — When an EvolutionStorage adapter is injected, insights are
persisted after creation and loaded from storage for query operations.
"""

from datetime import datetime
from typing import Any

from atlas.evolution.models import (
    EvolutionInsight,
    EvolutionProposal,
    EvolutionRecord,
)
from atlas.experience.models import TrackedGoal


class EvolutionIntelligenceEngine:
    """
    Orchestrates evolution outcome analysis.

    Uses injected EvolutionMemory, ExperienceRepository, and InsightScorer
    to produce structured EvolutionInsight objects from executed proposals.

    Insights are stored in-memory and optionally persisted via an injected
    EvolutionStorage adapter. When storage is available, get_insights()
    prioritises storage reads with in-memory fallback.

    Architecture:
      analyze_proposal()
          │
          ├── EvolutionMemory.get_proposal()
          ├── EvolutionMemory.get_records_by_type("execution")
          ├── ExperienceRepository.get_tracked_goals()
          ├── ExperienceRepository.get_experiences_since()
          │
          └── InsightScorer methods
                  │
                  └── EvolutionInsight → (optional) EvolutionStorage
    """

    def __init__(
        self,
        evolution_memory: Any = None,
        experience_repository: Any = None,
        insight_scorer: Any = None,
        storage: Any = None,
        knowledge_pipeline: Any = None,
    ):
        """
        Initialise the intelligence engine.

        Args:
            evolution_memory: An EvolutionMemory instance for fetching
                proposals and execution records. Optional.
            experience_repository: An ExperienceRepository instance for
                fetching tracked goals and experiences. Optional.
            insight_scorer: An InsightScorer instance for scoring.
                Optional — if None, scoring produces default values.
            storage: An EvolutionStorage instance for persisting insights.
                Optional — currently unused, reserved for Phase 12.3+.
            knowledge_pipeline: Optional EvolutionKnowledgePipeline for
                automatic consolidation of generated insights.
                Skipped if None.
        """
        self._evolution_memory = evolution_memory
        self._experience_repository = experience_repository
        self._insight_scorer = insight_scorer
        self._storage = storage
        self._knowledge_pipeline = knowledge_pipeline

        # In-memory insight storage
        self._insights: dict[str, EvolutionInsight] = {}
        # Track which execution records have been analyzed
        self._analyzed_record_ids: set[str] = set()
        self._insight_counter = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def evolution_memory(self):
        """Return the injected EvolutionMemory, or None."""
        return self._evolution_memory

    @property
    def experience_repository(self):
        """Return the injected ExperienceRepository, or None."""
        return self._experience_repository

    @property
    def insight_scorer(self):
        """Return the injected InsightScorer, or None."""
        return self._insight_scorer

    @property
    def storage(self):
        """Return the injected EvolutionStorage, or None."""
        return self._storage

    # ------------------------------------------------------------------
    # Single proposal analysis
    # ------------------------------------------------------------------

    def analyze_proposal(
        self,
        proposal_id: str,
    ) -> EvolutionInsight | None:
        """
        Analyze a single executed proposal and produce an EvolutionInsight.

        Workflow:
          1. Fetch the EvolutionProposal from EvolutionMemory.
          2. Find its execution EvolutionRecord.
          3. Match a TrackedGoal from ExperienceRepository.
          4. Collect experiences after the execution timestamp.
          5. Delegate to InsightScorer for scoring.
          6. Create, store, and return the EvolutionInsight.

        Post-Core F7: a failed governed execution (success=False on its
        execution record) is classified deterministically as a "failure"
        from the record's own outcome metadata, so it is represented in
        the learning record and can never be mis-scored as a success.

        Args:
            proposal_id: The ID of the executed proposal to analyze.

        Returns:
            An EvolutionInsight, or None if the proposal cannot be found
            or is not yet executed.
        """
        if self._evolution_memory is None:
            return None

        # 1. Fetch proposal
        proposal = self._evolution_memory.get_proposal(proposal_id)
        if proposal is None:
            return None

        # 2. Find execution record
        execution_record = self._find_execution_record(proposal_id)
        if execution_record is None:
            return None

        # Skip if already analyzed
        if execution_record.record_id in self._analyzed_record_ids:
            existing = self._get_insight_by_execution_record(
                execution_record.record_id,
            )
            if existing is not None:
                return existing

        # 3. Match tracked goal
        tracked_goal = self._find_tracked_goal(proposal_id)

        # 4. Collect experiences after execution
        experiences = self._collect_experiences(execution_record)

        # 5. Classify outcome.
        # Post-Core F7: a failed governed execution is classified
        # deterministically as a failure from the execution record's own
        # outcome metadata — never by the experience-based heuristic and
        # never as a success. A failed action can therefore never become a
        # successful learning record.
        if not execution_record.metadata.get("success", True):
            outcome = "failure"
            effectiveness = 0.0
            confidence = 1.0
            evidence_quality = 0.0
            regression_risk = 1.0
            evidence_summary = "Execution failed: {}".format(
                execution_record.metadata.get("error", "unknown execution error")
            )
        else:
            scorer = self._insight_scorer
            if scorer is not None:
                effectiveness = scorer.score_effectiveness(
                    proposal, tracked_goal, experiences,
                )
                confidence = scorer.score_confidence(experiences)
                evidence_quality = scorer.score_evidence_quality(
                    proposal, experiences,
                )
                regression_risk = scorer.score_regression_risk(experiences)
                outcome = scorer.classify_outcome(effectiveness, confidence)

                # Build evidence summary
                evidence_summary = self._build_evidence_summary(
                    tracked_goal, experiences, outcome,
                )
            else:
                # Default values when no scorer is available
                effectiveness = 0.0
                confidence = 0.0
                evidence_quality = 0.0
                regression_risk = 0.0
                outcome = "inconclusive"
                evidence_summary = "No InsightScorer available."

        # 6. Create insight
        insight = EvolutionInsight(
            insight_id=self._next_insight_id(),
            proposal_id=proposal_id,
            execution_record_id=execution_record.record_id,
            tracked_goal_id=getattr(tracked_goal, "goal_id", ""),
            outcome=outcome,
            confidence=confidence,
            effectiveness_score=effectiveness,
            evidence_summary=evidence_summary,
            evidence_count=len(experiences),
            evidence_quality=evidence_quality,
            regression_risk=regression_risk,
            analyzed_at=datetime.now(),
            proposal_title=proposal.title,
            proposal_summary=proposal.summary,
            metadata={
                "scorer_available": self._insight_scorer is not None,
                "tracked_goal_found": tracked_goal is not None,
                "experience_count": len(experiences),
                "execution_success": execution_record.metadata.get("success", True),
            },
        )

        # Store in memory
        self._insights[insight.insight_id] = insight
        self._analyzed_record_ids.add(execution_record.record_id)

        # Persist to storage if available (best-effort)
        if self._storage is not None:
            self._persist_insight(insight)

        # Feed into knowledge pipeline for automatic consolidation
        if self._knowledge_pipeline is not None:
            try:
                self._knowledge_pipeline.record_insight(insight)
                self._knowledge_pipeline.consolidate()
            except Exception:
                pass

        return insight

    # ------------------------------------------------------------------
    # Bulk analysis
    # ------------------------------------------------------------------

    def analyze_all(self) -> list[EvolutionInsight]:
        """
        Analyze all proposals that have an execution record and do not
        already have an insight.

        Post-Core F7: the gate is keyed on the existence of an execution
        EvolutionRecord rather than on the proposal status. This includes
        failed governed executions (proposal left in its pre-execution
        status) so their failure outcome reaches the analysis path.

        Returns:
            A list of new EvolutionInsight instances.
        """
        if self._evolution_memory is None:
            return []

        # Get all proposals
        proposals = self._evolution_memory.get_all_proposals()
        new_insights: list[EvolutionInsight] = []

        for proposal in proposals:
            # Check if already analyzed
            execution_record = self._find_execution_record(proposal.proposal_id)
            if execution_record is None:
                continue
            if execution_record.record_id in self._analyzed_record_ids:
                continue

            insight = self.analyze_proposal(proposal.proposal_id)
            if insight is not None:
                new_insights.append(insight)

        return new_insights

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_insights(
        self,
        proposal_id: str | None = None,
        limit: int = 50,
    ) -> list[EvolutionInsight]:
        """
        Return available insights, optionally filtered by proposal_id.

        Priority: storage if available and memory is empty, otherwise memory.

        Args:
            proposal_id: If provided, return only insights for this
                proposal. If None, return all insights.
            limit: Maximum number of insights to return.

        Returns:
            A list of EvolutionInsight instances, newest first.
        """
        # If memory is empty but storage is available, load from storage
        if not self._insights and self._storage is not None:
            try:
                if self._storage.is_available():
                    stored = self._storage.load_insights(
                        proposal_id=proposal_id,
                        limit=limit,
                    )
                    return [self._insight_from_dict(d) for d in stored]
            except Exception:
                pass

        all_insights = list(self._insights.values())

        if proposal_id is not None:
            filtered = [
                ins for ins in all_insights
                if ins.proposal_id == proposal_id
            ]
        else:
            filtered = all_insights

        # Sort newest first
        filtered.sort(key=lambda i: i.analyzed_at, reverse=True)
        return filtered[:limit]

    def get_feedback_for_planner(self) -> dict[str, Any]:
        """
        Return a summary of all analyzed insights for planner consumption.

        Returns:
            A dictionary with:
              - successful_categories: list of proposal titles that succeeded
              - failed_categories: list of proposal titles that failed
              - average_effectiveness: float
              - average_confidence: float
              - total_analyzed: int
        """
        if not self._insights:
            return {
                "successful_categories": [],
                "failed_categories": [],
                "average_effectiveness": 0.0,
                "average_confidence": 0.0,
                "total_analyzed": 0,
            }

        insights = list(self._insights.values())
        total = len(insights)

        successful = [ins for ins in insights if ins.outcome == "success"]
        failed = [ins for ins in insights if ins.outcome == "failure"]

        avg_effectiveness = (
            sum(ins.effectiveness_score for ins in insights) / total
        )
        avg_confidence = (
            sum(ins.confidence for ins in insights) / total
        )

        return {
            "successful_categories": [ins.proposal_title for ins in successful],
            "failed_categories": [ins.proposal_title for ins in failed],
            "average_effectiveness": round(avg_effectiveness, 4),
            "average_confidence": round(avg_confidence, 4),
            "total_analyzed": total,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_execution_record(
        self,
        proposal_id: str,
    ) -> EvolutionRecord | None:
        """Find the execution EvolutionRecord for a given proposal."""
        if self._evolution_memory is None:
            return None

        records = self._evolution_memory.get_records_by_type("execution")
        for record in records:
            if proposal_id in record.related_ids:
                return record
        return None

    def _find_tracked_goal(
        self,
        proposal_id: str,
    ) -> Any:
        """
        Find a TrackedGoal that matches a proposal.

        Tries to match by goal_id == proposal_id first, then by
        recommendation_id == proposal_id, then by goal_title containing
        the proposal title.
        """
        if self._experience_repository is None:
            return None

        goals = self._experience_repository.get_tracked_goals()

        # Try exact goal_id match
        for goal in goals:
            if goal.goal_id == proposal_id:
                return goal

        # Try recommendation_id match
        for goal in goals:
            if getattr(goal, "recommendation_id", "") == proposal_id:
                return goal

        # Try title-based match
        proposal = (
            self._evolution_memory.get_proposal(proposal_id)
            if self._evolution_memory is not None
            else None
        )
        if proposal is not None:
            title_lower = proposal.title.lower()
            title_keywords = {w for w in title_lower.split() if len(w) > 4}
            if title_keywords:
                for goal in goals:
                    goal_title_lower = goal.goal_title.lower()
                    if any(kw in goal_title_lower for kw in title_keywords):
                        return goal

        return None

    def _collect_experiences(
        self,
        execution_record: EvolutionRecord,
    ) -> list:
        """Collect experiences after the execution timestamp."""
        if self._experience_repository is None:
            return []

        return self._experience_repository.get_experiences_since(
            execution_record.timestamp,
        )

    def _build_evidence_summary(
        self,
        tracked_goal: Any,
        experiences: list,
        outcome: str,
    ) -> str:
        """Build a human-readable evidence summary."""
        parts = []

        if tracked_goal is not None:
            goal_outcome = getattr(tracked_goal, "outcome", None)
            goal_reason = getattr(tracked_goal, "outcome_reason", "")
            if goal_outcome is not None:
                parts.append(
                    f"OutcomeTracker: {goal_outcome}."
                )
            if goal_reason:
                parts.append(goal_reason)

        exp_count = len(experiences)
        if exp_count > 0:
            parts.append(
                f"Analyzed {exp_count} experiences after execution."
            )

        if outcome in ("success", "partial", "failure"):
            parts.append(f"Classification: {outcome}.")

        return " ".join(parts) if parts else "No evidence available."

    def _get_insight_by_execution_record(
        self,
        execution_record_id: str,
    ) -> EvolutionInsight | None:
        """Find an existing insight for a given execution record."""
        for insight in self._insights.values():
            if insight.execution_record_id == execution_record_id:
                return insight
        return None

    def _next_insight_id(self) -> str:
        """Generate a unique insight identifier."""
        self._insight_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"INS-{timestamp}-{self._insight_counter:04d}"

    def _persist_insight(
        self,
        insight: EvolutionInsight,
    ) -> None:
        """Persist an insight dict to storage, best-effort."""
        if self._storage is None:
            return
        if not self._storage.is_available():
            return
        try:
            self._storage.store_insight(self._insight_to_dict(insight))
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Failed to persist insight %s", insight.insight_id,
            )

    @staticmethod
    def _insight_to_dict(insight: EvolutionInsight) -> dict[str, Any]:
        """Serialize an EvolutionInsight to a JSON-safe dictionary."""
        return {
            "insight_id": insight.insight_id,
            "proposal_id": insight.proposal_id,
            "execution_record_id": insight.execution_record_id,
            "tracked_goal_id": insight.tracked_goal_id,
            "outcome": insight.outcome,
            "confidence": insight.confidence,
            "effectiveness_score": insight.effectiveness_score,
            "evidence_summary": insight.evidence_summary,
            "evidence_count": insight.evidence_count,
            "evidence_quality": insight.evidence_quality,
            "regression_risk": insight.regression_risk,
            "analyzed_at": insight.analyzed_at.isoformat()
            if hasattr(insight.analyzed_at, "isoformat")
            else str(insight.analyzed_at),
            "proposal_title": insight.proposal_title,
            "proposal_summary": insight.proposal_summary,
            "metadata": dict(insight.metadata),
        }

    @staticmethod
    def _insight_from_dict(data: dict[str, Any]) -> EvolutionInsight:
        """Reconstruct an EvolutionInsight from a dictionary."""
        analyzed_at = data.get("analyzed_at", "")
        if isinstance(analyzed_at, str):
            try:
                analyzed_at = datetime.fromisoformat(analyzed_at)
            except (ValueError, TypeError):
                analyzed_at = datetime.now()

        return EvolutionInsight(
            insight_id=data.get("insight_id", ""),
            proposal_id=data.get("proposal_id", ""),
            execution_record_id=data.get("execution_record_id", ""),
            tracked_goal_id=data.get("tracked_goal_id", ""),
            outcome=data.get("outcome", "inconclusive"),
            confidence=data.get("confidence", 0.0),
            effectiveness_score=data.get("effectiveness_score", 0.0),
            evidence_summary=data.get("evidence_summary", ""),
            evidence_count=data.get("evidence_count", 0),
            evidence_quality=data.get("evidence_quality", 0.0),
            regression_risk=data.get("regression_risk", 0.0),
            analyzed_at=analyzed_at,
            proposal_title=data.get("proposal_title", ""),
            proposal_summary=data.get("proposal_summary", ""),
            metadata=data.get("metadata", {}),
        )
