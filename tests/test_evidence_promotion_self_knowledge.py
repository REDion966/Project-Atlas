"""Step 3 (third slice) — evidence → … → OWNER promotion → self-knowledge.

Validates, with the real kernel, that the EXISTING governed pipeline can
complete the whole remaining Step 3 path for a proposal generated from
validated evidence:

    ConcreteGap -> DevelopmentNeed -> resolved source file -> targeted change
      -> DevelopmentCycleController -> PENDING_APPROVAL
      -> OWNER development approval
      -> sandbox execution -> verification VERIFIED
      -> promotion review
      -> OWNER promotion approval
      -> existing PromotionExecutor (isolated promotion target)
      -> existing self-knowledge records

It also pins the blocking gap this validation exposed and its minimal fix: the
governed orchestrator's promotion review is opened through the EXISTING
artifact-capturing mechanism, so the review is ACTIONABLE (it can be approved
and promoted). Before the fix the review was listed with no registered
artifact every approval/promotion raised "not found".

Promotion targets an ISOLATED temporary repository root, so the working
repository is never written.
"""

from __future__ import annotations

import posixpath
from pathlib import Path

import pytest

from atlas.orchestration.development_orchestrator import DevelopmentState

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _started_atlas(monkeypatch, tmp_path):
    """Established isolated real-kernel pattern (temp EvolutionStorage)."""
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    # Isolated promotion target: PromotionExecutor writes here, never into the
    # working repository.
    isolated_root = tmp_path / "promotion_repo"
    isolated_root.mkdir(parents=True, exist_ok=True)
    atlas._promotion_repo_root = lambda: isolated_root  # noqa: SLF001
    return atlas, isolated_root


def _evidence_proposal(atlas):
    """A REAL evidence-generated proposal from a REAL investigation + gap."""
    from atlas.conversation.evidence_gap_analysis import EvidenceGapAnalyzer
    from atlas.conversation.investigation import InvestigationService
    from atlas.evolution.evidence_development import resolve_gap_target

    report = InvestigationService().investigate("the goal plan composer")
    analysis = EvidenceGapAnalyzer().analyze(report)
    architecture = atlas.architecture_model()
    for gap in analysis.gaps:
        target, _ = resolve_gap_target(gap.component, architecture=architecture)
        if target is not None:
            outcome = atlas.propose_development_from_evidence_gap(
                analysis, gap_id=gap.gap_id
            )
            return outcome, gap, target
    raise AssertionError("no resolvable real evidence gap")


class TestFullEvidenceLifecycle:
    def test_complete_path_including_owner_approved_promotion(self, monkeypatch, tmp_path):
        atlas, isolated = _started_atlas(monkeypatch, tmp_path)
        try:
            owner = atlas._session_context  # noqa: SLF001
            outcome, gap, target = _evidence_proposal(atlas)
            proposal_id = outcome.to_dict()["proposal_id"]
            assert outcome.to_dict()["proposal_status"] == "PENDING_APPROVAL"

            # 1. No approval yet: nothing runs.
            first = atlas.run_development_for_prepared_proposal(proposal_id)
            assert first.state is DevelopmentState.AWAITING_OWNER
            assert first.execution_status == "" and first.verification_status == ""

            # 2. OWNER development approval -> sandbox execution + verification.
            atlas.confirm_development_approval(owner, proposal_id)
            second = atlas.run_development_for_prepared_proposal(proposal_id)
            assert second.execution_status == "SUCCESS"
            assert second.verification_status == "VERIFIED"
            review_id = second.promotion_review_id
            assert review_id

            # The review is ACTIONABLE: the existing artifact capture ran.
            assert review_id in atlas._promotion_artifacts  # noqa: SLF001
            reviews = atlas.pending_promotion_reviews()
            assert reviews and reviews[0]["proposal_id"] == proposal_id
            assert reviews[0]["manifest_file_count"] >= 1  # real change evidence
            assert reviews[0]["evidence_complete"] is True

            # 3. Promotion without the OWNER promotion approval is refused.
            with pytest.raises(Exception):
                atlas.promote_validated_change(owner, review_id)
            assert not (isolated / outcome.test_path).exists()
            assert not (isolated / "mod.py").exists()

            # 4. OWNER promotion approval + the existing promotion executor.
            atlas.approve_promotion_review(owner, review_id)
            result = atlas.promote_validated_change(owner, review_id)
            assert str(getattr(result, "outcome", "")) == "PromotionOutcome.PROMOTED"

            # The authorised change landed in the ISOLATED root only.
            assert (isolated / outcome.test_path).exists()
            assert not (_REPO_ROOT / outcome.test_path).exists()

            # 5. Existing promotion + self-knowledge records.
            assert len(atlas._evolution_memory.get_records_by_type(  # noqa: SLF001
                "development_promotion"
            )) == 1
        finally:
            atlas.shutdown()

    def test_promotion_approval_is_owner_only(self, monkeypatch, tmp_path):
        atlas, isolated = _started_atlas(monkeypatch, tmp_path)
        try:
            from atlas.session.context import SessionContext

            owner = atlas._session_context  # noqa: SLF001
            atlas._authority_service.add_user("analyst")  # noqa: SLF001
            user_session = SessionContext.from_session(
                atlas._session_manager.create_session("analyst")  # noqa: SLF001
            )
            outcome, _, _ = _evidence_proposal(atlas)
            proposal_id = outcome.to_dict()["proposal_id"]
            atlas.confirm_development_approval(owner, proposal_id)
            review_id = atlas.run_development_for_prepared_proposal(
                proposal_id
            ).promotion_review_id

            with pytest.raises(Exception):
                atlas.approve_promotion_review(user_session, review_id)
            with pytest.raises(Exception):
                atlas.promote_validated_change(user_session, review_id)
            assert not (isolated / outcome.test_path).exists()
        finally:
            atlas.shutdown()


class TestSelfKnowledgeAfterPromotion:
    def test_no_capability_claims_are_recorded_for_a_coverage_change(
        self, monkeypatch, tmp_path
    ):
        """A coverage-test change declares no capability, so the EXISTING
        capability-scoped self-knowledge projection records nothing; the change
        itself is represented by the filesystem-derived architecture model."""
        atlas, isolated = _started_atlas(monkeypatch, tmp_path)
        try:
            owner = atlas._session_context  # noqa: SLF001
            outcome, _, _ = _evidence_proposal(atlas)
            proposal_id = outcome.to_dict()["proposal_id"]
            atlas.confirm_development_approval(owner, proposal_id)
            review_id = atlas.run_development_for_prepared_proposal(
                proposal_id
            ).promotion_review_id
            atlas.approve_promotion_review(owner, review_id)
            atlas.promote_validated_change(owner, review_id)

            memory = atlas._evolution_memory  # noqa: SLF001
            assert memory.get_records_by_type("capability_activation") == []
            assert memory.get_records_by_type("capability_self_knowledge_refresh") == []
            # No capability was declared by the promoted change.
            proposal = memory.get_proposal(proposal_id)
            assert "capability_name" not in str(proposal.metadata)
        finally:
            atlas.shutdown()

    def test_the_filesystem_derived_model_represents_test_modules(self, monkeypatch, tmp_path):
        """The EXISTING architecture self-knowledge already represents `tests.*`
        modules (the representation a promoted coverage module joins)."""
        atlas, _ = _started_atlas(monkeypatch, tmp_path)
        try:
            model = atlas.architecture_model()
            located = model.locate("tests.test_conversation_state")
            assert located.found is True
            assert located.matched_kind == "module"
        finally:
            atlas.shutdown()


class TestPromotionReviewActionable:
    def test_orchestrated_review_is_reviewable_and_actionable(self, monkeypatch, tmp_path):
        """The review the orchestrator opens carries real change evidence and is
        visible to the reviewer (the pre-fix review was inert)."""
        atlas, isolated = _started_atlas(monkeypatch, tmp_path)
        try:
            owner = atlas._session_context  # noqa: SLF001
            outcome, _, _ = _evidence_proposal(atlas)
            proposal_id = outcome.to_dict()["proposal_id"]
            atlas.confirm_development_approval(owner, proposal_id)
            run = atlas.run_development_for_prepared_proposal(proposal_id)

            # The orchestrator opened (and registered) an actionable review.
            assert run.promotion_review_id
            assert run.promotion_review_id in atlas._promotion_artifacts  # noqa: SLF001

            pending = atlas.pending_promotion_reviews()
            assert len(pending) == 1
            entry = pending[0]
            assert entry["proposal_id"] == proposal_id
            assert entry["manifest_file_count"] >= 1
            assert entry["evidence_complete"] is True

            detail = atlas.promotion_review_details(entry["request_id"])
            assert detail is not None
            assert detail["proposal_id"] == proposal_id
        finally:
            atlas.shutdown()
