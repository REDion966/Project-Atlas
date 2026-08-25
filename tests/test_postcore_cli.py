"""Operational Maturity track — T1 operator CLI tests.

Covers:
  * parser registration (`atlas postcore ...` reachable through main());
  * operate / research / develop / review presentation commands over a
    started Atlas;
  * develop reaching PENDING_APPROVAL and STOPPING there;
  * malformed / missing need input failing closed;
  * SAFE_MODE surfaced clearly;
  * governance boundary: the CLI module never authorizes, executes,
    schedules, promotes, or imports execution machinery.

Pure verification. No live network. No repository mutation.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from atlas.cli.postcore_commands import (
    _load_need,
    _safe_mode_line,
    cmd_develop,
    cmd_operate,
    cmd_research,
    cmd_review,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _need_file(tmp_path: Path, payload: dict) -> str:
    path = tmp_path / "need.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _args(**overrides):
    base = {
        "action": "develop",
        "question": "",
        "sources": [],
        "query_id": "",
        "need_file": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestParserRegistration:
    def test_postcore_group_reachable_via_main(self, monkeypatch, capsys, tmp_path):
        """`atlas postcore ...` is registered and dispatches end-to-end."""
        from atlas.cli import main as cli_main

        monkeypatch.setattr(
            "atlas.cli.main.load_workspace_service", lambda: MagicMock()
        )
        monkeypatch.setattr(
            "sys.argv",
            ["atlas", "postcore", "research", "--question", "registration q"],
        )
        cli_main.main()
        out = capsys.readouterr().out
        assert "Acquisition complete" in out


class TestOperateAndResearch:
    def test_operate_runs_bounded_cycle(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            out = cmd_operate(atlas, _args(action="operate"))
            assert "Operation cycle complete" in out
            assert "Decision:" in out
        finally:
            atlas.shutdown()

    def test_research_requires_question(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            out = cmd_research(atlas, _args(action="research"))
            assert out.startswith("error:")
        finally:
            atlas.shutdown()

    def test_research_reports_decision(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            args = _args(
                action="research",
                question="bounded research sources",
                query_id="cli-f10-1",
            )
            out = cmd_research(atlas, args)
            assert "Acquisition complete" in out
            assert "Decision:" in out
        finally:
            atlas.shutdown()


class TestDevelop:
    def test_develop_reaches_pending_approval(self, tmp_path):
        from atlas.kernel.atlas import Atlas

        need_file = _need_file(
            tmp_path,
            {
                "title": "CLI develop need",
                "summary": "Operator-driven preparation.",
                "candidate_id": "CAND-CLI-1",
                "code_changes": [
                    {"path": "docs/cli_note.md", "content": "# note\n"}
                ],
            },
        )
        atlas = Atlas()
        try:
            atlas.start()
            out = cmd_develop(atlas, _args(need_file=need_file))
            assert "Development proposal prepared" in out
            assert "PENDING_APPROVAL" in out
            assert "STOPPED at the human approval boundary" in out
        finally:
            atlas.shutdown()

    def test_malformed_json_fails_closed(self, tmp_path):
        from atlas.kernel.atlas import Atlas

        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        atlas = Atlas()
        try:
            atlas.start()
            out = cmd_develop(atlas, _args(need_file=str(bad)))
            assert out.startswith("error: malformed need JSON")
        finally:
            atlas.shutdown()

    def test_missing_title_fails_closed(self, tmp_path):
        from atlas.kernel.atlas import Atlas

        need_file = _need_file(tmp_path, {"summary": "no title"})
        atlas = Atlas()
        try:
            atlas.start()
            out = cmd_develop(atlas, _args(need_file=need_file))
            assert out.startswith("error:")
        finally:
            atlas.shutdown()

    def test_missing_need_file_fails_closed(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            out = cmd_develop(atlas, _args(need_file=str(Path("nope.json"))))
            assert out.startswith("error:")
        finally:
            atlas.shutdown()


class TestNeedContractValidation:
    """Deterministic need-file contract enforcement at the operator boundary."""

    def _atlas_with_counting_approval(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            calls: list = []
            manager = atlas._approval_manager  # noqa: SLF001
            original = manager.create_approval_request

            def counting(proposal):
                calls.append(1)
                return original(proposal)

            manager.create_approval_request = counting  # noqa: SLF001
            return atlas, calls
        except Exception:
            atlas.shutdown()
            raise

    def _run_develop(self, atlas, tmp_path, payload):
        need_file = tmp_path / "need.json"
        need_file.write_text(json.dumps(payload), encoding="utf-8")
        return cmd_develop(atlas, _args(need_file=str(need_file)))

    def test_malformed_test_files_shape_rejected_before_persistence(
        self, tmp_path
    ):
        atlas, calls = self._atlas_with_counting_approval()
        try:
            out = self._run_develop(
                atlas,
                tmp_path,
                {
                    "title": "t",
                    "code_changes": [
                        {"path": "a.md", "content": "# a"}
                    ],
                    "test_files": {"paths": "['tests']"},
                },
            )
            assert out.startswith("error:")
            assert "not a pytest test module" in out
            # Rejected BEFORE any durable proposal/approval persistence.
            assert calls == []
        finally:
            atlas.shutdown()

    def test_non_string_code_change_content_rejected(self, tmp_path):
        atlas, calls = self._atlas_with_counting_approval()
        try:
            out = self._run_develop(
                atlas,
                tmp_path,
                {
                    "title": "t",
                    "code_changes": [
                        {
                            "path": "a.md",
                            "content": {"brief": "describes the change"},
                        }
                    ],
                },
            )
            assert out.startswith("error:")
            assert "code_changes[0].content" in out
            assert "must be a string" in out
            assert calls == []
        finally:
            atlas.shutdown()

    @pytest.mark.parametrize(
        "payload_fragment",
        [
            {"path": "", "content": "# x"},
            {"path": 123, "content": "# x"},
            {"path": "a.py"},
            {"content": "# x"},
        ],
    )
    def test_invalid_path_or_content_fields_rejected(
        self, tmp_path, payload_fragment
    ):
        atlas, calls = self._atlas_with_counting_approval()
        try:
            out = self._run_develop(
                atlas,
                tmp_path,
                {"title": "t", "code_changes": [payload_fragment]},
            )
            assert out.startswith("error:")
            assert calls == []
        finally:
            atlas.shutdown()

    def test_empty_content_rejected(self, tmp_path):
        atlas, calls = self._atlas_with_counting_approval()
        try:
            out = self._run_develop(
                atlas,
                tmp_path,
                {
                    "title": "t",
                    "code_changes": [{"path": "a.md", "content": "   "}],
                },
            )
            assert out.startswith("error:")
            assert "must not be empty" in out
            assert calls == []
        finally:
            atlas.shutdown()

    def test_valid_contract_still_accepted(self, tmp_path):
        atlas, calls = self._atlas_with_counting_approval()
        try:
            out = self._run_develop(
                atlas,
                tmp_path,
                {
                    "title": "valid contract need",
                    "code_changes": [
                        {"path": "docs/x.md", "content": "# x\n"}
                    ],
                    "test_files": {
                        "tests/test_x.py": "def test_x():\n    assert True\n"
                    },
                },
            )
            assert "PENDING_APPROVAL" in out
            assert len(calls) == 1
        finally:
            atlas.shutdown()


class TestReviewAndSafeMode:
    def test_review_reports_summary(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            out = cmd_review(atlas, _args(action="review"))
            assert "Self-management review complete" in out
            assert "Review ID: SMR-" in out
        finally:
            atlas.shutdown()

    def test_safe_mode_surfaced_when_active(self):
        fake = SimpleNamespace(boot_safe_mode=True, boot_report=None)
        assert "SAFE_MODE active" in _safe_mode_line(fake)

    def test_no_safe_mode_notice_when_clean(self):
        report = SimpleNamespace(safe_mode=False)
        fake = SimpleNamespace(boot_safe_mode=False, boot_report=report)
        assert _safe_mode_line(fake) == ""

    def test_safe_mode_introspection_fails_closed(self):
        class _RaisingBool:
            def __bool__(self) -> bool:  # pragma: no cover - exercised via raise
                raise RuntimeError("boom")

        fake = SimpleNamespace(boot_safe_mode=_RaisingBool(), boot_report=None)
        assert "SAFE_MODE state unavailable" in _safe_mode_line(fake)

    def test_load_need_requires_file(self):
        with pytest.raises(ValueError):
            _load_need(_args())


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
    "authorize",
    "execute_request",
    "schedule_request",
    "apply",
    "promote",
    "rollback",
)


class TestGovernanceBoundary:
    def _tree(self):
        source = (
            _REPO_ROOT / "atlas/cli/postcore_commands.py"
        ).read_text(encoding="utf-8")
        return ast.parse(source, filename="postcore_commands.py")

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