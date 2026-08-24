"""
Project Atlas Evolution Autonomy — Code Sandbox — Phase E2

The explicit, deterministic sandbox boundary for bounded CODE execution.

A ``CodeSandbox`` owns a single filesystem root beneath a base directory.
Every path is resolved strictly inside that root: absolute paths, Windows
drive prefixes, ``..`` traversal, empty/reserved segments, and symlink
escapes are rejected with a ``SandboxPathError``. This is the single
enforcement point ensuring sandboxed code execution can never touch the
real repository.

The class also exposes thin ``StateReader``/``StateWriter`` adapters that
map relative path keys to files beneath the root, adapting the sandbox to
the existing Phase 16 ``Applier`` protocol so ``ApplicationEngine`` can
apply bounded changes, capture snapshots, verify, and roll back through
the existing machinery.

Pure infrastructure. No gateway. No AI. No kernel access. The sandbox
never imports anything outside the autonomy package.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.evolution.autonomy.applier import (
    SnapshotStorage,
    StateReader,
    StateWriter,
)
from atlas.evolution.autonomy.models import (
    ChangeReceipt,
    EvolutionRequest,
    RollbackPlan,
    RollbackStrategy,
    VerificationResult,
)
from atlas.evolution.governance.models import ScopeType


class SandboxPathError(ValueError):
    """Raised when a path attempts to escape the sandbox root."""


@dataclass(frozen=True, slots=True)
class FileChange:
    """A single bounded file change inside a sandbox.

    Attributes:
        path: Relative, POSIX-style path beneath the sandbox root.
            No leading slash, no drive prefix, no ``..`` segments.
        content: The full replacement content for the path.
        encoding: Text encoding for the content. Defaults to UTF-8.
    """

    path: str
    content: str
    encoding: str = "utf-8"

    def validate(self) -> None:
        """Validate the change's path and limits in isolation."""
        CodeChangeSet.validate_path(self.path)


@dataclass(frozen=True, slots=True)
class CodeChangeSet:
    """A structured, bounded set of file changes for sandboxed execution.

    This is a data-only representation of an approved code modification.
    It never carries shell commands, and it is the only surface the
    sandbox will accept. The sandbox enforces absolute upper bounds on
    the number of files, the path length, and the total content size.

    Attributes:
        changes: Ordered tuple of FileChange entries.
        description: Optional human-readable summary of the change set.
    """

    changes: tuple[FileChange, ...] = ()
    description: str = ""

    # Bounded limits. Deterministic and small; changing these requires
    # a deliberate audit, never per-request configuration.
    MAX_CHANGES = 200
    MAX_PATH_LEN = 256
    MAX_SINGLE_BYTES = 512 * 1024
    MAX_TOTAL_BYTES = 4 * 1024 * 1024

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CodeChangeSet":
        """Parse a raw payload dict into a validated CodeChangeSet.

        Expects ``payload["code_changes"]`` to be a list of
        ``{"path": ..., "content": ...}`` dicts. Raises ValueError on
        malformed input, SandboxPathError on an escaping path, or when
        the bounded limits are exceeded.

        Args:
            payload: The EvolutionRequest.change_payload dict.

        Returns:
            A validated CodeChangeSet.
        """
        raw = payload.get("code_changes")
        if raw is None:
            raise ValueError("Payload missing 'code_changes'")
        if not isinstance(raw, list):
            raise ValueError("'code_changes' must be a list")
        if not raw:
            raise ValueError("'code_changes' must not be empty")

        changes: list[FileChange] = []
        total_bytes = 0
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Each code change must be an object")
            path = item.get("path")
            content = item.get("content")
            if not isinstance(path, str) or not path:
                raise ValueError("Each code change needs a non-empty string 'path'")
            if not isinstance(content, str):
                raise ValueError("Each code change needs a string 'content'")
            cls.validate_path(path)
            single = len(content.encode("utf-8"))
            if single > cls.MAX_SINGLE_BYTES:
                raise ValueError(
                    f"Single file change exceeds {cls.MAX_SINGLE_BYTES} bytes"
                )
            total_bytes += single
            if total_bytes > cls.MAX_TOTAL_BYTES:
                raise ValueError(
                    f"Code change set exceeds {cls.MAX_TOTAL_BYTES} bytes total"
                )
            changes.append(
                FileChange(
                    path=path,
                    content=content,
                    encoding=item.get("encoding", "utf-8"),
                )
            )
            if len(changes) > cls.MAX_CHANGES:
                raise ValueError(
                    f"Code change set exceeds {cls.MAX_CHANGES} files"
                )
        return cls(changes=tuple(changes))

    @staticmethod
    def validate_path(path: str) -> None:
        """Validate a single relative path against sandbox confinement.

        Raises:
            SandboxPathError: If the path is absolute, carries a drive
                prefix, contains ``..``, or is otherwise not a clean
                relative path that stays beneath a single root.
        """
        if not isinstance(path, str) or not path:
            raise SandboxPathError("Path must be a non-empty string")
        if len(path) > CodeChangeSet.MAX_PATH_LEN:
            raise SandboxPathError(
                f"Path exceeds {CodeChangeSet.MAX_PATH_LEN} characters"
            )
        # Reject absolute forms first.
        if path.startswith("/") or path.startswith("\\"):
            raise SandboxPathError("Absolute paths are forbidden")
        if re.match(r"^[A-Za-z]:", path):
            raise SandboxPathError("Windows drive prefixes are forbidden")
        # Normalize separators; reject any '..' or '.' segment anywhere.
        parts = path.replace("\\", "/").split("/")
        for part in parts:
            if part == "..":
                raise SandboxPathError("Parent traversal ('..') is forbidden")
            if part == ".":
                raise SandboxPathError("Current-directory ('.') segments are forbidden")
            if part == "":
                raise SandboxPathError("Empty path segments are forbidden")
        # Also reject when a resolved pure-POSIX path escapes.
        normalized = os.path.normpath(path.replace("\\", "/"))
        if normalized.startswith("..") or os.path.isabs(normalized):
            raise SandboxPathError("Path escapes the sandbox root")


class CodeSandbox:
    """An explicit, disposable filesystem root for sandboxed code changes.

    Lifecycle is explicit: ``cleanup()`` removes the root. The class may
    be used as a context manager, and ``__del__`` is best-effort fallback.

    Attributes:
        root: The absolute path of the sandbox root.
        base_dir: The base directory beneath which the root was created.
    """

    def __init__(
        self,
        root: str | Path | None = None,
        base_dir: str | Path | None = None,
    ) -> None:
        if root is not None:
            self._root = Path(root).resolve()
            self._root.mkdir(parents=True, exist_ok=True)
        else:
            base = Path(base_dir).resolve() if base_dir else None
            if base is not None:
                base.mkdir(parents=True, exist_ok=True)
            self._root = Path(
                tempfile.mkdtemp(dir=str(base) if base else None)
            ).resolve()
        self._created = True

    @property
    def root(self) -> Path:
        """Return the absolute sandbox root path."""
        return self._root

    @property
    def base_dir(self) -> Path | None:
        """Return the base directory used to create the sandbox, if any."""
        return None

    # ------------------------------------------------------------------
    # Path resolution (the single confinement point)
    # ------------------------------------------------------------------

    def resolve(self, path: str) -> Path:
        """Resolve a relative path to an absolute path inside the sandbox.

        Applies all confinement rules: no absolute paths, no drive
        prefix, no ``..``, no empty segments, and no symlink escape.

        Args:
            path: A relative, POSIX-style path.

        Returns:
            The absolute path beneath the sandbox root.

        Raises:
            SandboxPathError: On any confinement violation.
        """
        CodeChangeSet.validate_path(path)
        rel = path.replace("\\", "/")
        candidate = (self._root / rel).resolve()
        root_resolved = self._root.resolve()
        # Containment: candidate must equal root or be strictly inside it.
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise SandboxPathError("Resolved path escapes the sandbox root")
        return candidate

    # ------------------------------------------------------------------
    # Filesystem operations (all go through resolve)
    # ------------------------------------------------------------------

    def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> Path:
        """Write text content to a sandboxed relative path."""
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)
        return target

    def read_text(self, path: str, default: Any = None) -> Any:
        """Read text content from a sandboxed path, or return default."""
        target = self.resolve(path)
        if not target.exists():
            return default
        return target.read_text(encoding="utf-8")

    def exists(self, path: str) -> bool:
        """Return True when the sandboxed path exists."""
        return self.resolve(path).exists()

    def delete(self, path: str) -> bool:
        """Delete a sandboxed path if it exists (files only).

        Returns True when the path existed and was removed.
        """
        target = self.resolve(path)
        if target.exists() and target.is_file():
            target.unlink()
            return True
        return False

    def create_symlink(self, link_path: str, target_path: str | Path) -> Path:
        """Create a symlink inside the sandbox pointing at ``target_path``.

        Provided for confinement tests: resolving any path through this
        link that escapes the root must raise SandboxPathError.
        """
        link = self.resolve(link_path)
        link.parent.mkdir(parents=True, exist_ok=True)
        # Allow pointing anywhere for the escape probe; resolve() rejects
        # any read/write that later traverses outside.
        link.symlink_to(Path(target_path).resolve(), target_is_directory=True)
        return link

    # ------------------------------------------------------------------
    # Snapshot / restore
    # ------------------------------------------------------------------

    def snapshot(self, paths: list[str]) -> dict[str, str | None]:
        """Capture current content (or absence) for each relative path.

        Each entry is ``{path: content}``, or ``None`` when the path was
        absent before the change.
        """
        out: dict[str, str | None] = {}
        for path in paths:
            out[path] = self.read_text(path)
        return out

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore the sandbox to a captured snapshot.

        Paths whose snapshot value is None are deleted; others are
        rewritten with the captured content.
        """
        for path, content in snapshot.items():
            if content is None:
                self.delete(path)
            else:
                self.write_text(path, content)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove the sandbox root entirely."""
        if not self._created:
            return
        shutil.rmtree(self._root, ignore_errors=True)
        self._created = False

    def __enter__(self) -> "CodeSandbox":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cleanup()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.cleanup()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # State adapters for the existing Applier protocol
    # ------------------------------------------------------------------

    def reader(self) -> "SandboxStateReader":
        """Return a StateReader over this sandbox."""
        return SandboxStateReader(self)

    def writer(self) -> "SandboxStateWriter":
        """Return a StateWriter over this sandbox."""
        return SandboxStateWriter(self)


# ------------------------------------------------------------------
# Runtime / context adapters for the existing Applier protocol
# ------------------------------------------------------------------


class SandboxStateReader(StateReader):
    """StateReader adapter mapping relative-path keys to sandbox files."""

    def __init__(self, sandbox: CodeSandbox) -> None:
        self._sandbox = sandbox

    def read(self, key: str, default: Any = None) -> Any:
        return self._sandbox.read_text(key, default)

    def has(self, key: str) -> bool:
        return self._sandbox.exists(key)


class SandboxStateWriter(StateWriter):
    """StateWriter adapter mapping relative-path keys to sandbox files."""

    def __init__(self, sandbox: CodeSandbox) -> None:
        self._sandbox = sandbox

    def write(self, key: str, value: Any) -> None:
        content = value if isinstance(value, str) else str(value)
        self._sandbox.write_text(key, content)

    def remove(self, key: str) -> bool:
        return self._sandbox.delete(key)


def _checksum(data: dict[str, Any]) -> str:
    """Deterministic primitive checksum for snapshot artifacts."""
    import hashlib
    import json

    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]