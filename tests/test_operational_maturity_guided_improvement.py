"""Operational Maturity track — T2 guided-improvement composite proof.

Proves the complete governed guided-improvement path over EXISTING
infrastructure, with model=None throughout:

    detected need (evidence ids)
        → F8 bounded information acquisition
        → F9 development preparation → DRAFT proposal
        → ApprovalManager → PENDING_APPROVAL          [STOP]
        → explicit human approval (user:cli)          [the gate]
        → DevelopmentPlanner.plan() (APPROVED required)
        → SelfDevelopmentLoop inside a disposable CodeSandbox
            implement → pytest verify → accept/rollback
        → durable DevelopmentOutcome + LearningMemory evidence

Also proves negative/fail-closed behavior:
  * an unapproved proposal cannot proceed to planning;
  * failing sandbox tests produce FAILED outcomes and never acceptance;
  * the real repository is never mutated (sandbox is discarded).

No production orchestration is added; this is a pure test harness composing
existing public APIs. No AI model is used anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.models import ProposalStatus
from atlas.kernel.atlas import Atlas
from tests.test_durable_guided_improvement import _storage_class


@pytest.fixture(autouse=True)
def _isolated_evolution_storage(monkeypatch, tmp_path):
    """Kernel-starting tests here must not touch the operator database."""
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage",
        _storage_class(tmp_path),
    )


def _need_payload(**overrides):
    base = {
        "title": "Composite guided-improvement need",
        "summary": "Prove the governed loop end-to-end.",
        "rationale": "Durable evidence from F11 review.",
        "candidate_id": "CAND-OM-1",
        "research_question": "bounded guided improvement sources",
        "code_changes": [
            {"path": "docs/om_proof_note.md", "content": "# om proof\n"}
        ],
        "test_files": {
            "tests/test_om_proof.py": (
                "def test_om_proof_passes():\n    assert True\n"
            )
        },
    }
    base.update(overrides)
    return base


def _capture_approval(atlas):
    """Instrument the EXISTING ApprovalManager seam (test-only spy).

    Captures the proposal + approval request objects so the harness can walk
    the real continuation after the kernel controller stops. No behavior is
    changed: the original method still runs.
    """
    captured: dict = {}
    manager = atlas._approval_manager  # noqa: SLF001
    original = manager.create_approval_request

    def spy(proposal):
        captured["proposal"] = proposal
        request = original(proposal)
        captured["request"] = request
        return request

    manager.create_approval_request = spy  # noqa: SLF001
    return captured


def _approve(atlas, captured):
    """The explicit human approval gate (existing ApprovalManager API).

    Two-step contract: record the decision, then apply it to the proposal.
    """
    manager = atlas._approval_manager  # noqa: SLF001
    manager.approve(captured["request"], comment="user:cli explicit approval")
    manager.update_proposal_from_decision(
        captured["proposal"], captured["request"]
    )


class TestGuidedImprovementComposite:
    def test_full_governed_loop_with_model_none(self, tmp_path):
        atlas = Atlas()
        try:
            atlas.start()
            captured = _capture_approval(atlas)
            need_file = tmp_path / "need.json"
            need_file.write_text(
                json.dumps(_need_payload()), encoding="utf-8"
            )

            # --- F8: bounded research before drafting ---
            acquisition = atlas.run_information_acquisition(
                question="bounded guided improvement sources",
                query_id="om-comp-1",
            )
            assert acquisition.decision in ("research", "noop")

            # --- F9: preparation stops at the human boundary ---
            from tests.test_postcore_cli import _args, cmd_develop

            development = cmd_develop(atlas, _args(need_file=str(need_file)))
            assert "PENDING_APPROVAL" in development
            assert captured["proposal"].status is ProposalStatus.PENDING_APPROVAL

            # --- Explicit human approval (existing ApprovalManager API) ---
            _approve(atlas, captured)
            assert captured["proposal"].status is ProposalStatus.APPROVED

            # --- Governed development path: plan + sandbox SDL ---
            plan = atlas.development_planner.plan(captured["proposal"])
            assert len(plan.steps) == 7

            run_result = atlas.self_development_loop.run(captured["proposal"])

            # Sandbox execution verified and ACCEPTED the change.
            assert run_result.status is DevelopmentOutcomeStatus.SUCCESS
            assert run_result.outcomes
            assert run_result.outcomes[-1].outcome is (
                DevelopmentOutcomeStatus.SUCCESS
            )

            # Durable learning evidence recorded in the EXISTING store.
            learning_memory = getattr(
                atlas._learning_engine, "memory", None
            )  # noqa: SLF001
            if learning_memory is not None:
                assert learning_memory.insight_count >= 1

            # The real repository was never touched — the change lived and
            # died inside the disposable sandbox.
            assert not Path("docs/om_proof_note.md").exists()
            assert not Path("tests/test_om_proof.py").exists()
        finally:
            atlas.shutdown()


class TestFailClosedLegs:
    def test_unapproved_proposal_cannot_proceed(self):
        """A DRAFT proposal is refused by the existing planner gate."""
        from atlas.evolution.development_planner import (
            DevelopmentPlanner,
            DevelopmentPlannerError,
        )
        from atlas.evolution.models import (
            EvolutionProposal,
            ImprovementPlan,
            ImprovementPriority,
        )

        draft = EvolutionProposal(
            proposal_id="DEV-UNAPPROVED",
            title="Unapproved",
            summary="s",
            rationale="r",
            expected_benefit="b",
            risks="r",
            impact_analysis="i",
            implementation_approach="a",
            plan=ImprovementPlan(
                plan_id="p1",
                title="t",
                description="d",
                priority=ImprovementPriority.MEDIUM,
            ),
            status=ProposalStatus.DRAFT,
        )
        with pytest.raises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(draft)

    def test_failing_verification_produces_failed_outcome(self, tmp_path):
        """Failing sandbox tests FAIL the run and never touch the repo."""
        from tests.test_postcore_cli import _args, cmd_develop

        atlas = Atlas()
        try:
            atlas.start()
            captured = _capture_approval(atlas)
            need_file = tmp_path / "need.json"
            need_file.write_text(
                json.dumps(
                    _need_payload(
                        candidate_id="CAND-OM-2",
                        code_changes=[
                            {
                                "path": "docs/om_fail_note.md",
                                "content": "# x\n",
                            }
                        ],
                        test_files={
                            "tests/test_om_fail.py": (
                                "def test_om_should_fail():\n    assert False\n"
                            )
                        },
                    )
                ),
                encoding="utf-8",
            )

            development = cmd_develop(atlas, _args(need_file=str(need_file)))
            assert "PENDING_APPROVAL" in development

            _approve(atlas, captured)
            plan = atlas.development_planner.plan(captured["proposal"])
            run_result = atlas.self_development_loop.run(captured["proposal"])

            # Failing sandbox verification must never be accepted; the
            # bounded loop terminates without success (FAILED or, when the
            # iteration budget is consumed by repeated failures,
            # ITERATIONS_EXHAUSTED).
            assert run_result.status is not DevelopmentOutcomeStatus.SUCCESS
            assert all(
                o.outcome is not DevelopmentOutcomeStatus.SUCCESS
                for o in run_result.outcomes
            )
            assert not Path("docs/om_fail_note.md").exists()
        finally:
            atlas.shutdown()