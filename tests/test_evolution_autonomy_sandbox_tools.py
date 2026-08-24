"""
Phase E4 — Sandbox Testing & Inspection Tools — focused tests.

Covers:
1. pytest succeeds inside a sandbox workspace
2. pytest failure is captured correctly (pass/fail/error/timeout)
3. pytest cannot execute outside a sandbox workspace
4. pytest cannot be converted into arbitrary shell execution
5. output is bounded
6. timeout / failure handling
7. git status works inside a sandbox workspace
8. git diff works inside a sandbox workspace
9. git inspection is read-only
10. dangerous git operations are rejected
11. sandbox escape attempts fail closed
12. tool registration works through the existing ToolRegistry / ToolExecutor /
    ToolEngine path
13. direct bypass of governance is impossible through the intended interface
14. malformed / invalid requests fail safely
15. (E2 / E3 / Phase D regressions are run in the batch suite, not here)
"""

import os
import subprocess
import tempfile
import unittest

from atlas.evolution.autonomy.sandbox_tools import (
    MAX_OUTPUT_BYTES,
    SAFE_GIT_SUBCOMMANDS,
    SandboxWorkspace,
    _confined_rel,
    _controlled_env,
    _git_inspection,
    _is_secret_key,
    git_diff_tool,
    git_status_tool,
    pytest_tool,
    register_sandbox_tools,
    sandbox_tools,
)
from atlas.tools.engine import ToolEngine
from atlas.tools.executor import ToolExecutor
from atlas.tools.registry import ToolRegistry
from atlas.tools.selector import ToolSelector


def _write(ws: SandboxWorkspace, rel: str, content: str) -> None:
    """Write a file inside a sandbox workspace."""
    ws.write_text(rel, content)


def _write_git(ws: SandboxWorkspace, rel: str, content: str) -> None:
    """Write a file inside a sandbox workspace (test-scoped alias)."""
    _write(ws, rel, content)


def _init_git_repo(ws: SandboxWorkspace) -> None:
    """Seed a disposable git repository inside the sandbox workspace."""
    subprocess.run(["git", "init", "-b", "main"], cwd=ws.path, check=True,
                   capture_output=True, text=True)
    _write(ws, "seed.txt", "hello\n")
    subprocess.run(["git", "add", "seed.txt"], cwd=ws.path, check=True,
                   capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=atlas", "-c", "user.email=atlas@local",
         "commit", "-m", "seed"], cwd=ws.path, check=True,
        capture_output=True, text=True)  # noqa


def _head(ws: SandboxWorkspace) -> str:
    """Return the current git HEAD commit id inside the workspace."""
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ws.path,
                          capture_output=True, text=True)
    return (proc.stdout or "").strip()


class TestPytestSecurityControls(unittest.TestCase):
    """Requirements 3, 4, 5, 6 — boundedness, no shell, no escape, no secrets."""

    def test_timeout_handling(self):
        with SandboxWorkspace.create() as ws:
            _write_git(ws, "slow_test.py",
                       "import time\n\ndef test_slow():\n    time.sleep(5)\n")
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": "slow_test.py",
                 "timeout_seconds": 0.3}
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "timeout")

    def test_output_is_bounded(self):
        # The tool must never return more than MAX_OUTPUT_BYTES per channel,
        # regardless of how much the child process writes.
        with SandboxWorkspace.create() as ws:
            _write_git(ws, "noisy.py",
                       "def test_noisy():\n    print('Y' * 200000)\n"
                       "    assert True\n")
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": "noisy.py"}
            )
            self.assertLessEqual(
                len(result.output["stdout"].encode("utf-8")),
                MAX_OUTPUT_BYTES,
            )
            self.assertLessEqual(
                len(result.output["stderr"].encode("utf-8")),
                MAX_OUTPUT_BYTES,
            )

    def test_bounded_helper_truncates(self):
        from atlas.evolution.autonomy.sandbox_tools import _bounded
        big = "X" * (MAX_OUTPUT_BYTES * 2)
        kept, truncated = _bounded(big)
        self.assertTrue(truncated)
        self.assertLessEqual(len(kept.encode("utf-8")), MAX_OUTPUT_BYTES)
        # Small output is returned untouched, not truncated.
        small, small_trunc = _bounded("ok")
        self.assertEqual(small, "ok")
        self.assertFalse(small_trunc)

    def test_option_injection_target_rejected(self):
        with SandboxWorkspace.create() as ws:
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": "-k"}
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "invalid")

    def test_parent_traversal_target_rejected(self):
        with SandboxWorkspace.create() as ws:
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": "../escape.py"}
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "invalid")

    def test_absolute_target_rejected(self):
        with SandboxWorkspace.create() as ws:
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": ws.path}
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "invalid")

    def test_arbitrary_command_param_is_ignored(self):
        """A 'command' key must never be executed — only fixed pytest runs."""
        with SandboxWorkspace.create() as ws:
            _write_git(ws, "test_ok.py", "def test_ok():\n    assert True\n")
            result = pytest_tool().handler(
                {"workspace": ws.path,
                 "command": f"import os; os.remove('{ws.path}')"}
            )
            self.assertTrue(result.success)
            self.assertTrue(os.path.isdir(ws.path))

    def test_controlled_env_does_not_forward_credentials(self):
        # Prove the child-process env drops credential-like keys entirely.
        env = _controlled_env()
        for key in env:
            self.assertFalse(_is_secret_key(key), f"secret forwarded: {key}")
        self.assertNotIn("API_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)

    def test_confined_rel_and_marker_helpers(self):
        with SandboxWorkspace.create() as ws:
            rel = _confined_rel(ws.path, "nested/file.py", "target")
            self.assertEqual(rel, "nested/file.py")
            self.assertTrue(SandboxWorkspace.is_workspace(ws.path))
            marker = ws.path + os.sep + ".atlas_sandbox_token"
            self.assertTrue(os.path.exists(marker))
        # After cleanup the workspace marker must be gone.
        self.assertFalse(os.path.exists(marker))


class TestPytestWorkspace(unittest.TestCase):
    """Requirements 1, 2 — pytest runs and distinguishes pass/fail/error."""

    def test_pytest_passes_inside_sandbox(self):
        with SandboxWorkspace.create() as ws:
            _write_git(ws, "test_ok.py", "def test_ok():\n    assert 1 == 1\n")
            result = pytest_tool().handler({"workspace": ws.path})
            self.assertTrue(result.success)
            self.assertEqual(result.output["outcome"], "passed")
            self.assertEqual(result.output["exit_code"], 0)

    def test_pytest_with_named_target(self):
        with SandboxWorkspace.create() as ws:
            _write_git(ws, "test_ok.py", "def test_ok():\n    assert 1 == 1\n")
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": "test_ok.py"}
            )
            self.assertTrue(result.success)
            self.assertEqual(result.output["outcome"], "passed")

    def test_pytest_failure_is_captured(self):
        with SandboxWorkspace.create() as ws:
            _write_git(ws, "test_bad.py", "def test_bad():\n    assert 1 == 2\n")
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": "test_bad.py"}
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "failed")
            self.assertEqual(result.output["exit_code"], 1)

    def test_pytest_error_exit_two_maps_to_error(self):
        with SandboxWorkspace.create() as ws:
            # A syntactically broken module makes pytest exit code 2.
            _write_git(ws, "broken.py", "def broken(:\n    pass\n")
            result = pytest_tool().handler(
                {"workspace": ws.path, "target": "broken.py"}
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "error")

    def test_pytest_rejects_non_sandbox_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            result = pytest_tool().handler({"workspace": td})
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "invalid")
            self.assertIn("sandbox", result.error.lower())

    def test_pytest_requires_workspace(self):
        result = pytest_tool().handler({})
        self.assertFalse(result.success)
        self.assertEqual(result.output["outcome"], "invalid")

    def test_result_is_bounded_tool_result(self):
        with SandboxWorkspace.create() as ws:
            result = pytest_tool().handler({"workspace": ws.path})
            self.assertEqual(result.tool_name, "sandbox_pytest")
            self.assertIn("stdout", result.output)
            self.assertIn("stderr", result.output)
            self.assertIn("sandbox_path", result.output)


class TestGitInspection(unittest.TestCase):
    """Requirements 7, 8 — git status/diff work inside a sandbox workspace."""

    def _workspace_with_repo_and_change(self):
        ws = SandboxWorkspace.create()
        _init_git_repo(ws)
        return ws

    def test_git_status_works_inside_sandbox(self):
        with SandboxWorkspace.create() as ws:
            _init_git_repo(ws)
            result = git_status_tool().handler({"workspace": ws.path})
            self.assertTrue(result.success)
            self.assertEqual(result.output["outcome"], "passed")
            self.assertEqual(result.output["exit_code"], 0)

    def test_git_diff_works_inside_sandbox(self):
        with SandboxWorkspace.create() as ws:
            _init_git_repo(ws)
            # A working-tree change after the seed commit makes diff non-empty.
            _write_git(ws, "seed.txt", "hello changed\n")
            result = git_diff_tool().handler({"workspace": ws.path})
            self.assertTrue(result.success)
            self.assertEqual(result.output["outcome"], "passed")
            self.assertEqual(result.output["exit_code"], 0)

    def test_git_status_path_scoped(self):
        with SandboxWorkspace.create() as ws:
            _init_git_repo(ws)
            result = git_status_tool().handler(
                {"workspace": ws.path, "path": "seed.txt"}
            )
            self.assertTrue(result.success)

    def test_git_tools_reject_non_sandbox_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            for tool in (git_status_tool(), git_diff_tool()):
                result = tool.handler({"workspace": td})
                self.assertFalse(result.success)
                self.assertEqual(result.output["outcome"], "invalid")

    def test_git_tools_reject_escaping_path(self):
        with SandboxWorkspace.create() as ws:
            result = git_status_tool().handler(
                {"workspace": ws.path, "path": "../escape"}
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "invalid")


class TestGitReadOnlyAndDangerousOps(unittest.TestCase):
    """Requirements 9, 10 — git inspection is read-only; dangerous ops blocked."""

    def test_git_status_is_read_only(self):
        with SandboxWorkspace.create() as ws:
            _init_git_repo(ws)
            before = _head(ws)
            result = git_status_tool().handler({"workspace": ws.path})
            after = _head(ws)
            self.assertTrue(result.success)
            self.assertEqual(before, after)

    def test_git_diff_is_read_only(self):
        with SandboxWorkspace.create() as ws:
            _init_git_repo(ws)
            _write_git(ws, "seed.txt", "changed in tree\n")
            before = _head(ws)
            result = git_diff_tool().handler({"workspace": ws.path})
            after = _head(ws)
            self.assertTrue(result.success)
            self.assertEqual(before, after)

    def test_whitelist_excludes_dangerous_subcommands(self):
        for forbidden in ("commit", "push", "reset", "checkout", "merge",
                          "rebase", "stash", "restore", "switch"):
            self.assertNotIn(forbidden, SAFE_GIT_SUBCOMMANDS)

    def test_forbidden_subcommand_rejected_even_internally(self):
        with SandboxWorkspace.create() as ws:
            _init_git_repo(ws)
            result = _git_inspection(
                "git_commit", "commit", "sandbox_git_commit",
                {"workspace": ws.path},
            )
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "invalid")
            self.assertIn("forbidden", result.error.lower())

    def test_no_mutation_after_tools_run(self):
        with SandboxWorkspace.create() as ws:
            _init_git_repo(ws)
            git_status_tool().handler({"workspace": ws.path})
            git_diff_tool().handler({"workspace": ws.path})
            # Repo still contains exactly the initial commit (no new commits).
            log = subprocess.run(["git", "log", "--oneline"], cwd=ws.path,
                                 capture_output=True, text=True)
            self.assertIn("seed", log.stdout.lower())


class TestRegistrationThroughEngine(unittest.TestCase):
    """Requirement 12 — E4 tools register and run via the existing tool path."""

    def test_registration_through_tool_registry(self):
        registry = ToolRegistry()
        tools = register_sandbox_tools(registry)
        self.assertEqual(len(tools), 3)
        for name in ("sandbox_pytest", "sandbox_git_status", "sandbox_git_diff"):
            self.assertIsNotNone(registry.get(name))
            self.assertEqual(registry.get(name).category, "code")

    def test_registration_rejects_duplicate(self):
        registry = ToolRegistry()
        register_sandbox_tools(registry)
        with self.assertRaises(ValueError):
            register_sandbox_tools(registry)

    def test_tool_names_constant(self):
        names = [t.name for t in sandbox_tools()]
        self.assertEqual(names, ["sandbox_pytest", "sandbox_git_status",
                                 "sandbox_git_diff"])

    def test_execution_through_tool_executor(self):
        registry = ToolRegistry()
        register_sandbox_tools(registry)
        executor = ToolExecutor(registry)
        with SandboxWorkspace.create() as ws:
            _write_git(ws, "test_ok.py", "def test_ok():\n    assert True\n")
            result = executor.execute_by_name(
                "sandbox_pytest", {"workspace": ws.path}
            )
            self.assertTrue(result.success)
            self.assertEqual(result.output["outcome"], "passed")

    def test_discovery_through_tool_engine(self):
        registry = ToolRegistry()
        register_sandbox_tools(registry)
        engine = ToolEngine(registry, ToolSelector(), ToolExecutor(registry))
        names = {t.name for t in engine.available_tools()}
        self.assertIn("sandbox_pytest", names)
        self.assertIn("sandbox_git_status", names)
        self.assertIn("sandbox_git_diff", names)

    def test_unregistered_tool_executes_as_error(self):
        registry = ToolRegistry()
        executor = ToolExecutor(registry)
        result = executor.execute_by_name("sandbox_pytest", {})
        self.assertFalse(result.success)
        self.assertIn("not registered", result.error)


class TestSafetyBoundaries(unittest.TestCase):
    """Requirements 13, 14 — no governance bypass; malformed requests fail."""

    def test_tools_never_import_authorization_manager(self):
        import inspect
        from atlas.evolution.autonomy import sandbox_tools
        src = inspect.getsource(sandbox_tools)
        self.assertNotIn("AuthorizationManager", src)
        self.assertNotIn("ScopeType", src)

    def test_code_remains_constitutionally_protected(self):
        from atlas.evolution.autonomy.scope_classifier import STATE_SCOPES
        from atlas.evolution.governance.models import ScopeType
        self.assertNotIn(ScopeType.CODE, STATE_SCOPES)

    def test_authorization_manager_still_refuses_code(self):
        from atlas.evolution.autonomy.authorization_manager import (
            AuthorizationManager,
            AuthorizationRequest,
        )
        from atlas.evolution.autonomy.models import AutonomyPolicy
        from atlas.evolution.autonomy.models import EvolutionRequest
        from atlas.evolution.governance.models import ScopeType

        manager = AuthorizationManager(policy=AutonomyPolicy(enabled=True))
        request = EvolutionRequest(
            request_id="R-CODE", source="test",
            target_scope=ScopeType.CODE,
            change_payload={"code_changes": [{"path": "a.py", "content": "x"}]},
        )
        result = manager.request_user_authorization(
            request,
            AuthorizationRequest(authorized_by="user:cli"),
        )
        self.assertFalse(result.authorized)
        self.assertIn("protected", result.reason.lower())

    def test_malformed_timeout_fails_safely(self):
        with SandboxWorkspace.create() as ws:
            for bad in ("-1", "99999", "abc"):
                result = pytest_tool().handler(
                    {"workspace": ws.path, "timeout_seconds": bad}
                )
                self.assertFalse(result.success)
                self.assertEqual(result.output["outcome"], "invalid")

    def test_missing_workspace_for_git_fails_safely(self):
        for tool in (git_status_tool(), git_diff_tool()):
            result = tool.handler({})
            self.assertFalse(result.success)
            self.assertEqual(result.output["outcome"], "invalid")

    def test_sandbox_workspace_requires_marker(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(SandboxWorkspace.is_workspace(td))
            self.assertFalse(SandboxWorkspace.is_workspace(os.path.join(td, "nope")))

    def test_wrapper_bridges_existing_code_sandbox(self):
        from atlas.evolution.autonomy.code_sandbox import CodeSandbox
        with CodeSandbox() as cs:
            wrapped = SandboxWorkspace.from_code_sandbox(cs)
            self.assertTrue(SandboxWorkspace.is_workspace(wrapped.path))
            wrapped.write_text("probe.txt", "hello")
            self.assertEqual(wrapped.read_text("probe.txt"), "hello")


if __name__ == "__main__":
    unittest.main()