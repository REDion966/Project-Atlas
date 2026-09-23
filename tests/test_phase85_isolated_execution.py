"""Phase 8.5 — Acquisition execution in isolation: evidence contract.

Investigation result: acquisition already runs inside the existing
sandbox/development machinery (``SelfDevelopmentLoop`` + ``CodeSandbox``), so no
unrestricted installer or code-execution mechanism was introduced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.evolution.autonomy.code_sandbox import (
    CodeChangeSet,
    CodeSandbox,
    SandboxPathError,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PASS_TEST = "def test_visible():\n    assert True\n"
_FAIL_TEST = "def test_visible():\n    assert False\n"


def _approved(test_body=_PASS_TEST):
    plan = ImprovementPlan(
        plan_id="IMP-P85",
        title="t",
        description="d",
        priority=ImprovementPriority.MEDIUM,
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-P85",
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
            "code_changes": [{"path": "atlas/example/widget.py", "content": "V = 1\n"}],
            "test_files": {"tests/test_widget.py": test_body},
        },
    )


class TestPhase85IsolatedExecution:
    def test_acquisition_runs_inside_the_sandbox_not_production(self):
        result = SelfDevelopmentLoop().run(_approved(), max_iterations=1)
        assert result.status is DevelopmentOutcomeStatus.SUCCESS
        assert result.outcomes[0].changed_files == ["atlas/example/widget.py"]
        # The acquisition workload never reached the live repository.
        assert not (_REPO_ROOT / "atlas/example/widget.py").exists()

    def test_escaping_paths_are_rejected(self):
        with pytest.raises(SandboxPathError):
            CodeChangeSet.from_payload(
                {"code_changes": [{"path": "../evil.py", "content": "x"}]}
            )

    def test_sandbox_is_disposable(self, tmp_path):
        sandbox = CodeSandbox(base_dir=tmp_path)
        root = sandbox.root
        sandbox.write_text("a.txt", "x")
        assert root.exists()
        sandbox.cleanup()
        assert not root.exists()

    def test_failed_acquisition_does_not_promote(self):
        result = SelfDevelopmentLoop().run(
            _approved(test_body=_FAIL_TEST), max_iterations=1
        )
        assert result.status is not DevelopmentOutcomeStatus.SUCCESS
        assert not (_REPO_ROOT / "atlas/example/widget.py").exists()
