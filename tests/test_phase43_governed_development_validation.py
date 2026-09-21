"""Phase 4.3 — Governed self-development end-to-end validation.

Drives the REAL kernel lifecycle with predictable, model-free workloads:

    DevelopmentNeed
      -> run_development_cycle   (DRAFT proposal + approval request, STOP at
                                  PENDING_APPROVAL)
      -> OWNER confirm           (APPROVED)
      -> run_development_execution (sandbox implement + pytest + diagnosis/
                                  recovery + verification)
      -> evidence persisted

No external model or network is contacted anywhere; the live repository is
asserted unchanged before/after execution.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.development_test_selection import select_relevant_tests
from atlas.evolution.development_verification import VerificationStatus
from atlas.evolution.models import ProposalStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]

PASS_CODE = "VISIBLE = 1\n"
PASS_TEST = "def test_visible():\n    assert True\n"
FAIL_TEST = "def test_visible():\n    assert 1 == 2\n"


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - environment without git
        return ""


def _make_atlas(tmp_path, monkeypatch):
    """Start a real Atlas kernel whose evolution + research stores are tmp."""
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage
    from tests.test_durable_guided_improvement import _storage_class

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )

    class _TmpResearchStorage(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.ResearchSQLiteStorage", _TmpResearchStorage
    )

    atlas = kernel_mod.Atlas()
    atlas.start()
    assert atlas.session_context is not None, "kernel did not establish an owner session"
    return atlas


def _need(
    code_changes,
    test_files,
    *,
    evidence=("ev-1",),
    research_question="",
    title="Add a visible value",
):
    return DevelopmentNeed(
        title=title,
        summary="Introduce a visible value.",
        rationale="deterministic test need",
        expected_benefit="a visible value exists",
        target_components=["sandbox_mod"],
        candidate_id="cand-43",
        evidence_change_ids=tuple(evidence),
        research_question=research_question,
        metadata={"code_changes": code_changes, "test_files": test_files},
    )


def _passing_need(**kwargs):
    return _need(
        [{"path": "sandbox_mod.py", "content": PASS_CODE}],
        {"test_sandbox_mod.py": PASS_TEST},
        **kwargs,
    )


def _failing_need(**kwargs):
    return _need(
        [{"path": "sandbox_mod.py", "content": PASS_CODE}],
        {"test_sandbox_mod.py": FAIL_TEST},
        **kwargs,
    )


# ---------------------------------------------------------------------------
# End-to-end governed lifecycle
# ---------------------------------------------------------------------------


class TestGovernedLifecycleEndToEnd:
    def test_happy_path_stops_at_approval_then_executes_verified(
        self, tmp_path, monkeypatch
    ):
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            head_before = _git_head()

            cycle = atlas.run_development_cycle(_passing_need())
            assert cycle.ok and cycle.status == "ok"
            assert cycle.decision == "prepared"
            assert cycle.proposal_status == "PENDING_APPROVAL"
            proposal_id = cycle.proposal_id
            assert proposal_id.startswith("DEV-")
            assert cycle.approval_request_id

            # Execution BEFORE approval must fail closed.
            with pytest.raises(RuntimeError):
                atlas.run_development_execution(atlas.session_context, proposal_id)

            # OWNER approves.
            proposal = atlas.confirm_development_approval(
                atlas.session_context, proposal_id
            )
            assert proposal.status == ProposalStatus.APPROVED

            result = atlas.run_development_execution(
                atlas.session_context, proposal_id
            )

            assert result.status == DevelopmentOutcomeStatus.SUCCESS
            assert result.iterations_used == 1
            assert result.outcomes[-1].outcome == DevelopmentOutcomeStatus.SUCCESS
            assert result.outcomes[-1].test_outcome == "passed"

            # Verification integrated + objective.
            assert result.verification is not None
            assert result.verification.status == VerificationStatus.VERIFIED
            assert result.verification.iterations_examined == 1
            assert result.verification.all_tests_passed is True

            # Live repository unchanged; no sandbox artifact leaked.
            assert _git_head() == head_before
            assert not (_REPO_ROOT / "sandbox_mod.py").exists()
            if result.sandbox_path:
                sandbox = Path(result.sandbox_path).resolve()
                assert _REPO_ROOT not in sandbox.parents

            # Evidence persisted on the proposal (read-only metadata).
            stored = atlas._evolution_memory.get_proposal(proposal_id)
            assert stored.metadata["verification"]["status"] == "verified"
            assert stored.metadata["execution"]["result_status"] == "SUCCESS"
        finally:
            atlas.shutdown()

    def test_persistent_failure_is_bounded_and_safe(self, tmp_path, monkeypatch):
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            head_before = _git_head()
            cycle = atlas.run_development_cycle(_failing_need())
            assert cycle.ok
            atlas.confirm_development_approval(
                atlas.session_context, cycle.proposal_id
            )

            result = atlas.run_development_execution(
                atlas.session_context, cycle.proposal_id
            )

            assert result.status == DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED
            assert result.iterations_used == 3  # bounded, never unbounded
            assert len(result.outcomes) == 3
            assert all(
                o.outcome == DevelopmentOutcomeStatus.FAILED for o in result.outcomes
            )
            # Diagnosis + recovery evidence produced deterministically.
            assert result.diagnosis is not None
            assert result.recovery is not None
            assert result.diagnosis.failure_class.value == "verification"
            # Objective verification refuses to claim success.
            assert result.verification is not None
            assert result.verification.status != VerificationStatus.VERIFIED
            assert result.verification.all_tests_passed is False

            # No unsafe progression: repository untouched, no promotion.
            assert _git_head() == head_before
            assert not (_REPO_ROOT / "sandbox_mod.py").exists()
        finally:
            atlas.shutdown()

    def test_failure_diagnosis_drives_bounded_correction_to_success(self):
        """failure -> diagnosis -> corrected retry -> success (loop level).

        The kernel's default supplier is deterministic (no self-correction);
        a corrective supplier is injected here to validate the transitions.
        """
        from atlas.evolution.development_models import SandboxWorkload
        from atlas.evolution.models import EvolutionProposal, ImprovementPlan, ImprovementPriority
        from atlas.evolution.self_development_loop import SelfDevelopmentLoop

        seen: list[list[str]] = []

        def supplier(proposal, history):
            seen.append(
                [
                    (o.metadata.get("recovery") or {}).get("strategy", "")
                    for o in history
                ]
            )
            failing = bool(history) is False
            return SandboxWorkload(
                code_changes=({"path": "mod.py", "content": PASS_CODE},),
                test_files={
                    "test_mod.py": FAIL_TEST if failing else PASS_TEST
                },
                verify_target="test_mod.py",
            )

        plan = ImprovementPlan(
            plan_id="IMP-43",
            title="t",
            description="d",
            priority=ImprovementPriority.HIGH,
            target_components=["mod"],
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-43",
            title="t",
            summary="s",
            rationale="r",
            expected_benefit="b",
            risks="low",
            impact_analysis="modifies mod.py",
            implementation_approach="add a constant and a test",
            plan=plan,
            status=ProposalStatus.APPROVED,
        )
        result = SelfDevelopmentLoop(change_supplier=supplier).run(
            proposal, max_iterations=3
        )

        assert result.status == DevelopmentOutcomeStatus.SUCCESS
        assert result.iterations_used == 2
        assert seen[0] == []  # no prior diagnosis on the first attempt
        assert seen[1] == ["no_recovery"]  # diagnosis carried into the retry


# ---------------------------------------------------------------------------
# Authority / approval / fail-closed
# ---------------------------------------------------------------------------


class TestAuthorityAndFailClosed:
    def test_non_owner_cannot_approve_or_execute(self, tmp_path, monkeypatch):
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            authority = atlas._authority_service
            authority.add_user("Alice", principal_id="alice")
            user_ctx = atlas.start_user_session("alice")
            assert user_ctx is not None

            cycle = atlas.run_development_cycle(_passing_need())
            proposal_id = cycle.proposal_id

            with pytest.raises(RuntimeError):
                atlas.confirm_development_approval(user_ctx, proposal_id)

            atlas.confirm_development_approval(
                atlas.session_context, proposal_id
            )
            with pytest.raises(RuntimeError):
                atlas.run_development_execution(user_ctx, proposal_id)
        finally:
            atlas.shutdown()

    def test_unapproved_proposal_never_executes(self, tmp_path, monkeypatch):
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            cycle = atlas.run_development_cycle(_passing_need())
            with pytest.raises(RuntimeError):
                atlas.run_development_execution(
                    atlas.session_context, cycle.proposal_id
                )
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# Research-assisted development
# ---------------------------------------------------------------------------


class TestResearchAssistedDevelopment:
    def test_need_without_evidence_triggers_bounded_research(
        self, tmp_path, monkeypatch
    ):
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            need = _passing_need(
                evidence=(),
                research_question="Research the memory architecture.",
            )
            cycle = atlas.run_development_cycle(need)

            assert cycle.ok
            assert cycle.researched is True
            assert cycle.research_summary
            assert cycle.research_summary.get("status") in (
                "ok",
                "noop",
                "partial",
            )

            proposal = atlas._evolution_memory.get_proposal(cycle.proposal_id)
            assert "research" in proposal.metadata
            assert proposal.metadata["research"] == cycle.research_summary
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# Model independence
# ---------------------------------------------------------------------------


class TestModelIndependence:
    def test_full_lifecycle_runs_with_providers_and_network_blocked(
        self, tmp_path, monkeypatch
    ):
        atlas = _make_atlas(tmp_path, monkeypatch)
        calls = {"n": 0}

        def _boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("external provider/model was contacted")

        import atlas.ai.ai_service as ai_service

        monkeypatch.setattr(ai_service.AIService, "chat", _boom)
        monkeypatch.setattr(ai_service.AIService, "complete", _boom)
        try:
            import atlas.ai.router.ai_router as ai_router

            monkeypatch.setattr(ai_router.AIRouter, "chat", _boom)
            monkeypatch.setattr(ai_router.AIRouter, "complete", _boom)
        except Exception:  # pragma: no cover - optional module
            pass

        def _blocked_connect(*args, **kwargs):
            raise RuntimeError("network access attempted")

        monkeypatch.setattr(socket.socket, "connect", _blocked_connect)

        try:
            cycle = atlas.run_development_cycle(_passing_need())
            atlas.confirm_development_approval(
                atlas.session_context, cycle.proposal_id
            )
            result = atlas.run_development_execution(
                atlas.session_context, cycle.proposal_id
            )
            assert result.status == DevelopmentOutcomeStatus.SUCCESS
            assert result.verification.status == VerificationStatus.VERIFIED
            assert calls["n"] == 0
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# Relevant-test selection
# ---------------------------------------------------------------------------


class TestRelevantTestSelection:
    def test_selection_is_deterministic_and_bounded(self):
        available = [
            "tests/test_evolution_self_development_loop.py",
            "tests/test_other.py",
            "tests/test_evolution_foo.py",
        ]
        changed = ["atlas/evolution/self_development_loop.py"]
        first = select_relevant_tests(changed, available)
        assert first == ("tests/test_evolution_self_development_loop.py",)
        assert select_relevant_tests(changed, available) == first

    def test_unrelated_change_selects_nothing(self):
        assert select_relevant_tests(["atlas/zzz.py"], ["tests/test_other.py"]) == ()


# ---------------------------------------------------------------------------
# Phase 5 boundaries
# ---------------------------------------------------------------------------


class TestPhase5Boundaries:
    def test_no_live_apply_and_autonomy_disabled(self, tmp_path, monkeypatch):
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            store = atlas._schedule_store
            assert store is not None
            assert store.policy.enabled is False  # no autonomous execution

            head_before = _git_head()
            cycle = atlas.run_development_cycle(_passing_need())
            atlas.confirm_development_approval(
                atlas.session_context, cycle.proposal_id
            )
            atlas.run_development_execution(atlas.session_context, cycle.proposal_id)

            # No repository promotion/apply occurred.
            assert _git_head() == head_before
            assert not (_REPO_ROOT / "sandbox_mod.py").exists()
        finally:
            atlas.shutdown()
