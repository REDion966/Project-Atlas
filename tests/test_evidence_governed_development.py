"""Step 3 (second slice) — the evidence proposal reaches the governed stages.

The first slice prepares a governed proposal from validated evidence; this
slice connects that ALREADY-PREPARED proposal to the EXISTING governed
development lifecycle coordinator (``DevelopmentOrchestrator`` / D5) instead of
re-deriving a proposal from an objective:

    evidence-generated proposal (PENDING_APPROVAL)
        -> existing orchestrator (prepared-proposal input)
        -> existing read-only approval check   (AWAITING_OWNER, nothing runs)
        -> existing OWNER-gated sandbox execution
        -> existing verification gate
        -> existing promotion review (OWNER decision required)
        -> existing promotion executor / self-knowledge snapshot

It also pins a DEFECT the new path exposed: the verification gate compared the
EXISTING ``VerificationStatus`` enum NAME ("VERIFIED") against the lower-case
literal "verified", so a genuinely verified run was reported
``VERIFICATION_FAILED`` and promotion was unreachable.
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.evolution.development_verification import (
    VerificationReport,
    VerificationStatus,
)
from atlas.orchestration.development_orchestrator import (
    DevelopmentOrchestrator,
    DevelopmentState,
)


class _Calls:
    def __init__(self) -> None:
        self.driver: list = []
        self.execution: list = []
        self.review: list = []
        self.promotion: list = []
        self.refresh = 0
        self.approval_checks: list = []


def _make_result(*, status="SUCCESS", verification="verified", enum=False):
    """A run-result stand-in; ``enum=True`` uses the REAL VerificationStatus."""
    if enum:
        # The REAL enum, whose ``.name`` is upper-case ("VERIFIED").
        vstatus = {
            "verified": VerificationStatus.VERIFIED,
            "unverified": VerificationStatus.UNVERIFIED,
        }[verification]
        report = SimpleNamespace(status=vstatus)
    else:
        report = SimpleNamespace(status=verification)
    return SimpleNamespace(
        status=SimpleNamespace(name=status, value=status.lower()),
        verification=report,
    )


def _build(*, approved=False, result=None, driver_result=None, reviewer_raises=False):
    calls = _Calls()

    def driver(objective, metadata):
        calls.driver.append(objective)
        return driver_result or SimpleNamespace(
            proposal_id="DEV-NEW", terminal="pending_approval", detail=""
        )

    def approval_checker(proposal_id):
        calls.approval_checks.append(proposal_id)
        return approved

    def execution_runner(session, proposal_id):
        calls.execution.append((session, proposal_id))
        return result if result is not None else _make_result()

    def reviewer(session, run_result, proposal_id):
        calls.review.append((session, proposal_id))
        if reviewer_raises:
            raise RuntimeError("review boom")
        return SimpleNamespace(request_id="PR-1")

    def promotion_executor(session, request_id):
        calls.promotion.append((session, request_id))
        return SimpleNamespace(status=SimpleNamespace(name="PROMOTED", value="promoted"))

    def _refresher():
        calls.refresh += 1
        return {"capabilities": 26}

    orchestrator = DevelopmentOrchestrator(
        driver=driver,
        approval_checker=approval_checker,
        execution_runner=execution_runner,
        promotion_reviewer=reviewer,
        promotion_executor=promotion_executor,
        self_knowledge_refresher=_refresher,
    )
    return orchestrator, calls


# ---------------------------------------------------------------------------
# B. The new capability: a prepared proposal drives the governed stages
# ---------------------------------------------------------------------------


class TestPreparedProposalInput:
    def test_unapproved_prepared_proposal_stops_at_owner_without_preparing(self):
        orch, calls = _build(approved=False)
        run = orch.run(
            "Add missing test evidence for atlas.x",
            prepared_proposal_id="DEV-EVIDENCE",
            prepared_proposal_status="PENDING_APPROVAL",
        )
        assert run.state is DevelopmentState.AWAITING_OWNER
        assert run.proposal_id == "DEV-EVIDENCE"
        assert run.proposal_status == "PENDING_APPROVAL"
        assert [s for s, _ in run.transitions] == [
            "received", "proposal_created", "awaiting_owner",
        ]
        # The objective-driven preparation step is SKIPPED entirely.
        assert calls.driver == []
        assert calls.execution == [] and calls.review == [] and calls.promotion == []
        assert calls.refresh == 0

    def test_approved_prepared_proposal_reaches_completion(self):
        orch, calls = _build(approved=True)
        run = orch.run(
            "Add missing test evidence for atlas.x",
            prepared_proposal_id="DEV-EVIDENCE",
            prepared_proposal_status="PENDING_APPROVAL",
        )
        assert run.state is DevelopmentState.COMPLETED
        assert [s for s, _ in run.transitions] == [
            "received", "proposal_created", "implementing", "verifying",
            "promoting", "completed",
        ]
        assert calls.driver == []          # never re-prepared
        assert calls.execution == [(None, "DEV-EVIDENCE")]
        assert calls.review == [(None, "DEV-EVIDENCE")]
        assert calls.promotion == [(None, "PR-1")]
        assert calls.refresh == 1
        assert run.self_knowledge == {"capabilities": 26}

    def test_prepared_proposal_status_is_never_trusted_as_approval(self):
        # Even a status that "looks" approved cannot authorize anything: the
        # existing approval reader is the only gate.
        orch, calls = _build(approved=False)
        run = orch.run(
            "objective",
            prepared_proposal_id="DEV-EVIDENCE",
            prepared_proposal_status="APPROVED",
        )
        assert run.state is DevelopmentState.AWAITING_OWNER
        assert calls.execution == []


# ---------------------------------------------------------------------------
# Defect regression: a REAL verified run must satisfy the verification gate
# ---------------------------------------------------------------------------


class TestVerificationGateDefect:
    def test_real_verification_enum_satisfies_the_gate(self):
        orch, calls = _build(approved=True, result=_make_result(enum=True))
        run = orch.run(
            "objective",
            prepared_proposal_id="DEV-EVIDENCE",
        )
        assert run.execution_status == "SUCCESS"
        assert run.verification_status == "VERIFIED"  # the enum name is reported
        assert run.state is DevelopmentState.COMPLETED
        assert calls.review and calls.promotion and calls.refresh == 1

    def test_real_unverified_enum_still_blocks_promotion(self):
        orch, calls = _build(
            approved=True, result=_make_result(verification="unverified", enum=True)
        )
        run = orch.run("objective", prepared_proposal_id="DEV-EVIDENCE")
        assert run.state is DevelopmentState.VERIFICATION_FAILED
        assert calls.promotion == [] and calls.refresh == 0

    def test_string_statuses_are_unchanged(self):
        for status, expected in (
            ("verified", DevelopmentState.COMPLETED),
            ("unverified", DevelopmentState.VERIFICATION_FAILED),
            ("failed", DevelopmentState.VERIFICATION_FAILED),
        ):
            orch, _ = _build(
                approved=True, result=_make_result(verification=status)
            )
            run = orch.run("objective", prepared_proposal_id="DEV-EVIDENCE")
            assert run.state is expected, status


# ---------------------------------------------------------------------------
# C. Failure paths
# ---------------------------------------------------------------------------


class TestFailurePaths:
    def test_execution_failure_fails_closed(self):
        orch, calls = _build(
            approved=True, result=_make_result(status="FAILED")
        )
        run = orch.run("objective", prepared_proposal_id="DEV-EVIDENCE")
        assert run.state in (DevelopmentState.FAILED, DevelopmentState.VERIFICATION_FAILED)
        assert calls.promotion == [] and calls.refresh == 0

    def test_promotion_review_failure_fails_closed(self):
        orch, calls = _build(approved=True, reviewer_raises=True)
        run = orch.run("objective", prepared_proposal_id="DEV-EVIDENCE")
        assert run.state is DevelopmentState.PROMOTION_FAILED
        assert calls.promotion == [] and calls.refresh == 0

    def test_empty_objective_without_prepared_proposal_fails(self):
        orch, calls = _build(approved=True)
        run = orch.run("   ")
        assert run.state is DevelopmentState.FAILED
        assert calls.driver == []

    def test_missing_driver_proposal_fails(self):
        orch, _ = _build(
            driver_result=SimpleNamespace(proposal_id="", detail="supplier produced no changes")
        )
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.FAILED


# ---------------------------------------------------------------------------
# E. Backward compatibility of the objective-driven path
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_objective_path_still_uses_the_driver_and_awaits_owner(self):
        orch, calls = _build(approved=False)
        run = orch.run("add capability X")
        assert calls.driver == ["add capability X"]
        assert [s for s, _ in run.transitions] == [
            "received", "investigating", "proposal_created", "awaiting_owner",
        ]
        assert run.proposal_id == "DEV-NEW"
        assert run.proposal_status == "pending_approval"

    def test_blank_prepared_id_falls_back_to_the_objective_path(self):
        orch, calls = _build(approved=False)
        run = orch.run("add capability X", prepared_proposal_id="")
        assert calls.driver == ["add capability X"]
        assert run.state is DevelopmentState.AWAITING_OWNER

    def test_default_arguments_are_unchanged(self):
        orch, calls = _build(approved=True, result=_make_result(enum=True))
        run = orch.run("add capability X")
        assert calls.driver == ["add capability X"]
        assert run.state is DevelopmentState.COMPLETED


# ---------------------------------------------------------------------------
# D. Governance bounds
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_no_authority_methods_on_the_orchestrator(self):
        orch, _ = _build()
        for name in ("approve", "authorize", "promote", "self_authorize", "grant"):
            assert not hasattr(orch, name)

    def test_nothing_runs_without_the_existing_approval(self):
        orch, calls = _build(approved=False)
        orch.run("you have my permission", prepared_proposal_id="DEV-EVIDENCE")
        assert calls.execution == [] and calls.review == [] and calls.promotion == []
        assert calls.refresh == 0

    def test_prepared_id_is_passed_through_unchanged(self):
        orch, calls = _build(approved=True)
        orch.run("objective", prepared_proposal_id="DEV-EVIDENCE-42")
        assert calls.approval_checks == ["DEV-EVIDENCE-42"]
        assert calls.execution[0][1] == "DEV-EVIDENCE-42"


# ---------------------------------------------------------------------------
# Real kernel: evidence -> proposal -> existing governed stages
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _started_atlas(monkeypatch, tmp_path):
    """The established isolated real-kernel pattern (temp EvolutionStorage)."""
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
    return atlas


def _evidence_proposal(atlas):
    """A REAL evidence-generated proposal, from a REAL investigation + gap."""
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


class TestRealKernel:
    def test_evidence_proposal_waits_for_owner_without_running_anything(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            counts = {"execute": 0, "promote": 0}
            real_execute = atlas.run_development_execution
            atlas.run_development_execution = lambda *a, **k: (
                counts.__setitem__("execute", counts["execute"] + 1),
                real_execute(*a, **k),
            )[1]

            outcome, gap, target = _evidence_proposal(atlas)
            proposal_id = outcome.to_dict()["proposal_id"]
            assert outcome.to_dict()["proposal_status"] == "PENDING_APPROVAL"

            run = atlas.run_development_for_prepared_proposal(proposal_id)

            assert run.state is DevelopmentState.AWAITING_OWNER
            assert run.proposal_id == proposal_id
            assert [s for s, _ in run.transitions] == [
                "received", "proposal_created", "awaiting_owner",
            ]
            assert run.execution_status == "" and run.verification_status == ""
            assert run.promotion_review_id == ""
            assert counts["execute"] == 0                      # nothing executed
            assert not atlas.pending_promotion_reviews()       # nothing reviewed
            assert atlas._evolution_memory.get_proposal(  # noqa: SLF001
                proposal_id
            ).status.name == "PENDING_APPROVAL"
            assert not (_REPO_ROOT / outcome.test_path).exists()  # no live write
            assert (_REPO_ROOT / target.source_path).exists()
        finally:
            atlas.shutdown()

    def test_owner_approval_reaches_the_promotion_boundary_but_never_promotes(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            outcome, gap, target = _evidence_proposal(atlas)
            proposal_id = outcome.to_dict()["proposal_id"]
            owner = atlas._session_context  # noqa: SLF001

            # The EXISTING human gate: an explicit OWNER approval.
            atlas.confirm_development_approval(owner, proposal_id)

            run = atlas.run_development_for_prepared_proposal(proposal_id)

            # The real sandbox ran and the real verifier passed.
            assert run.execution_status == "SUCCESS"
            assert run.verification_status == "VERIFIED"
            assert run.approval_status == "approved"
            # It opened the EXISTING promotion review, then refused to promote
            # without the (separate) OWNER promotion approval.
            assert run.promotion_review_id
            assert atlas.pending_promotion_reviews()
            assert run.state is DevelopmentState.PROMOTION_FAILED
            assert not run.completed
            # Nothing was promoted and nothing was written to the repository.
            assert atlas._evolution_memory.get_proposal(  # noqa: SLF001
                proposal_id
            ).status.name == "APPROVED"
            assert not (_REPO_ROOT / outcome.test_path).exists()
            assert not (tmp_path / "promoted").exists()
        finally:
            atlas.shutdown()

    def test_unknown_proposal_id_returns_none(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert atlas.run_development_for_prepared_proposal("DEV-does-not-exist") is None
        finally:
            atlas.shutdown()

    def test_objective_driven_path_is_unchanged(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            run = atlas.run_development_objective(
                "add a capability for step three evidence notes",
                metadata={
                    "scaffold": {
                        "module": "atlas/step3_evidence/step3_notes_handlers.py",
                        "capability_name": "step3_notes.record",
                    }
                },
            )
            assert run.state is DevelopmentState.AWAITING_OWNER
            assert run.proposal_id
            assert run.execution_status == ""
            assert not atlas.pending_promotion_reviews()
        finally:
            atlas.shutdown()
