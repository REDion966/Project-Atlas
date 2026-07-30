"""
Atlas InsightScorer — Phase 12.1

Deterministic scoring system for evaluating whether past evolution
proposals produced measurable improvement.

Pure calculation. No AI, no LLM, no storage access, no infrastructure.
All inputs are passed in as arguments. All outputs are floats [0.0, 1.0]
or outcome strings.

Scoring does NOT modify any objects — it only reads and returns.
"""

from typing import Any

from atlas.evolution.models import EvolutionProposal
from atlas.experience.models import GoalOutcome, StructuredExperience


# ---------------------------------------------------------------------------
# Heuristic thresholds (tunable, not configurable at runtime)
# ---------------------------------------------------------------------------

_MIN_EXPERIENCES_FOR_EFFECTIVENESS = 5
_HIGH_CONFIDENCE_THRESHOLD = 50
_LOW_CONFIDENCE_THRESHOLD = 5
_SUCCESS_EFFECTIVENESS_MIN = 0.75
_SUCCESS_CONFIDENCE_MIN = 0.6
_FAILURE_EFFECTIVENESS_MAX = 0.3
_FAILURE_CONFIDENCE_MIN = 0.6


class InsightScorer:
    """
    Pure scoring logic for evolution outcome analysis.

    All methods are stateless and deterministic. Same inputs always
    produce the same outputs. No side effects.

    No constructor dependencies — instantiate freely.
    """

    # ------------------------------------------------------------------
    # Effectiveness
    # ------------------------------------------------------------------

    def score_effectiveness(
        self,
        proposal: EvolutionProposal,
        tracked_goal: Any,
        experiences: list[StructuredExperience],
    ) -> float:
        """
        Estimate whether the proposed improvement produced positive change.

        Uses tracked goal outcome as primary signal, with evidence count
        as a floor. Returns 0.0–1.0.

        Args:
            proposal: The EvolutionProposal that was executed.
            tracked_goal: The TrackedGoal created by OutcomeTracker.
            experiences: StructuredExperience records after execution.

        Returns:
            0.0–1.0 effectiveness score.
        """
        # Insufficient evidence → conservative default
        if len(experiences) < _MIN_EXPERIENCES_FOR_EFFECTIVENESS:
            return 0.3

        # Base score from tracked goal outcome
        outcome = self._get_goal_outcome(tracked_goal)
        base = self._outcome_to_effectiveness(outcome)

        # Boost or penalise based on experience success rate
        if experiences:
            success_rate = self._experience_success_rate(experiences)
            if base > 0.5:
                # Positive outcome: use the better of base and rate
                return min(1.0, max(base, success_rate))
            # Negative outcome: use the worse of base and (1 - rate)
            return max(0.0, min(base, 1.0 - success_rate))

        return base

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def score_confidence(
        self,
        experiences: list[StructuredExperience],
    ) -> float:
        """
        Estimate confidence based on quantity of evidence.

        Rules:
          - 0 experiences → 0.0
          - Few experiences → low confidence
          - Many experiences → high confidence

        Returns:
            0.0–1.0 confidence score.
        """
        count = len(experiences)

        if count == 0:
            return 0.0

        if count >= _HIGH_CONFIDENCE_THRESHOLD:
            return 1.0

        # Linear ramp from 0 to _HIGH_CONFIDENCE_THRESHOLD
        raw = count / _HIGH_CONFIDENCE_THRESHOLD

        # Apply a gentle floor for single-digit counts
        if count <= _LOW_CONFIDENCE_THRESHOLD:
            raw *= 0.5  # Penalise very small sample sizes

        return min(1.0, max(0.0, raw))

    # ------------------------------------------------------------------
    # Evidence quality
    # ------------------------------------------------------------------

    def score_evidence_quality(
        self,
        proposal: EvolutionProposal,
        experiences: list[StructuredExperience],
    ) -> float:
        """
        Estimate how relevant the available evidence is to the proposal.

        Uses simple keyword overlap between the proposal's title/summary
        and the experience text fields (user_input, reasoning_goal,
        planning_goal, concepts_extracted).

        No NLP. No external libraries. Pure string matching.

        Args:
            proposal: The EvolutionProposal that was executed.
            experiences: StructuredExperience records to evaluate.

        Returns:
            0.0–1.0 evidence quality score.
        """
        if not experiences:
            return 0.0

        # Extract keywords from proposal (words >= 5 chars, lowercased)
        proposal_keywords = self._extract_keywords(
            f"{proposal.title} {proposal.summary}",
        )
        if not proposal_keywords:
            return 0.0

        # Score each experience on keyword overlap
        total_overlap = 0.0
        for exp in experiences:
            exp_text = self._build_experience_text(exp)
            exp_keywords = self._extract_keywords(exp_text)

            if not exp_keywords:
                continue

            # Jaccard-like: count matching keywords
            matched = sum(1 for kw in proposal_keywords if kw in exp_keywords)
            union = max(len(proposal_keywords), len(exp_keywords))
            total_overlap += matched / union if union > 0 else 0.0

        return min(1.0, total_overlap / len(experiences))

    # ------------------------------------------------------------------
    # Regression risk
    # ------------------------------------------------------------------

    def score_regression_risk(
        self,
        experiences: list[StructuredExperience],
    ) -> float:
        """
        Estimate whether negative signals appeared after execution.

        Considers:
          - Experiences with FAILURE or PARTIAL outcome
          - Tool failures
          - Planning validation errors

        Returns:
            0.0–1.0 regression risk score.
        """
        if not experiences:
            return 0.0

        failure_count = 0
        tool_failure_count = 0
        planning_error_count = 0

        for exp in experiences:
            outcome_name = exp.outcome.name if hasattr(exp.outcome, "name") else str(exp.outcome)
            if outcome_name in ("FAILURE", "PARTIAL"):
                failure_count += 1
            if exp.tool_name and not exp.tool_success:
                tool_failure_count += 1
            if exp.planning_validation_errors > 0:
                planning_error_count += 1

        total = len(experiences)

        # Weight: failures carry more weight than planning errors
        failure_rate = failure_count / total if total > 0 else 0.0
        tool_failure_rate = (tool_failure_count / total) * 0.7
        planning_error_rate = (planning_error_count / total) * 0.3

        raw_risk = failure_rate + tool_failure_rate + planning_error_rate

        return min(1.0, max(0.0, raw_risk))

    # ------------------------------------------------------------------
    # Outcome classification
    # ------------------------------------------------------------------

    def classify_outcome(
        self,
        effectiveness: float,
        confidence: float,
    ) -> str:
        """
        Classify the overall outcome based on effectiveness and confidence.

        Args:
            effectiveness: score from score_effectiveness() (0.0–1.0).
            confidence: score from score_confidence() (0.0–1.0).

        Returns:
            One of: "success", "failure", "partial", "inconclusive".
        """
        if effectiveness >= _SUCCESS_EFFECTIVENESS_MIN and confidence >= _SUCCESS_CONFIDENCE_MIN:
            return "success"

        if effectiveness <= _FAILURE_EFFECTIVENESS_MAX and confidence >= _FAILURE_CONFIDENCE_MIN:
            return "failure"

        # Moderate evidence → partial
        if confidence >= _LOW_CONFIDENCE_THRESHOLD / _HIGH_CONFIDENCE_THRESHOLD:
            return "partial"

        return "inconclusive"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_goal_outcome(tracked_goal: Any) -> GoalOutcome:
        """Extract GoalOutcome from a TrackedGoal-like object."""
        if tracked_goal is None:
            return GoalOutcome.PENDING
        outcome = getattr(tracked_goal, "outcome", GoalOutcome.PENDING)
        if isinstance(outcome, GoalOutcome):
            return outcome
        return GoalOutcome.PENDING

    @staticmethod
    def _outcome_to_effectiveness(outcome: GoalOutcome) -> float:
        """Map a GoalOutcome to a base effectiveness score."""
        mapping = {
            GoalOutcome.IMPLEMENTED: 0.7,
            GoalOutcome.ACCEPTED: 0.6,
            GoalOutcome.PENDING: 0.5,
            GoalOutcome.REJECTED: 0.25,
            GoalOutcome.OBSOLETE: 0.3,
        }
        return mapping.get(outcome, 0.5)

    @staticmethod
    def _experience_success_rate(experiences: list[StructuredExperience]) -> float:
        """Calculate the proportion of experiences with SUCCESS outcome."""
        if not experiences:
            return 0.0
        successes = sum(
            1 for e in experiences
            if hasattr(e.outcome, "name") and e.outcome.name == "SUCCESS"
        )
        return successes / len(experiences)

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """Extract significant keywords from a text string.

        Filters to words >= 5 characters, lowercased, alphanumeric only.
        """
        words = text.lower().split()
        return {
            "".join(ch for ch in w if ch.isalnum())
            for w in words
            if len(w) >= 5
        }

    @staticmethod
    def _build_experience_text(exp: StructuredExperience) -> str:
        """Combine all searchable text fields from an experience."""
        concepts = " ".join(getattr(exp, "concepts_extracted", []))
        return (
            f"{getattr(exp, 'user_input', '')} "
            f"{getattr(exp, 'reasoning_goal', '')} "
            f"{getattr(exp, 'planning_goal', '')} "
            f"{concepts}"
        )
