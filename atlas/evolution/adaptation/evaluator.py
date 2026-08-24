"""Atlas Post-Core F5 — Adaptation Evaluator.

The deterministic observer/evaluator that closes the governed adaptation loop.

Responsibilities:
  1. Evaluate a proposal's lifecycle state (DRAFT/PENDING -> NOT_EXECUTED,
     REJECTED -> GOVERNANCE_REJECTED, DEFERRED -> DEFERRED, SUPERSEDED ->
     SUPERSEDED, APPROVED+no outcome -> APPROVED_NOT_EXECUTED).
  2. Evaluate an executed Phase E ``DevelopmentOutcome`` (reusing
     ``effectiveness_proxy``, verification, and rollback state).
  3. Convert evaluations into bounded ``AdaptationFeedback`` carrying F2/F3
     bridge signals (freshness/lifecycle) for future reassessment.
  4. (Optional) record into the EXISTING ``EvolutionMemory`` /
     ``LearningMemory`` via duck-typed ``store_record`` /
     ``store_recommendation``.

The evaluator NEVER:
  * approves / rejects / defers a proposal
  * invokes SelfDevelopmentLoop / DevelopmentPlanner / sandbox / subprocess
  * invokes ApprovalManager / AuthorizationManager / gateway
  * mutates registries or CODE authorization
  * creates a daemon / scheduler / memory

Determinism + idempotency contract: identical (proposal, outcome, now) inputs
always produce the identical evaluation/feedback, and repeated calls do not
create duplicate feedback records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from atlas.evolution.adaptation.evaluation import (
    AdaptationEvaluation,
    AdaptationEvaluationState,
    AdaptationFeedback,
    AdaptationFeedbackSignal,
    utc_now,
)
from atlas.evolution.models import EvolutionProposal, ProposalStatus

#: Terminal statuses that indicate a FAILED executed outcome (Phase E).
_EXECUTED_FAILED_STATUSES = (
    "FAILED",
    "ITERATIONS_EXHAUSTED",
    "UNAVAILABLE_CAPABILITY",
    "INVALID_OBJECTIVE",
)

#: Bound on the number of proposals/outcomes processed per call.
DEFAULT_MAX_ITEMS: int = 10


class AdaptationEvaluator:
    """Evaluate adaptation proposals + outcomes; produce bounded feedback.

    Args:
        max_items: Injectable processing cap (default 10).
        now: Optional clock callable (UTC); injectable for tests.
    """

    def __init__(
        self,
        max_items: int = DEFAULT_MAX_ITEMS,
        now: Any | None = None,
    ) -> None:
        if max_items < 1:
            raise ValueError("max_items must be >= 1")
        self._max_items = max_items
        self._now = now or utc_now

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_proposal(
        self,
        proposal: EvolutionProposal,
        now: datetime | None = None,
    ) -> AdaptationEvaluation:
        """Evaluate a proposal's lifecycle state (no execution outcome)."""
        when = now or self._now()
        status = proposal.status
        target_key = self._target_key(proposal)
        base = dict(
            proposal_id=proposal.proposal_id,
            target_key=target_key,
            evidence_change_ids=self._evidence_changes(proposal),
            evidence_knowledge_ids=self._evidence_knowledge(proposal),
            evaluated_at=when,
        )

        if status in (ProposalStatus.DRAFT, ProposalStatus.PENDING_APPROVAL):
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:not-executed",
                state=AdaptationEvaluationState.NOT_EXECUTED,
                effectiveness=None,
                approval_occurred=False,
                execution_occurred=False,
                reason="not-executed",
                **base,
            )

        if status == ProposalStatus.APPROVED:
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:approved-not-executed",
                state=AdaptationEvaluationState.APPROVED_NOT_EXECUTED,
                approval_occurred=True,
                execution_occurred=False,
                reason="approved-not-executed",
                **base,
            )

        if status == ProposalStatus.REJECTED:
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:rejected",
                state=AdaptationEvaluationState.GOVERNANCE_REJECTED,
                approval_occurred=False,
                execution_occurred=False,
                reason="governance-rejected",
                **base,
            )

        if status == ProposalStatus.DEFERRED:
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:deferred",
                state=AdaptationEvaluationState.DEFERRED,
                approval_occurred=False,
                execution_occurred=False,
                reason="deferred",
                **base,
            )

        if status == ProposalStatus.SUPERSEDED:
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:superseded",
                state=AdaptationEvaluationState.SUPERSEDED,
                approval_occurred=False,
                execution_occurred=False,
                reason="superseded",
                **base,
            )

        # IMPLEMENTED or unknown -> approved-not-executed (no outcome).
        return AdaptationEvaluation(
            evaluation_id=f"ADE-{proposal.proposal_id}:approved-not-executed",
            state=AdaptationEvaluationState.APPROVED_NOT_EXECUTED,
            approval_occurred=status == ProposalStatus.IMPLEMENTED,
            execution_occurred=False,
            reason="approved-not-executed",
            **base,
        )

    def evaluate_outcome(
        self,
        proposal: EvolutionProposal,
        outcome: Any,
        now: datetime | None = None,
    ) -> AdaptationEvaluation:
        """Evaluate an executed Phase E DevelopmentOutcome (or run result).

        Reuses ``effectiveness_proxy`` when available. Never interprets
        governance states as technical outcomes.
        """
        when = now or self._now()
        if outcome is None:
            return self.evaluate_proposal(proposal, now=when)

        target_key = self._target_key(proposal)
        outcome_id = str(getattr(outcome, "outcome_id", "") or "")
        if not outcome_id:
            outcome_id = str(getattr(outcome, "plan_id", "") or "") or "outcome"

        status = getattr(outcome, "outcome", None)
        status_name = status.name if hasattr(status, "name") else str(status or "")

        verification_passed = bool(getattr(outcome, "verification_passed", False))
        rollback_occurred = bool(getattr(outcome, "rollback_occurred", False))
        raw_proxy = getattr(outcome, "effectiveness_proxy", None)

        changes = self._evidence_changes(proposal)
        knowledge = self._evidence_knowledge(proposal)
        base_outcome = dict(
            proposal_id=proposal.proposal_id,
            target_key=target_key,
            outcome_id=outcome_id,
            approval_occurred=True,
            execution_occurred=True,
            evidence_change_ids=changes,
            evidence_knowledge_ids=knowledge,
            evaluated_at=when,
        )

        # Technical failure.
        if status_name in _EXECUTED_FAILED_STATUSES:
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:{outcome_id}",
                state=AdaptationEvaluationState.FAILED,
                effectiveness=0.0,
                confidence=0.8,
                reason="failed",
                verification_passed=False,
                rollback_occurred=rollback_occurred,
                **base_outcome,
            )

        # SUCCESS with verification passed -> reuse effectiveness_proxy.
        if status_name in ("SUCCESS", "IMPLEMENTED"):
            if not verification_passed:
                return AdaptationEvaluation(
                    evaluation_id=f"ADE-{proposal.proposal_id}:{outcome_id}",
                    state=AdaptationEvaluationState.FAILED,
                    effectiveness=0.0,
                    confidence=0.8,
                    reason="verification-failed",
                    verification_passed=False,
                    rollback_occurred=rollback_occurred,
                    **base_outcome,
                )
            proxy = self._bounded_proxy(raw_proxy)
            effectiveness = proxy if proxy is not None else 1.0
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:{outcome_id}",
                state=AdaptationEvaluationState.SUCCESSFUL,
                effectiveness=effectiveness,
                confidence=0.9,
                reason="successful",
                verification_passed=True,
                rollback_occurred=False,
                **base_outcome,
            )

        # Rollback regardless of terminal status -> technical failure.
        if rollback_occurred:
            return AdaptationEvaluation(
                evaluation_id=f"ADE-{proposal.proposal_id}:{outcome_id}",
                state=AdaptationEvaluationState.FAILED,
                effectiveness=0.0,
                confidence=0.9,
                reason="rollback",
                verification_passed=False,
                rollback_occurred=True,
                **base_outcome,
            )

        # Unknown / partial outcome -> bounded partial effectiveness.
        proxy = self._bounded_proxy(raw_proxy)
        effectiveness = proxy if proxy is not None else 0.5
        uncertain_success = (
            status_name == "SUCCESS" and bool(getattr(outcome, "success", True))
        )
        return AdaptationEvaluation(
            evaluation_id=f"ADE-{proposal.proposal_id}:{outcome_id}",
            state=(
                AdaptationEvaluationState.SUCCESSFUL
                if uncertain_success
                else AdaptationEvaluationState.FAILED
            ),
            effectiveness=effectiveness,
            confidence=0.6,
            reason="uncertain",
            verification_passed=None,
            rollback_occurred=False,
            **base_outcome,
        )

    def evaluate_many(
        self,
        proposals: Iterable[EvolutionProposal],
        outcomes_by_proposal_id: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> tuple[AdaptationEvaluation, ...]:
        """Evaluate bounded, deduplicated proposals (deterministic order)."""
        outcomes = outcomes_by_proposal_id or {}
        seen: dict[str, AdaptationEvaluation] = {}
        for proposal in proposals or ():
            if not isinstance(proposal, EvolutionProposal):
                continue
            outcome = outcomes.get(proposal.proposal_id)
            evaluation = (
                self.evaluate_outcome(proposal, outcome, now=now)
                if outcome is not None
                else self.evaluate_proposal(proposal, now=now)
            )
            seen[evaluation.evaluation_id] = evaluation
        ordered = sorted(seen.values(), key=lambda e: e.evaluation_id)
        return tuple(ordered[: max(1, self._max_items)])

    # ------------------------------------------------------------------
    # Feedback generation
    # ------------------------------------------------------------------

    def feedback_for(
        self,
        evaluation: AdaptationEvaluation,
        now: datetime | None = None,
    ) -> AdaptationFeedback:
        """Produce deterministic feedback (with F2/F3 bridge signals)."""
        when = now or self._now()
        state = evaluation.state

        if state is AdaptationEvaluationState.SUCCESSFUL:
            return self._feedback(
                evaluation, AdaptationFeedbackSignal.RETAIN,
                retain=True, freshness="refresh", lifecycle="deprioritize",
                reason="successful", now=when,
            )
        if state is AdaptationEvaluationState.FAILED:
            return self._feedback(
                evaluation, AdaptationFeedbackSignal.RECONSIDER,
                reconsider=True, freshness="reassess", lifecycle="reassess",
                reason="failed", now=when,
            )
        if state is AdaptationEvaluationState.GOVERNANCE_REJECTED:
            return self._feedback(
                evaluation, AdaptationFeedbackSignal.REJECTED,
                reason="governance-rejected", now=when,
            )
        if state is AdaptationEvaluationState.DEFERRED:
            return self._feedback(
                evaluation, AdaptationFeedbackSignal.DEFERRED,
                reason="deferred", now=when,
            )
        if state is AdaptationEvaluationState.SUPERSEDED:
            return self._feedback(
                evaluation, AdaptationFeedbackSignal.SUPERSEDED,
                reason="superseded", now=when,
            )
        # NOT_EXECUTED / APPROVED_NOT_EXECUTED.
        return self._feedback(
            evaluation, AdaptationFeedbackSignal.NOT_EXECUTED,
            reason="not-executed", now=when,
        )

    def feedback_for_many(
        self,
        evaluations: Iterable[AdaptationEvaluation],
        now: datetime | None = None,
    ) -> tuple[AdaptationFeedback, ...]:
        """Produce bounded, deduplicated feedback (deterministic order)."""
        seen: dict[str, AdaptationFeedback] = {}
        for evaluation in evaluations or ():
            feedback = self.feedback_for(evaluation, now=now)
            seen[feedback.feedback_id] = feedback
        ordered = sorted(seen.values(), key=lambda f: f.feedback_id)
        return tuple(ordered[: max(1, self._max_items)])

    def record(
        self,
        evaluation: AdaptationEvaluation,
        evolution_memory: Any | None = None,
        learning_memory: Any | None = None,
    ) -> AdaptationFeedback:
        """Evaluate, then best-effort record into the existing memory stores.

        * ``evolution_memory.store_record(EvolutionRecord)`` — appends an
          evolution history record (append-only, matching existing semantics).
        * ``learning_memory.store_recommendation(ImprovementRecommendation)`` —
          appends a bounded recommendation.

        Deterministic and idempotent: calling this repeatedly produces the same
        evaluation + feedback and does not create duplicate feedback records.
        """
        feedback = self.feedback_for(evaluation)
        if evolution_memory is not None:
            store_record = getattr(evolution_memory, "store_record", None)
            if store_record is not None:
                from atlas.evolution.models import EvolutionRecord

                try:
                    store_record(EvolutionRecord(
                        record_id=f"EVL-{evaluation.evaluation_id}",
                        event_type="adaptation_evaluation",
                        description=(
                            f"{evaluation.state.name}: {evaluation.reason}"
                        ),
                        related_ids=[
                            evaluation.proposal_id, evaluation.outcome_id,
                        ],
                        timestamp=evaluation.evaluated_at,
                        metadata=evaluation.to_dict(),
                    ))
                except Exception:
                    pass
        if learning_memory is not None:
            store_rec = getattr(learning_memory, "store_recommendation", None)
            if store_rec is not None:
                from atlas.learning_engine.models import (
                    ImprovementRecommendation,
                    InsightImportance,
                )

                try:
                    store_rec(ImprovementRecommendation(
                        recommendation_id=f"ADF-{evaluation.evaluation_id}",
                        title=f"Adaptation {evaluation.state.name}",
                        description=feedback.reason,
                        source_insight_ids=list(evaluation.evidence_knowledge_ids),
                        target_area=evaluation.target_key,
                        priority=InsightImportance.MEDIUM,
                        actionable=True,
                    ))
                except Exception:
                    pass
        return feedback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _feedback(
        evaluation: AdaptationEvaluation,
        signal: AdaptationFeedbackSignal,
        now: datetime,
        reason: str,
        retain: bool = False,
        reconsider: bool = False,
        freshness: str = "none",
        lifecycle: str = "none",
    ) -> AdaptationFeedback:
        refs = list(evaluation.evidence_change_ids) + list(
            evaluation.evidence_knowledge_ids
        )
        return AdaptationFeedback(
            feedback_id=f"ADF-{evaluation.evaluation_id}",
            proposal_id=evaluation.proposal_id,
            evaluation_id=evaluation.evaluation_id,
            target_key=evaluation.target_key,
            outcome_id=evaluation.outcome_id,
            signal=signal,
            retain_adaptation=retain,
            reconsider_adaptation=reconsider,
            appears_ineffective=(
                evaluation.effectiveness is not None
                and evaluation.effectiveness < 0.5
            ),
            freshness_signal=freshness,
            lifecycle_signal=lifecycle,
            reason=reason,
            evidence_refs=tuple(dict.fromkeys(refs)),
            evaluated_at=now,
        )

    @staticmethod
    def _target_key(proposal: EvolutionProposal) -> str:
        target = (
            proposal.metadata.get("target_key", "") if proposal.metadata else ""
        )
        if target:
            return str(target)
        plan = getattr(proposal, "plan", None)
        components = getattr(plan, "target_components", []) if plan is not None else []
        if components:
            return str(components[0])
        return proposal.proposal_id

    @staticmethod
    def _evidence_changes(proposal: EvolutionProposal) -> tuple[str, ...]:
        if not proposal.metadata:
            return ()
        raw = proposal.metadata.get("evidence_change_ids", []) or []
        return tuple(dict.fromkeys(str(x) for x in raw if x))

    @staticmethod
    def _evidence_knowledge(proposal: EvolutionProposal) -> tuple[str, ...]:
        if not proposal.metadata:
            return ()
        raw = proposal.metadata.get("evidence_knowledge_ids", []) or []
        return tuple(dict.fromkeys(str(x) for x in raw if x))

    @staticmethod
    def _bounded_proxy(value: Any) -> float | None:
        """Bound an effectiveness proxy to [0.0, 1.0], or None."""
        if value is None:
            return None
        try:
            return round(min(1.0, max(0.0, float(value))), 3)
        except (TypeError, ValueError):
            return None