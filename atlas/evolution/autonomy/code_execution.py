"""
Atlas Evolution Autonomy — Code Execution — Phase E2

The smallest governed execution foundation for bounded CODE changes.

Contains:
  - :class:`CodeApplier` — implements the existing ``Applier`` protocol for
    ``ScopeType.CODE``, operating entirely inside a :class:`CodeSandbox`.
  - :class:`SandboxCodeExecutor` — the orchestration seam that turns a
    validated ``CodeChangeSet`` into a sandboxed lifecycle:
    sandbox creation → snapshot → apply → verify → accept OR rollback.

CRITICAL INVARIANT — this module NEVER touches the real repository. All
filesystem access is confined to the disposable ``CodeSandbox`` root, which
is created beneath the system temp dir (or an explicit ``base_dir``) and
removed on cleanup. The executor returns a structured result; it does not
write to the repository, run arbitrary commands, or mint its own
authorization.

The CODE scope remains constitutionally protected in the existing Phase 16
state machine (``scope_classifier.STATE_SCOPES`` excludes it; ``AuthorizationManager``
refuses it unconditionally). E2 deliberately does NOT reopen that boundary;
this execution foundation is the mechanics a later, explicitly approved
governance decision may connect to the authorized request lifecycle.

Pure infrastructure. No gateway. No AI. No kernel access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.applier import (
    ApplyResult,
    SnapshotStorage,
    StateReader,
    StateWriter,
    _checksum,
)
from atlas.evolution.autonomy.code_sandbox import (
    CodeChangeSet,
    CodeSandbox,
)
from atlas.evolution.autonomy.models import (
    ChangeReceipt,
    EvolutionRequest,
    RollbackPlan,
    RollbackStrategy,
    VerificationResult,
)
from atlas.evolution.governance.models import ScopeType


class CodeApplier:
    """Applier for CODE-scope evolution requests inside a CodeSandbox.

    Conforms to the existing ``Applier`` protocol so it can be registered on
    the ``ApplierRegistry`` when a governance decision deliberately opens the CODE
    boundary. Until then it is exercised directly by the
    ``SandboxCodeExecutor`` (and tests).

    Payload shape (``change_payload``):
        ``{"code_changes": [{"path": "rel/path.py", "content": "..."}]}``
    """

    scope = ScopeType.CODE

    def supports(self, scope: ScopeType) -> bool:
        """Return True when this applier handles the CODE scope."""
        return scope == self.scope

    def can_apply(
        self,
        request: EvolutionRequest,
        reader: StateReader,
    ) -> bool:
        """Pre-check: the request targets CODE and carries a valid payload."""
        if request.target_scope != self.scope:
            return False
        try:
            CodeChangeSet.from_payload(request.change_payload)
        except Exception:
            return False
        return True

    def capture_snapshot(
        self,
        request_id: str,
        reader: StateReader,
        storage: SnapshotStorage,
        now: datetime | None = None,
    ) -> RollbackPlan:
        """Capture a store-level snapshot of the sandbox before mutation."""
        when = now if now is not None else datetime.now()
        snapshot_id = f"snap-code-{request_id}-{int(when.timestamp())}"
        snapshot_data = {"domain": "code", "keys": {}}
        storage.store_snapshot(
            snapshot_id=snapshot_id,
            request_id=request_id,
            snapshot_data=snapshot_data,
            checksum=_checksum(snapshot_data),
            created_at=when.isoformat(),
        )
        return RollbackPlan(
            strategy=RollbackStrategy.SNAPSHOT,
            snapshot_ref=snapshot_id,
            inverse_description="Restore sandbox snapshot before code change",
            steps=["restore sandbox files from snapshot"],
        )

    def apply(
        self,
        request: EvolutionRequest,
        writer: StateWriter,
        now: datetime | None = None,
    ) -> ApplyResult:
        """Apply a validated CodeChangeSet to the sandbox writer."""
        try:
            changeset = CodeChangeSet.from_payload(request.change_payload)
        except Exception as exc:
            return ApplyResult(
                success=False,
                error=f"Invalid code change payload: {exc}",
            )
        when = now if now is not None else datetime.now()
        changed_keys: list[str] = []
        after_refs: dict[str, Any] = {}
        for change in changeset.changes:
            change.validate()
            writer.write(change.path, change.content)
            changed_keys.append(change.path)
            after_refs[change.path] = change.content

        receipt = ChangeReceipt(
            request_id=request.request_id,
            changed_keys=changed_keys,
            before_refs={},
            after_refs=after_refs,
            version_delta="+0.0.1",
            target_tags=["code"],
            applied_at=when,
        )
        return ApplyResult(
            success=True,
            receipt=receipt,
            terminal_status="COMPLETED",
        )

    def verify(
        self,
        request: EvolutionRequest,
        reader: StateReader,
        now: datetime | None = None,
    ) -> VerificationResult:
        """Read-back probe: every changed path exists with matching content."""
        try:
            changeset = CodeChangeSet.from_payload(request.change_payload)
        except Exception:
            return VerificationResult(
                passed=False,
                checks=[],
                details="Invalid code change payload during verification",
                scope=self.scope,
                verified_at=now if now is not None else datetime.now(),
            )
        checks: list[dict[str, Any]] = []
        all_ok = True
        for change in changeset.changes:
            present = reader.has(change.path)
            current = reader.read(change.path, default=None)
            content_match = current == change.content
            checks.append(
                {
                    "path": change.path,
                    "present": present,
                    "content_match": content_match,
                }
            )
            if not present or not content_match:
                all_ok = False
        return VerificationResult(
            passed=all_ok,
            checks=checks,
            details=(
                "All code change files present and matching"
                if all_ok
                else "Code change verification failed"
            ),
            scope=self.scope,
            verified_at=now if now is not None else datetime.now(),
        )


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    """Structured result of a sandboxed CODE execution attempt.

    Attributes:
        success: True only when apply + verify both succeeded.
        applied_files: The ordered paths that were applied.
        verification: The VerificationResult produced by the read-back probe.
        rollback_occurred: True when a failed attempt was rolled back.
        sandbox_path: The absolute sandbox root path (existed during the
            attempt; cleaned up after).
        error: Human-readable failure reason, or "" on success.
    """

    success: bool
    applied_files: list[str] = field(default_factory=list)
    verification: VerificationResult | None = None
    rollback_occurred: bool = False
    sandbox_path: str = ""
    error: str = ""


class SandboxCodeExecutor:
    """Runs a validated CodeChangeSet through the full sandboxed lifecycle.

    The executor owns the sandbox lifecycle (create → snapshot → apply →
    verify → accept OR rollback → cleanup). It never touches the real
    repository and never grants authorization — it is the mechanics that a
    future approved governance decision can connect to an authorized
    ``EvolutionRequest``.

    Args:
        base_dir: Optional base directory beneath which the sandbox root is
            created. Defaults to the system temporary directory.
        seed: Optional mapping of relative path → initial content, written
            into the sandbox before the snapshot so rollback can be proven
            to restore prior state.
        post_apply_hook: Optional ``Callable[[CodeSandbox], None]`` invoked
            after ``apply`` and before ``verify``. Intended for tests to
            simulate post-apply corruption (or for future verification
            providers); returning normally leaves the sandbox untouched.
    """

    def __init__(
        self,
        base_dir: str | None = None,
        seed: dict[str, str] | None = None,
        post_apply_hook=None,
    ) -> None:
        self._base_dir = base_dir
        self._seed = seed or {}
        self._post_apply_hook = post_apply_hook

    def execute(
        self,
        request: EvolutionRequest,
        now: datetime | None = None,
    ) -> SandboxExecutionResult:
        """Execute a CODE EvolutionRequest inside a disposable sandbox."""
        if request.target_scope != ScopeType.CODE:
            return SandboxExecutionResult(
                success=False,
                error="Request is not CODE-scoped",
            )

        # Validate the payload once up front for a deterministic error.
        try:
            changeset = CodeChangeSet.from_payload(request.change_payload)
        except Exception as exc:
            return SandboxExecutionResult(
                success=False,
                error=f"Invalid code change payload: {exc}",
            )

        applier = CodeApplier()
        with CodeSandbox(base_dir=self._base_dir) as sandbox:
            # Seed optional initial state (proves restore restores it).
            for path, content in self._seed.items():
                sandbox.write_text(path, content)

            reader = sandbox.reader()
            writer = sandbox.writer()

            # Capture prior state for rollback.
            paths = [change.path for change in changeset.changes]
            snapshot = sandbox.snapshot(paths)

            # Apply.
            result = applier.apply(request, writer, now=now)
            if not result.success:
                sandbox.restore(snapshot)
                return SandboxExecutionResult(
                    success=False,
                    applied_files=paths,
                    rollback_occurred=True,
                    sandbox_path=str(sandbox.root),
                    error=result.error,
                )

            # Post-apply hook: run after apply, before verify (test seam).
            if self._post_apply_hook is not None:
                self._post_apply_hook(sandbox)

            # Verify.
            verification = applier.verify(request, reader, now=now)
            if not verification.passed:
                sandbox.restore(snapshot)
                return SandboxExecutionResult(
                    success=False,
                    applied_files=paths,
                    verification=verification,
                    rollback_occurred=True,
                    sandbox_path=str(sandbox.root),
                    error="Verification failed; sandbox restored",
                )

            return SandboxExecutionResult(
                success=True,
                applied_files=paths,
                verification=verification,
                sandbox_path=str(sandbox.root),
            )