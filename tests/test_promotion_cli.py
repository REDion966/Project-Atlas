"""Stage H — promotion review visibility CLI tests.

Covers the read-only ``atlas promotion pending`` operator surface:

  * the presentation command over an empty vs. seeded pending queue,
  * parser registration end-to-end through ``main()``,
  * the governance boundary (no approve/reject/promote/execute call and
    no forbidden import).

Presentation-only. No network. No repository mutation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from atlas.cli.promotion_commands import cmd_promotion_pending, cmd_promotion_show


_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_evolution_storage(monkeypatch, tmp_path):
    """Redirect evolution persistence away from the operator database.

    The promotion view reads the kernel-owned EvolutionMemory, which is
    restored from SQLiteEvolutionStorage. Without this fixture the parser
    test would observe real pending reviews in the operator DB.
    """
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage",
        TmpSQLiteEvolutionStorage,
    )


def _fake_atlas(pending):
    return SimpleNamespace(pending_promotion_reviews=lambda: pending)


def _fake_atlas_show(detail, found=True):
    return SimpleNamespace(
        pending_promotion_reviews=lambda: [],
        promotion_review_details=lambda request_id: (
            detail if found else None
        ),
    )


def _args(**overrides):
    base = {"action": "pending", "request_id": ""}
    base.update(overrides)
    return SimpleNamespace(**base)


class TestPromotionPendingCommand:
    def test_empty_queue(self):
        out = cmd_promotion_pending(_fake_atlas([]), _args())
        assert out == "No promotion reviews pending."

    def test_pending_reviews_rendered(self):
        atlas = _fake_atlas(
            [
                {
                    "request_id": "PROM-1",
                    "proposal_id": "PROP-A",
                    "status": "pending_review",
                    "risk_level": "high",
                    "recommendation": "needs_review",
                    "final_priority_score": 0.75,
                    "evidence_complete": True,
                    "manifest_file_count": 2,
                }
            ]
        )
        out = cmd_promotion_pending(atlas, _args())
        assert "1 promotion review(s) pending" in out
        assert "[PROM-1] PROP-A" in out
        assert "risk=high" in out
        assert "score=0.75" in out
        assert "evidence=complete" in out
        assert "files=2" in out

    def test_missing_score_renders_dash(self):
        atlas = _fake_atlas(
            [
                {
                    "request_id": "PROM-2",
                    "proposal_id": "PROP-B",
                    "status": "pending_review",
                    "risk_level": "low",
                    "recommendation": "ready_for_promotion",
                    "final_priority_score": None,
                    "evidence_complete": False,
                    "manifest_file_count": 0,
                }
            ]
        )
        out = cmd_promotion_pending(atlas, _args())
        assert "score=-" in out
        assert "evidence=incomplete" in out


class TestPromotionShowCommand:
    def test_show_renders_full_detail(self):
        atlas = _fake_atlas_show(
            {
                "request_id": "PROM-1",
                "proposal_id": "PROP-A",
                "status": "pending_review",
                "risk_level": "medium",
                "recommendation": "needs_review",
                "created_at": "2026-08-27T00:00:00",
                "decided_at": "",
                "decision_comment": "",
                "evidence_complete": True,
                "manifest_file_count": 1,
                "verification_status": "passed",
                "test_summary": "3 passed",
                "changed_files": ["pkg/a.py"],
                "change_manifest": {
                    "files": [
                        {"path": "pkg/a.py", "size": 5, "excerpt": "A"}
                    ],
                    "truncated": False,
                },
            }
        )
        out = cmd_promotion_show(atlas, _args(action="show", request_id="PROM-1"))
        assert "Promotion request: PROM-1" in out
        assert "proposal_id:       PROP-A" in out
        assert "status:            pending_review" in out
        assert "risk_level:        medium" in out
        assert "recommendation:    needs_review" in out
        assert "evidence:          complete (1 file(s))" in out
        assert "verification:      passed" in out
        assert "test_summary:      3 passed" in out
        assert "pkg/a.py (5 bytes)" in out
        assert "excerpt:        A" in out or "A" in out

    def test_unknown_request_id(self):
        atlas = _fake_atlas_show({}, found=False)
        out = cmd_promotion_show(atlas, _args(action="show", request_id="PROM-X"))
        assert out == "Promotion request 'PROM-X' not found."

    def test_missing_request_id(self):
        atlas = _fake_atlas_show({})
        out = cmd_promotion_show(atlas, _args(action="show", request_id=""))
        assert out == "error: promotion show requires a request_id"

    def test_empty_evidence_renders_dashes(self):
        atlas = _fake_atlas_show(
            {
                "request_id": "PROM-2",
                "proposal_id": "",
                "status": "pending_review",
                "risk_level": "",
                "recommendation": "",
                "created_at": "",
                "decided_at": "",
                "decision_comment": "",
                "evidence_complete": False,
                "manifest_file_count": 0,
                "verification_status": "",
                "test_summary": "",
                "changed_files": [],
                "change_manifest": {"files": [], "truncated": False},
            }
        )
        out = cmd_promotion_show(atlas, _args(action="show", request_id="PROM-2"))
        assert "proposal_id:       -" in out
        assert "evidence:          incomplete (0 file(s))" in out
        assert "verification:      -" in out


class TestParserRegistration:
    def test_promotion_group_reachable_via_main(self, monkeypatch, capsys):
        """`atlas promotion pending` is registered and dispatches
        end-to-end without network or repository mutation."""
        from atlas.cli import main as cli_main

        monkeypatch.setattr(
            "atlas.cli.main.load_workspace_service", lambda: MagicMock()
        )
        monkeypatch.setattr("sys.argv", ["atlas", "promotion", "pending"])
        cli_main.main()
        out = capsys.readouterr().out
        # Atlas boots against a fresh in-memory evolution store; the view
        # is empty unless the operator DB already holds pending reviews.
        assert "No promotion reviews pending." in out

    def test_promotion_show_unknown_registered_via_main(
        self, monkeypatch, capsys
    ):
        """`atlas promotion show <unknown>` is registered and dispatches
        end-to-end, reporting the request as not found (read-only)."""
        from atlas.cli import main as cli_main

        monkeypatch.setattr(
            "atlas.cli.main.load_workspace_service", lambda: MagicMock()
        )
        monkeypatch.setattr(
            "sys.argv",
            ["atlas", "promotion", "show", "PROM-DOES-NOT-EXIST"],
        )
        cli_main.main()
        out = capsys.readouterr().out
        # Atlas boots against a fresh in-memory evolution store, so the
        # request cannot exist; the command fails soft, never resolves.
        assert "not found" in out


_FORBIDDEN_CLI_MODULES = (
    "atlas.ai",
    "subprocess",
    "threading",
    "multiprocessing",
    "asyncio",
    "atlas.evolution.autonomy",
    "atlas.evolution.execution_gateway",
)

_FORBIDDEN_CLI_CALLS = (
    "approve",
    "reject",
    "promote",
    "execute",
    "apply",
    "schedule_request",
    "authorize",
    "execute_request",
)


class TestGovernanceBoundary:
    def _tree(self):
        source = (
            _REPO_ROOT / "atlas/cli/promotion_commands.py"
        ).read_text(encoding="utf-8")
        return ast.parse(source, filename="promotion_commands.py")

    def test_no_forbidden_imports(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == p or alias.name.startswith(p + ".")
                        for p in _FORBIDDEN_CLI_MODULES
                    ), f"CLI imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    node.module == p or node.module.startswith(p + ".")
                    for p in _FORBIDDEN_CLI_MODULES
                ), f"CLI imports {node.module}"

    def test_no_governance_or_execution_calls(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", getattr(func, "id", ""))
                assert name not in _FORBIDDEN_CLI_CALLS, f"CLI calls {name}()"
