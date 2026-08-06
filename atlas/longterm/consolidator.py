"""Atlas Long-Term Learning — Consolidator (Track C, Batch 3).

Dedup/merge episodes & procedures and apply principled forgetting from a
:class:`~atlas.longterm.models.MemoryDecayPolicy` (age + importance).
The consolidator is deterministic, never raises, and returns a
:class:`ConsolidationResult` describing what would be/ was forgotten.

Forgetting is decided here but NEVER applied directly — application is a
governed evolution path (see :mod:`atlas.longterm.evolution_integration`).
The consolidator only names candidate ids and emits audit records.

No infrastructure dependencies. No AI. No storage. No gateway. No kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from typing import Iterable

from atlas.longterm.catalog import (
    CONSOLIDATION_ID_PREFIX,
    DEFAULT_CONSOLIDATION_OPERATION,
)
from atlas.longterm.models import (
    ConsolidationRecord,
    ConsolidationStatus,
    Episode,
    MemoryDecayPolicy,
    Procedure,
)


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    """Deterministic outcome of one consolidation pass (never raises)."""

    records: tuple[ConsolidationRecord, ...] = ()
    episodes_kept: tuple[Episode, ...] = ()
    episodes_consolidated: tuple[Episode, ...] = ()
    procedures_kept: tuple[Procedure, ...] = ()
    procedures_merged: tuple[Procedure, ...] = ()
    episodes_flagged: tuple[str, ...] = ()
    procedures_flagged: tuple[str, ...] = ()
    error: str = ""

    @property
    def ok(self) -> bool:
        """True when the pass completed without error."""
        return not self.error


class Consolidator:
    """Pure dedup / merge / principled-forgetting pass.

    Args:
        policy: Forgetting configuration. Defaults to :class:`MemoryDecayPolicy`.
        now: Injected clock for deterministic age checks (defaults to
            :func:`datetime.now`).
    """

    def __init__(
        self,
        policy: MemoryDecayPolicy | None = None,
        now: datetime | None = None,
    ) -> None:
        self._policy = policy or MemoryDecayPolicy()
        self._now = now

    # ------------------------------------------------------------------
    # Consolidation pass
    # ------------------------------------------------------------------

    def consolidate(
        self,
        episodes: Iterable[Episode] | None = None,
        procedures: Iterable[Procedure] | None = None,
    ) -> ConsolidationResult:
        """Run one consolidation pass (dedup → merge → forget flags).

        ``None`` inputs are treated as empty collections. Never raises:
        structural errors are captured in ``result.error`` and the pass
        returns empty results instead of propagating.
        """
        try:
            return self._consolidate(episodes or (), procedures or ())
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ConsolidationResult(error=str(exc))

    # ------------------------------------------------------------------
    # Internal pass
    # ------------------------------------------------------------------

    def _consolidate(
        self,
        episodes: Iterable[Episode],
        procedures: Iterable[Procedure],
    ) -> ConsolidationResult:
        episodes_sorted = sorted(episodes, key=lambda e: e.episode_id)
        procedures_sorted = sorted(procedures, key=lambda p: p.procedure_id)

        episodes_kept, episodes_consolidated = self._dedup_episodes(episodes_sorted)
        procedures_kept, procedures_merged = self._merge_procedures(procedures_sorted)

        if not self._policy.enabled:
            return ConsolidationResult(
                records=(),
                episodes_kept=tuple(episodes_kept),
                episodes_consolidated=tuple(episodes_consolidated),
                procedures_kept=tuple(procedures_kept),
                procedures_merged=tuple(procedures_merged),
            )

        flagged_episodes = self._flag_forgettable(
            episodes_kept,
            ttl_days=self._policy.episode_ttl_days,
            min_importance=self._policy.min_importance,
        )
        flagged_procedures = self._flag_forgettable(
            procedures_kept,
            ttl_days=self._policy.procedure_ttl_days,
            min_importance=self._policy.min_importance,
        )

        records = self._build_records(
            flagged_episodes,
            flagged_procedures,
            episodes_consolidated,
            procedures_merged,
        )

        return ConsolidationResult(
            records=tuple(records),
            episodes_kept=tuple(episodes_kept),
            episodes_consolidated=tuple(episodes_consolidated),
            procedures_kept=tuple(procedures_kept),
            procedures_merged=tuple(procedures_merged),
            episodes_flagged=tuple(flagged_episodes),
            procedures_flagged=tuple(flagged_procedures),
        )

    # ------------------------------------------------------------------
    # Dedup / merge
    # ------------------------------------------------------------------

    @staticmethod
    def _dedup_episodes(
        episodes: list[Episode],
    ) -> tuple[list[Episode], list[Episode]]:
        """Keep the highest-importance instance per episode id."""
        kept: list[Episode] = []
        consolidated: list[Episode] = []
        best_by_id: dict[str, Episode] = {}
        for episode in episodes:
            best = best_by_id.get(episode.episode_id)
            if best is None:
                best_by_id[episode.episode_id] = episode
                continue
            if episode.importance > best.importance:
                best_by_id[episode.episode_id] = episode
                consolidated.append(best)
            else:
                consolidated.append(episode)
        kept = [best_by_id[eid] for eid in sorted(best_by_id)]
        return kept, consolidated

    @staticmethod
    def _merge_procedures(
        procedures: list[Procedure],
    ) -> tuple[list[Procedure], list[Procedure]]:
        """Merge duplicates (same id) into one procedure."""
        merged: dict[str, Procedure] = {}
        merged_out: list[Procedure] = []
        for procedure in procedures:
            existing = merged.get(procedure.procedure_id)
            if existing is None:
                merged[procedure.procedure_id] = procedure
                continue
            combined = _merge_procedure_pair(existing, procedure)
            merged[procedure.procedure_id] = combined
            merged_out.append(procedure)
        kept = [merged[pid] for pid in sorted(merged)]
        return kept, merged_out

    # ------------------------------------------------------------------
    # Principled forgetting
    # ------------------------------------------------------------------

    def _flag_forgettable(
        self,
        items: Iterable[Episode | Procedure],
        ttl_days: int,
        min_importance: float,
    ) -> list[str]:
        """Return ids of items that are age/importance-based forget candidates.

        Rules (all deterministic):
          * A stale item (older than ``ttl_days``) is always a candidate
            when ``ttl_days > 0`` and no recent activity exists.
          * An item with importance below ``min_importance`` is a candidate.
        """
        flagged: list[str] = []
        for item in items:
            importance = (
                item.importance
                if isinstance(item, Episode)
                else _procedure_importance(item)
            )
            recent = self._last_activity(item)
            stale = (
                ttl_days > 0
                and recent is not None
                and recent < self._now_value() - timedelta(days=ttl_days)
            )
            low_importance = importance < min_importance
            if stale or low_importance:
                flagged.append(item_id(item))
        return sorted(flagged)

    def _build_records(
        self,
        flagged_episodes: list[str],
        flagged_procedures: list[str],
        episodes_consolidated: list[Episode],
        procedures_merged: list[Procedure],
    ) -> list[ConsolidationRecord]:
        """Emit audit records for every consolidation decision."""
        records: list[ConsolidationRecord] = []
        if episodes_consolidated:
            records.append(
                self._record(
                    operation="dedup",
                    target_type="episode",
                    target_ids=[e.episode_id for e in episodes_consolidated],
                    reason="duplicate episode ids merged by importance",
                )
            )
        if procedures_merged:
            records.append(
                self._record(
                    operation="merge",
                    target_type="procedure",
                    target_ids=[p.procedure_id for p in procedures_merged],
                    reason="duplicate procedure ids merged",
                )
            )
        if flagged_episodes:
            records.append(
                self._record(
                    operation="forget",
                    target_type="episode",
                    target_ids=flagged_episodes,
                    reason="age/importance-based forgetting candidate",
                )
            )
        if flagged_procedures:
            records.append(
                self._record(
                    operation="forget",
                    target_type="procedure",
                    target_ids=flagged_procedures,
                    reason="age/importance-based forgetting candidate",
                )
            )
        return records

    def _record(
        self,
        operation: str,
        target_type: str,
        target_ids: list[str],
        reason: str,
    ) -> ConsolidationRecord:
        """Build one deterministic PENDING consolidation record."""
        now = self._now_value()
        return ConsolidationRecord(
            record_id=f"{CONSOLIDATION_ID_PREFIX}:{now:%Y%m%d%H%M%S}:{len(target_ids)}:{target_type}",
            status=ConsolidationStatus.PENDING,
            operation=operation or DEFAULT_CONSOLIDATION_OPERATION,
            target_type=target_type,
            target_ids=tuple(sorted(target_ids)),
            reason=reason,
            created_at=now,
            metadata={
                "consolidator": "atlas.longterm.consolidator.Consolidator",
            },
        )

    def _now_value(self) -> datetime:
        """Return the injected clock or the current time."""
        return self._now if self._now is not None else datetime.now()

    @staticmethod
    def _last_activity(item: Episode | Procedure) -> datetime | None:
        """Most recent timestamp for an item (None when unknown)."""
        if isinstance(item, Episode):
            return item.ended_at or item.started_at
        return item.last_used_at or item.created_at


def item_id(item: Episode | Procedure) -> str:
    """Return the stable id for an episode or procedure."""
    return item.episode_id if isinstance(item, Episode) else item.procedure_id


def _procedure_importance(procedure: Procedure) -> float:
    """Importance proxy for a procedure (confidence-weighted usage)."""
    if procedure.total_applications == 0:
        return procedure.confidence
    return round(
        procedure.confidence * procedure.success_rate, 4
    )


def _merge_procedure_pair(first: Procedure, second: Procedure) -> Procedure:
    """Merge two procedures sharing an id into a single deterministic one."""
    success_count = first.success_count + second.success_count
    failure_count = first.failure_count + second.failure_count
    total = success_count + failure_count
    confidence = round(success_count / total, 4) if total else max(
        first.confidence, second.confidence
    )
    source_ids = tuple(
        sorted(set((*first.source_episode_ids, *second.source_episode_ids)))
    )
    tags = tuple(sorted(set((*first.tags, *second.tags))))
    return Procedure(
        procedure_id=first.procedure_id,
        name=first.name,
        description=first.description or second.description,
        kind=first.kind,
        category=first.category,
        steps=_merge_steps(first, second),
        source_episode_ids=source_ids,
        success_count=success_count,
        failure_count=failure_count,
        confidence=confidence,
        created_at=min(first.created_at, second.created_at),
        last_used_at=max(
            first.last_used_at or first.created_at,
            second.last_used_at or second.created_at,
        ),
        tags=tags,
        metadata={
            **first.metadata,
            **second.metadata,
            "consolidated_from": list(source_ids),
        },
    )


def _merge_steps(first: Procedure, second: Procedure) -> tuple:
    """Union of two procedures' steps keyed by step_id (deterministic)."""
    by_id: dict[str, object] = {}
    for step in (*first.steps, *second.steps):
        by_id.setdefault(step.step_id, step)
    return tuple(
        by_id[step_id] for step_id in sorted(by_id)
    )
