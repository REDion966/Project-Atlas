"""Atlas Evolution — Promotion Artifact (Phase 5.2).

Captures, at development-execution time (before the disposable sandbox
disappears), the COMPLETE post-change content and the per-path PRE-change
state + hashes required for a safe, consistency-checked promotion.

The pre-change state is read from the live repository, which development never
mutates (development runs only inside a disposable sandbox), so capturing
after a run is faithful. Nothing is overwritten or merged here.

Pure filesystem READ + hashing. No AI, no network, no writes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from atlas.evolution.autonomy.code_sandbox import CodeChangeSet, SandboxPathError

#: Maximum number of files a promotion artifact may carry.
MAX_ARTIFACT_FILES: int = 20


def hash_content(content: str) -> str:
    """Return the deterministic sha256 hex digest of ``content``."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _resolve(repo_root: Path, rel_path: str) -> Path:
    """Resolve ``rel_path`` strictly inside ``repo_root`` (fail-closed)."""
    CodeChangeSet.validate_path(rel_path)
    root = repo_root.resolve()
    candidate = (root / rel_path.replace("\\", "/")).resolve()
    if candidate != root and root not in candidate.parents:
        raise SandboxPathError("resolved path escapes the repository root")
    return candidate


@dataclass(frozen=True, slots=True)
class PromotionFileEntry:
    """One file's pre/post state within a promotion artifact."""

    path: str
    pre_state: str | None  # None == the file did not exist
    pre_hash: str
    post_content: str
    post_hash: str

    @property
    def is_new(self) -> bool:
        return self.pre_state is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "pre_state": "ABSENT" if self.pre_state is None else "present",
            "pre_hash": self.pre_hash,
            "post_hash": self.post_hash,
            "post_size": len(self.post_content),
        }


@dataclass(frozen=True, slots=True)
class PromotionArtifact:
    """A validated, hash-bound changeset captured for governed promotion."""

    artifact_id: str
    proposal_id: str
    files: tuple[PromotionFileEntry, ...] = ()
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "proposal_id": self.proposal_id,
            "files": [entry.to_dict() for entry in self.files],
            "created_at": self.created_at.isoformat(),
        }


class PromotionArtifactError(ValueError):
    """Raised when a changeset cannot be captured as a promotion artifact."""


def capture_promotion_artifact(
    changed_contents: Iterable[Any],
    *,
    proposal_id: str,
    repo_root: str | Path,
    now: datetime | None = None,
) -> PromotionArtifact:
    """Capture a promotion artifact for ``changed_contents``.

    ``changed_contents`` is the sandbox workload's ``code_changes``-shaped
    sequence of ``{"path": ..., "content": ...}`` dicts. Fails closed on
    malformed/duplicate paths, path escape, or an over-large changeset.
    """
    root = Path(repo_root)
    if not root.is_dir():
        raise PromotionArtifactError("repository root is not a directory")

    entries: list[PromotionFileEntry] = []
    seen: set[str] = set()
    for item in changed_contents or ():
        if not isinstance(item, dict):
            raise PromotionArtifactError("each change must be an object")
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not path.strip():
            raise PromotionArtifactError("each change needs a non-empty 'path'")
        if not isinstance(content, str):
            raise PromotionArtifactError("each change needs a string 'content'")
        rel = path.strip().replace("\\", "/")
        if rel in seen:
            raise PromotionArtifactError(f"duplicate change path: {rel!r}")
        seen.add(rel)
        try:
            target = _resolve(root, rel)
        except SandboxPathError as exc:
            raise PromotionArtifactError(f"path rejected: {rel!r} ({exc})") from exc

        if target.is_file():
            try:
                pre_state: str | None = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise PromotionArtifactError(
                    f"cannot read pre-state for {rel!r}: {exc}"
                ) from exc
            pre_hash = hash_content(pre_state)
        else:
            pre_state = None
            pre_hash = hash_content("")  # hash of the ABSENT sentinel

        entries.append(
            PromotionFileEntry(
                path=rel,
                pre_state=pre_state,
                pre_hash=pre_hash,
                post_content=content,
                post_hash=hash_content(content),
            )
        )

    if not entries:
        raise PromotionArtifactError("no changes to capture")
    if len(entries) > MAX_ARTIFACT_FILES:
        raise PromotionArtifactError(
            f"artifact exceeds {MAX_ARTIFACT_FILES} files"
        )

    entries.sort(key=lambda entry: entry.path)
    stamp = now or datetime.now()
    artifact_id = "promoart:" + hashlib.sha256(
        (
            f"{proposal_id}:{stamp.isoformat()}:"
            + "|".join(e.path for e in entries)
        ).encode("utf-8")
    ).hexdigest()[:16]
    return PromotionArtifact(
        artifact_id=artifact_id,
        proposal_id=proposal_id,
        files=tuple(entries),
        created_at=stamp,
    )
