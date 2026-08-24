"""Atlas Post-Core F3 — Lifecycle Assessment Models.

Pure data models for the deterministic capability/model/tool/skill lifecycle
assessment layer.

These models reuse (never duplicate) the existing:
  * F1 ``EnvironmentChange`` / ``EnvironmentEntity`` (environment signals)
  * F2 ``KnowledgeFreshnessAssessment`` (freshness signals)
  * existing registry/lifecycle metadata (``SkillStatus``, model profile
    metadata, tool metadata)

``LifecycleTarget`` is a normalized read-only projection of one lifecycle
subject. Callers build it from existing registry objects via the duck-typed
helpers in ``targets.py``. The assessor never mutates the underlying
registries or objects.

Pure data. No logic beyond shape validation. No infrastructure. No AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any


def utc_now() -> datetime:
    """Return the current time as a UTC-aware datetime."""
    return datetime.now(timezone.utc)


class LifecycleTargetKind(Enum):
    """The kind of lifecycle subject being assessed."""

    CAPABILITY = auto()
    MODEL = auto()
    TOOL = auto()
    SKILL = auto()


class LifecycleAction(Enum):
    """Deterministic recommended lifecycle action.

    F3 never performs the action; it only recommends. Actual adaptation and
    governed execution belong to later phases.
    """

    NONE = auto()       # No actionable evidence
    REVIEW = auto()     # Inspect / reassess; evidence is ambiguous
    DEPRECATE = auto()  # Mark for deprecation (audit keeps the record)
    REPLACE = auto()    # A valid explicit alternative is already known
    FALLBACK = auto()   # Prefer an explicit alternative when primary fails


class LifecycleReason(Enum):
    """Deterministic reason behind a lifecycle assessment."""

    EXPLICIT_DEPRECATION = auto()  # Existing metadata/status says deprecated
    UNAVAILABLE = auto()           # Existing metadata/status says unavailable
    ENVIRONMENT_CHANGE = auto()    # A relevant F1 change was observed
    STALE_KNOWLEDGE = auto()       # Supporting F2 knowledge is STALE
    UNCERTAIN_KNOWLEDGE = auto()   # Supporting F2 knowledge is UNCERTAIN
    DEPENDENCY_CHANGED = auto()    # An explicitly declared dependency changed
    REPLACEMENT_AVAILABLE = auto() # An explicit replacement is already known
    VALID = auto()                 # No actionable evidence; target is healthy
    UNKNOWN = auto()               # No deterministic reason assignable


@dataclass(frozen=True, slots=True)
class LifecycleTarget:
    """Normalized, read-only projection of one lifecycle subject.

    Attributes:
        target_kind: CAPABILITY / MODEL / TOOL / SKILL.
        identifier: Stable identifier within the kind (e.g. a model profile's
            ``provider:model`` string, a tool name, a skill id).
        status: Optional existing lifecycle status string (e.g. ``ACTIVE``,
            ``DEPRECATED``, ``unavailable``).
        available: Optional explicit availability flag.
        deprecated: Optional explicit deprecation flag.
        replacement: Optional explicitly-known alternative identifier. F3
            never invents a replacement.
        affected_domains: Domain-name vocabulary an environment change must
            match to affect this target (deterministic opt-in).
        dependency_entity_keys: Explicit subject keys this target depends on;
            an F1 change of one of these affects this target (opt-in, never an
            invented graph).
        knowledge_dependencies: Explicit F2 knowledge IDs whose freshness
            affects this target (opt-in).
        metadata: Optional bounded additional context.
    """

    target_kind: LifecycleTargetKind
    identifier: str
    status: str = ""
    available: bool | None = None
    deprecated: bool = False
    replacement: str = ""
    affected_domains: frozenset[str] = frozenset()
    dependency_entity_keys: frozenset[str] = frozenset()
    knowledge_dependencies: frozenset[str] = frozenset()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("identifier must be a non-empty string")
        if self.replacement and self.replacement == self.identifier:
            raise ValueError("replacement must differ from the target identifier")
        if not isinstance(self.target_kind, LifecycleTargetKind):
            raise TypeError("target_kind must be a LifecycleTargetKind")

    @property
    def key(self) -> str:
        """Canonical key matching the F1 entity-key vocabulary."""
        return f"{self.target_kind.name}:{self.identifier}"


@dataclass(frozen=True, slots=True)
class LifecycleAssessment:
    """A deterministic lifecycle assessment of one target.

    Attributes:
        target_kind: Kind of the assessed target.
        target_identifier: Identifier of the assessed target.
        action: Recommended deterministic action.
        reasons: Ordered tuple of ALL deterministic reasons (never only the
            first one found).
        priority: Bounded severity in [0.0, 1.0].
        evidence_change_ids: F1 change IDs that contributed (if any).
        evidence_knowledge_ids: F2 knowledge IDs that contributed (if any).
        assessed_at: UTC assessment timestamp.
        rationale: Stable keyword-based rationale (never free-form AI text).
    """

    target_kind: LifecycleTargetKind
    target_identifier: str
    action: LifecycleAction
    reasons: tuple[LifecycleReason, ...] = ()
    priority: float = 0.0
    evidence_change_ids: tuple[str, ...] = ()
    evidence_knowledge_ids: tuple[str, ...] = ()
    assessed_at: datetime = field(default_factory=utc_now)
    rationale: str = ""

    @property
    def target_key(self) -> str:
        """Canonical target key."""
        return f"{self.target_kind.name}:{self.target_identifier}"


@dataclass(frozen=True, slots=True)
class LifecycleAssessmentResult:
    """Bounded, deterministically-ordered collection of assessments.

    Attributes:
        assessments: Tuple of per-target assessments.
        assessed_at: UTC timestamp of the run.
    """

    assessments: tuple[LifecycleAssessment, ...] = ()
    assessed_at: datetime = field(default_factory=utc_now)

    @property
    def count(self) -> int:
        """Number of assessments."""
        return len(self.assessments)

    @property
    def actionable(self) -> "tuple[LifecycleAssessment, ...]":
        """Assessments whose action is not NONE (deterministically ordered)."""
        return tuple(a for a in self.ordered() if a.action is not LifecycleAction.NONE)

    def ordered(self) -> "tuple[LifecycleAssessment, ...]":
        """Return assessments sorted by priority desc, kind, id, action.

        Sorting never depends on dict/set iteration order.
        """
        return tuple(sorted(
            self.assessments,
            key=lambda a: (
                -a.priority,
                a.target_kind.value,
                a.target_identifier,
                a.action.value,
            ),
        ))