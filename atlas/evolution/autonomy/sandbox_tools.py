"""
Atlas Evolution Autonomy — Sandbox Testing & Inspection Tools — Phase E4

Governed, deterministic toolchain primitives that let Atlas inspect and
test a sandboxed development change WITHOUT leaving the E2 ``CodeSandbox``
boundary and WITHOUT running arbitrary commands.

Contains:
  - :class:`SandboxWorkspace` — mints a **sandbox identity token** inside a
    ``CodeSandbox`` root so tools can positively identify a genuine
    workspace and reject arbitrary paths (e.g. the real repository root).
  - :class:`SandboxRunReport` — the smallest bounded result-capture model.
    It never carries secrets, credentials, prompts, or uncapped output.
  - ``run_pytest_in_sandbox`` / ``inspect_git_status_in_sandbox`` /
    ``inspect_git_diff_in_sandbox`` — fixed-command, fail-closed handlers.
  - ``pytest_tool()`` / ``git_status_tool()`` / ``git_diff_tool()`` /
    ``register_sandbox_tools(registry)`` — registration through the EXISTING
    :class:`~atlas.tools.registry.ToolRegistry` surface.

GOVERNANCE / SAFETY CONTRACT
------------------------------
* These tools are pure mechanics. They never grant authorization, never call
  the external authorization or rule subsystems, and never reopen the
  constitutional CODE boundary. The existing RiskPolicy / governance /
  authorization layers remain authoritative.
* The tools operate only on a workspace that ``SandboxWorkspace`` minted. An
  invalid or non-sandbox workspace fails closed.
* Commands are internally constructed from a *fixed* command list. There is
  no user-supplied command string, no ``shell=True``, and no general-purpose
  command executor. Arbitrary shell commands or ``git`` subcommands cannot be
  smuggled through the tool interface.
* pytest ``target`` / git ``path`` are validated as sandbox-confined relative
  paths and are never interpreted as shell syntax.
* Credential-bearing environment variables are not forwarded to the child
  process; only a small allow-listed set is preserved.

Pure infrastructure. No gateway. No AI. No kernel access.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.evolution.autonomy.code_sandbox import (
    CodeChangeSet,
    CodeSandbox,
    SandboxPathError,
)
from atlas.tools.models import Tool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# Boundedness constants (deterministic; audit these, never per-request)
# ---------------------------------------------------------------------------

#: Maximum bytes of captured stdout OR stderr retained in a result.
MAX_OUTPUT_BYTES: int = 64 * 1024

#: Default subprocess timeout for a single pytest run.
DEFAULT_TIMEOUT_SECONDS: float = 30.0

#: Hard upper bound on the ``timeout_seconds`` tool parameter.
MAX_TIMEOUT_SECONDS: float = 120.0

#: Marker file name stamped inside a sandbox workspace.
SANDBOX_MARKER: str = ".atlas_sandbox_token"

#: Marker content prefix proving the workspace was minted as a sandbox.
MARKER_PREFIX: str = "atlas-sandbox-v1:"

#: Git subcommands the git inspection tools may perform. Fixed and minimal.
SAFE_GIT_SUBCOMMANDS: frozenset[str] = frozenset({"status", "diff"})

#: Environment keys permitted (by simple name) in the child-process env.
_ALLOWED_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "HOMEDRIVE",
        "HOMEPATH",
    }
)

#: Substrings disqualifying an environment key from being forwarded.
_SECRET_MARKERS: tuple[str, ...] = (
    "KEY", "SECRET", "PASSWORD", "TOKEN", "CREDENTIAL", "AUTHORIZATION",
    "PRIVATE",
)


class SandboxWorkspaceError(ValueError):
    """Raised when a workspace reference is invalid or unsafe."""


# ---------------------------------------------------------------------------
# Bounded result capture (Requirement C)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SandboxRunReport:
    """Bounded, structured capture of one sandbox tool operation.

    Attributes:
        operation: Stable operation identifier (e.g. ``"pytest"``).
        success:   Whether the operation ran without an infrastructure error.
        outcome:   ``passed`` | ``failed`` | ``error`` | ``timeout``
            | ``invalid`` | ``skipped``.
        exit_code: Process exit code, when a subprocess was spawned.
        stdout / stderr: Bounded output (at most ``MAX_OUTPUT_BYTES``).
        stdout_truncated / stderr_truncated: True when output was capped.
        changed_files: Relative paths the operation changed, when known.
        sandbox_path: The workspace path (only present when validated).
        error:     Human-readable failure reason (never dumps secrets).
    """

    operation: str
    success: bool = False
    outcome: str = "invalid"
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    changed_files: list[str] = field(default_factory=list)
    sandbox_path: str | None = None
    error: str = ""

    def to_tool_result(self, tool_name: str) -> ToolResult:
        """Adapt this report to the existing ``ToolResult`` contract."""
        report = {
            "operation": self.operation,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "changed_files": list(self.changed_files),
            "sandbox_path": self.sandbox_path,
        }
        return ToolResult(
            tool_name=tool_name,
            success=self.success,
            output=report,
            error=self.error,
            metadata={
                "operation": self.operation,
                "outcome": self.outcome,
                "exit_code": self.exit_code,
            },
        )


def _bounded(text: str, limit: int = MAX_OUTPUT_BYTES) -> tuple[str, bool]:
    """Truncate ``text`` to ``limit`` bytes; return ``(text, truncated)``."""
    if text is None:
        return "", False
    suffix = "\n...[truncated]"
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text, False
    keep = max(0, limit - len(suffix.encode("utf-8")))
    kept = encoded[:keep].decode("utf-8", errors="replace").rstrip()
    return kept + suffix, True


def _is_secret_key(key: str) -> bool:
    """True when an environment key name looks like it carries credentials."""
    upper = key.upper()
    return any(marker in upper for marker in _SECRET_MARKERS)


def _controlled_env() -> dict:
    """Minimal, allow-listed environment for a child process.

    Candidate keys are copied from ``os.environ`` only when their name is in
    the allow list and does not look like a credential. PATH is preserved so
    the ``git`` binary stays resolvable.
    """
    env: dict = {"PYTHONDONTWRITEBYTECODE": "1"}
    for key in _ALLOWED_ENV_KEYS:
        if _credential_key(key):
            env[key] = os.environ[key]
    return env


def _credential_key(key: str) -> bool:
    """True when ``key`` is in the env and is not a secret name."""
    return key in os.environ and not _is_secret_key(key)


def _invalid_report(
    operation: str, message: str, sandbox_path: str | None = None,
) -> SandboxRunReport:
    """Produce a deterministic fail-closed report."""
    return SandboxRunReport(
        operation=operation,
        success=False,
        outcome="invalid",
        sandbox_path=sandbox_path,
        error=message,
    )


# ---------------------------------------------------------------------------
# SandboxWorkspace — minted sandbox identity
# ---------------------------------------------------------------------------


class SandboxWorkspace:
    """A ``CodeSandbox`` root stamped with a credentials-checked identity.

    ``SandboxWorkspace`` is the only way to reference a sandbox service for
    the E4 tools. It wraps an E2 :class:`CodeSandbox` and writes a marker file
    whose content is ``MARKER_PREFIX + token``. Tools require the marker so an
    arbitrary path (e.g. the real repository root) is rejected.

    Does not grant authorization, does not bypass governance, and does not
    make the underlying CODE authorization boundary any more permissive.
    """

    def __init__(self, code_sandbox: CodeSandbox, token: str) -> None:
        self._code_sandbox = code_sandbox
        self._code_sandbox.write_text(SANDBOX_MARKER, MARKER_PREFIX + token)
        self._token = token

    @classmethod
    def create(cls, base_dir=None) -> "SandboxWorkspace":
        """Create a fresh disposable sandbox workspace beneath ``base_dir``."""
        return cls(CodeSandbox(base_dir=base_dir), secrets.token_hex(16))

    @classmethod
    def from_code_sandbox(cls, code_sandbox: CodeSandbox) -> "SandboxWorkspace":
        """Wrap an existing E2 ``CodeSandbox`` as a tool workspace."""
        return cls(code_sandbox, secrets.token_hex(16))

    # ------------------------------------------------------------------
    # Identity / validation
    # ------------------------------------------------------------------

    @property
    def path(self) -> str:
        """Absolute path of the sandbox workspace root."""
        return str(self._code_sandbox.root)

    @property
    def root(self) -> Path:
        """The sandbox root as a ``Path``."""
        return self._code_sandbox.root

    @property
    def token(self) -> str:
        """The minted sandbox identity token."""
        return self._token

    def marker_content(self) -> str:
        """The exact marker content written into the workspace."""
        return MARKER_PREFIX + self._token

    @staticmethod
    def is_workspace(workspace: str | Path) -> bool:
        """Return True when ``workspace`` looks like a minted sandbox.

        A directory qualifies when the marker exists and its content carries
        the sandbox marker prefix. Any other path — including the repository
        root — is not a sandbox workspace and must fail closed.
        """
        root = Path(workspace)
        if not root.is_dir():
            return False
        marker = root / SANDBOX_MARKER
        if not marker.is_file():
            return False
        try:
            content = marker.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return False
        return content.startswith(MARKER_PREFIX)

    # ------------------------------------------------------------------
    # Confined filesystem access (reuses E2 CodeSandbox.resolve)
    # ------------------------------------------------------------------

    def resolve(self, rel_path: str) -> Path:
        """Resolve a relative path strictly inside the workspace root."""
        return self._code_sandbox.resolve(rel_path)

    def write_text(self, rel_path: str, content: str) -> Path:
        """Write a file inside the workspace (confined)."""
        return self._code_sandbox.write_text(rel_path, content)

    def read_text(self, rel_path: str, default: Any = None) -> Any:
        """Read a file inside the workspace (confined)."""
        return self._code_sandbox.read_text(rel_path, default)

    def exists(self, rel_path: str) -> bool:
        """True when the confined relative path exists."""
        return self._code_sandbox.exists(rel_path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove the sandbox root and its identity marker."""
        self._code_sandbox.cleanup()

    def __enter__(self) -> "SandboxWorkspace":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cleanup()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.cleanup()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Workspace + confined-path extraction
# ---------------------------------------------------------------------------


def _require_workspace(params: dict[str, Any]) -> str:
    """Extract and validate the ``workspace`` parameter.

    Raises:
        SandboxWorkspaceError: When the parameter is missing, not a directory,
            or is not a minted sandbox workspace.
    """
    raw = params.get("workspace")
    if raw is None or not isinstance(raw, str) or not raw.strip():
        raise SandboxWorkspaceError(
            "A 'workspace' path to a valid sandbox is required."
        )
    if not SandboxWorkspace.is_workspace(raw):
        raise SandboxWorkspaceError(
            "Refusing non-sandbox workspace: the path is not a "
            "minted sandbox workspace."
        )
    return str(Path(raw).resolve())


def _confined_rel(
    workspace: str, rel_arg: Any, label: str,
) -> str | None:
    """Validate and return a sandbox-confined relative path.

    Returns ``None`` when ``rel_arg`` is absent. Raises ``SandboxPathError``
    when the value is not a safe relative path or escapes the workspace.
    """
    if rel_arg is None:
        return None
    if not isinstance(rel_arg, str) or not rel_arg.strip():
        raise SandboxPathError(f"'{label}' must be a non-empty string")
    rel = rel_arg.strip()
    if rel.startswith("-"):
        raise SandboxPathError(
            f"'{label}' must not begin with '-' (option injection)"
        )
    if not _safe_relative(rel):
        raise SandboxPathError(f"'{label}' is not a safe relative path")
    candidate = Path(workspace) / rel.replace("\\", "/")
    real_candidate = candidate.resolve()
    real_ws = Path(workspace).resolve()
    if real_candidate != real_ws and real_ws not in real_candidate.parents:
        raise SandboxPathError(f"'{label}' escapes the sandbox workspace")
    return rel.replace("\\", "/")


def _safe_relative(rel: str) -> bool:
    """Return True when ``rel`` is a clean, confined relative path.

    Uses E2's ``CodeChangeSet.validate_path`` semantics (no absolute path, no
    drive prefix, no ``..``, no empty or '.' segments).
    """
    try:
        CodeChangeSet.validate_path(rel)
    except SandboxPathError:
        return False
    return True


# ---------------------------------------------------------------------------
# Fixed-command subprocess runner (no generic command executor)
# ---------------------------------------------------------------------------


def _bounded_timeout_seconds(value: Any) -> float:
    """Validate the ``timeout_seconds`` tool parameter (bounded)."""
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SandboxWorkspaceError("'timeout_seconds' must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise SandboxWorkspaceError(
            "'timeout_seconds' must be numeric"
        ) from exc
    if parsed <= 0.0 or parsed > MAX_TIMEOUT_SECONDS:
        raise SandboxWorkspaceError(
            f"'timeout_seconds' must be in (0, {MAX_TIMEOUT_SECONDS}]"
        )
    return parsed


def _spawn(
    operation: str,
    argv: list[str],
    workspace: str,
    timeout_seconds: float,
    *,
    failure_message: str,
    no_tests_exit_code: int | None = None,
) -> SandboxRunReport:
    """Run a fixed command list inside the workspace with a bounded result.

    The command list is always assembled by the caller from trusted tokens;
    this helper never accepts a user-supplied command string and never uses
    ``shell=True``. Afterward the helper always links ``changed_files=[]`` and
    ``sandbox_path=workspace`` so the mixin fields are populated.
    """
    env: dict = _controlled_env()
    stdout_text: str = ""
    stderr_text: str = ""
    exit_code: int | None = None
    outcome: str = "error"
    error: str = failure_message
    ran: bool = False

    try:
        proc = subprocess.run(
            argv,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        ran = True
    except subprocess.TimeoutExpired as exc:
        outcome = "timeout"
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        error = f"{failure_message}; timed out after {timeout_seconds:g}s"
    except (OSError, subprocess.SubprocessError) as exc:
        outcome = "error"
        error = f"{failure_message}: {exc}"

    if ran:
        if exit_code == 0:
            outcome = "passed"
            error = ""
        elif (
            no_tests_exit_code is not None
            and exit_code == no_tests_exit_code
        ):
            outcome = "no_tests_collected"
            error = (
                f"{failure_message}; pytest collected no tests "
                f"(exit code {exit_code})."
            )
        else:
            outcome = "failed"
            error = failure_message

    stdout_kept, stdout_trunc = _bounded(stdout_text)
    stderr_kept, stderr_trunc = _bounded(stderr_text)

    report = SandboxRunReport(
        operation=operation,
        success=(outcome == "passed"),
        outcome=outcome,
        exit_code=exit_code,
        stdout=stdout_kept,
        stderr=stderr_kept,
        stdout_truncated=stdout_trunc,
        stderr_truncated=stderr_trunc,
        sandbox_path=workspace,
        error=error,
    )
    return report


# ---------------------------------------------------------------------------
# pytest handler
# ---------------------------------------------------------------------------


def run_pytest_in_sandbox(params: dict[str, Any]) -> ToolResult:
    """Run pytest ONLY inside a sandbox workspace (fixed command list).

    This tool never accepts a command string, never uses ``shell=True``, and
    can only target a confined relative path inside a minted workspace.
    """
    try:
        workspace = _require_workspace(params)
        timeout = _bounded_timeout_seconds(params.get("timeout_seconds"))
        target = _confined_rel(workspace, params.get("target"), "target")
    except (SandboxWorkspaceError, SandboxPathError) as exc:
        return _invalid_report("pytest", str(exc)).to_tool_result("sandbox_pytest")

    argv = [sys.executable, "-m", "pytest"]
    argv.append(target or ".")

    # pytest exit 5 means "no tests collected" — report it distinctly so
    # operators can tell a documentation-only change from a genuine failure.
    report = _spawn(
        "pytest",
        argv,
        workspace,
        timeout,
        failure_message="pytest failed to start",
        no_tests_exit_code=5,
    )

    # pytest exit semantics: 0 = passed, 1 = failed, 2 = interrupted/error,
    # 5 = no tests collected (reported as ``no_tests_collected``).
    if report.exit_code == 2 and report.outcome == "failed":
        report.outcome = "error"
        report.error = report.error or "pytest reported an error (exit 2)."
    if report.outcome == "error":
        report.success = False
    return report.to_tool_result("sandbox_pytest")


# ---------------------------------------------------------------------------
# Git inspection handlers
# ---------------------------------------------------------------------------


def _git_inspection(
    operation: str,
    subcommand: str,
    tool_name: str,
    params: dict[str, Any],
) -> ToolResult:
    """Run a fixed, read-only ``git`` subcommand inside a sandbox workspace."""
    if subcommand not in SAFE_GIT_SUBCOMMANDS:
        return _invalid_report(
            operation, f"Refusing forbidden git subcommand: '{subcommand}'",
        ).to_tool_result(tool_name)
    try:
        workspace = _require_workspace(params)
        path = _confined_rel(workspace, params.get("path"), "path")
    except (SandboxWorkspaceError, SandboxPathError) as exc:
        return _invalid_report(tool_name, str(exc)).to_tool_result(tool_name)

    argv = ["git", subcommand]
    if path:
        argv += ["--", path]

    report = _spawn(
        tool_name,
        argv,
        workspace,
        _bounded_timeout_seconds(params.get("timeout_seconds")),
        failure_message=f"git {subcommand} failed",
    )
    report.operation = tool_name
    return report.to_tool_result(tool_name)


def inspect_git_status_in_sandbox(params: dict[str, Any]) -> ToolResult:
    """Run ``git status`` read-only inside a sandbox workspace."""
    return _git_inspection("git_status", "status", "sandbox_git_status", params)


def inspect_git_diff_in_sandbox(params: dict[str, Any]) -> ToolResult:
    """Run ``git diff`` read-only inside a sandbox workspace."""
    return _git_inspection("git_diff", "diff", "sandbox_git_diff", params)


# ---------------------------------------------------------------------------
# Tool definitions (existing atlas.tools.models.Tool surface)
# ---------------------------------------------------------------------------


def pytest_tool() -> Tool:
    """Return the ``sandbox_pytest`` tool (executes pytest in a sandbox)."""
    return Tool(
        name="sandbox_pytest",
        description=(
            "Run pytest against a test path inside a sandbox workspace. "
            "Never targets the real repository. Captures a bounded result. "
            "Governed: cannot run arbitrary shell commands or escape the "
            "sandbox workspace."
        ),
        parameters=[
            ToolParameter(
                name="workspace",
                description="Absolute path of a minted sandbox workspace.",
                type_hint="string",
                required=True,
            ),
            ToolParameter(
                name="target",
                description="Relative path to a test file/folder inside the "
                "workspace (default: run all tests in the workspace).",
                type_hint="string",
                required=False,
            ),
            ToolParameter(
                name="timeout_seconds",
                description=(
                    f"Max run time in seconds (default {DEFAULT_TIMEOUT_SECONDS:g}, "
                    f"max {MAX_TIMEOUT_SECONDS:g})."
                ),
                type_hint="number",
                required=False,
            ),
        ],
        category="code",
        handler=run_pytest_in_sandbox,
        tags=["sandbox", "governed", "test", "pytest", "evolution"],
        metadata={"evolution_tool": True, "operation": "pytest", "read_only": False},
    )


def git_status_tool() -> Tool:
    """Return the ``sandbox_git_status`` tool (read-only, sandbox-only)."""
    return Tool(
        name="sandbox_git_status",
        description=(
            "Run git status read-only inside a sandbox workspace. "
            "Never commits, pushes, resets, or mutates repository state."
        ),
        parameters=[
            ToolParameter(
                name="workspace",
                description="Path of a minted sandbox workspace.",
                type_hint="string",
                required=True,
            ),
            ToolParameter(
                name="path",
                description="Optional confined relative path to scope the status.",
                type_hint="string",
                required=False,
            ),
            ToolParameter(
                name="timeout_seconds",
                description=f"Max run time in seconds (default {DEFAULT_TIMEOUT_SECONDS:g}).",
                type_hint="number",
                required=False,
            ),
        ],
        category="code",
        handler=inspect_git_status_in_sandbox,
        tags=["sandbox", "governed", "git", "inspect", "evolution"],
        metadata={"sandbox_tool": True, "operation": "git_status", "read_only": True},
    )


def git_diff_tool() -> Tool:
    """Return the ``sandbox_git_diff`` tool (read-only, sandbox-only)."""
    return Tool(
        name="sandbox_git_diff",
        description=(
            "Run git diff read-only inside a sandbox workspace. "
            "Never mutates repository state and rejects arbitrary git "
            "subcommands (commit/push/reset/checkout are unsupported)."
        ),
        parameters=[
            ToolParameter(
                name="workspace",
                description="Path of a minted sandbox workspace.",
                type_hint="string",
                required=True,
            ),
            ToolParameter(
                name="path",
                description="Optional relative path to limit the diff.",
                type_hint="string",
                required=False,
            ),
            ToolParameter(
                name="timeout_seconds",
                description=f"Timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS:g}).",
                type_hint="number",
                required=False,
            ),
        ],
        category="code",
        handler=inspect_git_diff_in_sandbox,
        tags=["sandbox", "governed", "git", "inspect", "evolution"],
        metadata={"sandbox_tool": True, "operation": "git_diff", "read_only": True},
    )


#: The fixed set of E4 sandbox tool names.
SANDBOX_TOOL_NAMES: tuple[str, ...] = (
    "sandbox_pytest",
    "sandbox_git_status",
    "sandbox_git_diff",
)


def sandbox_tools() -> list[Tool]:
    """Return the three E4 sandbox tools."""
    return [pytest_tool(), git_status_tool(), git_diff_tool()]


def register_sandbox_tools(registry) -> list[Tool]:
    """Register the E4 sandbox tools into an existing Registry.

    Args:
        registry: An instance conforming to the ``atlas.tools.registry``
            register(name=...) contract (a ``ToolRegistry``).

    Returns:
        The list of registered tools.

    Raises:
        ValueError: If any E4 tool name is already registered.
    """
    tools = sandbox_tools()
    for tool in tools:
        registry.register(tool)
    return tools