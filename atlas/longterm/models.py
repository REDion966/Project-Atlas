"""Atlas Long-Term Learning — Data Models (Track C, Batch 1).

Pure data containers for the Track C long-term learning layer. Every model
is a frozen, slotted dataclass with a ``to_dict()`` serializer — mirroring
the Phase 17.1 research-models and Phase 18.1 toolchain-models contract so
storage adapters and capability handlers can serialize long-term artifacts
without touching business logic.

No infrastructure dependencies. No AI. No storage. No gateway. No kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EpisodeKind(Enum):
    """How an episode is categorized.

    PIPELINE  — a single cognitive pipeline execution (from ExperienceAccumulator).
    SESSION   — a user interaction session spanning multiple pipeline runs.
    TASK      — a goal-directed task execution (may span multiple pipelines).
    """

    PIPELINE = auto()
    SESSION = auto()
    TASK = auto()


class ProcedureKind(Enum):
    """How a procedure is realized.

    DISTILLED — extracted from repeated episode patterns by ProcedureExtractor.
    MANUAL    — explicitly registered by a user or external component.
    """

    DISTILLED = auto()
    MANUAL = auto()


class ConsolidationStatus(Enum):
    """Lifecycle state of a consolidation record.

    PENDING   — consolidation proposed but not yet applied.
    APPLIED   — consolidation applied to the repositories.
    REJECTED  — consolidation refused (e.g., governance sink missing).
    """

    PENDING = auto()
    APPLIED = auto()
    REJECTED = auto()


# ---------------------------------------------------------------------------
# Episode
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EpisodeEvent:
    """A single event within an :class:`Episode`.

    Attributes:
        event_id: Stable unique identifier.
        episode_id: Identifier of the parent episode.
        sequence: Ordinal position within the episode (0-based).
        event_type: Type of event (e.g. "pipeline_start", "tool_execution").
        summary: Human-readable description of the event.
        occurred_at: When the event occurred.
        metadata: Additional event context.
    """

    event_id: str
    episode_id: str
    sequence: int = 0
    event_type: str = ""
    summary: str = ""
    occurred_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "event_id": self.event_id,
            "episode_id": self.episode_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "summary": self.summary,
            "occurred_at": self.occurred_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class Episode:
    """An event-sequence recollection of what Atlas did and observed.

    Attributes:
        episode_id: Stable unique identifier.
        kind: How the episode is categorized (see :class:`EpisodeKind`).
        title: Short human-readable title.
        summary: Longer description of the episode.
        events: Ordered tuple of :class:`EpisodeEvent`.
        outcome: Outcome label (e.g. "success", "failure", "partial").
        source_experience_id: Optional reference to the source
            :class:`~atlas.experience.models.StructuredExperience`.
        started_at: When the episode began.
        ended_at: When the episode ended.
        importance: Importance score (0.0–1.0) for retention decisions.
        tags: Tags for discovery and matching.
        metadata: Additional context.
    """

    episode_id: str
    kind: EpisodeKind = EpisodeKind.PIPELINE
    title: str = ""
    summary: str = ""
    events: tuple[EpisodeEvent, ...] = ()
    outcome: str = ""
    source_experience_id: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    importance: float = 0.5
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested events become dicts)."""
        return {
            "episode_id": self.episode_id,
            "kind": self.kind.name,
            "title": self.title,
            "summary": self.summary,
            "events": tuple(e.to_dict() for e in self.events),
            "outcome": self.outcome,
            "source_experience_id": self.source_experience_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "importance": self.importance,
            "tags": tuple(self.tags),
            "metadata": self.metadata,
        }

    @property
    def event_count(self) -> int:
        """Number of events in the episode."""
        return len(self.events)

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds (0.0 if ended_at is None)."""
        if self.ended_at is None:
            return 0.0
        return (self.ended_at - self.started_at).total_seconds()


# ---------------------------------------------------------------------------
# Procedure
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProcedureStep:
    """A single step within a :class:`Procedure`.

    Attributes:
        step_id: Stable identifier unique within the procedure.
        description: What the step accomplishes.
        tool_name: Optional tool associated with the step.
        parameters: Optional parameters for the tool.
        depends_on: Step IDs that must complete before this step.
    """

    step_id: str
    description: str = ""
    tool_name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "step_id": self.step_id,
            "description": self.description,
            "tool_name": self.tool_name,
            "parameters": dict(self.parameters),
            "depends_on": tuple(self.depends_on),
        }


@dataclass(frozen=True, slots=True)
class Procedure:
    """A reusable task/method pattern distilled from repeated execution.

    Attributes:
        procedure_id: Stable unique identifier.
        name: Human-readable procedure name.
        description: What the procedure accomplishes.
        kind: How the procedure is realized (see :class:`ProcedureKind`).
        category: Functional category (e.g. "analysis", "research", "tool").
        steps: Ordered tuple of :class:`ProcedureStep`.
        source_episode_ids: Episodes that contributed to this procedure.
        success_count: Number of successful applications.
        failure_count: Number of failed applications.
        confidence: Confidence score (0.0–1.0) in the procedure's reliability.
        created_at: When the procedure was created.
        last_used_at: When the procedure was last applied.
        tags: Tags for discovery and matching.
        metadata: Additional context.
    """

    procedure_id: str
    name: str
    description: str = ""
    kind: ProcedureKind = ProcedureKind.DISTILLED
    category: str = "utility"
    steps: tuple[ProcedureStep, ...] = ()
    source_episode_ids: tuple[str, ...] = ()
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested steps become dicts)."""
        return {
            "procedure_id": self.procedure_id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind.name,
            "category": self.category,
            "steps": tuple(s.to_dict() for s in self.steps),
            "source_episode_ids": tuple(self.source_episode_ids),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "tags": tuple(self.tags),
            "metadata": self.metadata,
        }

    @property
    def step_count(self) -> int:
        """Number of steps in the procedure."""
        return len(self.steps)

    @property
    def total_applications(self) -> int:
        """Total number of times the procedure has been applied."""
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        """Success rate (0.0–1.0); 0.0 when never applied."""
        total = self.total_applications
        if total == 0:
            return 0.0
        return self.success_count / total


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConsolidationRecord:
    """Audit record of a consolidation / forgetting operation.

    Attributes:
        record_id: Stable unique identifier.
        status: Lifecycle state (see :class:`ConsolidationStatus`).
        operation: Operation type (e.g. "merge", "dedup", "forget").
        target_type: What was consolidated ("episode" or "procedure").
        target_ids: Identifiers of the consolidated items.
        reason: Why the consolidation was performed.
        created_at: When the consolidation was proposed.
        applied_at: When the consolidation was applied (None if not applied).
        metadata: Additional context.
    """

    record_id: str
    status: ConsolidationStatus = ConsolidationStatus.PENDING
    operation: str = ""
    target_type: str = ""
    target_ids: tuple[str, ...] = ()
    reason: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    applied_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "record_id": self.record_id,
            "status": self.status.name,
            "operation": self.operation,
            "target_type": self.target_type,
            "target_ids": tuple(self.target_ids),
            "reason": self.reason,
            "created_at": self.created_at,
            "applied_at": self.applied_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryDecayPolicy:
    """Configuration for principled forgetting.

    Attributes:
        max_episodes: Maximum number of episodes retained before consolidation.
        max_procedures: Maximum number of procedures retained before consolidation.
        episode_ttl_days: Episodes older than this many days are candidates for
            forgetting (0 disables age-based forgetting).
        procedure_ttl_days: Procedures unused for this many days are candidates
            for forgetting (0 disables age-based forgetting).
        min_importance: Episodes/procedures with importance below this threshold
            are candidates for forgetting.
        consolidation_threshold: Minimum number of episodes sharing a pattern
            before a procedure is distilled.
        enabled: Whether consolidation/forgetting is active.
    """

    max_episodes: int = 10_000
    max_procedures: int = 1_000
    episode_ttl_days: int = 0
    procedure_ttl_days: int = 0
    min_importance: float = 0.1
    consolidation_threshold: int = 3
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "max_episodes": self.max_episodes,
            "max_procedures": self.max_procedures,
            "episode_ttl_days": self.episode_ttl_days,
            "procedure_ttl_days": self.procedure_ttl_days,
            "min_importance": self.min_importance,
            "consolidation_threshold": self.consolidation_threshold,
            "enabled": self.enabled,
        }