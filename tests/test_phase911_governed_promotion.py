"""Phase 9.11 — Governed promotion and activation: evidence contract.

Investigation result: Atlas-owned development cannot bypass the governance
boundary — successful sandbox development opens a promotion REVIEW, promotion
execution requires authorization, and activation happens only through
``CapabilityActivator``.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.evolution.promotion_executor import PromotionExecutor, PromotionOutcome
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
    PromotionStatus,
)
from atlas.reasoning.execution.registry import CapabilityRegistry


def _verified_run():
    outcome = DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id="P",
        plan_id="PL",
        iteration=1,
        verification_passed=True,
        test_outcome="passed",
        changed_files=["atlas/example/widget_handlers.py"],
    )
    return SimpleNamespace(
        status=DevelopmentOutcomeStatus.SUCCESS,
        outcomes=[outcome],
        iterations_used=1,
        message="ok",
        plan=None,
    )


class TestPhase911GovernedPromotion:
    def test_successful_development_does_not_auto_promote(self):
        gate = PromotionGate(evolution_memory=EvolutionMemory())
        assessment = gate.assess(_verified_run(), proposal_id="P")
        assert assessment.recommendation is PromotionRecommendation.READY_FOR_PROMOTION

        review = gate.request_review(assessment)
        assert review.status is PromotionStatus.PENDING_REVIEW
        gate.approve(review, comment="owner")
        assert review.status is PromotionStatus.APPROVED
        # Approval means "ready for promotion" — never an automatic production change.
        assert review.status is not PromotionStatus.PROMOTED

    def test_promotion_executor_requires_authorization(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        content = "VALUE = 1\n"
        (root / "mod.py").write_text(content, encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": "mod.py", "content": content}], proposal_id="P", repo_root=root
        )
        result = PromotionExecutor(root).promote(artifact, authorized=False)
        assert result.outcome is PromotionOutcome.REFUSED_UNAUTHORIZED
        assert result.ok is False

    def test_review_approval_alone_does_not_activate(self):
        registry = CapabilityRegistry()
        gate = PromotionGate(evolution_memory=EvolutionMemory())
        review = gate.request_review(gate.assess(_verified_run(), proposal_id="P"))
        gate.approve(review, comment="owner")
        # Nothing is registered until the governed CapabilityActivator runs.
        assert registry.registered_names == []
