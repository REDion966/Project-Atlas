"""
Atlas Evolution Autonomy — Version Manager — Phase 16.6

Manages the append-only ``AtlasStateVersion`` manifest chain.

Responsibilities:
- Produce a genesis ``1.0.0`` manifest when autonomy is first enabled.
- Compute the next version given an applied ``EvolutionRequest`` and its
  ``ChangeReceipt``.
- Persist every new version to the injected storage.
- Surface the current version and per-scope version tags.

Per the architecture:
- major: execution-level advance or user-issued major bump.
- minor: capability register/enhance or new scope activation.
- patch: applied state change or rollback.
- Per-scope versions track blast radius for config, memory, knowledge,
  and each capability.
- The manifest is append-only; no destructive overwrites.

No gateway. No kernel. No AI. No scheduling. No runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    ChangeReceipt,
    EvolutionRequest,
)
from atlas.evolution.governance.models import ScopeType


class VersionStorage(Protocol):
    """Minimal storage surface for version persistence."""

    def store_version(self, version: AtlasStateVersion) -> None:
        ...

    def load_latest_version(self) -> AtlasStateVersion | None:
        ...


@dataclass(frozen=True, slots=True)
class VersionDelta:
    """Deterministic version change derived from a request + receipt."""

    bump_major: bool = False
    bump_minor: bool = False
    bump_patch: bool = False
    per_scope_bump: dict[str, str] = field(default_factory=dict)


class VersionManager:
    """Pure version-management engine.

    Constructor-injected ``storage`` implements ``VersionStorage``.
    An optional ``clock`` callable supports deterministic tests.
    """

    def __init__(
        self,
        storage: VersionStorage,
        clock: Any | None = None,
    ) -> None:
        self._storage = storage
        self._clock = clock if clock is not None else datetime.now

    @property
    def current_version(self) -> AtlasStateVersion | None:
        """Return the latest persisted version, or None."""
        return self._storage.load_latest_version()

    def ensure_genesis(self) -> AtlasStateVersion:
        """Return the current version; create genesis ``1.0.0`` if absent."""
        latest = self._storage.load_latest_version()
        if latest is not None:
            return latest
        genesis = AtlasStateVersion(
            major=1,
            minor=0,
            patch=0,
            manifest_id=self._manifest_id("genesis"),
            applied_request_ids=[],
            parent_version="",
            scope_versions={
                "config": "0",
                "memory": "0",
                "knowledge": "0",
                "capability": "0",
            },
            tags=["genesis"],
            created_at=self._clock(),
        )
        self._storage.store_version(genesis)
        return genesis

    def compute_next_version(
        self,
        request: EvolutionRequest,
        receipt: ChangeReceipt,
    ) -> AtlasStateVersion:
        """Compute the next manifest version from the latest version."""
        latest = self.ensure_genesis()
        delta = self._compute_delta(request, receipt)

        major = latest.major + (1 if delta.bump_major else 0)
        minor = latest.minor + (1 if delta.bump_minor else 0)
        patch = latest.patch + (1 if delta.bump_patch else 0)

        # Reset lower ordinates on major/minor bumps per semver convention.
        if delta.bump_major:
            minor = 0
            patch = 0
        elif delta.bump_minor:
            patch = 0

        scope_versions = dict(latest.scope_versions)
        for scope_key, bump in delta.per_scope_bump.items():
            current = int(scope_versions.get(scope_key, "0"))
            scope_versions[scope_key] = str(current + 1)

        tags = ["apply", request.target_scope.name.lower()]
        if request.authorization and request.authorization.mode:
            tags.append(request.authorization.mode.name.lower())

        return AtlasStateVersion(
            major=major,
            minor=minor,
            patch=patch,
            manifest_id=self._manifest_id(receipt.request_id),
            applied_request_ids=latest.applied_request_ids + [receipt.request_id],
            parent_version=latest.manifest_id,
            scope_versions=scope_versions,
            tags=tags,
            created_at=self._clock(),
        )

    def record_version(
        self,
        request: EvolutionRequest,
        receipt: ChangeReceipt,
    ) -> AtlasStateVersion:
        """Compute and persist the next version."""
        version = self.compute_next_version(request, receipt)
        self._storage.store_version(version)
        return version

    def record_rollback_version(
        self,
        rolled_back_request_id: str,
        current_version: AtlasStateVersion | None = None,
    ) -> AtlasStateVersion:
        """Record a patch bump for a rollback without adding the request."""
        latest = current_version or self.ensure_genesis()
        scope_versions = dict(latest.scope_versions)
        return AtlasStateVersion(
            major=latest.major,
            minor=latest.minor,
            patch=latest.patch + 1,
            manifest_id=self._manifest_id(f"rollback-{rolled_back_request_id}"),
            applied_request_ids=list(latest.applied_request_ids),
            parent_version=latest.manifest_id,
            scope_versions=scope_versions,
            tags=["rollback"],
            created_at=self._clock(),
        )

    @staticmethod
    def _compute_delta(
        request: EvolutionRequest,
        receipt: ChangeReceipt,
    ) -> VersionDelta:
        """Deterministic delta from request scope and receipt version_delta."""
        scope = request.target_scope
        version_delta = receipt.version_delta

        if version_delta == "+1.0.0":
            return VersionDelta(bump_major=True, bump_patch=True)
        if version_delta == "+0.1.0" or scope == ScopeType.CAPABILITY:
            scope_key = "capability"
            return VersionDelta(
                bump_minor=True,
                bump_patch=True,
                per_scope_bump={scope_key: "+1"},
            )

        scope_key = scope.name.lower()
        if scope == ScopeType.CONFIG:
            scope_key = "config"
        elif scope == ScopeType.MEMORY:
            scope_key = "memory"
        elif scope == ScopeType.KNOWLEDGE:
            scope_key = "knowledge"
        elif scope == ScopeType.CAPABILITY:
            scope_key = "capability"

        return VersionDelta(
            bump_patch=True,
            per_scope_bump={scope_key: "+1"},
        )

    def _manifest_id(self, seed: str) -> str:
        """Deterministic manifest identifier."""
        now = self._clock()
        return f"manifest-{seed}-{int(now.timestamp())}"


@dataclass(frozen=True, slots=True)
class ScopedVersionView:
    """Read-only view of version tags for status reporting."""

    config_version: str = "0"
    memory_version: str = "0"
    knowledge_version: str = "0"
    capability_version: str = "0"

    @classmethod
    def from_state_version(cls, version: AtlasStateVersion | None) -> "ScopedVersionView":
        if version is None:
            return cls()
        return cls(
            config_version=version.scope_versions.get("config", "0"),
            memory_version=version.scope_versions.get("memory", "0"),
            knowledge_version=version.scope_versions.get("knowledge", "0"),
            capability_version=version.scope_versions.get("capability", "0"),
        )
