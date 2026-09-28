"""Step 4 — continuous self-improvement validation (first validation slice).

Proves the complete real-world loop with two isolated Atlas instances over the
SAME persisted ``EvolutionStorage`` and a deployment tree that Atlas itself
inspects:

    Atlas #1: need -> investigation -> evidence -> ConcreteGap -> development
              need -> proposal -> OWNER development approval -> sandbox ->
              verification -> OWNER promotion approval -> PromotionExecutor
              -> the change lands in the tree Atlas inspects

    Atlas #2: NEW instance, same persisted state -> the SAME underlying need
              -> a FRESH investigation observes the promoted change (a real
              ``test`` finding naming the component) -> the original gap is
              gone -> no redundant development is created

A control run without the promotion proves the resolution is caused by the
improvement and not by evaluation drift.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from atlas.conversation.evidence_gap_analysis import (
    EvidenceGapAnalyzer,
    GapCategory,
)
from atlas.conversation.investigation import InvestigationService
from atlas.evolution.evidence_development import resolve_gap_target
from atlas.orchestration.development_orchestrator import DevelopmentState

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TARGET = "the goal plan composer"
_SKIP = shutil.ignore_patterns(
    ".git", ".venv", "__pycache__", "*.pyc", "logs", "atlas_data", "data",
    ".commandcode", ".pytest_cache", "MagicMock",
)


@pytest.fixture
def deployment(tmp_path):
    """An isolated deployment tree Atlas inspects (a copy of the repository).

    The promotion writes into THIS tree, so the working repository is never
    modified; each test gets a fresh copy so the tests stay independent.
    """
    root = tmp_path / "deployment"
    shutil.copytree(_REPO_ROOT, root, ignore=_SKIP, dirs_exist_ok=True)
    return root


def _started_atlas(monkeypatch, db_path: Path, tree: Path):
    """A real kernel over the given persisted storage and deployment tree."""
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    isolated_db = db_path

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=isolated_db)

    # Patch both the kernel symbol and the storage module symbol so every
    # construction path uses the isolated database.
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    monkeypatch.setattr(
        "atlas.storage.evolution_storage.SQLiteEvolutionStorage",
        TmpSQLiteEvolutionStorage,
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    # Isolation guard: the kernel must be reading the isolated database, never
    # the repository's default one.
    assert Path(atlas._evolution_storage.db_path) == isolated_db  # noqa: SLF001
    atlas._promotion_repo_root = lambda: tree  # noqa: SLF001
    return atlas


def _evaluate(tree: Path):
    """The SAME need, evaluated against the tree Atlas inspects."""
    report = InvestigationService(repo_root=tree).investigate(_TARGET)
    return report, EvidenceGapAnalyzer().analyze(report)


def _first_gap(analysis, architecture):
    """The first gap whose component the architecture model can resolve."""
    for gap in analysis.gaps:
        target, _ = resolve_gap_target(gap.component, architecture=architecture)
        if target is not None:
            return gap, target
    raise AssertionError("no resolvable gap in the report")


class TestContinuousLoop:
    def test_improvement_closes_the_original_gap_across_instances(
        self, monkeypatch, tmp_path, deployment
    ):
        db = tmp_path / "evolution.db"
        tree = deployment

        # ---------------- Atlas #1: first cycle + promotion ---------------
        atlas1 = _started_atlas(monkeypatch, db, tree)
        try:
            report1, analysis1 = _evaluate(tree)
            gap, target = _first_gap(analysis1, atlas1.architecture_model())
            assert gap.category is GapCategory.UNTESTED_COMPONENT
            outcome = atlas1.propose_development_from_evidence_gap(
                analysis1, gap_id=gap.gap_id
            )
            proposal_id = outcome.to_dict()["proposal_id"]
            assert outcome.to_dict()["proposal_status"] == "PENDING_APPROVAL"

            owner = atlas1._session_context  # noqa: SLF001
            assert (
                atlas1.run_development_for_prepared_proposal(proposal_id).state
                is DevelopmentState.AWAITING_OWNER
            )
            atlas1.confirm_development_approval(owner, proposal_id)
            ran = atlas1.run_development_for_prepared_proposal(proposal_id)
            assert (ran.execution_status, ran.verification_status) == (
                "SUCCESS",
                "VERIFIED",
            )
            review_id = ran.promotion_review_id

            # No promotion without the separate OWNER promotion approval.
            with pytest.raises(Exception):
                atlas1.promote_validated_change(owner, review_id)
            assert not (tree / outcome.test_path).exists()

            atlas1.approve_promotion_review(owner, review_id)
            promoted = atlas1.promote_validated_change(owner, review_id)
            assert str(getattr(promoted, "outcome", "")) == "PromotionOutcome.PROMOTED"
            assert (tree / outcome.test_path).exists()
            assert not (_REPO_ROOT / outcome.test_path).exists()
        finally:
            atlas1.shutdown()

        # ---------------- Atlas #2: new instance, same persisted state ----
        atlas2 = _started_atlas(monkeypatch, db, tree)
        try:
            persisted = atlas2._evolution_memory.get_proposal(proposal_id)  # noqa: SLF001
            assert persisted is not None and persisted.status.name == "APPROVED"
            assert len(
                atlas2._evolution_memory.get_records_by_type(  # noqa: SLF001
                    "development_promotion"
                )
            ) >= 1

            # The SAME underlying need, freshly evaluated by Atlas #2.
            report2, analysis2 = _evaluate(tree)
            # Atlas's own evidence pipeline now observes the promoted change.
            observed = [
                f for f in report2.findings
                if f.category == "test" and target.source_path.split("/")[-1][:-3] in f.description
            ]
            assert observed, "the promoted change was not observed by the investigation"
            # The original gap is resolved...
            assert [g for g in analysis2.gaps if g.component == gap.component] == []
            # ...and no redundant development is created for it.
            again = atlas2.propose_development_from_evidence_gap(analysis2, gap_id=gap.gap_id)
            assert again.status == "refused" and again.need is None
            assert "no concrete gaps" in again.reason
            assert [p.proposal_id for p in atlas2._evolution_memory.get_all_proposals()] == [  # noqa: SLF001
                proposal_id
            ]
        finally:
            atlas2.shutdown()

    def test_without_the_improvement_the_need_persists(
        self, monkeypatch, tmp_path, deployment
    ):
        """Control: with no promotion the same need is still reported and a new
        development proposal is created — so the resolution above is caused by
        the improvement, not by evaluation drift."""
        db = tmp_path / "control.db"
        tree = deployment

        atlas1 = _started_atlas(monkeypatch, db, tree)
        try:
            analysis1 = _evaluate(tree)[1]
            gap, target = _first_gap(analysis1, atlas1.architecture_model())
            first = atlas1.propose_development_from_evidence_gap(
                analysis1, gap_id=gap.gap_id
            )
            assert first.status == "prepared"
        finally:
            atlas1.shutdown()

        atlas2 = _started_atlas(monkeypatch, db, tree)
        try:
            analysis2 = _evaluate(tree)[1]
            assert [g for g in analysis2.gaps if g.component == gap.component]
            second = atlas2.propose_development_from_evidence_gap(
                analysis2, gap_id=gap.gap_id
            )
            assert second.status == "prepared"
            assert second.need is not None
            assert len(atlas2._evolution_memory.get_all_proposals()) == 2  # noqa: SLF001
        finally:
            atlas2.shutdown()


class TestContinuationBoundaries:
    def test_unapproved_development_never_executes(self, monkeypatch, tmp_path, deployment):
        db = tmp_path / "boundary.db"
        atlas = _started_atlas(monkeypatch, db, deployment)
        try:
            analysis = _evaluate(deployment)[1]
            gap, _ = _first_gap(analysis, atlas.architecture_model())
            outcome = atlas.propose_development_from_evidence_gap(analysis, gap_id=gap.gap_id)
            proposal_id = outcome.to_dict()["proposal_id"]
            run = atlas.run_development_for_prepared_proposal(proposal_id)
            assert run.state is DevelopmentState.AWAITING_OWNER
            assert run.execution_status == "" and run.verification_status == ""
            # This proposal has no promotion review at all.
            assert not [
                r for r in atlas.pending_promotion_reviews()
                if r["proposal_id"] == proposal_id
            ]
        finally:
            atlas.shutdown()

    def test_conversation_identifies_the_need_and_its_gaps(self, monkeypatch, tmp_path):
        """The loop's first link: the EXISTING conversation routes identify the
        need (investigation) and then its evidence gaps."""
        atlas = _started_atlas(monkeypatch, tmp_path / "chat.db", tmp_path / "unused")
        try:
            investigation = atlas.chat(f"Investigate {_TARGET}")
            assert "Investigation" in investigation.content
            assert atlas._conversation._last_investigation_report is not None  # noqa: SLF001

            gaps = atlas.chat("Analyze the findings.")
            assert (gaps.metadata or {}).get("gap_analysis", {}).get("status") == "complete"
            assert gaps.metadata["gap_analysis"]["evidence_basis"]
        finally:
            atlas.shutdown()

    def test_invalid_continuation_fails_closed(self, monkeypatch, tmp_path, deployment):
        atlas = _started_atlas(monkeypatch, tmp_path / "invalid.db", deployment)
        try:
            assert atlas.run_development_for_prepared_proposal("DEV-unknown") is None
            assert atlas.run_development_for_prepared_proposal("") is None
            from atlas.conversation.evidence_gap_analysis import GapAnalysisReport

            refused = atlas.propose_development_from_evidence_gap(
                GapAnalysisReport(target="t", objective="t", insufficient_evidence=True)
            )
            assert refused.status == "refused" and refused.need is None
        finally:
            atlas.shutdown()
