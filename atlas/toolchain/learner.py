"""Atlas Toolchain — Tool Learning (Phase 18.6).

Consumes execution outcomes (:class:`ToolChainResult` and the
:class:`ToolEffectivenessTracker`) and produces *deterministic* learning
recommendations for the tool-ecosystem layer.

Pure logic. No storage. No persistence. No evolution. No AI. No randomness.

The learner is the feedback surface for Track B: every executed chain
produces a :class:`ToolChainResult`, and the effectiveness tracker records
per-tool observations. The learner synthesizes that evidence into
deterministic recommendations and — when a chain is stable and effective —
emits a *learned* skill candidate (:class:`~atlas.toolchain.models.SkillKind.LEARNED`).

Determinism contract: identical inputs (results + tracker state) always
produce identical recommendations. No random sampling, no time-based
thresholds, no external signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.toolchain.catalog import (
    DEFAULT_EFFECTIVENESS,
    EFFECTIVENESS_MIN_OBSERVATIONS,
)
from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.models import (
    Skill,
    SkillKind,
    ToolChainResult,
    ToolStep,
)


# ---------------------------------------------------------------------------
# Learning recommendation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolLearningRecommendation:
    """A deterministic learning recommendation produced by the learner.

    Attributes:
        recommendation_id: Stable unique identifier.
        chain_id: The chain the recommendation refers to.
        action: What to do (e.g. "record", "promote", "learn_skill").
        reason: Human-readable explanation of *why*.
        skill: Optional learned :class:`Skill` candidate when the action is
            ``learn_skill``.
        confidence: Deterministic confidence score (0.0–1.0) derived purely
            from observed evidence (never random).
        metadata: Additional context.
    """

    recommendation_id: str
    chain_id: str
    action: str
    reason: str
    skill: Skill | None = None
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested skill becomes a dict)."""
        return {
            "recommendation_id": self.recommendation_id,
            "chain_id": self.chain_id,
            "action": self.action,
            "reason": self.reason,
            "skill": self.skill.to_dict() if self.skill is not None else None,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Deterministic action names
# ---------------------------------------------------------------------------

#: Action emitted when a chain succeeded and its tool set is stable.
ACT_RECORD: str = "record"

#: Action emitted when a chain's tools are all effective (above threshold).
ACT_PROMOTE: str = "promote"

#: Action emitted when the learner generates a learned skill candidate.
ACT_LEARN_SKILL: str = "learn_skill"

#: Action emitted when a chain failed; the learner notes the failure for
#: future evidence without promoting anything.
ACT_LEARN_FAILURE: str = "learn_failure"


# ---------------------------------------------------------------------------
# Deterministic constants
# ---------------------------------------------------------------------------

#: Minimum confidence for a learned skill candidate to be generated.
LEARN_MIN_CONFIDENCE: float = 0.6

#: Minimum number of successful executions required before a chain is
#: considered stable enough to learn a skill from.
LEARN_MIN_SUCCESS_OBSERVATIONS: int = 1

#: Threshold (0.0–1.0) on average tool effectiveness for promotion.
PROMOTE_EFFECTIVENESS_THRESHOLD: float = 0.6


# ---------------------------------------------------------------------------
# Learner
# ---------------------------------------------------------------------------


class ToolLearner:
    """Deterministic tool learning synthesizer.

    The learner consumes a :class:`ToolChainResult` plus a
    :class:`ToolEffectivenessTracker` (both injected) and produces a list of
    :class:`ToolLearningRecommendation`. It never persists anything, never
    calls AI, never accesses storage, and never uses randomness — identical
    inputs always yield identical recommendations.

    The learner is stateless between calls: it holds no internal history of
    its own. All evidence is read from the injected tracker at call time.
    """

    def __init__(self, tracker: ToolEffectivenessTracker | None = None) -> None:
        """Initialise the learner with an optional effectiveness tracker.

        Args:
            tracker: A :class:`ToolEffectivenessTracker`-shaped object used
                to read effectiveness evidence. If ``None``, a fresh empty
                tracker is created internally (the learner owns it in that
                case). An injected tracker lets callers share evidence
                across learners.
        """
        self._tracker: ToolEffectivenessTracker = tracker or ToolEffectivenessTracker()

    @property
    def tracker(self) -> ToolEffectivenessTracker:
        """The effectiveness tracker the learner reads evidence from."""
        return self._tracker

    # ------------------------------------------------------------------
    # Public learning
    # ------------------------------------------------------------------

    def learn(
        self,
        result: ToolChainResult | None,
    ) -> list[ToolLearningRecommendation]:
        """Produce deterministic learning recommendations from a result.

        Args:
            result: The :class:`ToolChainResult` produced by executing a
                chain. May be ``None`` (malformed input) — in that case the
                learner returns an empty list (fail-closed).

        Returns:
            A list of :class:`ToolLearningRecommendation`, deterministic
            for identical inputs. Ordered: record/promote/learn_skill for a
            successful chain; learn_failure for a failed chain.
        """
        if result is None:
            return []

        chain_id: str = result.chain_id or "unknown"
        success: bool = bool(result.success)
        step_results: tuple[dict[str, Any], ...] = result.step_results or ()

        if not success:
            return self._failure_recommendations(chain_id, result)

        return self._success_recommendations(chain_id, result, step_results)

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------

    def _success_recommendations(
        self,
        chain_id: str,
        result: ToolChainResult,
        step_results: tuple[dict[str, Any], ...],
    ) -> list[ToolLearningRecommendation]:
        """Build recommendations for a successful chain execution.

        Deterministic:
          1. Always emit a ``record`` action (evidence accumulation).
          2. Compute the average effectiveness of the chain's tools.
          3. If the effectiveness exceeds the promotion threshold, emit a
             ``promote`` action.
          4. If the chain is stable (all steps succeeded) and the average
             effectiveness is at least :data:`LEARN_MIN_CONFIDENCE`, emit a
             ``learn_skill`` action carrying a LEARNED skill candidate.
        """
        recommendations: list[ToolLearningRecommendation] = []

        recommendations.append(
            self._recommendation(
                chain_id=chain_id,
                action=ACT_RECORD,
                reason="Chain executed successfully; record as evidence.",
                confidence=1.0,
                metadata={"success": True},
            )
        )

        # Collect the chain's tools from step results.
        tool_names: list[str] = []
        for step in step_results:
            name = str(step.get("tool_name", ""))
            if name:
                tool_names.append(name)

        avg_effectiveness: float = self._average_effectiveness(tool_names)

        if avg_effectiveness >= PROMOTE_EFFECTIVENESS_THRESHOLD:
            recommendations.append(
                self._recommendation(
                    chain_id=chain_id,
                    action=ACT_PROMOTE,
                    reason=(
                        f"Chain tools average effectiveness "
                        f"{avg_effectiveness:.2f} meets promotion threshold."
                    ),
                    confidence=avg_effectiveness,
                    metadata={"avg_effectiveness": avg_effectiveness},
                )
            )

        if self._can_learn(tool_names, avg_effectiveness):
            skill: Skill = self._build_learned_skill(chain_id, tool_names)
            recommendations.append(
                self._recommendation(
                    chain_id=chain_id,
                    action=ACT_LEARN_SKILL,
                    reason=(
                        "Chain is stable and tools are effective; "
                        "emit a learned skill candidate."
                    ),
                    skill=skill,
                    confidence=avg_effectiveness,
                    metadata={"avg_effectiveness": avg_effectiveness},
                )
            )

        return recommendations

    # ------------------------------------------------------------------
    # Failure path
    # ------------------------------------------------------------------

    def _failure_recommendations(
        self,
        chain_id: str,
        result: ToolChainResult,
    ) -> list[ToolLearningRecommendation]:
        """Build a single fail-closed ``learn_failure`` recommendation."""
        error: str = result.error or "unknown error"
        return [
            self._recommendation(
                chain_id=chain_id,
                action=ACT_LEARN_FAILURE,
                reason=f"Chain failed; recording failure evidence: {error}.",
                confidence=0.0,
                metadata={"error": error},
            )
        ]

    # ------------------------------------------------------------------
    # Deterministic helpers
    # ------------------------------------------------------------------

    def _average_effectiveness(self, tool_names: list[str]) -> float:
        """Compute the average effectiveness score of the given tools.

        Tools with no observations contribute :data:`DEFAULT_EFFECTIVENESS`.
        Deterministic: the average of a fixed set of scores is stable.
        """
        if not tool_names:
            return DEFAULT_EFFECTIVENESS

        total: float = 0.0
        for name in tool_names:
            score = self._tracker.score(name)
            total += score.effectiveness
        return total / len(tool_names)

    def _can_learn(self, tool_names: list[str], avg_effectiveness: float) -> bool:
        """Decide whether to emit a learned skill candidate.

        Deterministic criteria:
          - At least one tool in the chain.
          - Average effectiveness >= :data:`LEARN_MIN_CONFIDENCE`.
          - Every tool has at least one observation (evidence exists).
          - The chain has enough successful evidence
            (:data:`LEARN_MIN_SUCCESS_OBSERVATIONS` of tools observed).
        """
        if not tool_names:
            return False
        if avg_effectiveness < LEARN_MIN_CONFIDENCE:
            return False

        # Deterministic evidence check: every tool must have been observed
        # at least LEARN_MIN_SUCCESS_OBSERVATIONS times.
        for name in tool_names:
            records = self._tracker.observations(name)
            if len(records) < LEARN_MIN_SUCCESS_OBSERVATIONS:
                return False
        return True

    def _build_learned_skill(self, chain_id: str, tool_names: list[str]) -> Skill:
        """Build a LEARNED skill candidate from a stable chain.

        The skill wraps a :class:`~atlas.toolchain.models.ToolChain` whose
        steps are reconstructed from the observed effectiveness evidence.
        The step descriptions and parameters are left minimal (the learner
        does not guess parameters — it only records the tool ordering).
        """
        steps: tuple[ToolStep, ...] = tuple(
            ToolStep(
                step_id=f"step:{index:04d}",
                tool_name=name,
                description="Learned step.",
            )
            for index, name in enumerate(tool_names)
        )

        from atlas.toolchain.models import ToolChain

        chain = ToolChain(
            chain_id=f"chain::{self._slug(chain_id)}",
            goal=f"Learned goal for chain '{chain_id}'.",
            steps=steps,
            strategy="sequential",
        )

        return Skill(
            skill_id=f"skill::learned::{self._slug(chain_id)}",
            name=f"Learned {self._slug(chain_id)}",
            description="Learned skill from effective chain execution.",
            kind=SkillKind.LEARNED,
            category="toolchain",
            chain=chain,
            metadata={
                "source_chain_id": chain_id,
                "learned": True,
            },
        )

    # ------------------------------------------------------------------
    # Recommendation / id helpers
    # ------------------------------------------------------------------

    def _recommendation(
        self,
        *,
        chain_id: str,
        action: str,
        reason: str,
        confidence: float,
        skill: Skill | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolLearningRecommendation:
        """Build a single recommendation with a deterministic id."""
        return ToolLearningRecommendation(
            recommendation_id=f"rec::{action}::{self._slug(chain_id)}",
            chain_id=chain_id,
            action=action,
            reason=reason,
            skill=skill,
            confidence=confidence,
            metadata=metadata or {},
        )

    @staticmethod
    def _slug(value: str) -> str:
        """Deterministic slug of a value for ids.

        Lowercases, keeps alphanumerics and dashes, collapses runs of
        non-alphanumerics into a single dash, and trims edge dashes.
        Falls back to ``unknown`` for empty input.
        """
        if not value:
            return "unknown"
        cleaned: str = "".join(
            ch.lower() if ch.isalnum() or ch == "-" else "-" for ch in value
        )
        parts: list[str] = [p for p in cleaned.split("-") if p]
        slug: str = "-".join(parts)
        return slug or "unknown"