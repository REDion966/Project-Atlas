"""Atlas Evolution — Transactional Promotion Executor (Phase 5.2).

A tightly-bounded, OWNER-authorized, path-confined executor that applies a
validated :class:`~atlas.evolution.promotion_artifact.PromotionArtifact` into
the live repository as a single TRANSACTION:

  1. validate the complete changeset (paths, confinement, sensitive modules);
  2. require every live target to still match its captured pre-state/hash
     (stale/drifted targets are REFUSED — never overwritten or merged);
  3. snapshot all affected paths;
  4. apply the complete set;
  5. read back and verify the complete set;
  6. only then record a version + audit and mark PROMOTED.

On any failure the ENTIRE changeset is restored, and the rollback itself is
verified; if rollback cannot be verified the executor fails closed with
``ROLLBACK_UNVERIFIED`` and never claims a successful rollback or promotion.

This is a SEPARATE, explicit seam. It does not touch
``EvolutionExecutionGateway`` (whose CODE refusal is preserved), does not
register CODE on the applier registry, and never calls
``AuthorizationManager.authorize_autonomously``.

Pure filesystem + hashing. No AI, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

from atlas.evolution.autonomy.code_sandbox import SandboxPathError
from atlas.evolution.promotion_artifact import (
    PromotionArtifact,
    PromotionFileEntry,
    _resolve,
    hash_content,
)
from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES


class PromotionOutcome(str, Enum):
    """Terminal outcome of one promotion attempt."""

    PROMOTED = "promoted"
    REFUSED_UNAUTHORIZED = "refused_unauthorized"
    REFUSED_INVALID = "refused_invalid"
    REFUSED_STALE = "refused_stale"
    FAILED_ROLLED_BACK = "failed_rolled_back"
    ROLLBACK_UNVERIFIED = "rollback_unverified"


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Result of a promotion attempt (bounded, JSON-safe projection)."""

    outcome: PromotionOutcome
    detail: str = ""
    promoted_files: tuple[str, ...] = ()
    version_id: str = ""
    audit_id: str = ""
    activation_id: str = ""
    activated_capabilities: tuple[str, ...] = ()
    rollback_verified: bool | None = None
    completed_at: datetime = field(default_factory=datetime.now)

    @property
    def ok(self) -> bool:
        return self.outcome is PromotionOutcome.PROMOTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "detail": self.detail,
            "promoted_files": list(self.promoted_files),
            "version_id": self.version_id,
            "audit_id": self.audit_id,
            "activation_id": self.activation_id,
            "activated_capabilities": list(self.activated_capabilities),
            "rollback_verified": self.rollback_verified,
            "completed_at": self.completed_at.isoformat(),
        }


class PromotionExecutor:
    """Owns the transactional, consistency-checked promotion write.

    Args:
        repo_root: The live repository root (path-confined target).
        authorization_checker: Optional EXTRA callable(artifact) -> bool; when
            wired, promotion requires it to pass in addition to ``authorized``.
        version_recorder: Optional callable(artifact, result) -> str id,
            invoked only on success (fail-soft: an error does not corrupt the
            promoted state, but is reported).
        audit_recorder: Optional callable(artifact, result) -> str id.
        sensitive_prefixes: Architecture-sensitive module prefixes.
        allow_sensitive: When False (default), sensitive paths are refused.
    """

    def __init__(
        self,
        repo_root: str | Path,
        *,
        authorization_checker: Callable[[Any], bool] | None = None,
        version_recorder: Callable[[Any, Any], str] | None = None,
        audit_recorder: Callable[[Any, Any], str] | None = None,
        activator: Callable[[Any], Any] | None = None,
        sensitive_prefixes: Iterable[str] = ARCHITECTURE_SENSITIVE_PREFIXES,
        allow_sensitive: bool = False,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._authorization_checker = authorization_checker
        self._version_recorder = version_recorder
        self._audit_recorder = audit_recorder
        self._activator = activator
        self._sensitive_prefixes = tuple(sensitive_prefixes)
        self._allow_sensitive = allow_sensitive

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def promote(self, artifact: Any, *, authorized: bool) -> PromotionResult:
        """Apply ``artifact`` transactionally (OWNER-authorized only)."""
        if not authorized:
            return PromotionResult(
                PromotionOutcome.REFUSED_UNAUTHORIZED,
                "promotion is OWNER-only; not authorized",
            )
        if not self._repo_root.is_dir():
            return PromotionResult(
                PromotionOutcome.REFUSED_INVALID,
                "live repository root is not available",
            )
        if not isinstance(artifact, PromotionArtifact) or not artifact.files:
            return PromotionResult(
                PromotionOutcome.REFUSED_INVALID, "empty or malformed artifact"
            )
        if self._authorization_checker is not None:
            try:
                if not self._authorization_checker(artifact):
                    return PromotionResult(
                        PromotionOutcome.REFUSED_UNAUTHORIZED,
                        "authorization checker refused promotion",
                    )
            except Exception as exc:
                return PromotionResult(
                    PromotionOutcome.REFUSED_UNAUTHORIZED,
                    f"authorization check failed ({type(exc).__name__})",
                )

        # 1. Validate the complete changeset (no mutation on failure).
        invalid = self._validate_changeset(artifact)
        if invalid is not None:
            return PromotionResult(PromotionOutcome.REFUSED_INVALID, invalid)

        # 2. Pre-state consistency — refuse stale/drifted targets.
        stale = self._check_pre_state(artifact)
        if stale is not None:
            return PromotionResult(PromotionOutcome.REFUSED_STALE, stale)

        # 3. Snapshot all affected paths.
        snapshot = {entry.path: entry.pre_state for entry in artifact.files}

        # 4. Apply the complete set.
        try:
            for entry in artifact.files:
                self._write(entry.path, entry.post_content)
        except Exception as exc:
            return self._rollback(
                artifact, snapshot,
                f"apply failed: {type(exc).__name__}: {exc}",
            )

        # 5. Read-back verify the complete set.
        bad = self._verify_post_state(artifact)
        if bad is not None:
            return self._rollback(artifact, snapshot, f"verification failed: {bad}")

        # 6. Record the CODE version (required when a recorder is wired) and the
        #    audit record, then mark PROMOTED. A version-recording failure must
        #    NOT falsely report PROMOTED: restore the entire changeset and fail
        #    closed (rollback verified, as everywhere else).
        try:
            version_id = self._record_version(artifact)
        except Exception as exc:
            return self._rollback(
                artifact, snapshot,
                f"version recording failed: {type(exc).__name__}: {exc}",
            )
        if self._version_recorder is not None and not version_id:
            return self._rollback(
                artifact, snapshot, "version recording produced no version id"
            )

        # 7. Capability activation (bounded; only for declared capability
        #    modules). Registration on the existing registry must succeed
        #    BEFORE the promotion is reported — otherwise restore the entire
        #    changeset and fail closed (never a false "activated" success).
        activation_id = ""
        activated_capabilities: tuple[str, ...] = ()
        if callable(self._activator):
            try:
                activation = self._activator(artifact)
            except Exception as exc:
                return self._rollback(
                    artifact, snapshot,
                    f"capability activation failed: {type(exc).__name__}: {exc}",
                )
            activated_capabilities = tuple(
                getattr(activation, "capabilities", ()) or ()
            )
            activation_id = str(getattr(activation, "audit_id", "") or "")

        audit_id = self._record_audit(artifact)
        promoted = tuple(entry.path for entry in artifact.files)
        return PromotionResult(
            PromotionOutcome.PROMOTED,
            "changeset promoted",
            promoted_files=promoted,
            version_id=version_id,
            audit_id=audit_id,
            activation_id=activation_id,
            activated_capabilities=activated_capabilities,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _validate_changeset(self, artifact: PromotionArtifact) -> str | None:
        seen: set[str] = set()
        for entry in artifact.files:
            if not isinstance(entry, PromotionFileEntry):
                return "malformed artifact entry"
            if entry.path in seen:
                return f"duplicate path: {entry.path!r}"
            seen.add(entry.path)
            try:
                _resolve(self._repo_root, entry.path)
            except SandboxPathError as exc:
                return f"path rejected: {entry.path!r} ({exc})"
            dotted = entry.path.replace("\\", "/").rsplit(".", 1)[0].replace("/", ".")
            if not self._allow_sensitive and any(
                dotted.startswith(prefix) for prefix in self._sensitive_prefixes
            ):
                return f"architecture-sensitive path refused: {entry.path!r}"
            if hash_content(entry.post_content) != entry.post_hash:
                return f"post-hash mismatch in artifact for {entry.path!r}"
        return None

    def _check_pre_state(self, artifact: PromotionArtifact) -> str | None:
        for entry in artifact.files:
            target = _resolve(self._repo_root, entry.path)
            if entry.pre_state is None:
                if target.exists():
                    return f"target unexpectedly present: {entry.path!r}"
                continue
            if not target.is_file():
                return f"target missing: {entry.path!r}"
            try:
                live = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                return f"cannot read live target {entry.path!r}: {exc}"
            if hash_content(live) != entry.pre_hash:
                return f"live target drifted (stale): {entry.path!r}"
        return None

    def _verify_post_state(self, artifact: PromotionArtifact) -> str | None:
        for entry in artifact.files:
            target = _resolve(self._repo_root, entry.path)
            if not target.is_file():
                return f"missing after apply: {entry.path!r}"
            try:
                live = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                return f"cannot read back {entry.path!r}: {exc}"
            if hash_content(live) != entry.post_hash:
                return f"content mismatch after apply: {entry.path!r}"
        return None

    def _write(self, rel_path: str, content: str) -> None:
        target = _resolve(self._repo_root, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _restore(self, rel_path: str, pre_state: str | None) -> None:
        target = _resolve(self._repo_root, rel_path)
        if pre_state is None:
            if target.is_file():
                target.unlink()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(pre_state, encoding="utf-8")

    def _rollback(
        self,
        artifact: PromotionArtifact,
        snapshot: dict[str, str | None],
        reason: str,
    ) -> PromotionResult:
        """Restore the entire changeset and VERIFY the rollback."""
        try:
            for entry in artifact.files:
                self._restore(entry.path, snapshot.get(entry.path))
        except Exception as exc:
            return PromotionResult(
                PromotionOutcome.ROLLBACK_UNVERIFIED,
                f"{reason}; rollback raised: {type(exc).__name__}",
                rollback_verified=False,
            )

        for entry in artifact.files:
            target = _resolve(self._repo_root, entry.path)
            expected = snapshot.get(entry.path)
            if expected is None:
                if target.exists():
                    return PromotionResult(
                        PromotionOutcome.ROLLBACK_UNVERIFIED,
                        f"{reason}; rollback unverified (residual) {entry.path!r}",
                        rollback_verified=False,
                    )
                continue
            if not target.is_file() or hash_content(
                target.read_text(encoding="utf-8")
            ) != hash_content(expected):
                return PromotionResult(
                    PromotionOutcome.ROLLBACK_UNVERIFIED,
                    f"{reason}; rollback unverified {entry.path!r}",
                    rollback_verified=False,
                )

        return PromotionResult(
            PromotionOutcome.FAILED_ROLLED_BACK,
            f"{reason}; entire changeset restored and verified",
            rollback_verified=True,
        )

    def _record_version(self, artifact: PromotionArtifact) -> str:
        """Record the CODE version; raises on failure (never swallowed).

        When no ``version_recorder`` is wired the executor is running
        standalone (tests); version recording is then skipped and ``""`` is
        returned. When a recorder IS wired, a raised error or an empty result
        is treated as a failure by :meth:`promote`.
        """
        if not callable(self._version_recorder):
            return ""
        return str(self._version_recorder(artifact) or "")

    def _record_audit(self, artifact: PromotionArtifact) -> str:
        """Best-effort audit record (never breaks a successful promotion)."""
        if not callable(self._audit_recorder):
            return ""
        try:
            return str(self._audit_recorder(artifact) or "")
        except Exception:
            return ""
