"""Tests for Atlas Evolution Autonomy — Code Execution (Phase E2).

Proves the E2 safety invariants:

  - The sandbox rejects every path-escape vector (absolute, drive prefix,
    ``..`` traversal, empty segments, normalized escape, symlink escape).
  - A bounded CodeChangeSet applies only inside the sandbox root.
  - Successful application + verification produces a success result.
  - Verification failure prevents acceptance and rolls the sandbox back to
    its prior state.
  - The real repository is never touched.
  - CODE remains constitutionally protected in the existing state machine.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

from atlas.evolution.autonomy.code_execution import SandboxCodeExecutor
from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    EvolutionRequestStatus,
)
from atlas.evolution.governance.models import ScopeType


def _code_request(
    change_payload: dict,
    request_id: str = "REQ-CODE-1",
) -> EvolutionRequest:
    """Build a CODE-scoped EvolutionRequest with the given payload."""
    return EvolutionRequest(
        request_id=request_id,
        source="e2-test",
        target_scope=ScopeType.CODE,
        change_payload=change_payload,
        intended_level=3,  # ExecutionLevel.CODE_ARTIFACT
        status=EvolutionRequestStatus.AUTHORIZED,
    )


def _code_changes(*entries) -> dict:
    return {"code_changes": [dict(e) for e in entries]}


class TestSandboxConfinement(unittest.TestCase):
    """Path escape vectors are rejected deterministically."""

    def test_absolute_path_rejected(self):
        from atlas.evolution.autonomy.code_sandbox import (
            CodeChangeSet,
            SandboxPathError,
        )

        for path in ("/etc/passwd", "/abs.py", "C:/outside.txt", "D:\\win.py"):
            with self.assertRaises(SandboxPathError):
                CodeChangeSet.validate_path(path)

    def test_parent_traversal_rejected(self):
        from atlas.evolution.autonomy.code_sandbox import (
            CodeChangeSet,
            SandboxPathError,
        )

        for path in ("../escape.py", "a/../../escape.py", "a/./../escape.py"):
            with self.assertRaises(SandboxPathError):
                CodeChangeSet.validate_path(path)

    def test_empty_segments_rejected(self):
        from atlas.evolution.autonomy.code_sandbox import (
            CodeChangeSet,
            SandboxPathError,
        )

        for path in ("a//b.py", "a/./b.py", "a//b", "a/b/"):
            with self.assertRaises(SandboxPathError):
                CodeChangeSet.validate_path(path)

    def test_from_payload_rejects_escape(self):
        from atlas.evolution.autonomy.code_sandbox import (
            CodeChangeSet,
            SandboxPathError,
        )

        with self.assertRaises(SandboxPathError):
            CodeChangeSet.from_payload(
                _code_changes({"path": "../outside.py", "content": "x"})
            )

    def test_symlink_escape_raises_on_read(self):
        from atlas.evolution.autonomy.code_sandbox import (
            CodeSandbox,
            SandboxPathError,
        )

        with tempfile.TemporaryDirectory() as td:
            outside = tempfile.mkdtemp(prefix="outside_", dir=td)
            with CodeSandbox(base_dir=td) as sandbox:
                try:
                    link = sandbox.create_symlink("escape", outside)
                except OSError:
                    self.skipTest("symlinks unavailable on this platform")
                self.assertTrue(link.is_symlink())
                with self.assertRaises(SandboxPathError):
                    sandbox.read_text("escape/passwd.txt")


class TestSandboxLifecycle(unittest.TestCase):
    """Apply inside a sandbox; verification failure rolls back."""

    def test_valid_apply_and_verify_success(self):
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxCodeExecutor(base_dir=td)
            request = _code_request(
                _code_changes(
                    {"path": "new_file.py", "content": "print('hi')\n"}
                )
            )
            result = executor.execute(request)
            self.assertTrue(result.success)
            self.assertEqual(result.applied_files, ["new_file.py"])
            self.assertIsNotNone(result.verification)
            self.assertTrue(result.verification.passed)
            self.assertFalse(result.rollback_occurred)

    def test_apply_does_not_write_outside_sandbox(self):
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxCodeExecutor(base_dir=td)
            request = _code_request(
                _code_changes(
                    {"path": "sub/dir/file.txt", "content": "nested"}
                )
            )
            result = executor.execute(request)
            self.assertTrue(result.success)
            root = result.sandbox_path
            self.assertTrue(root.startswith(td))
            # Nothing is written directly to the temp base dir itself.
            self.assertNotIn("file.txt", os.listdir(td))

    def test_verification_failure_rolls_back_to_prior_state(self):
        # Seed the sandbox with a prior file, then corrupt the applied file
        # via the post_apply_hook so the read-back probe fails and the
        # executor restores the prior snapshot.
        def _corrupt(sandbox):
            sandbox.write_text("lib/util.py", "CORRUPTED\n")

        with tempfile.TemporaryDirectory() as td:
            executor = SandboxCodeExecutor(
                base_dir=td,
                seed={"lib/util.py": "PRIOR_BODY\n"},
                post_apply_hook=_corrupt,
            )
            request = _code_request(
                _code_changes(
                    {"path": "lib/util.py", "content": "NEW_BODY\n"}
                )
            )
            result = executor.execute(request)
            self.assertFalse(result.success)
            self.assertTrue(result.rollback_occurred)
            self.assertIsNotNone(result.verification)
            self.assertFalse(result.verification.passed)

    def test_non_code_scope_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxCodeExecutor(base_dir=td)
            request = EvolutionRequest(
                request_id="R-MEM",
                source="test",
                target_scope=ScopeType.MEMORY,
                change_payload={"entries": []},
            )
            result = executor.execute(request)
            self.assertFalse(result.success)
            self.assertIn("not CODE", result.error)

    def test_invalid_payload_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxCodeExecutor(base_dir=td)
            request = _code_request({"code_changes": []})
            result = executor.execute(request)
            self.assertFalse(result.success)
            self.assertIn("empty", result.error)

    def test_sandbox_restore_primitive_restores_prior_content(self):
        """Direct proof that CodeSandbox.restore returns the grid to prior state."""
        from atlas.evolution.autonomy.code_sandbox import CodeSandbox

        with tempfile.TemporaryDirectory() as td:
            with CodeSandbox(base_dir=td) as sandbox:
                sandbox.write_text("lib/util.py", "PRIOR\n")
                snapshot = sandbox.snapshot(["lib/util.py"])
                sandbox.write_text("lib/util.py", "NEW\n")
                self.assertEqual(sandbox.read_text("lib/util.py"), "NEW\n")
                sandbox.restore(snapshot)
                self.assertEqual(sandbox.read_text("lib/util.py"), "PRIOR\n")
            # Sandbox cleaned up automatically on context exit.


class TestGovernanceBoundaryIntact(unittest.TestCase):
    """E2 does NOT reopen the constitutional CODE boundary."""

    def test_scope_classifier_still_excludes_code(self):
        from atlas.evolution.autonomy.scope_classifier import STATE_SCOPES

        self.assertNotIn(ScopeType.CODE, STATE_SCOPES)

    def test_authorization_manager_still_refuses_code(self):
        from atlas.evolution.autonomy.authorization_manager import (
            AuthorizationManager,
            AuthorizationRequest,
        )
        from atlas.evolution.autonomy.models import AutonomyPolicy

        manager = AuthorizationManager(policy=AutonomyPolicy(enabled=True))
        request = _code_request({"code_changes": [{"path": "a.py", "content": "x"}]})
        result = manager.request_user_authorization(
            request,
            AuthorizationRequest(authorized_by="user:cli"),
        )
        self.assertFalse(result.authorized)


if __name__ == "__main__":
    unittest.main()