"""
Atlas Evolution Autonomy — Applier Protocol — Phase 16.5

Defines the abstract ``Applier`` protocol used by ``ApplicationEngine`` to
apply already-authorized state evolution to individual state domains.

Per the architecture:
- An applier is a pure application component.
- It does NOT dispatch, schedule, authorize, validate, or invoke AI.
- It does NOT touch the kernel, gateway, runtime, services, or EventBus.
- It ONLY mutates the state domain it owns and returns a ``ChangeReceipt``.

The protocol methods are:
  - supports(scope): whether this applier owns the scope.
  - can_apply(request, state_reader): lightweight pre-check before capture.
  - capture_snapshot(request_id, state_reader, storage): store a rollback artifact.
  - apply(request, state_writer): mutate the domain and return a receipt.
  - verify(request, state_reader): return a ``VerificationResult`` probe.

``state_reader`` and ``state_writer`` are injected interfaces so appliers
remain decoupled from concrete stores and from each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from atlas.evolution.autonomy.models import (
    ChangeReceipt,
    EvolutionRequest,
    RollbackPlan,
    VerificationResult,
)
from atlas.evolution.governance.models import ScopeType


class StateReadError(Exception):
    """Raised when a state read probe fails deterministically."""


class StateWriteError(Exception):
    """Raised when a state mutation cannot be completed."""


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Outcome of an applier ``apply`` call.

    Attributes:
        success: True when the mutation was applied without error.
        receipt: The ``ChangeReceipt`` describing what changed (None on failure).
        error: Human-readable failure reason when ``success`` is False.
        terminal_status: Suggested terminal status ("COMPLETED" or "FAILED").
    """

    success: bool
    receipt: ChangeReceipt | None = None
    error: str = ""
    terminal_status: str = "FAILED"


@runtime_checkable
class StateReader(Protocol):
    """Read-only view of a state domain for snapshot/verification."""

    def read(self, key: str, default: Any = None) -> Any:
        """Return the current value for ``key`` or ``default``."""
        ...

    def has(self, key: str) -> bool:
        """Return True when ``key`` exists in the domain."""
        ...


@runtime_checkable
class StateWriter(Protocol):
    """Mutable surface of a state domain used by appliers."""

    def write(self, key: str, value: Any) -> None:
        """Set ``key`` to ``value``."""
        ...

    def remove(self, key: str) -> bool:
        """Remove ``key``. Return True if it existed."""
        ...


class SnapshotStorage(Protocol):
    """Minimal storage surface needed to persist rollback snapshots."""

    def store_snapshot(
        self,
        snapshot_id: str,
        request_id: str,
        snapshot_data: dict[str, Any],
        checksum: str,
        created_at: str,
    ) -> None:
        ...


def _checksum(data: dict[str, Any]) -> str:
    """Deterministic primitive checksum for snapshot artifacts."""
    import hashlib
    import json

    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@runtime_checkable
class Applier(Protocol):
    """Protocol for a state-domain applier.

    Implementations are named by scope, e.g. ``ConfigApplier``,
    ``InformationApplier``, ``CapabilityApplier``.
    """

    @property
    def scope(self) -> ScopeType:
        """Return the ``ScopeType`` this applier owns."""
        ...

    def supports(self, scope: ScopeType) -> bool:
        """Return True when this applier handles ``scope``."""
        ...

    def can_apply(
        self,
        request: EvolutionRequest,
        reader: StateReader,
    ) -> bool:
        """Lightweight pre-check; return False if the apply should not proceed."""
        ...

    def capture_snapshot(
        self,
        request_id: str,
        reader: StateReader,
        storage: SnapshotStorage,
        now: datetime | None = None,
    ) -> RollbackPlan:
        """Capture a store-level snapshot before mutation and return a plan."""
        ...

    def apply(
        self,
        request: EvolutionRequest,
        writer: StateWriter,
        now: datetime | None = None,
    ) -> ApplyResult:
        """Apply the request to the domain and return a result."""
        ...

    def verify(
        self,
        request: EvolutionRequest,
        reader: StateReader,
        now: datetime | None = None,
    ) -> VerificationResult:
        """Verify the applied change is visible/readable in the domain."""
        ...


@dataclass(frozen=True, slots=True)
class DictStateReader:
    """Simple ``StateReader`` backed by an in-memory dict.

    Used for tests and for appliers that operate on lightweight
    configuration or capability registries.
    """

    _state: dict[str, Any] = field(default_factory=dict)

    def read(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._state


@dataclass(frozen=True, slots=True)
class DictStateWriter:
    """Simple ``StateWriter`` backed by an in-memory dict.

    The wrapped dict is shared by reference; this class only provides
    the protocol surface.
    """

    _state: dict[str, Any] = field(default_factory=dict)

    def write(self, key: str, value: Any) -> None:
        self._state[key] = value

    def remove(self, key: str) -> bool:
        if key in self._state:
            del self._state[key]
            return True
        return False
