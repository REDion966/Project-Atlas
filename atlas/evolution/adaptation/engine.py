"""Atlas Post-Core F4 — Adaptation Decision Engine.

The small governed decision/translation layer between F3 lifecycle
assessments and the EXISTING ``EvolutionProposal`` boundary.

Pipeline:

    F3 LifecycleAssessment
        -> AdaptationDecisionEngine.decide()
        -> AdaptationProposalCandidate      [proposal candidate ONLY]
        -> build_proposals() -> EvolutionProposal (status=DRAFT)

The engine NEVER:
  * approves a proposal (never sets APPROVED)
  * invokes ApprovalManager / AuthorizationManager
  * invokes DevelopmentPlanner / SelfDevelopmentLoop
  * executes code, sandbox, subprocesses, or research
  * mutates registries or memory
  * invents replacements/fallbacks

Determinism contract: identical assessments + identical policy produce an
identical, ordered list of candidates and DRAFT proposals.
"""

from __future__ import annotations

from typing import Iterable

from atlas.evolution.adaptation.models import (
    AdaptationProposalCandidate,
    AdaptationRisk,
)
from atlas.evolution.adaptation.policy import AdaptationDecisionPolicy
from atlas.evolution.lifecycle.models import (
    LifecycleAction,
    LifecycleAssessment,
    LifecycleReason,
    LifecycleTargetKind,
)
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)


class AdaptationDecisionEngine:
    """Translate F3 assessments into bounded, DRAFT proposal candidates."""

    def __init__(
        self,
        policy: AdaptationDecisionPolicy | None = None,
    ) -> None:
        self._policy = policy or AdaptationDecisionPolicy()

    @property
    def policy(self) -> AdaptationDecisionPolicy:
        """The applied decision policy (read-only)."""
        return self._policy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(
        self,
        assessments: Iterable[LifecycleAssessment],
        max_candidates: int | None = None,
    ) -> tuple[AdaptationProposalCandidate, ...]:
        """Convert actionable F3 assessments into proposal candidates.

        Conservative and deterministic:
          * NONE -> never a candidate.
          * REVIEW -> only when its priority clears the review threshold and
            the assessment is not solely uncertain (unless policy allows).
          * DEPRECATE -> only when explicit deprecation evidence present and
            priority clears the threshold.
          * REPLACE / FALLBACK -> only when a known replacement/fallback is
            already evidenced (REPLACEMENT_AVAILABLE) and priority clears the
            threshold.
          * Malformed / unreferenced targets are skipped (fail closed).

        Args:
            assessments: F3 lifecycle assessments.
            max_candidates: Optional per-call cap; defaults to policy cap.

        Returns:
            A deduplicated, deterministically-ordered tuple of candidates.
        """
        budget = max_candidates or self._policy.max_candidates
        seen: dict[str, AdaptationProposalCandidate] = {}

        for assessment in assessments or ():
            if not isinstance(assessment, LifecycleAssessment):
                continue  # fail closed on malformed input
            if assessment.action is LifecycleAction.NONE:
                continue
            candidate = self._candidate_for(assessment)
            if candidate is None:
                continue
            seen[candidate.candidate_id] = candidate

        ordered = sorted(
            seen.values(),
            key=lambda c: (-c.priority, c.candidate_id),
        )
        return tuple(ordered[:max(1, budget)])

    def build_proposals(
        self,
        candidates: Iterable[AdaptationProposalCandidate],
    ) -> tuple[EvolutionProposal, ...]:
        """Construct DRAFT EvolutionProposals for candidates.

        Uses the EXISTING proposal model (never APPROVED) and the EXISTING
        ImprovementPlan model. No approval, no persistence, no execution.
        """
        proposals: list[EvolutionProposal] = []
        for candidate in candidates or ():
            if not isinstance(candidate, AdaptationProposalCandidate):
                continue
            proposals.append(self._build_proposal(candidate))
        return tuple(proposals)

    def _candidate_for(
        self, assessment: LifecycleAssessment
    ) -> AdaptationProposalCandidate | None:
        action = assessment.action
        priority = assessment.priority
        reasons = set(assessment.reasons)
        policy = self._policy

        if action is LifecycleAction.REVIEW:
            # A REVIEW caused purely by uncertainty is deferred unless the
            # policy explicitly enables it.
            if (
                not policy.uncertain_actionable
                and reasons <= {LifecycleReason.UNCERTAIN_KNOWLEDGE}
            ):
                return None
            if priority < policy.review_priority_threshold:
                return None
            return self._build_candidate(
                assessment, action, LifecycleReason.ENVIRONMENT_CHANGE
            )

        if action is LifecycleAction.DEPRECATE:
            if (
                LifecycleReason.EXPLICIT_DEPRECATION not in reasons
                and LifecycleReason.UNAVAILABLE not in reasons
            ):
                return None  # defer: no explicit deprecation evidence
            if priority < policy.deprecate_priority_threshold:
                return None
            reason = (
                LifecycleReason.EXPLICIT_DEPRECATION
                if LifecycleReason.EXPLICIT_DEPRECATION in reasons
                else LifecycleReason.UNAVAILABLE
            )
            return self._build_candidate(assessment, action, reason)

        if action is LifecycleAction.REPLACE or action is LifecycleAction.FALLBACK:
            if (
                policy.require_explicit_replacement
                and LifecycleReason.REPLACEMENT_AVAILABLE not in reasons
            ):
                return None
            threshold = (
                policy.replace_priority_threshold
                if action is LifecycleAction.REPLACE
                else policy.fallback_priority_threshold
            )
            if priority < threshold:
                return None
            return self._build_candidate(
                assessment, action, LifecycleReason.REPLACEMENT_AVAILABLE
            )

        return None  # NONE / unknown actions produce nothing

    def _build_candidate(
        self,
        assessment: LifecycleAssessment,
        action: LifecycleAction,
        reason: LifecycleReason,
    ) -> AdaptationProposalCandidate:
        target_key = assessment.target_key
        risk = _classify_risk(action, assessment.target_kind)
        return AdaptationProposalCandidate(
            target_kind=assessment.target_kind,
            target_identifier=assessment.target_identifier,
            action=action,
            reason=reason,
            priority=assessment.priority,
            risk=risk,
            reasons=tuple(assessment.reasons),
            evidence_change_ids=tuple(assessment.evidence_change_ids),
            evidence_knowledge_ids=tuple(assessment.evidence_knowledge_ids),
            metadata={
                "assessment_rationale": assessment.rationale,
                "assessed_at": (
                    assessment.assessed_at.isoformat()
                    if hasattr(assessment.assessed_at, "isoformat")
                    else str(assessment.assessed_at)
                ),
            },
        )

    def generate(
        self,
        assessments: Iterable[LifecycleAssessment],
        max_candidates: int | None = None,
    ) -> tuple[EvolutionProposal, ...]:
        """One-shot convenience: decide candidates then build DRAFT proposals."""
        return self.build_proposals(
            self.decide(assessments, max_candidates=max_candidates)
        )

    def _build_proposal(
        self, candidate: AdaptationProposalCandidate
    ) -> EvolutionProposal:
        """Build one DRAFT EvolutionProposal from a candidate.

        The proposal is NEVER APPROVED here. It carries the candidate's
        evidence into the existing proposal metadata and an ImprovementPlan
        whose priority/scope are derived deterministically.
        """
        plan = ImprovementPlan(
            plan_id=f"IMP-{candidate.target_key}",
            title=candidate.title,
            description=candidate.objective,
            priority=_improvement_priority(candidate.risk),
            expected_benefit=candidate.expected_benefit,
            complexity_estimate="low",
            target_components=[candidate.target_key, candidate.proposed_scope],
        )
        return EvolutionProposal(
            proposal_id=candidate.candidate_id,
            title=candidate.title,
            summary=candidate.objective,
            rationale=candidate.rationale,
            expected_benefit=candidate.expected_benefit,
            risks=f"Risk: {candidate.risk.value}. Governed/approval required.",
            impact_analysis=(
                f"Target: {candidate.target_key}. "
                f"Scope: {candidate.proposed_scope}."
            ),
            implementation_approach=(
                "Deferred: requires existing governed approval and the "
                "existing governed self-development path."
            ),
            plan=plan,
            status=ProposalStatus.DRAFT,
            metadata={
                "source": "F4-adaptation",
                "adaptation_candidate_id": candidate.candidate_id,
                "action": candidate.action.name,
                "reasons": [r.name for r in candidate.reasons],
                "evidence_change_ids": list(candidate.evidence_change_ids),
                "evidence_knowledge_ids": list(candidate.evidence_knowledge_ids),
                "risk": candidate.risk.value,
                "priority": candidate.priority,
            },
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _classify_risk(
    action: LifecycleAction,
    kind: LifecycleTargetKind,
) -> AdaptationRisk:
    """Deterministic bounded risk classification (never authorization)."""
    if action in (LifecycleAction.REPLACE, LifecycleAction.FALLBACK):
        if kind in (LifecycleTargetKind.MODEL, LifecycleTargetKind.CAPABILITY):
            return AdaptationRisk.HIGH
        return AdaptationRisk.MEDIUM
    if action is LifecycleAction.DEPRECATE:
        return AdaptationRisk.LOW
    if action is LifecycleAction.REVIEW:
        return AdaptationRisk.LOW
    return AdaptationRisk.LOW


def _improvement_priority(risk: AdaptationRisk) -> ImprovementPriority:
    """Map candidate risk to the existing ImprovementPriority vocabulary."""
    if risk is AdaptationRisk.HIGH:
        return ImprovementPriority.CRITICAL
    if risk is AdaptationRisk.MEDIUM:
        return ImprovementPriority.HIGH
    return ImprovementPriority.MEDIUM