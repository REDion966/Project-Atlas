"""Phase 6.6 — Sandbox development: evidence contract.

Investigation result: development already occurs inside a fail-closed,
path-confined sandbox that is separate from production, so no second sandbox was
introduced.

* ``atlas/evolution/autonomy/code_sandbox.py::CodeSandbox`` — a disposable
  filesystem root; every path is resolved strictly inside it (absolute paths,
  drive prefixes, ``..`` traversal, and symlink escapes are rejected with
  ``SandboxPathError``). ``CodeChangeSet`` bounds the change payload.
* ``cleanup()`` discards the sandbox; production is never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.evolution.autonomy.code_sandbox import (
    CodeChangeSet,
    CodeSandbox,
    SandboxPathError,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


class TestPhase66SandboxDevelopment:
    def test_permitted_writes_stay_inside_the_sandbox(self, tmp_path):
        sandbox = CodeSandbox(base_dir=tmp_path)
        try:
            sandbox.write_text("atlas/example/mod.py", "VALUE = 1\n")
            assert sandbox.read_text("atlas/example/mod.py") == "VALUE = 1\n"
            assert sandbox.resolve("atlas/example/mod.py").is_relative_to(sandbox.root)
        finally:
            sandbox.cleanup()

    def test_forbidden_paths_are_rejected(self, tmp_path):
        sandbox = CodeSandbox(base_dir=tmp_path)
        try:
            for bad in ("/etc/passwd", "../escape.py", "a/../../b", "C:/x.py", ""):
                with pytest.raises(SandboxPathError):
                    sandbox.resolve(bad)
        finally:
            sandbox.cleanup()

    def test_change_set_rejects_escaping_paths(self):
        with pytest.raises(SandboxPathError):
            CodeChangeSet.from_payload(
                {"code_changes": [{"path": "../evil.py", "content": "x"}]}
            )

    def test_sandbox_is_separate_from_the_live_repository(self, tmp_path):
        sandbox = CodeSandbox(base_dir=tmp_path)
        try:
            assert sandbox.root != _REPO_ROOT
            assert _REPO_ROOT not in sandbox.root.parents
        finally:
            sandbox.cleanup()

    def test_cleanup_discards_sandbox_state(self, tmp_path):
        sandbox = CodeSandbox(base_dir=tmp_path)
        root = sandbox.root
        sandbox.write_text("a.txt", "x")
        assert root.exists()
        sandbox.cleanup()
        assert not root.exists()
