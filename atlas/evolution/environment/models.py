"""Atlas Post-Core F1 — Environment Observation Models.

Pure data models for the environment / world-state observation layer.

These models are intentionally separate from (but compatible with) the
existing ``atlas.evolution.models.Observation`` record — an environment
observation is a richer, normalized snapshot plus a deterministic change
record. The ``EnvironmentChange`` type carries exactly the provenance fields
the F1 contract requires: source, observed_at, subject entity, previous
state, current state, change type, and reliability.

Pure data. No business logic. No infrastructure. No AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Mapping


class EnvironmentDomain(Enum):
    """The domain an environment observation belongs to."""

    MODEL = auto()          # AI model profile (provider:model)
    PROVIDER = auto()       # AI provider availability
    TOOL = auto()           # registered tool state
    CAPABILITY = auto()     # registered capability state
    SKILL = auto()          # registered skill state
    RUNTIME = auto()        # safe runtime / environment metadata


class EnvironmentChangeType(Enum):
    """Deterministic classification of an observed change."""

    ADDED = auto()
    REMOVED = auto()
    CHANGED = auto()
    UNCHANGED = auto()


class ObservationReliability(Enum):
    """Confidence in the reliability of an observation source."""

    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


@dataclass(frozen=True, slots=True)
class EnvironmentEntity:
    """The subject identity of an environment observation.

    Attributes:
        domain: The domain this entity belongs to.
        entity_id: Stable identifier within the domain (e.g. ``openai:gpt-4``,
            ``tool:sandbox_pytest``).
    """

    domain: EnvironmentDomain
    entity_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.domain, EnvironmentDomain):
            raise TypeError("domain must be an EnvironmentDomain")
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise ValueError("entity_id must be a non-empty string")

    @property
    def key(self) -> str:
        """Deterministic, globally-unique identity key.

        Used as the dedup/compare key across observation cycles.
        """
        return f"{self.domain.name}:{self.entity_id}"

    def __str__(self) -> str:
        return self.key


@dataclass(frozen=True, slots=True)
class EnvironmentState:
    """A normalized snapshot of one environment subject at a point in time.

    Attributes:
        entity: The observed subject.
        state: Bounded, JSON-safe, secret-free state values.
        source: The observer/provider that produced this snapshot.
        observed_at: When the state was sampled.
        reliability: Reliability of the observation source.
        metadata: Optional bounded additional context.
    """

    entity: EnvironmentEntity
    state: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""
    observed_at: datetime = field(default_factory=datetime.now)
    reliability: ObservationReliability = ObservationReliability.MEDIUM
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Alias of the entity identity key."""
        return self.entity.key


@dataclass(frozen=True, slots=True)
class EnvironmentChange:
    """A deterministic change record between two environment states.

    Attributes:
        entity: The subject that changed (or is being reported).
        change_type: ADDED / REMOVED / CHANGED / UNCHANGED.
        previous: Prior state (None when the entity is newly added).
        current: Current state (None when the entity was removed).
        observed_at: When the change was detected.
        source: The observer/provider that reported the change.
        reliability: Reliability of the source.
        metadata: Optional bounded additional context.
    """

    entity: EnvironmentEntity
    change_type: EnvironmentChangeType
    previous: Mapping[str, Any] | None = None
    current: Mapping[str, Any] | None = None
    observed_at: datetime = field(default_factory=datetime.now)
    source: str = ""
    reliability: ObservationReliability = ObservationReliability.MEDIUM
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain, JSON-safe dict (no secrets, no objects)."""
        return {
            "entity": self.entity.key,
            "domain": self.entity.domain.name,
            "entity_id": self.entity.entity_id,
            "change_type": self.change_type.name,
            "previous": dict(self.previous or {}),
            "current": dict(self.current or {}),
            "observed_at": self.observed_at.isoformat(),
            "source": self.source,
            "reliability": self.reliability.name,
        }


@dataclass(frozen=True, slots=True)
class EnvironmentProviderFailure:
    """Bounded, structured failure of one observation provider.

    Never carries tracebacks, secrets, or environment dumps.
    """

    provider_name: str
    error: str
    occurred_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "error": self.error,
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class EnvironmentObservationResult:
    """Bounded result of one environment observation cycle.

    Attributes:
        cycle_id: Deterministic, monotonically increasing cycle identifier.
        ran_at: When the cycle ran.
        changes: Ordered tuple of detected changes (UNCHANGED included when
            requested; the observer filters them for event emission).
        failures: Ordered tuple of bounded provider failures.
        provider_count: Number of providers executed.
        observed_count: Number of distinct entities observed.
        success: False when at least one provider failed.
    """

    cycle_id: str
    ran_at: datetime = field(default_factory=datetime.now)
    changes: tuple[EnvironmentChange, ...] = ()
    failures: tuple[EnvironmentProviderFailure, ...] = ()
    provider_count: int = 0
    observed_count: int = 0
    success: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain, JSON-safe dict."""
        return {
            "cycle_id": self.cycle_id,
            "ran_at": self.ran_at.isoformat(),
            "changes": [c.to_dict() for c in self.changes],
            "failures": [f.to_dict() for f in self.failures],
            "provider_count": self.provider_count,
            "observed_count": self.observed_count,
            "success": self.success,
        }