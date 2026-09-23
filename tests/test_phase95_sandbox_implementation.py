"""Phase 9.5 — Atlas-owned sandbox implementation: evidence contract.

Investigation result: Atlas already applies its own ``CodeChangeSet`` inside a
disposable, path-confined ``CodeSandbox`` via ``SandboxImplementer`` /
``CodeApplier`` (with read-back verification) — no external coding agent.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.evolution.autonomy.code_sandbox import (
    CodeChangeSet,
    CodeSandbox,
    SandboxPathError,
)
from atlas.evolution.development_models import (
    DevelopmentOutcomeStatus,
    SandboxWorkload,
)
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import (
    SandboxImplementer,
    SelfDevelopmentLoop,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _workload():
    return SandboxWorkload(
        code_changes=({"path": "atlas/example/x.py", "content": "VALUE = 1\n"},)
    )


def _approved_proposal():
    plan = ImprovementPlan(
        plan_id="IMP-P95",
        title="t",
        description="d",
        priority=ImprovementPriority.MEDIUM,
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-P95",
        title="t",
        summary="s",
        rationale="r",
        expected_benefit="b",
        risks="low",
        impact_analysis="x",
        implementation_approach="y",
        plan=plan,
        status=ProposalStatus.APPROVED,
        metadata={
            "code_changes": [{"path": "atlas/example/x.py", "content": "VALUE = 1\n"}],
            "test_files": {"tests/test_x.py": "def test_ok():\n    assert True\n"},
        },
    )


class TestPhase95SandboxImplementation:
    def test_change_set_applies_inside_a_disposable_sandbox(self, tmp_path):
        sandbox = CodeSandbox(base_dir=tmp_path)
        try:
            success, changed, message = SandboxImplementer().apply(
                sandbox, SimpleNamespace(proposal_id="P"), _workload(), 1
            )
            assert success is True
            assert changed == ["atlas/example/x.py"]
            # Read-back verification: the sandbox holds exactly the change.
            assert sandbox.read_text("atlas/example/x.py") == "VALUE = 1\n"
        finally:
            sandbox.cleanup()

    def test_path_escape_is_rejected(self):
        with pytest.raises(SandboxPathError):
            CodeChangeSet.from_payload(
                {"code_changes": [{"path": "../evil.py", "content": "x"}]}
            )

    def test_sandbox_is_disposable(self, tmp_path):
        sandbox = CodeSandbox(base_dir=tmp_path)
        root = sandbox.root
        sandbox.write_text("a.txt", "x")
        sandbox.cleanup()
        assert not root.exists()

    def test_production_is_never_written(self):
        SelfDevelopmentLoop().run(_approved_proposal(), max_iterations=1)
        assert not (_REPO_ROOT / "atlas/example/x.py").exists()
