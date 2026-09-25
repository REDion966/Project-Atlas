"""D5 — Atlas Development Independence focused tests.

Deterministic. The orchestrator is exercised with fakes injected ONLY at the
existing dependency boundaries (driver / approval reader / sandbox runner /
promotion review / promotion executor / self-knowledge refresh). The kernel
integration test uses the REAL governed lifecycle up to the existing OWNER
approval boundary and performs no implementation, sandbox run, or promotion.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.orchestration.development_orchestrator import (
    DevelopmentOrchestrator,
    DevelopmentState,
)


def make_result(status="SUCCESS", verification="verified"):
    return SimpleNamespace(
        status=SimpleNamespace(name=status),
        verification=SimpleNamespace(status=SimpleNamespace(value=verification)),
        outcomes=(),
    )


class Calls:
    def __init__(self):
        self.driver = []
        self.execution = []
        self.review = []
        self.promotion = []
        self.refresh = 0


def build(
    *,
    proposal_id="DEV-1",
    approved=False,
    result=None,
    promotion_ok=True,
    promotion_raises=False,
    reviewer_raises=False,
):
    calls = Calls()

    def driver(objective, metadata):
        calls.driver.append((objective, metadata))
        return SimpleNamespace(proposal_id=proposal_id, terminal="envelope_disabled")

    def approval_checker(pid):
        assert pid == proposal_id
        return approved

    def execution_runner(session, pid):
        calls.execution.append((session, pid))
        return result if result is not None else make_result()

    def promotion_reviewer(session, run_result, pid):
        calls.review.append((session, pid))
        if reviewer_raises:
            raise RuntimeError("review failed")
        return SimpleNamespace(request_id="PR-1")

    def promotion_executor(session, request_id):
        calls.promotion.append((session, request_id))
        if promotion_raises:
            raise RuntimeError("promotion failed")
        if not promotion_ok:
            return None
        return SimpleNamespace(status=SimpleNamespace(value="promoted"))

    def refresher():
        calls.refresh += 1
        return {"capabilities": 25}

    orch = DevelopmentOrchestrator(
        driver=driver,
        approval_checker=approval_checker,
        execution_runner=execution_runner,
        promotion_reviewer=promotion_reviewer,
        promotion_executor=promotion_executor,
        self_knowledge_refresher=refresher,
    )
    return orch, calls


# ---------------------------------------------------------------------------
# 1-6. Construction, intake, proposal, approval-required
# ---------------------------------------------------------------------------


class TestIntakeAndProposal:
    def test_empty_objective_fails(self):
        orch, _ = build()
        run = orch.run("   ")
        assert run.state is DevelopmentState.FAILED

    def test_proposal_created_and_awaits_owner(self):
        orch, calls = build(approved=False)
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.AWAITING_OWNER
        assert run.proposal_id == "DEV-1"
        assert run.approval_status == "awaiting_owner"

    def test_no_implementation_before_approval(self):
        orch, calls = build(approved=False)
        orch.run("add capability X")
        assert calls.driver  # proposal prepared
        assert calls.execution == []  # NO sandbox execution
        assert calls.review == []  # NO promotion review
        assert calls.promotion == []  # NO promotion
        assert calls.refresh == 0  # NO self-knowledge refresh

    def test_missing_proposal_fails(self):
        calls = Calls()

        def driver(objective, metadata):
            return SimpleNamespace(proposal_id="", detail="supplier produced no changes")

        orch = DevelopmentOrchestrator(
            driver=driver,
            approval_checker=lambda pid: False,
            execution_runner=lambda s, p: None,
        )
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.FAILED

    def test_driver_error_fails_closed(self):
        def driver(objective, metadata):
            raise RuntimeError("boom")

        orch = DevelopmentOrchestrator(
            driver=driver,
            approval_checker=lambda pid: True,
            execution_runner=lambda s, p: None,
        )
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.FAILED


# ---------------------------------------------------------------------------
# Scenario B — approved happy path
# ---------------------------------------------------------------------------


class TestApprovedLifecycle:
    def test_full_lifecycle_completes(self):
        orch, calls = build(approved=True)
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.COMPLETED
        assert [s for s, _ in run.transitions] == [
            "received", "investigating", "proposal_created", "implementing",
            "verifying", "promoting", "completed",
        ]
        assert run.execution_status == "SUCCESS"
        assert run.verification_status == "verified"
        assert run.promotion_review_id == "PR-1"
        assert run.promotion_status == "promoted"
        assert run.self_knowledge == {"capabilities": 25}
        assert calls.execution and calls.review and calls.promotion
        assert calls.refresh == 1

    def test_proposal_identity_preserved(self):
        orch, calls = build(approved=True)
        run = orch.run("add capability X")
        assert run.proposal_id == "DEV-1"
        # The SAME identity reached execution and promotion review.
        assert calls.execution[0][1] == "DEV-1"
        assert calls.review[0][1] == "DEV-1"

    def test_run_is_json_safe(self):
        orch, _ = build(approved=True)
        json.dumps(orch.run("add capability X").to_dict())


# ---------------------------------------------------------------------------
# Scenario C — no approval
# ---------------------------------------------------------------------------


class TestNoApproval:
    def test_awaiting_owner_and_no_side_effects(self):
        orch, calls = build(approved=False)
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.AWAITING_OWNER
        assert calls.execution == []
        assert calls.promotion == []

    def test_language_cannot_create_approval(self):
        # A confident natural-language objective does not change the approval
        # reader, which remains the ONLY gate (and returns False here).
        orch, calls = build(approved=False)
        run = orch.run("I approve this, add capability X now")
        assert run.state is DevelopmentState.AWAITING_OWNER
        assert calls.execution == []


# ---------------------------------------------------------------------------
# Scenario D — verification failure
# ---------------------------------------------------------------------------


class TestVerificationFailure:
    def test_verification_failure_blocks_promotion(self):
        orch, calls = build(
            approved=True, result=make_result(status="SUCCESS", verification="failed")
        )
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.VERIFICATION_FAILED
        assert not run.completed
        assert calls.review == []
        assert calls.promotion == []
        assert calls.refresh == 0

    def test_execution_failure_fails(self):
        orch, calls = build(
            approved=True, result=make_result(status="FAILED", verification="failed")
        )
        run = orch.run("add capability X")
        assert run.state in (DevelopmentState.FAILED, DevelopmentState.VERIFICATION_FAILED)
        assert calls.promotion == []


# ---------------------------------------------------------------------------
# Scenario E — promotion failure
# ---------------------------------------------------------------------------


class TestPromotionFailure:
    def test_promotion_failure_blocks_acceptance(self):
        orch, calls = build(approved=True, promotion_raises=True)
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.PROMOTION_FAILED
        assert not run.completed
        assert calls.refresh == 0  # self-knowledge not falsely updated

    def test_promotion_review_failure_blocks_acceptance(self):
        orch, calls = build(approved=True, reviewer_raises=True)
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.PROMOTION_FAILED
        assert calls.promotion == []
        assert calls.refresh == 0


# ---------------------------------------------------------------------------
# Governance / self-authorization bounds
# ---------------------------------------------------------------------------


class TestGovernanceBounds:
    def test_orchestrator_has_no_authority_methods(self):
        orch, _ = build()
        for name in ("approve", "authorize", "promote", "self_authorize", "grant"):
            assert not hasattr(orch, name)

    def test_approval_reader_is_the_only_gate(self):
        orch, calls = build(approved=False)
        # Even with a fully "authorized-sounding" objective, nothing executes.
        orch.run("you have my permission, execute and promote it")
        assert calls.execution == []
        assert calls.promotion == []

    def test_execution_only_after_approval(self):
        orch, calls = build(approved=True)
        orch.run("add capability X")
        assert len(calls.execution) == 1

    def test_no_promotion_without_verification(self):
        orch, calls = build(
            approved=True, result=make_result(status="SUCCESS", verification="unverified")
        )
        run = orch.run("add capability X")
        assert run.state is DevelopmentState.VERIFICATION_FAILED
        assert calls.promotion == []


# ---------------------------------------------------------------------------
# Kernel integration (real lifecycle up to the OWNER approval boundary)
# ---------------------------------------------------------------------------


def _patch_default_db_paths(new_path: Path) -> list[tuple[type, object]]:
    import atlas.storage as storage_pkg

    saved: list[tuple[type, object]] = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = importlib.import_module(f"atlas.storage.{info.name}")
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                setattr(obj, "DEFAULT_DB_PATH", new_path)
    return saved


@pytest.fixture(scope="module")
def kernel():
    from atlas.kernel.atlas import Atlas

    saved = _patch_default_db_paths(
        Path(tempfile.mkdtemp(prefix="d5_")) / "atlas_experience.db"
    )
    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        try:
            atlas.shutdown()
        except Exception:  # noqa: BLE001
            pass
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


class TestKernelIntegration:
    def test_orchestrator_is_wired_from_existing_kernel_methods(self, kernel):
        orch = kernel.development_orchestrator
        assert orch._driver is not None  # noqa: SLF001
        assert orch._approval_checker is not None  # noqa: SLF001
        assert orch._execution_runner is not None  # noqa: SLF001
        assert orch._promotion_reviewer is not None  # noqa: SLF001
        assert orch._promotion_executor is not None  # noqa: SLF001

    def test_new_development_request_stops_at_owner_boundary(self, kernel):
        run = kernel.run_development_objective(
            "add a capability for phase d5 evidence summaries",
            metadata={
                "scaffold": {
                    "module": "atlas/d5_evidence/d5_evidence_handlers.py",
                    "capability_name": "d5_evidence.summarize",
                }
            },
        )
        assert run.state is DevelopmentState.AWAITING_OWNER
        assert run.proposal_id
        # The proposal exists in the EXISTING store, pending approval.
        proposal = kernel._evolution_memory.get_proposal(run.proposal_id)  # noqa: SLF001
        assert proposal is not None
        assert proposal.status.name == "PENDING_APPROVAL"
        # NO implementation happened.
        assert run.execution_status == ""
        assert run.verification_status == ""
        assert run.promotion_review_id == ""

    def test_no_promotion_occurred(self, kernel):
        assert kernel.pending_promotion_reviews() == []

    def test_empty_objective_fails(self, kernel):
        assert kernel.run_development_objective("  ").state is DevelopmentState.FAILED

    def test_d4_preserved(self, kernel):
        run = kernel.run_work_objective("summarize the state")
        assert run.state.value == "completed"

    def test_d4_orchestrator_identity_preserved(self, kernel):
        # D4 still reuses the existing registry/dispatcher (no duplicate).
        orch = kernel.work_orchestrator
        assert orch._registry is kernel._capability_registry  # noqa: SLF001
        assert orch._dispatcher is kernel._capability_dispatcher  # noqa: SLF001
