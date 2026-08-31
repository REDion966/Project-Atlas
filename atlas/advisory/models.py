"""Atlas Advisory — Pure domain models (P5/Proactive Advisory).

Bounded, frozen value objects for the P5 user-facing advisory surface.

Design contract:
  * Advisory items are INERT — they are read-only observations/suggestions
    that the kernel exposes to the operator. They never invoke a tool,
    capability, orchestration, development, governance, approval, or
    promotion boundary directly.
  * Suggested actions are strings that name the EXISTING governed
    path (e.g. ``atlas.run_self_management_review``,
    ``atlas.run_operation_cycle``) so the operator can decide what to run.
    They are advisory; the advisor never invokes them itself.
  * Owner / User authority is preserved via the ``principal_id`` field.
    User-scoped items never auto-escalate; Owner-only items are clearly
    labeled.
  * Provenance is bounded and JSON-safe; raw user text and credentials
    are never carried.
  * No schema change, no migration, no infrastructure imports.

No infrastructure, no kernel, no runtime, no AI, no governance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdvisorySeverity(str, Enum):
    """Bounded, ordered severity of an advisory item."""

    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"


class AdvisorySource(str, Enum):
    """Which existing signal produced this advisory item.

    Mirrors the post-core F-series and B3.x/B4 sources that the advisor
    composes — never a new dependency, never a private signal.
    """

    ENVIRONMENT = "environment"          # F1
    AVAILABILITY = "availability"        # F10
    SELF_MANAGEMENT = "self_management"  # F11
    COLLECTIVE = "collective"            # P4 (B3.x + governance)
    INTERACTION = "interaction"          # B3.x


@dataclass(frozen=True, slots=True)
class AdvisoryItem:
    """A single bounded, principal-attributed advisory observation/suggestion.

    Attributes:
        item_id: Stable unique id within one advisory run.
        severity: INFO / NOTICE / WARNING.
        source: Which existing signal produced this item.
        kind: Short stable kind (e.g. "environment_change", "offline_provider").
        summary: Bounded human-readable description.
        evidence_ids: Bounded list of source-record identifiers.
        suggested_action: A bounded hint naming an EXISTING governed
            kernel/CLI path. Never an executable instruction.
        requires_owner: True when the action's governing path is OWNER-only.
        principal_id: The principal the item is scoped to.
        recorded_at: When the item was created (UTC).
        metadata: Optional bounded advisory metadata (never executable).
    """

    item_id: str
    severity: AdvisorySeverity
    source: AdvisorySource
    kind: str
    summary: str
    evidence_ids: tuple[str, ...] = ()
    suggested_action: str = ""
    requires_owner: bool = False
    principal_id: str = ""
    recorded_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "severity": self.severity.value,
            "source": self.source.value,
            "kind": self.kind,
            "summary": self.summary,
            "evidence_ids": list(self.evidence_ids),
            "suggested_action": self.suggested_action,
            "requires_owner": self.requires_owner,
            "principal_id": self.principal_id,
            "recorded_at": self.recorded_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AdvisoryReport:
    """Bounded, deterministic, JSON-safe result of one advisory run.

    Attributes:
        advisory_id: Stable unique id within the process lifetime.
        generated_at: When the report was composed (UTC).
        principal_id: The principal the report is scoped to.
        items: Bounded ordered tuple of AdvisoryItem objects.
        source_errors: Bounded tuple of (source_name, message) for any
            fail-soft source failures (read-only path, never crashes).
        sources_used: Bounded tuple of source names that contributed.
    """

    advisory_id: str
    generated_at: datetime = field(default_factory=_utc_now)
    principal_id: str = ""
    items: tuple[AdvisoryItem, ...] = ()
    source_errors: tuple[tuple[str, str], ...] = ()
    sources_used: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "advisory_id": self.advisory_id,
            "generated_at": self.generated_at.isoformat(),
            "principal_id": self.principal_id,
            "items": [i.to_dict() for i in self.items],
            "source_errors": [list(e) for e in self.source_errors],
            "sources_used": list(self.sources_used),
            "count": self.count,
        }
