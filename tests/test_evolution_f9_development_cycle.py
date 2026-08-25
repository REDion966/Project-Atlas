"""Atlas Post-Core F9 - Governed Development Cycle tests.

Covers:
  * successful deterministic preparation -> DRAFT EvolutionProposal
  * ApprovalManager reached; controller STOPS at the approval boundary
  * NO automatic approval / authorization / execution / promotion
  * model=None path works (deterministic supplier; no atlas.ai imports)
  * bounded code_changes / test_files; fail-closed bounds
  * insufficient evidence -> single bounded F8 acquisition path
  * F8 failure / supplier failure -> fail closed
  * no recursive invocation, no daemon/thread/async loop
  * governance boundary intact; kernel bridge works; Atlas.tick() untouched

Pure verification. No live network. No repository mutation.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas.evolution.development_cycle import DevelopmentNeed
from tests.test_durable_guided_improvement import _storage_class


@pytest.fixture(autouse=True)
def _isolated_evolution_storage(monkeypatch, tmp_path):
    """Kernel-starting F9 bridge tests must not touch the operator DB."""
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage",
        _storage_class(tmp_path),
    )

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    ChangeSupplier,
    DeterministicChangeSupplier,
    DevelopmentCycleController,
    DevelopmentCyclePolicy,
    DevelopmentCycleResult,
    DevelopmentNeed,
    SuppliedChanges,
)
from atlas.evolution.models import ProposalStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]


def make_need(**overrides) -> DevelopmentNeed:
    """A minimal valid need with direct evidence and deterministic payload."""
    base = dict(
        title="Improve research source bounds",
        summary="Tighten the bounded source resolution path.",
        rationale="F2 flagged stale provenance on the source catalog.",
        expected_benefit="Fewer malformed sources reach extraction.",
        target_components=("atlas/research/source_catalog.py",),
        candidate_id="CAND-F9-001",
        evidence_change_ids=("CHG-1",),
        metadata={
            "code_changes": [
                {
                    "path": "atlas/research/source_catalog.py",
                    "content": "# tightened bounds\n",
                }
            ],
            "test_files": {
                "tests/test_source_bounds.py": "def test_bounds():\n    assert True\n"
            },
        },
    )
    base.update(overrides)
    return DevelopmentNeed(**base)


def make_controller(researcher=None, supplier=None) -> DevelopmentCycleController:
    return DevelopmentCycleController(
        approval_manager=ApprovalManager(),
        change_supplier=supplier,
        researcher=researcher,
    )


class SpyApprovalManager(ApprovalManager):
    """ApprovalManager that records which lifecycle methods are invoked."""

    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    def create_approval_request(self, proposal):
        self.calls.append("create_approval_request")
        return super().create_approval_request(proposal)

    def approve(self, request, comment=""):
        self.calls.append("approve")
        return super().approve(request, comment)

    def reject(self, request, comment=""):
        self.calls.append("reject")
        return super().reject(request, comment)


class RecordingApprovalManager(ApprovalManager):
    """ApprovalManager that records calls AND retains the submitted proposal."""

    def __init__(self):
        super().__init__()
        self.calls: list[str] = []
        self.last_proposal = None

    def create_approval_request(self, proposal):
        self.calls.append("create_approval_request")
        self.last_proposal = proposal
        return super().create_approval_request(proposal)

    def approve(self, request, comment=""):
        self.calls.append("approve")
        return super().approve(request, comment)

    def reject(self, request, comment=""):
        self.calls.append("reject")
        return super().reject(request, comment)


class TestSuccessfulPreparation:
    def test_deterministic_preparation_reaches_approval(self):
        spy = RecordingApprovalManager()
        controller = DevelopmentCycleController(approval_manager=spy)
        result = controller.run_development_cycle(make_need())

        assert result.ok
        assert result.decision == "prepared"
        assert result.proposal_status == "PENDING_APPROVAL"
        assert result.approval_request_id.startswith("APPR-")
        # ApprovalManager reached exactly once, via the submission surface.
        assert spy.calls == ["create_approval_request"]

    def test_draft_proposal_shape_and_provenance(self):
        spy = RecordingApprovalManager()
        controller = DevelopmentCycleController(approval_manager=spy)
        result = controller.run_development_cycle(make_need())
        assert result.ok

        proposal = spy.last_proposal
        assert result.proposal_id.startswith("DEV-")
        assert proposal.proposal_id == result.proposal_id
        assert proposal.status is ProposalStatus.PENDING_APPROVAL
        assert not result.researched  # direct evidence present -> no research
        assert result.research_summary == {}
        provenance = proposal.metadata["development_cycle"]
        assert provenance["candidate_id"] == "CAND-F9-001"
        assert provenance["change_origin"] == "deterministic"
        assert provenance["content_status"] == "unverified-draft"
        assert provenance["generated_by"] == "F9-development-cycle"

    def test_model_none_path_works(self):
        # No model anywhere: default deterministic supplier + no researcher.
        controller = DevelopmentCycleController(
            approval_manager=ApprovalManager(), researcher=None
        )
        result = controller.run_development_cycle(make_need())
        assert result.ok
        assert isinstance(controller._change_supplier, DeterministicChangeSupplier)


class TestGovernanceBoundary:
    def test_controller_stops_at_approval_no_auto_approve(self):
        spy = RecordingApprovalManager()
        controller = DevelopmentCycleController(approval_manager=spy)
        result = controller.run_development_cycle(make_need())

        assert result.ok
        # Only submission happened; NO approve/reject was invoked by F9.
        assert "approve" not in spy.calls
        assert "reject" not in spy.calls
        assert result.proposal_status == "PENDING_APPROVAL"

    def test_invalid_need_never_reaches_approval(self):
        spy = RecordingApprovalManager()
        controller = DevelopmentCycleController(approval_manager=spy)
        result = controller.run_development_cycle(make_need(title="   "))
        assert not result.ok
        assert spy.calls == []


_FORBIDDEN_F9_MODULES = (
    "atlas.ai",
    "atlas.evolution.autonomy",
    "atlas.research",
    "atlas.evolution.execution_gateway",
    "atlas.evolution.self_development_loop",
    "subprocess",
    "threading",
    "multiprocessing",
    "asyncio",
)

_FORBIDDEN_F9_CALLS = (
    "approve",
    "reject",
    "authorize",
    "execute_request",
    "apply",
    "promote",
)


class TestArchitecturalGuards:
    def _tree(self):
        source = (_REPO_ROOT / "atlas/evolution/development_cycle.py").read_text(
            encoding="utf-8"
        )
        return ast.parse(source, filename="development_cycle.py")

    def test_no_forbidden_imports(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == p or alias.name.startswith(p + ".")
                        for p in _FORBIDDEN_F9_MODULES
                    ), f"F9 imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    node.module == p or node.module.startswith(p + ".")
                    for p in _FORBIDDEN_F9_MODULES
                ), f"F9 imports {node.module}"

    def test_no_governance_or_execution_calls(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", getattr(func, "id", ""))
                assert (
                    name not in _FORBIDDEN_F9_CALLS
                ), f"F9 calls {name}() directly"

    def test_no_thread_daemon_or_async_constructs(self):
        src = inspect.getsource(
            __import__(
                "atlas.evolution.development_cycle", fromlist=["x"]
            )
        )
        for forbidden in ("Thread(", "daemon", "async def", "asyncio.run", "Timer("):
            assert forbidden not in src, f"F9 uses {forbidden}"


class TestKernelBridge:
    def test_bridge_preparation_and_tick_untouched(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        assert "run_development_cycle" not in tick_src

        atlas = Atlas()
        try:
            atlas.start()
            result = atlas.run_development_cycle(make_need())
            assert result is not None
            assert result.ok
            assert result.decision == "prepared"
            assert result.proposal_status == "PENDING_APPROVAL"
            assert atlas.development_controller is not None
        finally:
            atlas.shutdown()
        assert atlas.development_controller is None

    def test_bridge_fail_closed_before_start(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        with pytest.raises(RuntimeError):
            atlas.run_development_cycle(make_need())


class TestInsufficientEvidenceResearchPath:
    def test_insufficient_evidence_invokes_f8_once(self):
        calls: list[dict] = []

        class FakeAcquisition:
            status = "ok"

            def to_dict(self):
                return {
                    "acquisition_id": "ACQ-000001",
                    "status": "ok",
                    "report_id": "report:r1",
                    "sources": ("https://example.test/a",),
                    "confidence": 0.8,
                    "claim_count": 2,
                }

        def researcher(**kwargs):
            calls.append(kwargs)
            return FakeAcquisition()

        need = make_need(
            evidence_change_ids=(),
            evidence_knowledge_ids=(),
            research_question="how do bounded sources work?",
        )
        controller = make_controller(researcher=researcher)
        result = controller.run_development_cycle(need)

        assert result.ok
        assert result.researched is True
        assert len(calls) == 1  # exactly ONE acquisition invocation
        assert calls[0]["question"] == "how do bounded sources work?"
        assert result.research_summary["report_id"] == "report:r1"

    def test_sufficient_evidence_skips_research(self):
        researcher = MagicMock()
        controller = make_controller(researcher=researcher)
        result = controller.run_development_cycle(make_need())

        assert result.ok
        researcher.assert_not_called()


class TestFailClosed:
    def test_f8_failure_fails_closed(self):
        class FailedAcquisition:
            status = "failed"
            failures = (("research", "network unreachable"),)

        controller = make_controller(researcher=lambda **kw: FailedAcquisition())
        need = make_need(evidence_change_ids=(), evidence_knowledge_ids=())
        result = controller.run_development_cycle(need)

        assert not result.ok
        assert result.decision == "failed"
        assert any(stage == "research" for stage, _ in result.failures)
        assert result.proposal_id == ""

    def test_researcher_exception_fails_closed(self):
        def boom(**kwargs):
            raise RuntimeError("research exploded")

        need = make_need(evidence_change_ids=(), evidence_knowledge_ids=())
        result = make_controller(researcher=boom).run_development_cycle(need)
        assert not result.ok
        assert any(stage == "research" for stage, _ in result.failures)

    def test_missing_researcher_fails_closed(self):
        need = make_need(evidence_change_ids=(), evidence_knowledge_ids=())
        result = make_controller(researcher=None).run_development_cycle(need)

        assert not result.ok
        assert any(
            "researcher" in message for _, message in result.failures
        )

    def test_supplier_none_fails_closed(self):
        class EmptySupplier:
            def supply_changes(self, need):
                return None

        result = make_controller(supplier=EmptySupplier()).run_development_cycle(
            make_need()
        )
        assert not result.ok
        assert any(stage == "supplier" for stage, _ in result.failures)

    def test_supplier_exception_fails_closed(self):
        class BrokenSupplier:
            def supply_changes(self, need):
                raise RuntimeError("supplier exploded")

        result = make_controller(supplier=BrokenSupplier()).run_development_cycle(
            make_need()
        )
        assert not result.ok
        assert any(stage == "supplier" for stage, _ in result.failures)

    def test_oversize_content_fails_closed(self):
        big_need = make_need(
            metadata={
                # > max_content_chars (32_000) -> bounds failure, fail-closed.
                "code_changes": [{"path": "a.py", "content": "x" * 40_000}],
            },
        )
        result = make_controller().run_development_cycle(big_need)
        assert not result.ok
        assert any(stage == "bounds" for stage, _ in result.failures)


class TestBoundsAndIteration:
    def test_code_changes_bounded_by_policy(self):
        payload = {
            "code_changes": [
                {"path": f"f{i}.py", "content": "# c"} for i in range(20)
            ],
        }
        policy = DevelopmentCyclePolicy(max_code_changes=3)
        spy = RecordingApprovalManager()
        controller = DevelopmentCycleController(approval_manager=spy, policy=policy)
        result = controller.run_development_cycle(make_need(metadata=payload))

        assert result.ok
        assert len(spy.last_proposal.metadata["code_changes"]) <= 3

    def test_test_files_bounded_by_policy(self):
        tests = {f"tests/t{i}.py": "def test_x():\n    pass\n" for i in range(10)}
        payload = {
            "code_changes": [{"path": "m.py", "content": "# c"}],
            "test_files": tests,
        }
        policy = DevelopmentCyclePolicy(max_test_files=2)
        spy = RecordingApprovalManager()
        controller = DevelopmentCycleController(approval_manager=spy, policy=policy)
        result = controller.run_development_cycle(make_need(metadata=payload))

        assert result.ok
        assert len(spy.last_proposal.metadata["test_files"]) <= 2

    def test_no_recursive_invocation_one_call_per_cycle(self):
        calls: list[int] = []

        def researcher(**kwargs):
            calls.append(1)
            return None

        need = make_need(evidence_change_ids=(), evidence_knowledge_ids=())
        controller = make_controller(researcher=researcher)
        first = controller.run_development_cycle(need)
        second = controller.run_development_cycle(need)

        # Each explicit invocation performs at most ONE research call; two
        # invocations never recurse into each other or spawn extra work.
        assert len(calls) == 2
        assert not first.ok and not second.ok  # fake researcher returns None
        assert first.cycle_id != second.cycle_id